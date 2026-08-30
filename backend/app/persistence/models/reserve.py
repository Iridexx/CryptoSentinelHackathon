"""ORM models for the "Bank" store-of-value reserve.

See plans/Plan_Reserve.md. The reserve holds a USDC cash sleeve plus positions in
a small set of hard assets; a two-phase model (sweep → deploy) feeds it. Snapshots
mirror ``PnlSnapshot`` for the history chart.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

QTY_NUMERIC = Numeric(38, 18)
USD_NUMERIC = Numeric(20, 8)


class ReserveHolding(Base):
    """Current position in one reserve asset (one row per user+asset)."""

    __tablename__ = "reserve_holdings"
    __table_args__ = (UniqueConstraint("user_id", "asset", name="uq_reserve_holding_user_asset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(16), nullable=False)  # BTC, ETH, BNB, SOL, TRX
    venue: Mapped[str] = mapped_column(String(32), nullable=False, default="pancakeswap")
    quantity: Mapped[Decimal] = mapped_column(QTY_NUMERIC, nullable=False, default=Decimal("0"))
    avg_cost_usd: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False, default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReserveTransaction(Base):
    """Audit trail: every movement of cash or assets in the reserve.

    ``type`` is one of: ``transfer_in`` | ``transfer_out`` | ``sweep`` |
    ``deploy_buy`` | ``rebalance_buy`` | ``rebalance_sell``. ``sweep`` and
    ``transfer_in`` are cash-only (``asset`` is NULL, ``fee_usd`` is 0).
    """

    __tablename__ = "reserve_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    asset: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(QTY_NUMERIC, nullable=True)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(30, 18), nullable=True)
    value_usd: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False, default=Decimal("0"))
    fee_usd: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False, default=Decimal("0"))
    cash_usd_delta: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False, default=Decimal("0"))
    venue: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref: Mapped[str | None] = mapped_column(String(128), nullable=True)  # tx hash when live
    note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ReserveSnapshot(Base):
    """Hourly value snapshot of the reserve, for the history/benchmark chart."""

    __tablename__ = "reserve_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_value_usd: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False)
    cash_usd: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False, default=Decimal("0"))
    cost_basis_usd: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False, default=Decimal("0"))
    pnl_usd: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False, default=Decimal("0"))
    fees_cumulative_usd: Mapped[Decimal] = mapped_column(USD_NUMERIC, nullable=False, default=Decimal("0"))
    holdings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
