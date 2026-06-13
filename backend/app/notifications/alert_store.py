"""Persistent store for user alert configurations and price-checker state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from backend.app.schemas.alerts import AlertSyncRequest, PendingFavAlert

_STORE_PATH = Path("backend/storage/alerts.json")


@dataclass
class CheckerState:
    """Runtime state persisted between price-check ticks."""

    triggered_keys: set[str] = field(default_factory=set)
    range_last_notified: dict[str, float] = field(default_factory=dict)
    range_is_inside: dict[str, bool | None] = field(default_factory=dict)
    fav_ref_prices: dict[str, float] = field(default_factory=dict)
    pending_fav_alerts: dict[str, PendingFavAlert] = field(default_factory=dict)


class AlertStore:
    """File-backed store for the latest alert config received from the app."""

    def __init__(self, path: Path = _STORE_PATH) -> None:
        self.path = path
        self._lock = Lock()
        self._config: AlertSyncRequest | None = None
        self._state = CheckerState()
        self._load()

    def save_config(self, config: AlertSyncRequest) -> None:
        """Replace stored alert configuration, preserving backend-computed state."""
        with self._lock:
            merged_ref = dict(self._state.fav_ref_prices)
            for coin_id, price in config.fav_ref_prices.items():
                merged_ref.setdefault(coin_id, price)

            active_price_keys = {
                f"{alert.coin_id}:{alert.direction}:{alert.threshold}"
                for alert in config.price_alerts
            }
            active_range_keys = {
                f"{alert.coin_id}:{alert.min_price}:{alert.max_price}"
                for alert in config.range_alerts
            }
            active_fav_ids = {coin.id for coin in config.fav_coins}

            self._config = config
            self._state.triggered_keys.intersection_update(active_price_keys)
            self._state.range_last_notified = {
                key: value
                for key, value in self._state.range_last_notified.items()
                if key in active_range_keys
            }
            self._state.range_is_inside = {
                key: value
                for key, value in self._state.range_is_inside.items()
                if key in active_range_keys
            }
            self._state.fav_ref_prices = {
                coin_id: price
                for coin_id, price in merged_ref.items()
                if coin_id in active_fav_ids
            }
            self._state.pending_fav_alerts = {
                coin_id: alert
                for coin_id, alert in self._state.pending_fav_alerts.items()
                if coin_id in active_fav_ids
            }
            self._persist_locked()

    def get_config(self) -> AlertSyncRequest | None:
        with self._lock:
            return self._config

    def get_state(self) -> CheckerState:
        with self._lock:
            return CheckerState(
                triggered_keys=set(self._state.triggered_keys),
                range_last_notified=dict(self._state.range_last_notified),
                range_is_inside=dict(self._state.range_is_inside),
                fav_ref_prices=dict(self._state.fav_ref_prices),
                pending_fav_alerts={
                    coin_id: alert.model_copy()
                    for coin_id, alert in self._state.pending_fav_alerts.items()
                },
            )

    def update_state(self, state: CheckerState) -> None:
        with self._lock:
            self._state = state
            self._persist_locked()

    def pending_fav_alerts(self) -> list[PendingFavAlert]:
        """Return pending favorite alerts without clearing them."""

        with self._lock:
            return [alert.model_copy() for alert in self._state.pending_fav_alerts.values()]

    def dismiss_pending_fav_alert(self, coin_id: str) -> bool:
        """Acknowledge one favorite alert after the user dismisses its badge."""

        with self._lock:
            removed = self._state.pending_fav_alerts.pop(coin_id, None) is not None
            if removed:
                self._persist_locked()
            return removed

    def _persist_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": self._config.model_dump() if self._config else None,
            "state": {
                "triggered_keys": list(self._state.triggered_keys),
                "range_last_notified": self._state.range_last_notified,
                "range_is_inside": {k: v for k, v in self._state.range_is_inside.items()},
                "fav_ref_prices": self._state.fav_ref_prices,
                "pending_fav_alerts": {
                    coin_id: alert.model_dump()
                    for coin_id, alert in self._state.pending_fav_alerts.items()
                },
            },
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if cfg := data.get("config"):
                self._config = AlertSyncRequest.model_validate(cfg)
            if st := data.get("state"):
                self._state = CheckerState(
                    triggered_keys=set(st.get("triggered_keys", [])),
                    range_last_notified=st.get("range_last_notified", {}),
                    range_is_inside=st.get("range_is_inside", {}),
                    fav_ref_prices=st.get("fav_ref_prices", {}),
                    pending_fav_alerts={
                        coin_id: PendingFavAlert.model_validate(alert)
                        for coin_id, alert in st.get("pending_fav_alerts", {}).items()
                    },
                )
        except Exception:
            pass


_instance: AlertStore | None = None


def get_alert_store() -> AlertStore:
    global _instance
    if _instance is None:
        _instance = AlertStore()
    return _instance
