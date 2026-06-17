"""Read-side query service that assembles dashboard views from the DB."""

from __future__ import annotations

from decimal import Decimal

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
        return SpotView(
            open_positions=[
                SpotPositionView(
                    position_id=p.position_id,
                    asset=p.asset,
                    size=p.size,
                    entry_price=p.entry_price,
                    current_price=p.current_price,
                    pnl_unrealized=p.pnl_unrealized,
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
                    status=t.status,
                    tx_hash=t.tx_hash,
                    timestamp_utc=t.timestamp_utc.isoformat(),
                    block_timestamp_utc=t.block_timestamp_utc.isoformat() if t.block_timestamp_utc else None,
                )
                for t in trades
            ],
            realized_pnl_usd=Decimal("0"),
            unrealized_pnl_usd=unrealized,
            win_rate_pct=win["win_rate_pct"],
            trade_count=len(trades),
        )

    async def perp_view(self, user_id: str) -> PerpView:
        pos_repo = PerpPositionRepository(self._session)
        trade_repo = PerpTradeRepository(self._session)
        positions = await pos_repo.open_for_user(user_id)
        trades = await trade_repo.list_for_user(user_id, limit=100)
        closed = [t for t in trades if t.status == "confirmed"]
        unrealized = sum((p.pnl_unrealized for p in positions), Decimal("0"))
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
                    leverage=t.leverage,
                    status=t.status,
                    tx_hash=t.tx_hash,
                    timestamp_utc=t.timestamp_utc.isoformat(),
                    block_timestamp_utc=t.block_timestamp_utc.isoformat() if t.block_timestamp_utc else None,
                )
                for t in trades
            ],
            realized_pnl_usd=Decimal("0"),
            unrealized_pnl_usd=unrealized,
            win_rate_pct=round(len(closed) / len(trades) * 100, 1) if trades else 0.0,
            trade_count=len(trades),
        )

    async def global_view(self, user_id: str) -> GlobalView:
        pnl_repo = PnlRepository(self._session)
        spot_pos = SpotPositionRepository(self._session)
        perp_pos = PerpPositionRepository(self._session)
        portfolio = await pnl_repo.get_portfolio(user_id)
        snapshots = await pnl_repo.recent_for_user(user_id, limit=168)
        open_spot = await spot_pos.open_for_user(user_id)
        open_perp = await perp_pos.open_for_user(user_id)

        if portfolio is None:
            return GlobalView(
                total_equity_usd=Decimal("0"),
                initial_equity_usd=Decimal("0"),
                pnl_total_usd=Decimal("0"),
                pnl_total_pct=0.0,
                drawdown_pct=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
                drawdown_cap_pct=self._drawdown_cap_pct,
                exposure_pct=Decimal("0"),
                daily_pnl_usd=Decimal("0"),
                agent_status="idle",
                trades_today=0,
                open_spot_positions=len(open_spot),
                open_perp_positions=len(open_perp),
                pnl_history=[],
            )

        pnl_total = portfolio.total_equity_usd - portfolio.initial_equity_usd
        pnl_pct = (
            float(pnl_total / portfolio.initial_equity_usd * 100)
            if portfolio.initial_equity_usd > 0
            else 0.0
        )
        return GlobalView(
            total_equity_usd=portfolio.total_equity_usd,
            initial_equity_usd=portfolio.initial_equity_usd,
            pnl_total_usd=pnl_total,
            pnl_total_pct=round(pnl_pct, 2),
            drawdown_pct=portfolio.drawdown_pct,
            max_drawdown_pct=portfolio.max_drawdown_pct,
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
