"""Runtime-selected agent watchlist helpers."""

from __future__ import annotations

import json

from backend.app.core.config import Settings
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

WATCHLIST_STATE_KEY = "agent_watchlist_symbols"


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def selected_watchlist(settings: Settings) -> list[str]:
    """Return the persisted operational watchlist, filtered by the eligible universe."""

    raw = get_runtime_value(str(settings.default_user_id), WATCHLIST_STATE_KEY)
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    eligible = {normalize_symbol(token) for token in settings.eligible_tokens}
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = normalize_symbol(str(value))
        if symbol in eligible and symbol not in seen:
            selected.append(symbol)
            seen.add(symbol)
    return selected


def set_selected_watchlist(settings: Settings, symbols: list[str]) -> list[str]:
    """Persist an operational watchlist after validating it against Settings."""

    eligible = {normalize_symbol(token) for token in settings.eligible_tokens}
    selected: list[str] = []
    seen: set[str] = set()
    for value in symbols:
        symbol = normalize_symbol(value)
        if symbol not in eligible:
            raise ValueError(f"Asset is not in the eligible universe: {value}")
        if symbol not in seen:
            selected.append(symbol)
            seen.add(symbol)
    set_runtime_value(str(settings.default_user_id), WATCHLIST_STATE_KEY, json.dumps(selected))
    return selected
