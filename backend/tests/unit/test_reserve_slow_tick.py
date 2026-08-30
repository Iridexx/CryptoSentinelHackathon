"""R6 — the slow tick maintains the "Bank" reserve (sweep/deploy/rebalance/snapshot)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.agent.risk import KillSwitchState
from backend.app.agent.service import AgentService
from backend.app.core.config import Settings, load_yaml_settings
from backend.app.domain.reserve import pricing
from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.trades import SpotTrade
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.reserve import ReserveRepository
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db

USER = "00000000-0000-0000-0000-000000000001"
T0 = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
PRICES = {"BTC": Decimal("60000"), "ETH": Decimal("3000"), "BNB": Decimal("600"),
          "SOL": Decimal("150"), "TRX": Decimal("0.30")}


@pytest.fixture
async def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database._engine = None
    database._session_factory = None
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'a.db'}")
    create_all_sync()

    async def _fake_prices(settings, *, feed=None):
        return dict(PRICES)

    monkeypatch.setattr(pricing, "fetch_reserve_prices", _fake_prices)
    yield
    await close_db()
    reset_sync_db()


def _settings() -> Settings:
    return Settings(**{**load_yaml_settings(), "default_user_id": UUID(USER)})


def _service() -> AgentService:
    return AgentService(_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())


async def _seed(profit="0") -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("500"), initial_equity_usd=Decimal("500")
        )
        if Decimal(profit) != 0:
            session.add(SpotTrade(
                trade_id=f"p{profit}", user_id=USER, asset="DOGE", side="sell",
                amount=Decimal("1"), price=Decimal("1"), amount_quote=Decimal("1"),
                status="closed", timestamp_utc=datetime(2026, 8, 29, tzinfo=UTC),
                pnl_usd=Decimal(profit),
            ))
        await session.commit()


@pytest.mark.asyncio
async def test_reserve_tick_sweeps_deploys_and_snapshots(db) -> None:
    await _seed(profit="200")
    async with get_session_factory()() as session:
        await _service()._reserve_tick(session, T0)

        fields = await ReserveRepository(session).get_reserve_fields(USER)
        holdings = {h.asset for h in await ReserveRepository(session).list_holdings(USER)}
        snaps = await ReserveRepository(session).recent_snapshots(USER, limit=5)

    assert fields["reserve_transferred_net_usd"] == Decimal("40")  # 20% of 200
    assert {"BTC", "ETH", "BNB"} <= holdings                       # deployed
    assert len(snaps) == 1 and snaps[0].total_value_usd > 0


@pytest.mark.asyncio
async def test_reserve_tick_noop_when_disabled(db) -> None:
    await _seed(profit="200")
    svc = _service()
    svc.settings.reserve.enabled = False
    async with get_session_factory()() as session:
        await svc._reserve_tick(session, T0)
        assert await ReserveRepository(session).recent_snapshots(USER, limit=1) == []


@pytest.mark.asyncio
async def test_reserve_tick_hard_stop_skips_actions_but_snapshots(db) -> None:
    await _seed(profit="200")
    # Pre-fund the reserve so there is something to snapshot.
    async with get_session_factory()() as session:
        repo = ReserveRepository(session)
        await repo.upsert_holding(USER, "BTC", quantity=Decimal("0.001"), avg_cost_usd=Decimal("60000"), now=T0)
        await repo.set_reserve_fields(USER, now=T0, reserve_transferred_net_usd=Decimal("60"))
        await repo.commit()

    svc = _service()
    svc.risk.set_kill_switch(KillSwitchState.HARD_STOP)
    async with get_session_factory()() as session:
        await svc._reserve_tick(session, T0)
        fields = await ReserveRepository(session).get_reserve_fields(USER)
        snaps = await ReserveRepository(session).recent_snapshots(USER, limit=1)

    assert fields["reserve_transferred_net_usd"] == Decimal("60")  # no sweep
    assert len(snaps) == 1                                          # still snapshotted


@pytest.mark.asyncio
async def test_reserve_snapshot_dedup_by_interval(db) -> None:
    await _seed(profit="200")
    svc = _service()
    async with get_session_factory()() as session:
        await svc._reserve_tick(session, T0)
        await svc._reserve_tick(session, T0 + timedelta(minutes=10))   # < 60min → no new snap
        n_after_10 = len(await ReserveRepository(session).recent_snapshots(USER, limit=10))
        await svc._reserve_tick(session, T0 + timedelta(minutes=70))   # ≥ 60min → new snap
        n_after_70 = len(await ReserveRepository(session).recent_snapshots(USER, limit=10))

    assert n_after_10 == 1
    assert n_after_70 == 2


@pytest.mark.asyncio
async def test_hourly_portfolio_snapshot_uses_reserve_mtm(db) -> None:
    await _seed(profit="200")
    svc = _service()
    async with get_session_factory()() as session:
        await svc._reserve_tick(session, T0)          # writes a ReserveSnapshot
        await svc._snapshot_portfolio_hourly(session, T0)
        pnl = (await PnlRepository(session).recent_for_user(USER, limit=1))[0]
        r_snap = (await ReserveRepository(session).recent_snapshots(USER, limit=1))[0]
        pf = await PnlRepository(session).get_portfolio(USER)

    # total_portfolio = (total_equity − transferred_net) + reserve_snapshot_value
    expected = Decimal(str(pf.total_equity_usd)) - Decimal("40") + Decimal(str(r_snap.total_value_usd))
    assert abs(Decimal(str(pnl.total_portfolio_equity_usd)) - expected) < Decimal("0.01")
