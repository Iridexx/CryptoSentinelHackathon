"""R1 — configs/reserve.yaml, ReserveConfig, ReserveSettings override."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.core.config import ReserveConfig, load_yaml_settings
from backend.app.domain.reserve import settings as reserve_settings_module
from backend.app.domain.reserve.settings import load_reserve_settings, save_reserve_settings
from backend.app.schemas.reserve import ReserveSettings, ReserveTargetWeight

FIVE_ASSETS = [
    {"symbol": "BTC", "target_weight_pct": 40.0},
    {"symbol": "ETH", "target_weight_pct": 30.0},
    {"symbol": "BNB", "target_weight_pct": 20.0},
    {"symbol": "SOL", "target_weight_pct": 5.0},
    {"symbol": "TRX", "target_weight_pct": 5.0},
]


# ── versioned YAML ───────────────────────────────────────────────────────────


def test_reserve_yaml_loads_into_a_valid_config() -> None:
    flattened = load_yaml_settings()
    assert "reserve" in flattened, "reserve.yaml section not picked up by the loader"

    cfg = ReserveConfig.model_validate(flattened["reserve"])

    assert cfg.enabled is True
    assert cfg.symbols == ["BTC", "ETH", "BNB", "SOL", "TRX"]
    assert sum(a.target_weight_pct for a in cfg.assets) == pytest.approx(100.0)
    assert cfg.sweep_pct == 20.0
    assert cfg.sweep_interval_hours == 24
    assert cfg.withdrawal_cooldown_minutes == 1440
    trx = next(a for a in cfg.assets if a.symbol == "TRX")
    assert trx.aster_spot_symbol is None  # confirmed by R1b


# ── ReserveConfig validation ─────────────────────────────────────────────────


def test_reserve_config_rejects_weights_not_summing_to_100() -> None:
    bad = [{"symbol": "BTC", "target_weight_pct": 60.0}, {"symbol": "ETH", "target_weight_pct": 30.0}]
    with pytest.raises(ValidationError, match="sum to 100"):
        ReserveConfig(enabled=True, assets=bad)


def test_reserve_config_rejects_duplicate_symbols() -> None:
    dup = [
        {"symbol": "BTC", "target_weight_pct": 50.0},
        {"symbol": "btc", "target_weight_pct": 50.0},
    ]
    with pytest.raises(ValidationError, match="unique"):
        ReserveConfig(enabled=True, assets=dup)


def test_reserve_config_rejects_sweep_pct_out_of_range() -> None:
    with pytest.raises(ValidationError, match="sweep_pct"):
        ReserveConfig(enabled=True, assets=FIVE_ASSETS, sweep_pct=150.0)


def test_reserve_config_rejects_enabled_without_assets() -> None:
    with pytest.raises(ValidationError, match="no assets"):
        ReserveConfig(enabled=True, assets=[])


def test_reserve_config_disabled_skips_weight_checks() -> None:
    cfg = ReserveConfig(enabled=False, assets=[{"symbol": "BTC", "target_weight_pct": 12.0}])
    assert cfg.enabled is False


# ── ReserveSettings (runtime-tunable subset) ─────────────────────────────────


def test_reserve_settings_from_config_mirrors_yaml() -> None:
    cfg = ReserveConfig.model_validate(load_yaml_settings()["reserve"])
    s = ReserveSettings.from_config(cfg)

    assert s.enabled is True
    assert s.sweep_pct == 20.0
    assert {w.symbol for w in s.target_weights} == {"BTC", "ETH", "BNB", "SOL", "TRX"}
    assert sum(w.weight_pct for w in s.target_weights) == pytest.approx(100.0)


def test_reserve_settings_reconcile_drops_unknown_and_adds_missing() -> None:
    cfg = ReserveConfig(enabled=True, assets=FIVE_ASSETS)
    stale = ReserveSettings(
        enabled=True,
        target_weights=[
            ReserveTargetWeight(symbol="BTC", weight_pct=50.0),
            ReserveTargetWeight(symbol="DOGE", weight_pct=50.0),  # no longer configured
        ],
    )

    fixed = stale.reconcile_with_config(cfg)
    symbols = {w.symbol for w in fixed.target_weights}

    assert "DOGE" not in symbols
    assert symbols == {"BTC", "ETH", "BNB", "SOL", "TRX"}
    assert next(w for w in fixed.target_weights if w.symbol == "BTC").weight_pct == 50.0


def test_reserve_settings_rejects_weights_not_summing_to_100_when_enabled() -> None:
    with pytest.raises(ValidationError, match="sum to 100"):
        ReserveSettings(
            enabled=True,
            target_weights=[
                ReserveTargetWeight(symbol="BTC", weight_pct=70.0),
                ReserveTargetWeight(symbol="ETH", weight_pct=20.0),
            ],
        )


# ── runtime override load/save ──────────────────────────────────────────────


def test_load_reserve_settings_returns_default_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reserve_settings_module, "get_runtime_value", lambda *_: None)

    resp = load_reserve_settings("user-1")

    assert resp.source == "default"
    assert resp.settings.sweep_pct == 20.0


def test_save_then_load_round_trips_the_override(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        reserve_settings_module,
        "set_runtime_value",
        lambda uid, key, val: store.__setitem__((uid, key), val),
    )
    monkeypatch.setattr(
        reserve_settings_module,
        "get_runtime_value",
        lambda uid, key: store.get((uid, key)),
    )

    cfg = load_reserve_settings("user-2").settings
    updated = cfg.model_copy(update={"sweep_pct": 35.0, "auto_rebalance": False})
    saved = save_reserve_settings("user-2", updated)
    assert saved.source == "persisted"

    reloaded = load_reserve_settings("user-2")
    assert reloaded.source == "persisted"
    assert reloaded.settings.sweep_pct == 35.0
    assert reloaded.settings.auto_rebalance is False
