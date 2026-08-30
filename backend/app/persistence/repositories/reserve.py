"""Repository for the "Bank" store-of-value reserve.

Mutators that participate in a multi-write operation (`upsert_holding`,
`add_transaction`, `set_reserve_fields`) only ``flush`` — the caller
(``ReserveService``) owns the transaction and commits once, so a transfer/deploy
lands atomically (holdings + transaction rows + ``portfolio_state`` counters).
``save_snapshot`` is standalone and commits itself.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.pnl import PortfolioState
from backend.app.persistence.models.reserve import (
    ReserveHolding,
    ReserveSnapshot,
    ReserveTransaction,
)

_RESERVE_FIELDS = (
    "reserve_cash_usd",
    "reserve_transferred_net_usd",
    "last_swept_realized_pnl_usd",
    "last_deploy_at",
    "reserve_frozen",
)


class ReserveRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── holdings ─────────────────────────────────────────────────────────────

    async def list_holdings(self, user_id: str) -> list[ReserveHolding]:
        result = await self._session.execute(
            select(ReserveHolding)
            .where(ReserveHolding.user_id == user_id)
            .order_by(ReserveHolding.asset)
        )
        return list(result.scalars().all())

    async def get_holding(self, user_id: str, asset: str) -> ReserveHolding | None:
        result = await self._session.execute(
            select(ReserveHolding)
            .where(ReserveHolding.user_id == user_id)
            .where(ReserveHolding.asset == asset)
        )
        return result.scalar_one_or_none()

    async def upsert_holding(
        self,
        user_id: str,
        asset: str,
        *,
        quantity: Decimal,
        avg_cost_usd: Decimal,
        now: datetime,
        venue: str = "pancakeswap",
    ) -> ReserveHolding:
        """Set the absolute quantity / average cost for one asset. Flush only."""
        holding = await self.get_holding(user_id, asset)
        if holding is None:
            holding = ReserveHolding(
                user_id=user_id,
                asset=asset,
                venue=venue,
                quantity=quantity,
                avg_cost_usd=avg_cost_usd,
                updated_at=now,
            )
            self._session.add(holding)
        else:
            holding.quantity = quantity
            holding.avg_cost_usd = avg_cost_usd
            holding.venue = venue
            holding.updated_at = now
        await self._session.flush()
        return holding

    # ── transactions ─────────────────────────────────────────────────────────

    async def add_transaction(self, txn: ReserveTransaction) -> ReserveTransaction:
        """Append one audit-trail row. Flush only."""
        self._session.add(txn)
        await self._session.flush()
        return txn

    async def list_transactions(
        self, user_id: str, *, limit: int = 100
    ) -> list[ReserveTransaction]:
        result = await self._session.execute(
            select(ReserveTransaction)
            .where(ReserveTransaction.user_id == user_id)
            .order_by(ReserveTransaction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def sum_fees(self, user_id: str, *, since: datetime | None = None) -> Decimal:
        """Total fees paid by the reserve (D30). ``since`` filters by day."""
        stmt = select(func.sum(ReserveTransaction.fee_usd)).where(
            ReserveTransaction.user_id == user_id
        )
        if since is not None:
            stmt = stmt.where(ReserveTransaction.created_at >= since)
        val = (await self._session.execute(stmt)).scalar_one_or_none()
        return Decimal(str(val)) if val is not None else Decimal("0")

    # ── snapshots ────────────────────────────────────────────────────────────

    async def save_snapshot(self, snapshot: ReserveSnapshot) -> ReserveSnapshot:
        self._session.add(snapshot)
        await self._session.commit()
        await self._session.refresh(snapshot)
        return snapshot

    async def recent_snapshots(
        self, user_id: str, *, limit: int = 168
    ) -> list[ReserveSnapshot]:
        result = await self._session.execute(
            select(ReserveSnapshot)
            .where(ReserveSnapshot.user_id == user_id)
            .order_by(ReserveSnapshot.timestamp_utc.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def snapshots_since(
        self, user_id: str, since: datetime
    ) -> list[ReserveSnapshot]:
        result = await self._session.execute(
            select(ReserveSnapshot)
            .where(ReserveSnapshot.user_id == user_id)
            .where(ReserveSnapshot.timestamp_utc >= since)
            .order_by(ReserveSnapshot.timestamp_utc.asc())
        )
        return list(result.scalars().all())

    # ── portfolio_state reserve counters ─────────────────────────────────────

    async def get_reserve_fields(self, user_id: str) -> dict:
        """Read the reserve accounting fields off ``portfolio_state``.

        Missing row → zeroed defaults (first run, before any portfolio snapshot).
        """
        result = await self._session.execute(
            select(PortfolioState).where(PortfolioState.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {
                "reserve_cash_usd": Decimal("0"),
                "reserve_transferred_net_usd": Decimal("0"),
                "last_swept_realized_pnl_usd": Decimal("0"),
                "last_deploy_at": None,
                "reserve_frozen": False,
            }
        return {field: getattr(row, field) for field in _RESERVE_FIELDS}

    async def set_reserve_fields(self, user_id: str, *, now: datetime, **fields) -> None:
        """Mutate one or more reserve fields on ``portfolio_state``. Flush only.

        Raises ``ValueError`` if the portfolio row does not exist yet — the
        caller must have seeded it (the reserve never creates the portfolio).
        """
        unknown = set(fields) - set(_RESERVE_FIELDS)
        if unknown:
            raise ValueError(f"unknown reserve field(s): {sorted(unknown)}")
        result = await self._session.execute(
            select(PortfolioState).where(PortfolioState.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("portfolio_state row missing — seed it before reserve writes")
        for key, value in fields.items():
            setattr(row, key, value)
        row.updated_at = now
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()
