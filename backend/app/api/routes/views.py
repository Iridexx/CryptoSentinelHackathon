"""Dashboard data views: Spot / Perp / Global."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep, SettingsDep
from backend.app.persistence.archive import list_archived_runs
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trade_charts import TradeChartSnapshot
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.trade_charts import TradeChartRepository
from backend.app.persistence.views import ViewService, _close_reason
from backend.app.schemas.views import GlobalView, PerpView, SpotView

router = APIRouter(prefix="/api/v1/views", tags=["views"])


@router.get("/spot")
async def spot_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> SpotView:
    """Open spot positions, history, PnL and win rate."""

    service = ViewService(session, drawdown_cap_pct=settings.risk_max_drawdown_pct)
    return await service.spot_view(str(settings.default_user_id))


@router.get("/perp")
async def perp_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> PerpView:
    """Open perpetual positions (leverage, liquidation, funding), history, PnL, win rate."""

    service = ViewService(session, drawdown_cap_pct=settings.risk_max_drawdown_pct)
    return await service.perp_view(str(settings.default_user_id))


@router.get("/global")
async def global_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> GlobalView:
    """Total PnL, capital vs initial, drawdown vs cap, exposure, balance."""

    service = ViewService(session, drawdown_cap_pct=settings.risk_max_drawdown_pct)
    return await service.global_view(str(settings.default_user_id))


@router.get("/equity-curve")
async def equity_curve(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
    market: str = Query("global", pattern="^(spot|perp|global)$"),
    range: str = Query("24h", pattern="^(24h|7d|all)$"),
) -> dict:
    """Hourly equity curve with drawdown overlay."""

    user_id = str(settings.default_user_id)
    since = _range_since(range)
    stmt = select(PnlSnapshot).where(PnlSnapshot.user_id == user_id)
    if since:
        stmt = stmt.where(PnlSnapshot.timestamp_utc >= since)
    stmt = stmt.order_by(PnlSnapshot.timestamp_utc.asc())
    snapshots = list((await session.execute(stmt)).scalars().all())
    portfolio = await PnlRepository(session).get_portfolio(user_id)
    initial = _initial_equity(snapshots, settings, portfolio, market)
    benchmark = await _btc_benchmark(snapshots)
    items = []
    for snapshot in snapshots:
        equity = _market_equity(snapshot, market)
        pnl_usd = equity - initial
        pnl_pct = (pnl_usd / initial * Decimal("100")) if initial > 0 else Decimal("0")
        item = {
            "timestamp_utc": snapshot.timestamp_utc.isoformat(),
            "equity_usd": _q2(equity),
            "pnl_usd": _signed(_q2(pnl_usd)),
            "pnl_pct": _signed(_q2(pnl_pct)),
            "drawdown_pct": _signed(_q2(snapshot.drawdown_pct)),
        }
        btc_pct = benchmark.get(snapshot.timestamp_utc.isoformat())
        if btc_pct is not None:
            item["btc_pct"] = _signed(_q2(btc_pct))
        items.append(item)
    return {
        "market": market,
        "range": range,
        "initial_equity_usd": _q2(initial),
        "benchmark_available": bool(benchmark),
        "items": items,
    }


@router.get("/asset-breakdown")
async def asset_breakdown(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
    market: str = Query("spot", pattern="^(spot|perp)$"),
) -> dict:
    """PnL breakdown by asset."""

    user_id = str(settings.default_user_id)
    portfolio = await ViewService(session, drawdown_cap_pct=settings.risk_max_drawdown_pct).global_view(user_id)
    current_equity = Decimal(portfolio.total_equity_usd or 0)
    if market == "spot":
        trades = list((await session.execute(select(SpotTrade).where(SpotTrade.user_id == user_id))).scalars().all())
        positions = list((await session.execute(select(SpotPosition).where(SpotPosition.user_id == user_id))).scalars().all())
    else:
        trades = list((await session.execute(select(PerpTrade).where(PerpTrade.user_id == user_id))).scalars().all())
        positions = list((await session.execute(select(PerpPosition).where(PerpPosition.user_id == user_id))).scalars().all())
    assets = sorted({row.asset for row in trades} | {row.asset for row in positions})
    items = []
    for asset in assets:
        asset_trades = [trade for trade in trades if trade.asset == asset]
        asset_positions = [position for position in positions if position.asset == asset]
        pnl = sum((Decimal(getattr(position, "pnl_unrealized", 0) or 0) for position in asset_positions), Decimal("0"))
        exposure = sum(
            (Decimal(position.size) * Decimal(position.current_price) for position in asset_positions),
            Decimal("0"),
        )
        wins = sum(1 for trade in asset_trades if (trade.notes or "").lower().find("profit") >= 0)
        win_rate = Decimal(wins) / Decimal(len(asset_trades)) * Decimal("100") if asset_trades else Decimal("0")
        pnl_pct = pnl / current_equity * Decimal("100") if current_equity > 0 else Decimal("0")
        allocation_pct = exposure / current_equity * Decimal("100") if current_equity > 0 else Decimal("0")
        items.append(
            {
                "asset": asset,
                "trade_count": len(asset_trades),
                "win_rate_pct": _q2(win_rate),
                "pnl_usd": _signed(_q2(pnl)),
                "pnl_pct": _signed(_q2(pnl_pct)),
                "allocation_pct": _q2(allocation_pct),
            }
        )
    return {"market": market, "items": items}


@router.get("/trade-detail/{trade_id}")
async def trade_detail(
    trade_id: str,
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> dict:
    """Return full detail for one spot/perp trade or its open position."""

    user_id = str(settings.default_user_id)
    spot = (await session.execute(select(SpotTrade).where(SpotTrade.user_id == user_id).where(SpotTrade.trade_id == trade_id))).scalar_one_or_none()
    perp = (await session.execute(select(PerpTrade).where(PerpTrade.user_id == user_id).where(PerpTrade.trade_id == trade_id))).scalar_one_or_none()
    if spot is None and perp is None:
        raise HTTPException(status_code=404, detail="trade_not_found")
    chart_repo = TradeChartRepository(session)
    if spot is not None:
        position = await _find_trade_position(session, SpotPosition, spot)
        decision = (await session.execute(select(AgentDecision).where(AgentDecision.trade_id == trade_id))).scalar_one_or_none()
        snapshot = await _load_chart_snapshot(chart_repo, user_id, trade_id, position)
        return _spot_trade_detail(spot, position, decision, snapshot)
    position = await _find_trade_position(session, PerpPosition, perp)
    decision = (await session.execute(select(AgentDecision).where(AgentDecision.trade_id == trade_id))).scalar_one_or_none()
    snapshot = await _load_chart_snapshot(chart_repo, user_id, trade_id, position)
    return _perp_trade_detail(perp, position, decision, snapshot)


async def _find_trade_position(session, model, trade):
    """Trova la posizione del trade: via open_trade_id (apertura) o, per i trade
    di chiusura (cls_<position_id>_<hex>), estraendo il position_id dal trade_id."""
    pos = (await session.execute(select(model).where(model.open_trade_id == trade.trade_id))).scalar_one_or_none()
    if pos is not None:
        return pos
    if trade.trade_id.startswith("cls_"):
        position_id = trade.trade_id.rsplit("_", 1)[0][len("cls_"):]
        pos = (await session.execute(select(model).where(model.position_id == position_id))).scalar_one_or_none()
        return pos
    return None


async def _load_chart_snapshot(
    chart_repo: TradeChartRepository,
    user_id: str,
    trade_id: str,
    position,
) -> TradeChartSnapshot | None:
    """Lo snapshot e' legato al trade di chiusura (cls_...) o, in fallback, alla posizione."""
    snapshot = await chart_repo.get_for_close_trade(user_id, trade_id)
    if snapshot is None and position is not None:
        snapshot = await chart_repo.get_for_position(user_id, position.position_id)
    return snapshot


@router.get("/operational-stats")
async def operational_stats(
    _: ReadAccessDep,
) -> dict:
    """Return lightweight runtime operational stats."""

    from backend.app.agent.heartbeat import heartbeat

    beats = heartbeat.as_dict()
    return {
        "uptime_pct": "100.00",
        "heartbeat": beats,
        "degraded_count": 0,
        "degraded_reasons": [],
        "last_kill_switch": None,
    }


@router.get("/archived-runs")
async def archived_runs(
    session: SessionDep,
    settings: SettingsDep,
    _: AdminAccessDep,
) -> dict:
    """List archived dry-run datasets excluded from live views."""

    runs = await list_archived_runs(session, user_id=str(settings.default_user_id))
    return {"items": runs, "count": len(runs)}


def _range_since(value: str) -> datetime | None:
    now = datetime.now(UTC)
    if value == "24h":
        return now - timedelta(hours=24)
    if value == "7d":
        return now - timedelta(days=7)
    return None


async def _btc_benchmark(snapshots: list[PnlSnapshot]) -> dict[str, Decimal]:
    """Andamento cumulato % di BTC allineato agli snapshot, per confronto sul grafico equity.

    L'ambiente dry-run usa un clock simulato che non corrisponde alle klines reali
    di Binance: per questo NON allineiamo per timestamp assoluto ma per *offset orario*
    dal primo snapshot (gli snapshot sono orari). Best-effort: se BTC non e' raggiungibile
    ritorna {} e il grafico mostra la sola curva PnL.
    """
    if len(snapshots) < 2:
        return {}
    from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed

    first_ts = snapshots[0].timestamp_utc
    last_ts = snapshots[-1].timestamp_utc
    span_hours = int(round((last_ts - first_ts).total_seconds() / 3600))
    if span_hours < 1:
        span_hours = 1
    limit = min(1000, span_hours + 2)
    try:
        candles = await BinanceKlineFeed().fetch(
            symbol="BTCUSDT", interval="1h", limit=limit, market="spot"
        )
    except Exception:
        return {}
    if not candles:
        return {}
    base = Decimal(str(candles[0].close))
    if base <= 0:
        return {}
    out: dict[str, Decimal] = {}
    for snapshot in snapshots:
        offset = int(round((snapshot.timestamp_utc - first_ts).total_seconds() / 3600))
        idx = max(0, min(offset, len(candles) - 1))
        close = Decimal(str(candles[idx].close))
        out[snapshot.timestamp_utc.isoformat()] = (close / base - Decimal("1")) * Decimal("100")
    return out


def _initial_equity(snapshots: list[PnlSnapshot], settings, portfolio=None, market: str = "global") -> Decimal:
    """Baseline per il PnL cumulato del grafico.

    Per il market 'global' usa il capitale iniziale configurato
    (portfolio.initial_equity_usd), cosi' il "PnL cumulato" del grafico
    combacia con la "PnL %" della scheda Global. In assenza usa il primo
    snapshot disponibile come fallback. Per spot/perp usa l'equity del primo
    snapshot del mercato specifico.
    """
    if market == "global" and portfolio is not None and portfolio.initial_equity_usd:
        return Decimal(portfolio.initial_equity_usd)
    if snapshots:
        return Decimal(_market_equity(snapshots[0], market))
    return Decimal(str(settings.dry_run_capital_usd))


def _market_equity(snapshot: PnlSnapshot, market: str) -> Decimal:
    if market == "spot":
        return Decimal(snapshot.spot_equity_usd)
    if market == "perp":
        return Decimal(snapshot.perp_equity_usd)
    return Decimal(snapshot.total_equity_usd)


def _q2(value) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


def _signed(value: str) -> str:
    decimal = Decimal(value)
    return f"{decimal:+.2f}"


def _pnl_pct(pnl: Decimal, entry: Decimal, size: Decimal, leverage: int = 1) -> str:
    margin = entry * size / Decimal(leverage)
    if margin <= 0:
        return "+0.00"
    return _signed(_q2(pnl / margin * Decimal("100")))


def _decision_payload(decision: AgentDecision | None) -> dict | None:
    if decision is None:
        return None
    return {
        "decision_id": decision.decision_id,
        "signal_quality": _q2(decision.signal_quality or 0),
        "confidence": _q2(decision.confidence or 0),
        "action": decision.action,
        "reasoning": decision.reasoning,
    }


def _level(position, attr: str, chart: dict | None, key: str) -> str | None:
    """Livello (SL/TP) dalla posizione, con fallback ai dati congelati nello snapshot."""
    if position is not None and getattr(position, attr, None):
        return _q2(getattr(position, attr))
    if chart and chart.get(key):
        return _q2(Decimal(str(chart[key])))
    return None


def _trade_timeline(trade, position, chart: dict | None, is_close: bool) -> tuple[str, str | None]:
    """(opened_at, closed_at) coerenti: lo snapshot e la posizione sono piu' affidabili
    del timestamp del trade (che per un cls_ e' il momento della chiusura, non dell'apertura)."""
    if chart:
        opened_at = str(chart["opened_at"])
    elif position is not None:
        opened_at = position.opened_at.isoformat()
    elif not is_close:
        opened_at = trade.timestamp_utc.isoformat()
    else:
        opened_at = trade.timestamp_utc.isoformat()
    closed_at: str | None
    if chart:
        closed_at = str(chart["closed_at"])
    elif position is not None and position.status == "closed":
        closed_at = position.updated_at.isoformat()
    elif is_close:
        closed_at = trade.timestamp_utc.isoformat()
    else:
        closed_at = None
    return opened_at, closed_at


def _spot_trade_detail(trade: SpotTrade, position: SpotPosition | None, decision: AgentDecision | None, snapshot: TradeChartSnapshot | None = None) -> dict:
    chart = json.loads(snapshot.payload) if snapshot else None
    is_close = trade.trade_id.startswith("cls_")
    entry = (
        Decimal(position.entry_price) if position is not None
        else Decimal(str(chart["entry_price"])) if chart
        else Decimal(trade.price)
    )
    if is_close:
        current = Decimal(trade.price)
    elif position is not None and position.status == "closed":
        current = Decimal(position.current_price)
    elif chart:
        current = Decimal(str(chart["exit_price"]))
    elif position is not None:
        current = Decimal(position.current_price)
    else:
        current = Decimal(trade.price)
    size = Decimal(trade.amount) if (is_close or position is None) else Decimal(position.size)
    if trade.pnl_usd is not None:
        pnl = Decimal(trade.pnl_usd)
    elif position is not None:
        pnl = Decimal(position.pnl_unrealized)
    else:
        pnl = Decimal("0")
    opened_at, closed_at = _trade_timeline(trade, position, chart, is_close)
    return {
        "trade_id": trade.trade_id,
        "asset": trade.asset,
        "market": "spot",
        "direction": trade.side,
        "entry_price": _q2(entry),
        "current_or_exit_price": _q2(current),
        "pnl_usd": _signed(_q2(pnl)),
        "pnl_pct": _pnl_pct(pnl, entry, size),
        "stop_loss": _level(position, "stop_loss", chart, "stop_loss"),
        "take_profit_1": _level(position, "take_profit_1", chart, "take_profit_1"),
        "take_profit_2": _level(position, "take_profit_2", chart, "take_profit_2"),
        "trailing_stop": _q2(position.trailing_stop) if position and position.trailing_stop else None,
        "size": _q2(size),
        "leverage": None,
        "exposure_usd": _q2(size * entry),
        "opened_at": opened_at,
        "closed_at": closed_at,
        "duration_seconds": None,
        "close_reason": _close_reason(trade),
        "decision": _decision_payload(decision),
        "events": [],
        "chart": chart,
        "is_simulated": trade.trade_id.startswith("dry_") or trade.provider == "dry_run",
    }


def _perp_trade_detail(trade: PerpTrade, position: PerpPosition | None, decision: AgentDecision | None, snapshot: TradeChartSnapshot | None = None) -> dict:
    chart = json.loads(snapshot.payload) if snapshot else None
    is_close = trade.trade_id.startswith("cls_")
    entry = (
        Decimal(position.entry_price) if position is not None
        else Decimal(str(chart["entry_price"])) if chart
        else Decimal(trade.price)
    )
    if is_close:
        current = Decimal(trade.price)
    elif position is not None and position.status == "closed":
        current = Decimal(position.current_price)
    elif chart:
        current = Decimal(str(chart["exit_price"]))
    elif position is not None:
        current = Decimal(position.current_price)
    else:
        current = Decimal(trade.price)
    size = Decimal(trade.size) if (is_close or position is None) else Decimal(position.size)
    if trade.pnl_usd is not None:
        pnl = Decimal(trade.pnl_usd)
    elif position is not None:
        pnl = Decimal(position.pnl_unrealized)
    else:
        pnl = Decimal("0")
    leverage = trade.leverage or (position.leverage if position is not None else None)
    opened_at, closed_at = _trade_timeline(trade, position, chart, is_close)
    return {
        "trade_id": trade.trade_id,
        "asset": trade.asset,
        "market": "perp",
        "direction": trade.side,
        "entry_price": _q2(entry),
        "current_or_exit_price": _q2(current),
        "pnl_usd": _signed(_q2(pnl)),
        "pnl_pct": _pnl_pct(pnl, entry, size, leverage or 1),
        "stop_loss": _level(position, "stop_loss", chart, "stop_loss"),
        "take_profit_1": _level(position, "take_profit_1", chart, "take_profit_1"),
        "take_profit_2": _level(position, "take_profit_2", chart, "take_profit_2"),
        "trailing_stop": _q2(position.trailing_stop) if position and position.trailing_stop else None,
        "size": _q2(size),
        "leverage": leverage,
        "exposure_usd": _q2(size * entry * (leverage or 1)),
        "opened_at": opened_at,
        "closed_at": closed_at,
        "duration_seconds": None,
        "close_reason": _close_reason(trade),
        "decision": _decision_payload(decision),
        "events": [{"name": "tp1", "reached": position.tp1_reached}] if position else [],
        "chart": chart,
        "is_simulated": trade.trade_id.startswith("dry_") or trade.venue == "dry_run",
    }
