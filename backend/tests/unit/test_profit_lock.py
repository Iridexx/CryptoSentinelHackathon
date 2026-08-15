"""STEP 6 — Profit Lock Ratchet: validazione schema + funzione pura del ratchet."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.agent.service import _profit_lock_stop
from backend.app.schemas.mobile_agent import AgentMobileSettings

DEFAULT_STEPS = [(0.60, 0.25), (0.80, 0.50), (0.95, 0.75)]


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
    assert list(s.perp_profit_lock_steps) == [(0.60, 0.25), (0.80, 0.50), (0.95, 0.75)]


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

def D(x):
    return Decimal(str(x))


def test_no_step_before_threshold_returns_none():
    assert _profit_lock_stop(D(100), D(110), D(105), DEFAULT_STEPS, True) is None


def test_long_steps_and_levels():
    stop, prog, lock = _profit_lock_stop(D(100), D(110), D(106), DEFAULT_STEPS, True)
    assert prog == D("0.6") and lock == D("0.25") and stop == D("102.5")
    stop, prog, lock = _profit_lock_stop(D(100), D(110), D(108), DEFAULT_STEPS, True)
    assert prog == D("0.8") and lock == D("0.5") and stop == D("105")
    stop, prog, lock = _profit_lock_stop(D(100), D(110), D("109.5"), DEFAULT_STEPS, True)
    assert prog == D("0.95") and lock == D("0.75") and stop == D("107.5")


def test_reversal_at_88pct_locks_50():
    stop, prog, lock = _profit_lock_stop(D(100), D(110), D("108.8"), DEFAULT_STEPS, True)
    assert prog == D("0.88") and lock == D("0.5") and stop == D("105")


def test_short_symmetric():
    stop, prog, lock = _profit_lock_stop(D(100), D(90), D(94), DEFAULT_STEPS, False)
    assert prog == D("0.6") and lock == D("0.25") and stop == D("97.5")


def test_progress_clamped_and_span_guard():
    stop, prog, lock = _profit_lock_stop(D(100), D(110), D(120), DEFAULT_STEPS, True)
    assert prog == D("1") and lock == D("0.75")
    assert _profit_lock_stop(D(100), D(100), D(105), DEFAULT_STEPS, True) is None


def test_monotone_and_below_tp2():
    prev = D(0)
    for ex in ["106", "107", "108", "109", "109.9"]:
        res = _profit_lock_stop(D(100), D(110), D(ex), DEFAULT_STEPS, True)
        if res is None:
            continue
        stop, _, _ = res
        assert stop >= prev
        assert stop < D(110)
        prev = stop
