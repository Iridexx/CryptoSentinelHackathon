"""STEP 6 — Profit Lock Ratchet: validazione schema + funzione pura del ratchet."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.agent.service import _profit_lock_stop
from backend.app.schemas.mobile_agent import AgentMobileSettings

DEFAULT_STEPS = [(0.45, 0.25), (0.70, 0.50), (0.90, 0.70)]


# --------------------------- schema: migrazione modalità ---------------------------

def test_protection_mode_derived_from_trailing_on():
    s = AgentMobileSettings(perp_trailing_enabled=True)
    assert s.perp_protection_mode == "trailing"
    assert s.perp_trailing_enabled is True


def test_protection_mode_derived_from_trailing_off():
    s = AgentMobileSettings(perp_trailing_enabled=False)
    assert s.perp_protection_mode == "off"
    assert s.perp_trailing_enabled is False


def test_profit_lock_mode_forces_trailing_off():
    s = AgentMobileSettings(perp_protection_mode="profit_lock")
    assert s.perp_protection_mode == "profit_lock"
    assert s.perp_trailing_enabled is False


def test_trailing_mode_forces_trailing_on():
    s = AgentMobileSettings(perp_protection_mode="trailing", perp_trailing_enabled=False)
    assert s.perp_trailing_enabled is True


def test_invalid_protection_mode_rejected():
    with pytest.raises(ValueError):
        AgentMobileSettings(perp_protection_mode="banana")


# --------------------------- schema: validazione scalini ---------------------------

def test_default_steps_valid():
    s = AgentMobileSettings()
    assert list(s.perp_profit_lock_steps) == [(0.45, 0.25), (0.70, 0.50), (0.90, 0.70)]


@pytest.mark.parametrize("bad", [
    [(0.6, 0.7)],
    [(0.8, 0.25), (0.6, 0.5)],
    [(0.6, 0.5), (0.8, 0.4)],
    [(0.0, 0.25)],
    [(0.6, 1.0)],
    [(0.6,)],
])
def test_bad_steps_rejected(bad):
    with pytest.raises(ValueError):
        AgentMobileSettings(perp_profit_lock_steps=bad)


# --------------------------- funzione pura del ratchet -----------------------------
# Il ratchet misura il progresso nel tratto TP1→TP2.
# Esempio: TP1=104, TP2=110 → span=6.
# extreme=104 → progress=0% (appena raggiunto TP1), extreme=110 → progress=100%.

def D(x):
    return Decimal(str(x))


TP1_LONG = D(104)
TP2_LONG = D(110)
# span = 6


def test_no_step_before_threshold_returns_none():
    # extreme=106.5 → progress = 2.5/6 ≈ 0.417 → sotto soglia 0.45
    assert _profit_lock_stop(TP1_LONG, TP2_LONG, D("106.5"), DEFAULT_STEPS, True) is None


def test_tp1_none_returns_none():
    assert _profit_lock_stop(None, D(110), D(108), DEFAULT_STEPS, True) is None


def test_long_steps_and_levels():
    # progress 45%: extreme = 104 + 0.45*6 = 106.7 → lock 25% → stop = 104 + 0.25*6 = 105.5
    stop, prog, lock = _profit_lock_stop(TP1_LONG, TP2_LONG, D("106.7"), DEFAULT_STEPS, True)
    assert prog == D("0.45") and lock == D("0.25") and stop == D("105.5")
    # progress 70%: extreme = 104 + 0.7*6 = 108.2 → lock 50% → stop = 104 + 0.5*6 = 107
    stop, prog, lock = _profit_lock_stop(TP1_LONG, TP2_LONG, D("108.2"), DEFAULT_STEPS, True)
    assert prog == D("0.7") and lock == D("0.5") and stop == D(107)
    # progress 90%: extreme = 104 + 0.9*6 = 109.4 → lock 70% → stop = 104 + 0.7*6 = 108.2
    stop, prog, lock = _profit_lock_stop(TP1_LONG, TP2_LONG, D("109.4"), DEFAULT_STEPS, True)
    assert prog == D("0.9") and lock == D("0.70") and stop == D("108.2")


def test_reversal_at_80pct_locks_50():
    # extreme = 104 + 0.8*6 = 108.8 → progress 0.80 → lock 0.50 → stop = 107
    stop, prog, lock = _profit_lock_stop(TP1_LONG, TP2_LONG, D("108.8"), DEFAULT_STEPS, True)
    assert prog == D("0.8") and lock == D("0.5") and stop == D(107)


def test_short_symmetric():
    # Short: TP1=96, TP2=90 → span=6
    # extreme=93.3 → progress = (96-93.3)/6 = 0.45 → lock 25% → stop = 96 - 0.25*6 = 94.5
    stop, prog, lock = _profit_lock_stop(D(96), D(90), D("93.3"), DEFAULT_STEPS, False)
    assert prog == D("0.45") and lock == D("0.25") and stop == D("94.5")


def test_progress_clamped_and_span_guard():
    # extreme oltre TP2: clamped a 1.0
    stop, prog, lock = _profit_lock_stop(TP1_LONG, TP2_LONG, D(120), DEFAULT_STEPS, True)
    assert prog == D("1") and lock == D("0.70")
    # span = 0 (tp1 == tp2) → None
    assert _profit_lock_stop(D(110), D(110), D(115), DEFAULT_STEPS, True) is None


def test_monotone_and_below_tp2():
    prev = D(0)
    for ex in ["106.7", "108", "108.2", "109.4", "109.9"]:
        res = _profit_lock_stop(TP1_LONG, TP2_LONG, D(ex), DEFAULT_STEPS, True)
        if res is None:
            continue
        stop, _, _ = res
        assert stop >= prev
        assert stop < TP2_LONG
        prev = stop
