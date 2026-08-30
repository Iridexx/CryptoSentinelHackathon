"""Load/save the runtime override of the user-tunable reserve settings.

Mirrors the ``mobile_agent_settings`` pattern: ``configs/reserve.yaml`` is the
boot default, an optional per-user override lives in ``runtime_state`` and is
applied live. Reads degrade to the config default if persistence is unavailable
or the stored payload is stale/invalid.
"""

from __future__ import annotations

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value
from backend.app.schemas.reserve import ReserveSettings, ReserveSettingsResponse

logger = get_logger("domain.reserve.settings")

RESERVE_SETTINGS_KEY = "reserve_settings"


def load_reserve_settings(
    user_id: str,
    *,
    settings: Settings | None = None,
) -> ReserveSettingsResponse:
    """Return the effective reserve settings and their source.

    The persisted override is always reconciled against the current YAML asset
    list, so a config change never leaves a dangling weight.
    """

    cfg = (settings or get_settings()).reserve
    default = ReserveSettings.from_config(cfg)

    raw = get_runtime_value(user_id, RESERVE_SETTINGS_KEY)
    if not raw:
        return ReserveSettingsResponse(settings=default, source="default")

    try:
        stored = ReserveSettings.model_validate_json(raw)
    except Exception as exc:  # stale schema, corrupted payload
        logger.warning("reserve_settings_override_invalid", error_type=type(exc).__name__)
        return ReserveSettingsResponse(settings=default, source="default")

    return ReserveSettingsResponse(
        settings=stored.reconcile_with_config(cfg), source="persisted"
    )


def save_reserve_settings(
    user_id: str,
    incoming: ReserveSettings,
    *,
    settings: Settings | None = None,
) -> ReserveSettingsResponse:
    """Persist a reserve settings override for the user."""

    cfg = (settings or get_settings()).reserve
    reconciled = incoming.reconcile_with_config(cfg)
    set_runtime_value(user_id, RESERVE_SETTINGS_KEY, reconciled.model_dump_json())
    return ReserveSettingsResponse(settings=reconciled, source="persisted")
