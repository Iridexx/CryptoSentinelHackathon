"""R4b — reset/archive includes the reserve tables and clears its counters."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.persistence import database
from backend.app.persistence.archive import archive_dry_run_records, reset_all_data
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.reserve import (
    ReserveHolding,
    ReserveSnapshot,
    ReserveTransaction,
)
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.reserve import ReserveRepository

USER = "00000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}")
    yield
    await close_db()


async def _seed_reserve(session) -> None:
    repo = ReserveRepository(session)
    await repo.upsert_holding(USER, "BTC", quantity=Decimal("0.001"), avg_cost_usd=Decimal("60000"), now=NOW)
    await repo.add_transaction(ReserveTransaction(
        user_id=USER, type="sweep", value_usd=Decimal("20"), cash_usd_delta=Decimal("20"), created_at=NOW,
    ))
    await repo.save_snapshot(ReserveSnapshot(
        user_id=USER, timestamp_utc=NOW, total_value_usd=Decimal("60"),
        cost_basis_usd=Decimal("60"), pnl_usd=Decimal("0"),
    ))
    await repo.set_reserve_fields(
        USER, now=NOW, reserve_cash_usd=Decimal("5"),
        reserve_transferred_net_usd=Decimal("60"), reserve_frozen=True,
    )
    await repo.commit()


def _sel(model):
    from sqlalchemy import select

    return select(model).where(model.user_id == USER)


async def _counts(session) -> tuple[int, int, int]:
    holdings = len((await session.execute(_sel(ReserveHolding))).scalars().all())
    txns = len((await session.execute(_sel(ReserveTransaction))).scalars().all())
    snaps = len((await session.execute(_sel(ReserveSnapshot))).scalars().all())
    return holdings, txns, snaps


# ── archive_dry_run_records ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_archive_dry_run_archives_and_clears_reserve(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        await _seed_reserve(session)

        archive = await archive_dry_run_records(
            session, user_id=USER, delete_live=True,
            reset_portfolio_capital_usd=Decimal("500"),
        )

        assert await _counts(session) == (0, 0, 0)
        fields = await ReserveRepository(session).get_reserve_fields(USER)
        assert fields["reserve_cash_usd"] == Decimal("0")
        assert fields["reserve_transferred_net_usd"] == Decimal("0")
        assert fields["reserve_frozen"] is False

    payload = json.loads(archive.payload_json)
    assert len(payload["reserve_holdings"]) == 1
    assert len(payload["reserve_transactions"]) == 1
    assert len(payload["reserve_snapshots"]) == 1


@pytest.mark.asyncio
async def test_archive_clears_reserve_even_without_capital_reset(db) -> None:
    """Deleting the reserve rows must always zero the counters, or tradable_equity breaks."""
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        await _seed_reserve(session)

        await archive_dry_run_records(
            session, user_id=USER, delete_live=True, reset_portfolio_capital_usd=None,
        )

        assert await _counts(session) == (0, 0, 0)
        fields = await ReserveRepository(session).get_reserve_fields(USER)
        assert fields["reserve_transferred_net_usd"] == Decimal("0")


# ── reset_all_data ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_all_data_wipes_reserve_and_backs_it_up(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        await _seed_reserve(session)

        result = await reset_all_data(
            session, user_id=USER, backup_label="snap",
            reset_portfolio_capital_usd=Decimal("500"),
        )

        assert await _counts(session) == (0, 0, 0)
        pf = await PnlRepository(session).get_portfolio(USER)
        assert pf.reserve_transferred_net_usd == Decimal("0")
        assert pf.reserve_cash_usd == Decimal("0")
        assert pf.reserve_frozen is False

    assert result["deleted"]["reserve_holdings"] == 1
    assert result["deleted"]["reserve_transactions"] == 1
    assert result["deleted"]["reserve_snapshots"] == 1


@pytest.mark.asyncio
async def test_reset_all_data_without_backup_still_deletes_reserve(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        await _seed_reserve(session)
        result = await reset_all_data(session, user_id=USER, backup_label=None)
        assert await _counts(session) == (0, 0, 0)
    assert result["archived_run_id"] is None
    assert result["deleted"]["reserve_holdings"] == 1
