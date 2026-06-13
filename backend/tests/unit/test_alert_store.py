from pathlib import Path

from backend.app.notifications.alert_store import AlertStore, CheckerState
from backend.app.schemas.alerts import (
    AlertSyncRequest,
    FavCoin,
    PriceAlertItem,
    RangeAlertItem,
)


def _config() -> AlertSyncRequest:
    return AlertSyncRequest(
        price_alerts=[
            PriceAlertItem(
                coin_id="bitcoin",
                coin_name="Bitcoin",
                direction="above",
                threshold=100_000,
            )
        ],
        range_alerts=[
            RangeAlertItem(
                coin_id="ethereum",
                coin_name="Ethereum",
                min_price=3_000,
                max_price=4_000,
            )
        ],
        fav_coins=[FavCoin(id="bnb", name="BNB", symbol="BNB")],
        fav_ref_prices={"bnb": 600},
    )


def test_identical_sync_preserves_checker_state(tmp_path: Path) -> None:
    store = AlertStore(tmp_path / "alerts.json")
    config = _config()
    store.save_config(config)
    store.update_state(
        CheckerState(
            triggered_keys={"bitcoin:above:100000.0"},
            range_last_notified={"ethereum:3000.0:4000.0": 123.0},
            range_is_inside={"ethereum:3000.0:4000.0": True},
            fav_ref_prices={"bnb": 625},
        )
    )

    store.save_config(config)

    state = store.get_state()
    assert state.triggered_keys == {"bitcoin:above:100000.0"}
    assert state.range_last_notified == {"ethereum:3000.0:4000.0": 123.0}
    assert state.range_is_inside == {"ethereum:3000.0:4000.0": True}
    assert state.fav_ref_prices == {"bnb": 625}


def test_removed_alerts_prune_checker_state(tmp_path: Path) -> None:
    store = AlertStore(tmp_path / "alerts.json")
    store.save_config(_config())
    store.update_state(
        CheckerState(
            triggered_keys={"bitcoin:above:100000.0"},
            range_last_notified={"ethereum:3000.0:4000.0": 123.0},
            range_is_inside={"ethereum:3000.0:4000.0": True},
            fav_ref_prices={"bnb": 625},
        )
    )

    store.save_config(AlertSyncRequest())

    assert store.get_state() == CheckerState()
