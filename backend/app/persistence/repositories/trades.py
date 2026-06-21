"""Repository for spot and perpetual trade records."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.trades import PerpTrade, SpotTrade


class SpotTradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, trade: SpotTrade) -> SpotTrade:
        self._session.add(trade)
        await self._session.commit()
        await self._session.refresh(trade)
        return trade

    async def get(self, trade_id: str) -> SpotTrade | None:
        result = await self._session.execute(
            select(SpotTrade).where(SpotTrade.trade_id == trade_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 100,
        status: str | None = None,
    ) -> list[SpotTrade]:
        stmt = select(SpotTrade).where(SpotTrade.user_id == user_id)
        if status:
            stmt = stmt.where(SpotTrade.status == status)
        stmt = stmt.order_by(SpotTrade.timestamp_utc.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def win_rate(self, user_id: str) -> dict:
        trades = await self.list_for_user(user_id, limit=10_000, status="confirmed")
        if not trades:
            return {"total": 0, "wins": 0, "win_rate_pct": 0.0}
        wins = sum(1 for t in trades if t.side == "sell" and t.notes and "profit" in t.notes)
        return {
            "total": len(trades),
            "wins": wins,
            "win_rate_pct": round(wins / len(trades) * 100, 1),
        }

    async def count_since(
        self,
        user_id: str,
        *,
        since: datetime,
        status: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(SpotTrade)
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.timestamp_utc >= since)
        )
        if status:
            stmt = stmt.where(SpotTrade.status == status)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_today(self, user_id: str, now: datetime) -> int:
        """Conta trade spot dell'utente nel giorno corrente (da mezzanotte UTC)."""
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._session.execute(
            select(func.count())
            .select_from(SpotTrade)
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.timestamp_utc >= start)
        )
        return int(result.scalar_one())


class PerpTradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, trade: PerpTrade) -> PerpTrade:
        self._session.add(trade)
        await self._session.commit()
        await self._session.refresh(trade)
        return trade

    async def get(self, trade_id: str) -> PerpTrade | None:
        result = await self._session.execute(
            select(PerpTrade).where(PerpTrade.trade_id == trade_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 100,
        status: str | None = None,
    ) -> list[PerpTrade]:
        stmt = select(PerpTrade).where(PerpTrade.user_id == user_id)
        if status:
            stmt = stmt.where(PerpTrade.status == status)
        stmt = stmt.order_by(PerpTrade.timestamp_utc.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_today(self, user_id: str, now: datetime) -> int:
        """Conta trade perp dell'utente nel giorno corrente (da mezzanotte UTC)."""
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._session.execute(
            select(func.count())
            .select_from(PerpTrade)
            .where(PerpTrade.user_id == user_id)
            .where(PerpTrade.timestamp_utc >= start)
        )
        return int(result.scalar_one())
