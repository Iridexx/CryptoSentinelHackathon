"""Repository for PnL snapshots and global portfolio state."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.pnl import PnlSnapshot, PortfolioState


class PnlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_snapshot(self, snapshot: PnlSnapshot) -> PnlSnapshot:
        self._session.add(snapshot)
        await self._session.commit()
        await self._session.refresh(snapshot)
        return snapshot

    async def recent_for_user(self, user_id: str, *, limit: int = 168) -> list[PnlSnapshot]:
        """Return up to `limit` snapshots newest-first (default = 1 week of hourly)."""
        result = await self._session.execute(
            select(PnlSnapshot)
            .where(PnlSnapshot.user_id == user_id)
            .order_by(PnlSnapshot.timestamp_utc.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def upsert_portfolio(
        self,
        user_id: str,
        *,
        total_equity_usd: Decimal,
        initial_equity_usd: Decimal | None = None,
        peak_equity_usd: Decimal | None = None,
        drawdown_pct: Decimal = Decimal("0"),
        max_drawdown_pct: Decimal = Decimal("0"),
        exposure_pct: Decimal = Decimal("0"),
        daily_pnl_usd: Decimal = Decimal("0"),
        daily_loss_limit_used_pct: Decimal = Decimal("0"),
        agent_status: str = "idle",
        trades_today: int = 0,
    ) -> PortfolioState:
        result = await self._session.execute(
            select(PortfolioState).where(PortfolioState.user_id == user_id)
        )
        now = datetime.now(UTC)
        record = result.scalar_one_or_none()
        if record is None:
            record = PortfolioState(
                user_id=user_id,
                total_equity_usd=total_equity_usd,
                initial_equity_usd=initial_equity_usd or total_equity_usd,
                peak_equity_usd=peak_equity_usd or total_equity_usd,
                drawdown_pct=drawdown_pct,
                max_drawdown_pct=max_drawdown_pct,
                exposure_pct=exposure_pct,
                daily_pnl_usd=daily_pnl_usd,
                daily_loss_limit_used_pct=daily_loss_limit_used_pct,
                agent_status=agent_status,
                trades_today=trades_today,
                updated_at=now,
            )
            self._session.add(record)
        else:
            record.total_equity_usd = total_equity_usd
            if initial_equity_usd is not None:
                record.initial_equity_usd = initial_equity_usd
            if peak_equity_usd is not None:
                record.peak_equity_usd = peak_equity_usd
            record.drawdown_pct = drawdown_pct
            record.max_drawdown_pct = max_drawdown_pct
            record.exposure_pct = exposure_pct
            record.daily_pnl_usd = daily_pnl_usd
            record.daily_loss_limit_used_pct = daily_loss_limit_used_pct
            record.agent_status = agent_status
            record.trades_today = trades_today
            record.updated_at = now
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def get_portfolio(self, user_id: str) -> PortfolioState | None:
        result = await self._session.execute(
            select(PortfolioState).where(PortfolioState.user_id == user_id)
        )
        return result.scalar_one_or_none()
