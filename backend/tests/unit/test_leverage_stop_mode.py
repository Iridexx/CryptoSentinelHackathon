import pytest
from pydantic import ValidationError

from backend.app.agent.signals.perp.volume_profile import _atr_range_leverage, _stop_risk_leverage
from backend.app.schemas.mobile_agent import AgentMobileSettings


def _lev(entry, stop, *, risk=20.0, lo=3, hi=28):
    return _stop_risk_leverage(min_lev=lo, max_lev=hi, entry=entry, stop=stop, risk_pct=risk)


def test_stop_vicino_leva_alta_stop_lontano_leva_bassa():
    near, _ = _lev(100.0, 99.0)    # stop a 1%
    far, _ = _lev(100.0, 97.0)     # stop a 3%
    assert near > far


def test_perdita_a_stop_pieno_resta_circa_il_rischio():
    # 20% / (1,5% + 0,10% costo) = 12,5 -> 12x: a stop pieno ~19% del margine, mai sopra il 20%
    leverage, clamped = _lev(100.0, 98.5)
    assert leverage == 12
    assert not clamped
    assert leverage * (1.5 + 0.10) <= 20.0


def test_short_usa_la_distanza_assoluta():
    assert _lev(100.0, 101.5) == _lev(100.0, 98.5)


def test_limitata_al_massimo_con_stop_molto_vicino():
    leverage, clamped = _lev(100.0, 99.9)
    assert leverage == 28
    assert not clamped


def test_minimo_troppo_alto_apre_comunque_a_leva_minima():
    # stop al 10%: servirebbe ~2x, ma il minimo e' 3 -> entra a 3x e lo segnala, non salta.
    leverage, clamped = _lev(100.0, 90.0)
    assert leverage == 3
    assert clamped


def test_dati_mancanti_leva_minima():
    assert _lev(None, 99.0) == (3, False)
    assert _lev(100.0, None) == (3, False)
    assert _lev(100.0, 100.0) == (3, False)


def test_range_invertito_o_uguale_non_rompe():
    assert _lev(100.0, 98.5, lo=28, hi=3)[0] == 12
    assert _lev(100.0, 98.5, lo=28, hi=28)[0] == 28


def test_modalita_atr_invariata():
    # min == max: la leva ATR e' fissa (comportamento di oggi)
    assert _atr_range_leverage(min_lev=28, max_lev=28, atr_value=1.0, atr_min=0.5, atr_max=2.0) == 28


def test_schema_default_e_validazione():
    ms = AgentMobileSettings()
    assert ms.perp_leverage_mode == "atr"
    assert ms.perp_risk_at_stop_pct == 20.0
    assert AgentMobileSettings(perp_leverage_mode="stop").perp_leverage_mode == "stop"
    with pytest.raises(ValidationError):
        AgentMobileSettings(perp_leverage_mode="altro")
    for bad in (0.5, 101.0):
        with pytest.raises(ValidationError):
            AgentMobileSettings(perp_risk_at_stop_pct=bad)
