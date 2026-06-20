"""Runtime public wallet address selection for execution."""

from __future__ import annotations

import json
from typing import Iterable

from web3 import Web3

from backend.app.core.config import Settings
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

ACTIVE_WALLET_STATE_KEY = "execution_wallet_address"
WALLET_LIST_STATE_KEY = "execution_wallet_addresses"


def normalize_wallet_address(address: str) -> str:
    """Validate and checksum a public EVM address."""

    if not Web3.is_address(address):
        raise ValueError("Invalid EVM wallet address")
    return Web3.to_checksum_address(address)


def configured_wallet_addresses(settings: Settings) -> list[str]:
    """Return configured public wallet addresses plus runtime additions."""

    candidates: list[str] = []
    if settings.wallet_address:
        candidates.append(settings.wallet_address)
    candidates.extend(settings.wallet_addresses)
    raw_runtime = get_runtime_value(str(settings.default_user_id), WALLET_LIST_STATE_KEY)
    if raw_runtime:
        try:
            candidates.extend(json.loads(raw_runtime))
        except (TypeError, ValueError):
            pass
    return _dedupe_valid(candidates)


def get_active_wallet_address(settings: Settings) -> str | None:
    """Return the selected public wallet address, falling back to Settings."""

    wallets = configured_wallet_addresses(settings)
    if not wallets:
        return None
    raw = get_runtime_value(str(settings.default_user_id), ACTIVE_WALLET_STATE_KEY)
    if raw:
        try:
            selected = normalize_wallet_address(raw)
            if selected in wallets:
                return selected
        except ValueError:
            pass
    return wallets[0]


def add_wallet_address(settings: Settings, address: str) -> str:
    """Persist an additional public wallet address and select it."""

    normalized = normalize_wallet_address(address)
    wallets = configured_wallet_addresses(settings)
    if normalized not in wallets:
        wallets.append(normalized)
    set_runtime_value(str(settings.default_user_id), WALLET_LIST_STATE_KEY, json.dumps(wallets))
    set_active_wallet_address(settings, normalized)
    return normalized


def set_active_wallet_address(settings: Settings, address: str) -> str:
    """Persist the active public wallet address."""

    normalized = normalize_wallet_address(address)
    wallets = configured_wallet_addresses(settings)
    if normalized not in wallets:
        raise ValueError("Wallet address is not in the configured wallet list")
    set_runtime_value(str(settings.default_user_id), ACTIVE_WALLET_STATE_KEY, normalized)
    return normalized


def effective_wallet_settings(settings: Settings) -> Settings:
    """Return Settings with the runtime active wallet applied."""

    active = get_active_wallet_address(settings)
    if not active:
        return settings
    return settings.model_copy(update={"wallet_address": active})


def _dedupe_valid(addresses: Iterable[str]) -> list[str]:
    result: list[str] = []
    for address in addresses:
        try:
            normalized = normalize_wallet_address(str(address))
        except ValueError:
            continue
        if normalized not in result:
            result.append(normalized)
    return result
