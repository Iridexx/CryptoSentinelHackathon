"""Gamba prezzo del filtro trend-shock BTC.

Le altre tre gambe (ADX, NATR percentile, volume relativo) sono auto-referenziali:
un percentile spara per costruzione una frazione fissa del tempo, e le medie mobili
di ATR e volume si adattano al regime. Nel crollo del 30/08 notte questo si e' visto
in chiaro — con il crollo ancora in corso il NATR era sceso dal 100esimo al 96esimo
percentile, sotto la soglia, perche' la finestra si era "abituata".

Questa gamba misura il movimento in assoluto sulla finestra recente ed e' l'unica
che reagisce entro pochi minuti. I test la isolano confrontando due scenari identici
in tutto tranne che nelle ultime candele 5m: cosi' non dipendono dai valori assoluti
delle altre gambe, solo dal loro essere invariate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.agent.service import AgentService
from backend.app.persistence.runtime_state import set_runtime_value
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.schemas.mobile_agent import AgentMobileSettings
from backend.tests.unit.test_agent_step6 import USER_ID, settings as agent_settings

from backend.app.agent.signals.common.indicators import Candle

BASE = datetime(2026, 8, 30, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path):
    reset_sync_db()
    init_sync_db(f"sqlite:///{tmp_path / 'shock.db'}")
    create_all_sync()
    yield
    reset_sync_db()


def _candles(closes: list[float], minutes: int) -> list[Candle]:
    out = []
    for i, c in enumerate(closes):
        out.append(
            Candle(
                timestamp=BASE + timedelta(minutes=minutes * i),
                open=c,
                high=c * 1.001,
                low=c * 0.999,
                close=c,
                volume=100.0,
            )
        )
    return out


class _Feed:
    """Feed che risponde 15m e 5m; il tratto finale delle 5m e' parametrico."""

    def __init__(self, tail_5m: list[float]) -> None:
        self.tail_5m = tail_5m

    async def fetch(self, *, symbol, interval, limit, market):
        if interval == "15m":
            # Serie leggermente ondulata: le gambe ADX/NATR restano identiche fra
            # gli scenari, che e' tutto quello che serve al confronto.
            closes = [100 + (i % 5) * 0.1 for i in range(126)]
            return _candles(closes, 15)
        head = [100.0] * (55 - len(self.tail_5m))
        return _candles(head + self.tail_5m, 5)


def _service(feed, **overrides) -> AgentService:
    base = dict(
        perp_trend_shock_enabled=True,
        perp_trend_shock_return_enabled=True,
        perp_trend_shock_return_lookback_minutes=30,
        perp_trend_shock_return_threshold_pct=1.5,
    )
    base.update(overrides)
    ms = AgentMobileSettings(**base)
    set_runtime_value(str(USER_ID), "mobile_agent_settings", ms.model_dump_json())
    service = AgentService(
        agent_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace()
    )
    service.price_feed = feed
    return service


async def _evaluate(tail_5m: list[float], **overrides) -> dict:
    service = _service(_Feed(tail_5m), **overrides)
    return await service._btc_trend_shock_filter()


# Ultime 6 candele 5m = finestra di 30 minuti.
FLAT_TAIL = [100.0] * 6
CRASH_TAIL = [99.6, 99.2, 98.8, 98.4, 98.1, 97.8]   # -2.2% in 30 minuti
PUMP_TAIL = [100.4, 100.8, 101.2, 101.6, 101.9, 102.2]


@pytest.mark.asyncio
async def test_fast_selloff_adds_one_to_the_score(db) -> None:
    calm = await _evaluate(FLAT_TAIL)
    crash = await _evaluate(CRASH_TAIL)

    assert calm["return_triggered"] is False
    assert crash["return_triggered"] is True
    assert crash["return_pct"] < -1.5
    # Unica differenza fra i due scenari: le altre gambe sono invariate.
    assert crash["score"] == calm["score"] + 1


@pytest.mark.asyncio
async def test_violent_pump_triggers_too(db) -> None:
    """La gamba misura la violenza, non la direzione: il segno non conta."""
    pump = await _evaluate(PUMP_TAIL)

    assert pump["return_triggered"] is True
    assert pump["return_pct"] > 1.5


@pytest.mark.asyncio
async def test_move_below_threshold_does_not_trigger(db) -> None:
    mild = await _evaluate([99.9, 99.8, 99.7, 99.6, 99.5, 99.4])  # -0.6%

    assert mild["return_triggered"] is False
    assert -1.5 < mild["return_pct"] < 0


@pytest.mark.asyncio
async def test_leg_can_be_disabled(db) -> None:
    off = await _evaluate(CRASH_TAIL, perp_trend_shock_return_enabled=False)

    assert off["return_triggered"] is False
    assert off["return_pct"] is None


@pytest.mark.asyncio
async def test_threshold_is_configurable(db) -> None:
    """Con soglia 3% lo stesso -2.2% non basta piu'."""
    strict = await _evaluate(CRASH_TAIL, perp_trend_shock_return_threshold_pct=3.0)

    assert strict["return_triggered"] is False
