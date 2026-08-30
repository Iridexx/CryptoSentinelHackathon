"""R5 — /api/v1/agent/reserve routes."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.dependencies import require_admin_access, require_read_access
from backend.app.api.routes.reserve import router
from backend.app.core.config import get_settings
from backend.app.domain.reserve import pricing
from backend.app.persistence.database import close_db, get_session, get_session_factory, init_db
from backend.app.persistence.models.trades import SpotTrade
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db

USER = str(get_settings().default_user_id)
PRICES = {
    "BTC": Decimal("60000"), "ETH": Decimal("3000"), "BNB": Decimal("600"),
    "SOL": Decimal("150"), "TRX": Decimal("0.30"),
}


@pytest_asyncio.fixture
async def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    await close_db()
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'r.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'r.db'}")
    create_all_sync()

    async def _session_override():
        async with get_session_factory()() as session:
            yield session

    async def _fake_prices(settings, *, feed=None):
        return dict(PRICES)

    monkeypatch.setattr(pricing, "fetch_reserve_prices", _fake_prices)

    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    fastapi_app.dependency_overrides[get_session] = _session_override
    fastapi_app.dependency_overrides[require_read_access] = lambda: None
    fastapi_app.dependency_overrides[require_admin_access] = lambda: None
    yield fastapi_app
    await close_db()
    reset_sync_db()


async def _seed(*, profit="0") -> None:
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
async def test_get_reserve_empty(app) -> None:
    await _seed()
    r = TestClient(app).get("/api/v1/agent/reserve")
    assert r.status_code == 200
    body = r.json()
    assert body["value_usd"] == "0.00000000" or Decimal(body["value_usd"]) == 0
    assert body["frozen"] is False
    assert len(body["holdings"]) == 5


@pytest.mark.asyncio
async def test_transfer_in_without_profit_rejected(app) -> None:
    await _seed(profit="0")
    r = TestClient(app).post("/api/v1/agent/reserve/transfer", json={"amount_usd": 40, "direction": "in"})
    assert r.status_code == 400
    assert r.json()["detail"] == "no_profit_available"


@pytest.mark.asyncio
async def test_transfer_in_with_profit_funds_the_reserve(app) -> None:
    await _seed(profit="200")
    c = TestClient(app)
    r = c.post("/api/v1/agent/reserve/transfer", json={"amount_usd": 40, "direction": "in"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["cost_basis_usd"]) == Decimal("40")
    assert Decimal(body["value_usd"]) > Decimal("35")  # deployed minus fees
    # BTC/ETH/BNB bought, SOL/TRX deferred
    bought = {h["asset"] for h in body["holdings"] if Decimal(h["quantity"]) > 0}
    assert {"BTC", "ETH", "BNB"} <= bought


@pytest.mark.asyncio
async def test_settings_roundtrip_and_source(app) -> None:
    c = TestClient(app)
    default = c.get("/api/v1/agent/reserve/settings").json()
    assert default["source"] == "default"
    assert default["settings"]["sweep_pct"] == 20.0

    payload = dict(default["settings"])
    payload["sweep_pct"] = 35.0
    saved = c.post("/api/v1/agent/reserve/settings", json=payload)
    assert saved.status_code == 200
    assert saved.json()["source"] == "persisted"
    assert c.get("/api/v1/agent/reserve/settings").json()["settings"]["sweep_pct"] == 35.0


@pytest.mark.asyncio
async def test_disabling_settings_freezes_reserve_with_holdings(app) -> None:
    await _seed(profit="200")
    c = TestClient(app)
    c.post("/api/v1/agent/reserve/transfer", json={"amount_usd": 40, "direction": "in"})

    s = c.get("/api/v1/agent/reserve/settings").json()["settings"]
    s["enabled"] = False
    c.post("/api/v1/agent/reserve/settings", json=s)

    assert c.get("/api/v1/agent/reserve").json()["frozen"] is True


@pytest.mark.asyncio
async def test_target_weights_validation(app) -> None:
    c = TestClient(app)
    ok = c.post("/api/v1/agent/reserve/target-weights",
                json={"weights": {"BTC": 50, "ETH": 30, "BNB": 20, "SOL": 0, "TRX": 0}})
    assert ok.status_code == 200
    bad = c.post("/api/v1/agent/reserve/target-weights",
                 json={"weights": {"BTC": 70, "ETH": 20}})
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_transactions_endpoint(app) -> None:
    await _seed(profit="200")
    c = TestClient(app)
    c.post("/api/v1/agent/reserve/transfer", json={"amount_usd": 40, "direction": "in"})
    r = c.get("/api/v1/agent/reserve/transactions")
    assert r.status_code == 200
    types = {t["type"] for t in r.json()["items"]}
    assert "transfer_in" in types and "deploy_buy" in types


@pytest.mark.asyncio
async def test_deploy_and_rebalance_and_history(app) -> None:
    await _seed(profit="200")
    c = TestClient(app)
    c.post("/api/v1/agent/reserve/transfer", json={"amount_usd": 40, "direction": "in"})

    assert c.post("/api/v1/agent/reserve/deploy").status_code == 200
    reb = c.post("/api/v1/agent/reserve/rebalance", json={"dry_run": True})
    assert reb.status_code == 200 and reb.json()["dry_run"] is True

    hist = c.get("/api/v1/agent/reserve/history?range=all")
    assert hist.status_code == 200 and "items" in hist.json()
