"""Dashboard data views: Spot / Perp / Global."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep, SettingsDep
from backend.app.persistence.archive import list_archived_runs
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
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
    initial = _initial_equity(snapshots, settings)
    items = []
    for snapshot in snapshots:
        equity = _market_equity(snapshot, market)
        pnl_usd = equity - initial
        pnl_pct = (pnl_usd / initial * Decimal("100")) if initial > 0 else Decimal("0")
        items.append(
            {
                "timestamp_utc": snapshot.timestamp_utc.isoformat(),
                "equity_usd": _q2(equity),
                "pnl_usd": _signed(_q2(pnl_usd)),
                "pnl_pct": _signed(_q2(pnl_pct)),
                "drawdown_pct": _signed(_q2(snapshot.drawdown_pct)),
            }
        )
    return {"market": market, "range": range, "initial_equity_usd": _q2(initial), "items": items}


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
    if spot is not None:
        position = (await session.execute(select(SpotPosition).where(SpotPosition.open_trade_id == trade_id))).scalar_one_or_none()
        decision = (await session.execute(select(AgentDecision).where(AgentDecision.trade_id == trade_id))).scalar_one_or_none()
        return _spot_trade_detail(spot, position, decision)
    position = (await session.execute(select(PerpPosition).where(PerpPosition.open_trade_id == trade_id))).scalar_one_or_none()
    decision = (await session.execute(select(AgentDecision).where(AgentDecision.trade_id == trade_id))).scalar_one_or_none()
    return _perp_trade_detail(perp, position, decision)


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


def _initial_equity(snapshots: list[PnlSnapshot], settings) -> Decimal:
    if snapshots:
        return Decimal(snapshots[0].total_equity_usd)
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


def _pnl_pct(pnl: Decimal, entry: Decimal, size: Decimal) -> str:
    exposure = entry * size
    if exposure <= 0:
        return "+0.00"
    return _signed(_q2(pnl / exposure * Decimal("100")))


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


def _spot_trade_detail(trade: SpotTrade, position: SpotPosition | None, decision: AgentDecision | None) -> dict:
    current = Decimal(position.current_price) if position else Decimal(trade.price)
    size = Decimal(position.size) if position else Decimal(trade.amount)
    entry = Decimal(position.entry_price) if position else Decimal(trade.price)
    pnl = Decimal(position.pnl_unrealized) if position else Decimal("0")
    return {
        "trade_id": trade.trade_id,
        "asset": trade.asset,
        "market": "spot",
        "direction": trade.side,
        "entry_price": _q2(entry),
        "current_or_exit_price": _q2(current),
        "pnl_usd": _signed(_q2(pnl)),
        "pnl_pct": _pnl_pct(pnl, entry, size),
        "stop_loss": _q2(position.stop_loss) if position and position.stop_loss else None,
        "take_profit_1": _q2(position.take_profit_1) if position and position.take_profit_1 else None,
        "take_profit_2": _q2(position.take_profit_2) if position and position.take_profit_2 else None,
        "trailing_stop": _q2(position.trailing_stop) if position and position.trailing_stop else None,
        "size": _q2(size),
        "leverage": None,
        "exposure_usd": _q2(size * current),
        "opened_at": trade.timestamp_utc.isoformat(),
        "closed_at": trade.block_timestamp_utc.isoformat() if trade.block_timestamp_utc else None,
        "duration_seconds": None,
        "close_reason": _close_reason(trade),
        "decision": _decision_payload(decision),
        "events": [],
        "is_simulated": trade.trade_id.startswith("dry_") or trade.provider == "dry_run",
    }


def _perp_trade_detail(trade: PerpTrade, position: PerpPosition | None, decision: AgentDecision | None) -> dict:
    current = Decimal(position.current_price) if position else Decimal(trade.price)
    size = Decimal(position.size) if position else Decimal(trade.size)
    entry = Decimal(position.entry_price) if position else Decimal(trade.price)
    pnl = Decimal(position.pnl_unrealized) if position else Decimal("0")
    return {
        "trade_id": trade.trade_id,
        "asset": trade.asset,
        "market": "perp",
        "direction": trade.side,
        "entry_price": _q2(entry),
        "current_or_exit_price": _q2(current),
        "pnl_usd": _signed(_q2(pnl)),
        "pnl_pct": _pnl_pct(pnl, entry, size),
        "stop_loss": _q2(position.stop_loss) if position and position.stop_loss else None,
        "take_profit_1": _q2(position.take_profit_1) if position and position.take_profit_1 else None,
        "take_profit_2": _q2(position.take_profit_2) if position and position.take_profit_2 else None,
        "trailing_stop": _q2(position.trailing_stop) if position and position.trailing_stop else None,
        "size": _q2(size),
        "leverage": trade.leverage,
        "exposure_usd": _q2(size * current),
        "opened_at": trade.timestamp_utc.isoformat(),
        "closed_at": trade.block_timestamp_utc.isoformat() if trade.block_timestamp_utc else None,
        "duration_seconds": None,
        "close_reason": _close_reason(trade),
        "decision": _decision_payload(decision),
        "events": [{"name": "tp1", "reached": position.tp1_reached}] if position else [],
        "is_simulated": trade.trade_id.startswith("dry_") or trade.venue == "dry_run",
    }
