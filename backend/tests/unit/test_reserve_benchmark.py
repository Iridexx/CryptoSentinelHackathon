"""R6b — reserve benchmark on /history + volatility budget in GlobalView (D27/D28)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.dependencies import require_admin_access, require_read_access
from backend.app.api.routes import views as view_routes
from backend.app.api.routes.reserve import router
from backend.app.core.config import get_settings
from backend.app.persistence.database import close_db, get_session, get_session_factory, init_db
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.models.reserve import ReserveSnapshot
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.views import ViewService, _volatility_budget

USER = str(get_settings().default_user_id)
DAY0 = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


class _Row:
    def __init__(self, ts, total, portfolio):
        self.timestamp_utc = ts
        self.total_equity_usd = Decimal(str(total))
        self.total_portfolio_equity_usd = Decimal(str(portfolio))


# ── _volatility_budget (pure) ───────────────────────────────────────────────


def test_volatility_budget_insufficient_data() -> None:
    rows = [_Row(DAY0 + timedelta(days=i), 500, 500) for i in range(3)]
    assert _volatility_budget(rows).status == "insufficient_data"


def test_volatility_budget_reserve_dampens_vol_and_drawdown() -> None:
    trading = [500, 530, 490, 545, 470, 560, 455, 570, 480, 590]   # ±~6%
    portfolio = [500, 512, 498, 518, 492, 522, 490, 526, 500, 532]  # ±~2%
    rows = [
        _Row(DAY0 + timedelta(days=i), trading[i], portfolio[i])
        for i in range(len(trading))
    ]
    vb = _volatility_budget(rows)
    assert vb.status == "ready"
    assert vb.total_daily_vol_pct < vb.trading_daily_vol_pct
    assert vb.total_max_drawdown_pct <= vb.trading_max_drawdown_pct


# ── BTC klines cache (perf) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_btc_1h_klines_caches_and_serves_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    view_routes._BTC_KLINES_CACHE.clear()
    calls = {"n": 0}

    class _Feed:
        async def fetch(self, **kw):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("binance down")
            return [type("C", (), {"close": "60000"})() for _ in range(200)]

    monkeypatch.setattr(
        "backend.app.agent.signals.perp.binance_klines.BinanceKlineFeed", lambda *a, **k: _Feed()
    )
    first = await view_routes._btc_1h_klines(50)
    assert len(first) == 200 and calls["n"] == 1
    # within TTL: cache hit, no second upstream call
    assert await view_routes._btc_1h_klines(50) is first and calls["n"] == 1
    # force expiry -> upstream fails -> stale served, not empty
    key = next(iter(view_routes._BTC_KLINES_CACHE))
    view_routes._BTC_KLINES_CACHE[key] = (0.0, first)
    assert await view_routes._btc_1h_klines(50) is first
    view_routes._BTC_KLINES_CACHE.clear()


# ── GlobalView integration ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    await close_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'b.db'}")
    yield
    await close_db()


@pytest.mark.asyncio
async def test_global_view_includes_volatility_budget(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("500"), initial_equity_usd=Decimal("500")
        )
        for i in range(10):
            session.add(PnlSnapshot(
                user_id=USER, timestamp_utc=DAY0 + timedelta(days=i),
                total_equity_usd=Decimal(500 + (i % 3) * 20),
                total_portfolio_equity_usd=Decimal(500 + (i % 3) * 5),
            ))
        await session.commit()
        view = await ViewService(session).global_view(USER)

    assert view.volatility_budget is not None
    assert view.volatility_budget.status == "ready"


# ── /history benchmark ─────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    await close_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'h.db'}")

    async def _session_override():
        async with get_session_factory()() as session:
            yield session

    async def _fake_btc(rows):
        return {r.timestamp_utc.isoformat(): Decimal("3.5") for r in rows}

    monkeypatch.setattr(view_routes, "_btc_benchmark", _fake_btc)

    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    fastapi_app.dependency_overrides[get_session] = _session_override
    fastapi_app.dependency_overrides[require_read_access] = lambda: None
    fastapi_app.dependency_overrides[require_admin_access] = lambda: None
    yield fastapi_app
    await close_db()


@pytest.mark.asyncio
async def test_history_exposes_benchmark_lines(app) -> None:
    async with get_session_factory()() as session:
        for i in range(4):
            ts = DAY0 + timedelta(hours=i)
            session.add(ReserveSnapshot(
                user_id=USER, timestamp_utc=ts,
                total_value_usd=Decimal(40 + i * 2), cash_usd=Decimal("0"),
                cost_basis_usd=Decimal("40"), pnl_usd=Decimal(i * 2),
            ))
            session.add(PnlSnapshot(
                user_id=USER, timestamp_utc=ts, total_equity_usd=Decimal(500 + i * 10),
            ))
        await session.commit()

    r = TestClient(app).get("/api/v1/agent/reserve/history?range=all")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 4
    last = items[-1]
    assert Decimal(last["reserve_pct"]) == (Decimal("46") / Decimal("40") - 1) * 100  # +15%
    assert last["btc_hold_pct"] == "3.5"
    assert Decimal(last["trading_pct"]) == (Decimal("530") / Decimal("500") - 1) * 100  # +6%
