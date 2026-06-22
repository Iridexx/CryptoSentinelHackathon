"""Read-side query service that assembles dashboard views from the DB."""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from math import sqrt
from statistics import mean, stdev

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.positions import (
    PerpPositionRepository,
    SpotPositionRepository,
)
from backend.app.persistence.repositories.trades import (
    PerpTradeRepository,
    SpotTradeRepository,
)
from backend.app.schemas.views import (
    GlobalView,
    PerpPositionView,
    PerpTradeView,
    PerpView,
    PnlPoint,
    SpotPositionView,
    SpotTradeView,
    SpotView,
)


class ViewService:
    """Assembles the Spot / Perp / Global dashboard payloads."""

    def __init__(self, session: AsyncSession, *, drawdown_cap_pct: float = -15.0) -> None:
        self._session = session
        self._drawdown_cap_pct = drawdown_cap_pct

    async def spot_view(self, user_id: str) -> SpotView:
        pos_repo = SpotPositionRepository(self._session)
        trade_repo = SpotTradeRepository(self._session)
        positions = await pos_repo.open_for_user(user_id)
        trades = await trade_repo.list_for_user(user_id, limit=100)
        win = await trade_repo.win_rate(user_id)
        unrealized = sum((p.pnl_unrealized for p in positions), Decimal("0"))
        realized = sum((t.pnl_usd for t in trades if t.pnl_usd is not None), Decimal("0"))
        return SpotView(
            open_positions=[
                SpotPositionView(
                    position_id=p.position_id,
                    asset=p.asset,
                    size=p.size,
                    entry_price=p.entry_price,
                    current_price=p.current_price,
                    pnl_unrealized=p.pnl_unrealized,
                    pnl_pct=_position_pnl_pct(p.pnl_unrealized, p.entry_price, p.size),
                    stop_loss=p.stop_loss,
                    take_profit_1=p.take_profit_1,
                    take_profit_2=p.take_profit_2,
                    status=p.status,
                    opened_at=p.opened_at.isoformat(),
                )
                for p in positions
            ],
            history=[
                SpotTradeView(
                    trade_id=t.trade_id,
                    asset=t.asset,
                    side=t.side,
                    amount=t.amount,
                    price=t.price,
                    pnl_usd=_fmt_pnl(t.pnl_usd),
                    pnl_pct=_pnl_pct_str(t.pnl_usd, _spot_trade_entry_price(t), t.amount),
                    entry_price=_spot_trade_entry_price(t),
                    current_or_exit_price=t.price,
                    status=t.status,
                    close_reason=_close_reason(t),
                    tx_hash=t.tx_hash,
                    timestamp_utc=t.timestamp_utc.isoformat(),
                    block_timestamp_utc=t.block_timestamp_utc.isoformat() if t.block_timestamp_utc else None,
                    is_simulated=_is_spot_dry_run(t),
                )
                for t in trades
            ],
            realized_pnl_usd=realized,
            unrealized_pnl_usd=unrealized,
            win_rate_pct=win["win_rate_pct"],
            trade_count=len(trades),
        )

    async def perp_view(self, user_id: str) -> PerpView:
        pos_repo = PerpPositionRepository(self._session)
        trade_repo = PerpTradeRepository(self._session)
        positions = await pos_repo.open_for_user(user_id)
        trades = await trade_repo.list_for_user(user_id, limit=100)
        win = await trade_repo.win_rate(user_id)
        unrealized = sum((p.pnl_unrealized for p in positions), Decimal("0"))
        realized = sum((t.pnl_usd for t in trades if t.pnl_usd is not None), Decimal("0"))
        history_trades = [t for t in trades if t.status not in {"prepared", "pending"}]
        return PerpView(
            open_positions=[
                PerpPositionView(
                    position_id=p.position_id,
                    asset=p.asset,
                    side=p.side,
                    size=p.size,
                    entry_price=p.entry_price,
                    current_price=p.current_price,
                    leverage=p.leverage,
                    pnl_unrealized=p.pnl_unrealized,
                    pnl_pct=_position_pnl_pct(p.pnl_unrealized, p.entry_price, p.size),
                    stop_loss=p.stop_loss,
                    take_profit_1=p.take_profit_1,
                    take_profit_2=p.take_profit_2,
                    liquidation_price=p.liquidation_price,
                    funding_rate=p.funding_rate,
                    status=p.status,
                    opened_at=p.opened_at.isoformat(),
                )
                for p in positions
            ],
            history=[
                PerpTradeView(
                    trade_id=t.trade_id,
                    asset=t.asset,
                    side=t.side,
                    direction=t.direction,
                    size=t.size,
                    price=t.price,
                    pnl_usd=_fmt_pnl(t.pnl_usd),
                    pnl_pct=_pnl_pct_str(t.pnl_usd, _perp_trade_entry_price(t), t.size),
                    entry_price=_perp_trade_entry_price(t),
                    current_or_exit_price=t.price,
                    leverage=t.leverage,
                    status=t.status,
                    close_reason=_close_reason(t),
                    tx_hash=t.tx_hash,
                    timestamp_utc=t.timestamp_utc.isoformat(),
                    block_timestamp_utc=t.block_timestamp_utc.isoformat() if t.block_timestamp_utc else None,
                    is_simulated=_is_perp_dry_run(t),
                )
                for t in history_trades
            ],
            realized_pnl_usd=realized,
            unrealized_pnl_usd=unrealized,
            win_rate_pct=win["win_rate_pct"],
            trade_count=len(trades),
        )

    async def global_view(self, user_id: str) -> GlobalView:
        pnl_repo = PnlRepository(self._session)
        spot_pos = SpotPositionRepository(self._session)
        perp_pos = PerpPositionRepository(self._session)
        spot_trade_repo = SpotTradeRepository(self._session)
        perp_trade_repo = PerpTradeRepository(self._session)
        portfolio = await pnl_repo.get_portfolio(user_id)
        snapshots = await pnl_repo.recent_for_user(user_id, limit=168)
        open_spot = await spot_pos.open_for_user(user_id)
        open_perp = await perp_pos.open_for_user(user_id)

        unrealized = (
            sum((p.pnl_unrealized for p in open_spot), Decimal("0"))
            + sum((p.pnl_unrealized for p in open_perp), Decimal("0"))
        )
        realized_spot = await spot_trade_repo.sum_realized_pnl(user_id)
        realized_perp = await perp_trade_repo.sum_realized_pnl(user_id)
        realized = realized_spot + realized_perp

        if portfolio is None:
            return GlobalView(
                total_equity_usd=Decimal("0"),
                initial_equity_usd=Decimal("0"),
                pnl_total_usd=realized + unrealized,
                pnl_total_pct=0.0,
                realized_pnl_usd=realized,
                unrealized_pnl_usd=unrealized,
                drawdown_pct=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
                sharpe_status="insufficient_data",
                sharpe_ratio=None,
                drawdown_cap_pct=self._drawdown_cap_pct,
                exposure_pct=Decimal("0"),
                daily_pnl_usd=Decimal("0"),
                agent_status="idle",
                trades_today=0,
                open_spot_positions=len(open_spot),
                open_perp_positions=len(open_perp),
                pnl_history=[],
            )

        # Calcola total_equity direttamente dalla fonte, non dal DB cache
        # (evita sfasature tra fast_tick aggiornamenti e letture API)
        total_equity = portfolio.initial_equity_usd + realized + unrealized
        pnl_total = realized + unrealized
        sharpe = _daily_sharpe(snapshots)
        pnl_pct = (
            float(pnl_total / portfolio.initial_equity_usd * 100)
            if portfolio.initial_equity_usd > 0
            else 0.0
        )
        return GlobalView(
            total_equity_usd=total_equity,
            initial_equity_usd=portfolio.initial_equity_usd,
            pnl_total_usd=pnl_total,
            pnl_total_pct=round(pnl_pct, 2),
            realized_pnl_usd=realized,
            unrealized_pnl_usd=unrealized,
            drawdown_pct=portfolio.drawdown_pct,
            max_drawdown_pct=portfolio.max_drawdown_pct,
            sharpe_status=sharpe["status"],
            sharpe_ratio=sharpe["ratio"],
            drawdown_cap_pct=self._drawdown_cap_pct,
            exposure_pct=portfolio.exposure_pct,
            daily_pnl_usd=portfolio.daily_pnl_usd,
            agent_status=portfolio.agent_status,
            trades_today=portfolio.trades_today,
            open_spot_positions=len(open_spot),
            open_perp_positions=len(open_perp),
            pnl_history=[
                PnlPoint(
                    timestamp_utc=s.timestamp_utc.isoformat(),
                    total_equity_usd=s.total_equity_usd,
                    drawdown_pct=s.drawdown_pct,
                )
                for s in reversed(snapshots)
            ],
        )


def _fmt_pnl(pnl: Decimal | None) -> str:
    if pnl is None:
        return "+0.00"
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:.2f}"


def _pnl_pct_str(pnl: Decimal | None, price: Decimal, size: Decimal) -> str:
    if pnl is None or price <= 0 or size <= 0:
        return "+0.00"
    exposure = price * size
    return _format_signed_pct(pnl / exposure * 100)


def _format_signed_pct(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):+.2f}"


def _position_pnl_pct(pnl: Decimal, entry_price: Decimal, size: Decimal) -> str:
    exposure = entry_price * size
    if exposure <= 0:
        return "+0.00"
    return _format_signed_pct(pnl / exposure * Decimal("100"))


def _spot_trade_entry_price(t) -> Decimal:
    """Ricava il prezzo di ingresso per trade di chiusura spot (sell) usando pnl_usd.
    pnl = (exit - entry) * size  →  entry = exit - pnl / size
    """
    if t.side == "sell" and t.pnl_usd is not None and t.amount > Decimal("0"):
        return t.price - t.pnl_usd / t.amount
    return t.price


def _perp_trade_entry_price(t) -> Decimal:
    """Ricava il prezzo di ingresso per trade di chiusura perp (direction='close').
    Long:  pnl = (exit - entry) * size  →  entry = exit - pnl / size
    Short: pnl = (entry - exit) * size  →  entry = exit + pnl / size
    """
    if t.direction == "close" and t.pnl_usd is not None and t.size > Decimal("0"):
        if t.side == "long":
            return t.price - t.pnl_usd / t.size
        else:
            return t.price + t.pnl_usd / t.size
    return t.price


def _close_reason(trade) -> str | None:
    """Estrae il motivo di chiusura pulito dalle note (es. 'take_profit_1').

    Le chiusure automatiche salvano notes='auto_close:<reason>' (con '_partial'
    per le chiusure parziali). Le aperture non hanno un motivo di chiusura.
    """
    notes = trade.notes or ""
    prefix = "auto_close:"
    if not notes.startswith(prefix):
        return None
    reason = notes[len(prefix):].replace("_partial", "")
    return reason or None


def _is_spot_dry_run(trade) -> bool:
    return trade.trade_id.startswith("dry_") or trade.provider == "dry_run" or "dry_run" in (trade.notes or "")


def _is_perp_dry_run(trade) -> bool:
    return trade.trade_id.startswith("dry_") or trade.venue == "dry_run" or "dry_run" in (trade.notes or "")


def _daily_sharpe(snapshots) -> dict[str, str | None]:
    if len(snapshots) < 2:
        return {"status": "insufficient_data", "ratio": None}

    daily_equity: OrderedDict[str, Decimal] = OrderedDict()
    for snapshot in sorted(snapshots, key=lambda row: row.timestamp_utc):
        daily_equity[snapshot.timestamp_utc.date().isoformat()] = Decimal(snapshot.total_equity_usd)

    values = list(daily_equity.values())
    returns: list[float] = []
    for previous, current in zip(values, values[1:], strict=False):
        if previous > 0:
            returns.append(float((current - previous) / previous))
    if len(returns) < 7:
        return {"status": "insufficient_data", "ratio": None}
    volatility = stdev(returns)
    if volatility == 0:
        return {"status": "insufficient_data", "ratio": None}
    ratio = mean(returns) / volatility * sqrt(365)
    return {"status": "ready", "ratio": f"{Decimal(str(ratio)).quantize(Decimal('0.01'))}"}
