"""R2 — reserve ORM models, repository, portfolio_state counters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.reserve import ReserveSnapshot, ReserveTransaction
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.reserve import ReserveRepository

USER = "00000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    yield
    await close_db()


async def _seed_portfolio(session) -> None:
    await PnlRepository(session).upsert_portfolio(
        USER, total_equity_usd=Decimal("500"), initial_equity_usd=Decimal("500")
    )


# ── schema ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reserve_tables_created(db) -> None:
    async with get_session_factory()() as session:
        rows = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = {r[0] for r in rows.fetchall()}
    assert {"reserve_holdings", "reserve_transactions", "reserve_snapshots"} <= tables


@pytest.mark.asyncio
async def test_portfolio_state_has_reserve_columns(db) -> None:
    async with get_session_factory()() as session:
        info = await session.execute(text("PRAGMA table_info(portfolio_state)"))
        cols = {r[1] for r in info.fetchall()}
    assert {
        "reserve_cash_usd",
        "reserve_transferred_net_usd",
        "last_swept_realized_pnl_usd",
        "last_deploy_at",
        "reserve_frozen",
    } <= cols


# ── holdings ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_holding_create_then_update(db) -> None:
    async with get_session_factory()() as session:
        repo = ReserveRepository(session)
        await repo.upsert_holding(
            USER, "BTC", quantity=Decimal("0.001"), avg_cost_usd=Decimal("60000"), now=NOW
        )
        await session.commit()
        await repo.upsert_holding(
            USER, "BTC", quantity=Decimal("0.002"), avg_cost_usd=Decimal("61000"), now=NOW
        )
        await session.commit()

        holdings = await repo.list_holdings(USER)
        assert len(holdings) == 1
        assert holdings[0].asset == "BTC"
        assert holdings[0].quantity == Decimal("0.002000000000000000")
        assert holdings[0].avg_cost_usd == Decimal("61000.00000000")


@pytest.mark.asyncio
async def test_list_holdings_sorted_by_asset(db) -> None:
    async with get_session_factory()() as session:
        repo = ReserveRepository(session)
        for asset in ("SOL", "BTC", "ETH"):
            await repo.upsert_holding(
                USER, asset, quantity=Decimal("1"), avg_cost_usd=Decimal("1"), now=NOW
            )
        await session.commit()
        assert [h.asset for h in await repo.list_holdings(USER)] == ["BTC", "ETH", "SOL"]


# ── transactions & fees ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transactions_listed_newest_first_and_fees_summed(db) -> None:
    async with get_session_factory()() as session:
        repo = ReserveRepository(session)
        await repo.add_transaction(
            ReserveTransaction(
                user_id=USER, type="sweep", value_usd=Decimal("20"),
                fee_usd=Decimal("0"), cash_usd_delta=Decimal("20"),
                created_at=NOW, note="profit_sweep",
            )
        )
        await repo.add_transaction(
            ReserveTransaction(
                user_id=USER, type="deploy_buy", asset="BTC", quantity=Decimal("0.0002"),
                price_usd=Decimal("60000"), value_usd=Decimal("12"),
                fee_usd=Decimal("0.05"), cash_usd_delta=Decimal("-12"),
                created_at=NOW + timedelta(minutes=1),
            )
        )
        await repo.add_transaction(
            ReserveTransaction(
                user_id=USER, type="deploy_buy", asset="ETH", value_usd=Decimal("8"),
                fee_usd=Decimal("0.03"), cash_usd_delta=Decimal("-8"),
                created_at=NOW + timedelta(minutes=2),
            )
        )
        await session.commit()

        txns = await repo.list_transactions(USER)
        assert [t.type for t in txns][:1] == ["deploy_buy"]
        assert txns[-1].type == "sweep"
        assert await repo.sum_fees(USER) == Decimal("0.08000000")
        assert await repo.sum_fees(USER, since=NOW + timedelta(minutes=2)) == Decimal("0.03000000")


# ── snapshots ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshots_saved_and_read_back(db) -> None:
    async with get_session_factory()() as session:
        repo = ReserveRepository(session)
        for i in range(3):
            await repo.save_snapshot(
                ReserveSnapshot(
                    user_id=USER,
                    timestamp_utc=NOW + timedelta(hours=i),
                    total_value_usd=Decimal("40") + i,
                    cash_usd=Decimal("4"),
                    cost_basis_usd=Decimal("40"),
                    pnl_usd=Decimal(i),
                    fees_cumulative_usd=Decimal("0.08"),
                )
            )
        recent = await repo.recent_snapshots(USER, limit=2)
        assert len(recent) == 2
        # SQLite reads datetimes back tz-naive; compare on the wall clock.
        assert recent[0].timestamp_utc.replace(tzinfo=None) == (NOW + timedelta(hours=2)).replace(tzinfo=None)
        assert recent[0].total_value_usd == Decimal("42.00000000")  # newest first
        since = await repo.snapshots_since(USER, NOW + timedelta(hours=1))
        assert [s.pnl_usd for s in since] == [Decimal("1.00000000"), Decimal("2.00000000")]


# ── portfolio_state reserve counters ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_reserve_fields_zeroed_without_portfolio_row(db) -> None:
    async with get_session_factory()() as session:
        fields = await ReserveRepository(session).get_reserve_fields(USER)
    assert fields["reserve_cash_usd"] == Decimal("0")
    assert fields["reserve_transferred_net_usd"] == Decimal("0")
    assert fields["last_deploy_at"] is None
    assert fields["reserve_frozen"] is False


@pytest.mark.asyncio
async def test_set_reserve_fields_requires_portfolio_row(db) -> None:
    async with get_session_factory()() as session:
        with pytest.raises(ValueError, match="portfolio_state row missing"):
            await ReserveRepository(session).set_reserve_fields(
                USER, now=NOW, reserve_cash_usd=Decimal("10")
            )


@pytest.mark.asyncio
async def test_set_reserve_fields_updates_and_reads_back(db) -> None:
    async with get_session_factory()() as session:
        await _seed_portfolio(session)
        repo = ReserveRepository(session)
        await repo.set_reserve_fields(
            USER,
            now=NOW,
            reserve_cash_usd=Decimal("15.5"),
            reserve_transferred_net_usd=Decimal("50"),
            reserve_frozen=True,
            last_deploy_at=NOW,
        )
        await repo.commit()

        fields = await repo.get_reserve_fields(USER)
        assert fields["reserve_cash_usd"] == Decimal("15.50000000")
        assert fields["reserve_transferred_net_usd"] == Decimal("50.00000000")
        assert fields["reserve_frozen"] is True
        assert fields["last_deploy_at"] is not None


@pytest.mark.asyncio
async def test_set_reserve_fields_rejects_unknown_field(db) -> None:
    async with get_session_factory()() as session:
        await _seed_portfolio(session)
        with pytest.raises(ValueError, match="unknown reserve field"):
            await ReserveRepository(session).set_reserve_fields(
                USER, now=NOW, bogus_field=Decimal("1")
            )


@pytest.mark.asyncio
async def test_mutators_flush_only_so_rollback_discards(db) -> None:
    """A half-finished transfer rolls back cleanly (atomicity foundation for R3)."""
    async with get_session_factory()() as session:
        await _seed_portfolio(session)
        repo = ReserveRepository(session)
        await repo.set_reserve_fields(USER, now=NOW, reserve_cash_usd=Decimal("99"))
        await repo.add_transaction(
            ReserveTransaction(
                user_id=USER, type="sweep", value_usd=Decimal("99"),
                cash_usd_delta=Decimal("99"), created_at=NOW,
            )
        )
        await session.rollback()

    async with get_session_factory()() as session:
        repo = ReserveRepository(session)
        assert (await repo.get_reserve_fields(USER))["reserve_cash_usd"] == Decimal("0")
        assert await repo.list_transactions(USER) == []
