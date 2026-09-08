"""La curva PnL del grafico equity e' rebasata sull'inizio della finestra scelta,
come il benchmark BTC. Cambiare 24h / 7g / Tutto deve spostare ENTRAMBE le
percentuali (PnL e BTC), non solo quella di BTC — bug scheda Agente/Global.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.api.routes import views as views_route
from backend.app.core.config import get_settings
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db

USER = str(get_settings().default_user_id)


@pytest.fixture()
async def db(tmp_path: Path):
    await close_db()
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'eq.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'eq.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


async def _call(rng: str) -> dict:
    async with get_session_factory()() as session:
        return await views_route.equity_curve(
            session=session, settings=get_settings(), _=None, market="global", range=rng,
        )


@pytest.mark.asyncio
async def test_pnl_curve_is_window_relative(db, monkeypatch) -> None:
    async def _no_benchmark(_snapshots):
        return {}

    monkeypatch.setattr(views_route, "_btc_benchmark", _no_benchmark)

    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("1080"), initial_equity_usd=Decimal("1000"),
        )
        # 8 giorni di snapshot orari. Equity: 1000 all'inizio, 1100 un giorno fa,
        # 1080 adesso. -> "tutto" = +8%, "24h" = -1.82%.
        for h in range(8 * 24, -1, -1):
            ts = now - timedelta(hours=h)
            if h >= 24:
                eq = Decimal("1000") + (Decimal(str(8 * 24 - h)) / Decimal(str(8 * 24 - 24))) * Decimal("100")
            else:
                eq = Decimal("1100") - (Decimal(str(24 - h)) / Decimal("24")) * Decimal("20")
            session.add(PnlSnapshot(
                user_id=USER, timestamp_utc=ts, total_equity_usd=eq,
                spot_equity_usd=Decimal("0"), perp_equity_usd=eq,
            ))
        await session.commit()

    all_c = await _call("all")
    d1_c = await _call("24h")

    # Primo punto di ogni finestra parte da ~0%.
    assert abs(float(all_c["items"][0]["pnl_pct"])) < 0.01
    assert abs(float(d1_c["items"][0]["pnl_pct"])) < 0.01

    # L'ultimo punto dipende dalla finestra: +8% su tutto, negativo sulle 24h.
    assert float(all_c["items"][-1]["pnl_pct"]) == pytest.approx(8.0, abs=0.2)
    assert float(d1_c["items"][-1]["pnl_pct"]) == pytest.approx(-1.82, abs=0.2)
    assert float(all_c["items"][-1]["pnl_pct"]) != float(d1_c["items"][-1]["pnl_pct"])
