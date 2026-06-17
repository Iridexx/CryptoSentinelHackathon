"""Step 5 persistence layer tests: DB, repositories, migration, backup, views."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.persistence import database
from backend.app.persistence.backup import backup_db
from backend.app.persistence.database import check_db, close_db, get_session_factory, init_db
from backend.app.persistence.migration import migrate_json_to_db
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
from backend.app.persistence.repositories.decisions import AgentDecisionRepository
from backend.app.persistence.repositories.device_tokens import DeviceTokenRepository
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.positions import (
    PerpPositionRepository,
    SpotPositionRepository,
)
from backend.app.persistence.repositories.trades import PerpTradeRepository, SpotTradeRepository
from backend.app.persistence.repositories.x402_budget import X402BudgetRepository
from backend.app.persistence.views import ViewService

USER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
async def db(tmp_path: Path):
    # Reset module globals so each test gets a clean engine.
    database._engine = None
    database._session_factory = None
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    await init_db(url)
    yield url
    await close_db()


@pytest.mark.asyncio
async def test_check_db_reports_connected_with_latency(db) -> None:
    health = await check_db()
    assert health["connected"] is True
    assert "latency_ms" in health


@pytest.mark.asyncio
async def test_check_db_reports_disconnected_when_uninitialised() -> None:
    database._engine = None
    database._session_factory = None
    health = await check_db()
    assert health["connected"] is False


@pytest.mark.asyncio
async def test_json_migration_is_idempotent(db, tmp_path: Path) -> None:
    tokens_file = tmp_path / "fcm_tokens.json"
    tokens_file.write_text(
        json.dumps(
            {
                "tokens": [
                    {
                        "token_id": "abc123",
                        "token": "raw-token",
                        "user_id": USER,
                        "platform": "android",
                        "device_id": None,
                        "app_version": "1.0",
                        "locale": "it",
                        "created_at": "2026-06-15T10:00:00+00:00",
                        "updated_at": "2026-06-15T10:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    alerts_file = tmp_path / "alerts.json"
    alerts_file.write_text(
        json.dumps({"config": {"price_alerts": []}, "state": {"triggered_keys": ["x"]}}),
        encoding="utf-8",
    )

    factory = get_session_factory()
    async with factory() as session:
        await migrate_json_to_db(
            session, fcm_tokens_path=str(tokens_file), alerts_path=str(alerts_file)
        )
    # Second run must not duplicate.
    async with factory() as session:
        await migrate_json_to_db(
            session, fcm_tokens_path=str(tokens_file), alerts_path=str(alerts_file)
        )

    async with factory() as session:
        repo = DeviceTokenRepository(session)
        assert await repo.count() == 1
        assert await repo.tokens_for_user(USER) == ["raw-token"]


@pytest.mark.asyncio
async def test_x402_budget_persists_across_sessions(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = X402BudgetRepository(session)
        assert await repo.load_today(USER) == Decimal("0")
        await repo.save(USER, Decimal("0.20"))
    async with factory() as session:
        repo = X402BudgetRepository(session)
        assert await repo.load_today(USER) == Decimal("0.20")


@pytest.mark.asyncio
async def test_spot_trade_repo_save_and_list(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = SpotTradeRepository(session)
        await repo.save(
            SpotTrade(
                trade_id="t1",
                user_id=USER,
                asset="BNB",
                side="buy",
                amount=Decimal("1.5"),
                price=Decimal("600"),
                amount_quote=Decimal("900"),
                status="confirmed",
                timestamp_utc=datetime.now(UTC),
                block_timestamp_utc=datetime.now(UTC),
            )
        )
        trades = await repo.list_for_user(USER)
        assert len(trades) == 1
        assert trades[0].asset == "BNB"
        # UTC and on-chain timestamps are stored separately.
        assert trades[0].timestamp_utc is not None
        assert trades[0].block_timestamp_utc is not None


@pytest.mark.asyncio
async def test_perp_position_carries_leverage_and_liquidation(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = PerpPositionRepository(session)
        now = datetime.now(UTC)
        await repo.save(
            PerpPosition(
                position_id="p1",
                user_id=USER,
                asset="ETH",
                side="long",
                size=Decimal("2"),
                entry_price=Decimal("3000"),
                current_price=Decimal("3050"),
                leverage=3,
                liquidation_price=Decimal("2100"),
                funding_rate=Decimal("0.0001"),
                opened_at=now,
                updated_at=now,
            )
        )
        positions = await repo.open_for_user(USER)
        assert positions[0].leverage == 3
        assert positions[0].liquidation_price == Decimal("2100")


@pytest.mark.asyncio
async def test_portfolio_upsert_and_snapshot(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = PnlRepository(session)
        await repo.upsert_portfolio(
            USER,
            total_equity_usd=Decimal("1000"),
            initial_equity_usd=Decimal("1000"),
            peak_equity_usd=Decimal("1000"),
        )
        await repo.upsert_portfolio(
            USER,
            total_equity_usd=Decimal("1100"),
            drawdown_pct=Decimal("-2.0"),
        )
        portfolio = await repo.get_portfolio(USER)
        assert portfolio.total_equity_usd == Decimal("1100")
        assert portfolio.initial_equity_usd == Decimal("1000")

        await repo.save_snapshot(
            PnlSnapshot(
                user_id=USER,
                timestamp_utc=datetime.now(UTC),
                total_equity_usd=Decimal("1100"),
                drawdown_pct=Decimal("-2.0"),
            )
        )
        snaps = await repo.recent_for_user(USER)
        assert len(snaps) == 1


@pytest.mark.asyncio
async def test_decision_repo_records_reasoning(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = AgentDecisionRepository(session)
        await repo.save(
            AgentDecision(
                decision_id="d1",
                user_id=USER,
                timestamp_utc=datetime.now(UTC),
                asset="BNB",
                market="spot",
                action="enter",
                confidence=Decimal("0.82"),
                reasoning="VWAP reclaim with volume spike",
            )
        )
        decisions = await repo.recent_for_user(USER)
        assert decisions[0].action == "enter"
        assert "VWAP" in decisions[0].reasoning


@pytest.mark.asyncio
async def test_global_view_assembles_from_portfolio(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        pnl = PnlRepository(session)
        await pnl.upsert_portfolio(
            USER,
            total_equity_usd=Decimal("1100"),
            initial_equity_usd=Decimal("1000"),
            peak_equity_usd=Decimal("1150"),
            drawdown_pct=Decimal("-4.3"),
            max_drawdown_pct=Decimal("-6.0"),
            exposure_pct=Decimal("12.0"),
            agent_status="running",
            trades_today=2,
        )
    async with factory() as session:
        view = await ViewService(session, drawdown_cap_pct=-15.0).global_view(USER)
        assert view.total_equity_usd == Decimal("1100")
        assert view.pnl_total_usd == Decimal("100")
        assert view.pnl_total_pct == 10.0
        assert view.drawdown_cap_pct == -15.0
        assert view.agent_status == "running"


@pytest.mark.asyncio
async def test_spot_and_perp_views_return_open_positions(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await SpotPositionRepository(session).save(
            SpotPosition(
                position_id="sp1",
                user_id=USER,
                asset="BNB",
                size=Decimal("1"),
                entry_price=Decimal("600"),
                current_price=Decimal("620"),
                pnl_unrealized=Decimal("20"),
                opened_at=now,
                updated_at=now,
            )
        )
    async with factory() as session:
        spot = await ViewService(session).spot_view(USER)
        assert len(spot.open_positions) == 1
        assert spot.unrealized_pnl_usd == Decimal("20")
        perp = await ViewService(session).perp_view(USER)
        assert perp.open_positions == []


def test_backup_creates_timestamped_copy_and_prunes(tmp_path: Path) -> None:
    src = tmp_path / "local.db"
    src.write_bytes(b"SQLite format 3\x00stub")
    url = f"sqlite+aiosqlite:///{src}"
    backup_dir = tmp_path / "backups"

    created = backup_db(url, backup_dir, retention_days=7)
    assert created is not None
    assert created.exists()
    assert created.parent == backup_dir

    # An old backup gets pruned.
    old = backup_dir / "local_20000101T000000Z.db"
    old.write_bytes(b"old")
    import os

    old_time = datetime.now(UTC).timestamp() - 30 * 86_400
    os.utime(old, (old_time, old_time))
    backup_db(url, backup_dir, retention_days=7)
    assert not old.exists()


def test_backup_returns_none_for_missing_db(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'does_not_exist.db'}"
    assert backup_db(url, tmp_path / "backups") is None
