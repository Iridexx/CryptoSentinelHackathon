"""Gate 'movimento reale' del filtro trend-shock BTC.

NATR percentile e volume relativo sono gambe correlate: una singola candela
violenta (un flush di liquidazioni) le fa scattare entrambe, cioe' score 2 su un
evento solo, senza che BTC si sia davvero mosso. E' esattamente il falso shock
dell'8/9/2026 (score 2 con ADX 28 e return -0,97%), che ha fatto partire un flip
poi chiuso in perdita su LINK e BCH.

Con `perp_trend_shock_require_real_move` il BLOCKED pretende, oltre a score>=2,
almeno una gamba non auto-referenziale: ADX in trend oppure return oltre soglia.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.agent.service import AgentService
from backend.app.agent.signals.common.indicators import Candle
from backend.app.persistence.runtime_state import set_runtime_value
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.schemas.mobile_agent import AgentMobileSettings
from backend.tests.unit.test_agent_step6 import USER_ID, settings as agent_settings

BASE = datetime(2026, 9, 8, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path):
    reset_sync_db()
    init_sync_db(f"sqlite:///{tmp_path / 'shock.db'}")
    create_all_sync()
    yield
    reset_sync_db()


class _SpikeFeed:
    """BTC calmo e senza trend, ma con un'ultima candela 5m di volume enorme e le
    ultime 15m molto piu' volatili: NATR percentile e volume sparano, ADX e return no."""

    async def fetch(self, *, symbol, interval, limit, market):
        if interval == "15m":
            out = []
            for i in range(126):
                close = 100.0 + (i % 2) * 0.05          # oscilla, nessun trend
                wide = i >= 118                          # ultime candele: range largo
                span = 4.0 if wide else 0.1
                out.append(Candle(
                    timestamp=BASE + timedelta(minutes=15 * i),
                    open=close, high=close + span, low=close - span,
                    close=close, volume=100.0,
                ))
            return out
        # 5m: prezzo piatto (return ~0), volume normale tranne l'ultima CHIUSA.
        out = []
        for i in range(55):
            out.append(Candle(
                timestamp=BASE + timedelta(minutes=5 * i),
                open=100.0, high=100.05, low=99.95, close=100.0,
                volume=100.0 if i != 53 else 8000.0,
            ))
        return out


def _service(**overrides) -> AgentService:
    base = dict(
        perp_trend_shock_enabled=True,
        perp_trend_shock_adx_threshold=60.0,     # ADX non deve mai scattare qui
        perp_trend_shock_natr_percentile=95.0,
        perp_trend_shock_volume_threshold=2.0,
        perp_trend_shock_return_enabled=True,
        perp_trend_shock_return_threshold_pct=1.5,
    )
    base.update(overrides)
    ms = AgentMobileSettings(**base)
    set_runtime_value(str(USER_ID), "mobile_agent_settings", ms.model_dump_json())
    service = AgentService(
        agent_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace()
    )
    service.price_feed = _SpikeFeed()
    return service


@pytest.mark.asyncio
async def test_pure_spike_does_not_block_by_default(db) -> None:
    res = await _service()._btc_trend_shock_filter()

    assert res["natr_triggered"] is True
    assert res["vol_triggered"] is True
    assert res["adx_triggered"] is False
    assert res["return_triggered"] is False
    assert res["score"] >= 2
    assert res["real_move"] is False
    assert res["state"] != "BLOCKED", "spike di sola volatilita'/volume: niente shock"


@pytest.mark.asyncio
async def test_pure_spike_blocks_when_gate_disabled(db) -> None:
    res = await _service(perp_trend_shock_require_real_move=False)._btc_trend_shock_filter()

    assert res["score"] >= 2
    assert res["state"] == "BLOCKED", "col gate disattivato torna il comportamento storico"
