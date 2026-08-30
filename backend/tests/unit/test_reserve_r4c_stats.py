"""R4c / D31 — exposure & daily-loss on tradable equity, portfolio-equity snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.agent.service import AgentService
from backend.app.core.config import Settings, load_yaml_settings
from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.positions import SpotPosition
from backend.app.persistence.models.trades import SpotTrade
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.reserve import ReserveRepository
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)

USER = "00000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'a.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def _settings() -> Settings:
    return Settings(**{**load_yaml_settings(), "default_user_id": UUID(USER)})


def _service() -> AgentService:
    return AgentService(_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())


def _open_spot(entry: str, size: str) -> SpotPosition:
    return SpotPosition(
        position_id="p1", user_id=USER, asset="BTC", size=Decimal(size),
        entry_price=Decimal(entry), current_price=Decimal(entry),
        pnl_unrealized=Decimal("0"), status="open", opened_at=NOW, updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_exposure_and_daily_loss_measured_on_tradable_equity(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("500"), initial_equity_usd=Decimal("500")
        )
        # A losing trade today: realized −50 → total 450.
        session.add(SpotTrade(
            trade_id="l1", user_id=USER, asset="DOGE", side="sell", amount=Decimal("1"),
            price=Decimal("1"), amount_quote=Decimal("1"), status="closed",
            timestamp_utc=NOW, pnl_usd=Decimal("-50"),
        ))
        await ReserveRepository(session).set_reserve_fields(
            USER, now=NOW, reserve_transferred_net_usd=Decimal("100"),
        )
        await session.commit()

        await _service()._update_portfolio_state(session, [_open_spot("100", "1")], [], NOW)

        pf = await PnlRepository(session).get_portfolio(USER)

    # tradable = 450 − 100 = 350
    # exposure = 100 / 350 * 100 = 28.57  (not 100/450 = 22.22)
    assert pf.exposure_pct == Decimal("28.57")
    # daily loss = −50 / 350 * 100 = −14.29  (not −50/450 = −11.11)
    assert pf.daily_loss_limit_used_pct == Decimal("-14.29")


@pytest.mark.asyncio
async def test_stats_unchanged_without_a_reserve(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("500"), initial_equity_usd=Decimal("500")
        )
        session.add(SpotTrade(
            trade_id="l1", user_id=USER, asset="DOGE", side="sell", amount=Decimal("1"),
            price=Decimal("1"), amount_quote=Decimal("1"), status="closed",
            timestamp_utc=NOW, pnl_usd=Decimal("-50"),
        ))
        await session.commit()

        await _service()._update_portfolio_state(session, [_open_spot("100", "1")], [], NOW)
        pf = await PnlRepository(session).get_portfolio(USER)

    assert pf.exposure_pct == Decimal("22.22")           # 100 / 450
    assert pf.daily_loss_limit_used_pct == Decimal("-11.11")  # -50 / 450


@pytest.mark.asyncio
async def test_hourly_snapshot_stores_total_portfolio_equity(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        repo = ReserveRepository(session)
        await repo.upsert_holding(USER, "BTC", quantity=Decimal("0.0005"), avg_cost_usd=Decimal("60000"), now=NOW)
        await repo.set_reserve_fields(
            USER, now=NOW, reserve_cash_usd=Decimal("5"), reserve_transferred_net_usd=Decimal("35"),
        )
        await repo.commit()

        await _service()._snapshot_portfolio_hourly(session, NOW)
        snap = (await PnlRepository(session).recent_for_user(USER, limit=1))[0]

    # tradable = 600 − 35 = 565 ; reserve at cost = 5 + 0.0005*60000 = 35 ; total = 600
    assert snap.total_portfolio_equity_usd == Decimal("600.00000000")
