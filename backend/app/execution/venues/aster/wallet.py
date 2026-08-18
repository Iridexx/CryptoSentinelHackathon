"""Aster wallet view — read-only summary for the Wallet screen.

Shows the two addresses and the balance held on Aster. The sub-account address is
returned in full (funds are sent there), the API wallet abbreviated (it only signs).
The signing key is never returned, in any form.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.execution.venues.aster.client import AsterClient, AsterError, short_address

logger = get_logger("execution.venue.aster.wallet")

_CACHE_TTL_SECONDS = 30.0
_cache: dict[str, Any] = {"at": 0.0, "value": None}


@dataclass
class AsterAssetBalance:
    asset: str
    balance: str
    available: str


@dataclass
class AsterWalletView:
    configured: bool
    subaccount_name: str | None = None
    subaccount_address: str | None = None
    api_wallet_address_short: str | None = None
    balances: list[AsterAssetBalance] = field(default_factory=list)
    total_balance_usdt: str | None = None
    open_positions: int | None = None
    reachable: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["balances"] = [asdict(b) for b in self.balances]
        return data


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def get_wallet_view(settings, *, force_refresh: bool = False) -> AsterWalletView:
    """Addresses and balance held on Aster, or an explanation of what is missing."""
    enabled = getattr(settings, "aster_enabled", False)
    account = getattr(settings, "aster_account_address", "")
    api_wallet = getattr(settings, "aster_api_wallet_address", "")
    key = getattr(settings, "aster_api_wallet_private_key", "")
    name = getattr(settings, "aster_subaccount_name", "") or None

    if not (account and api_wallet and key):
        return AsterWalletView(
            configured=False,
            subaccount_name=name,
            error="Credenziali Aster non configurate sul server.",
        )

    if not enabled:
        return AsterWalletView(
            configured=True,
            subaccount_name=name,
            subaccount_address=account,
            api_wallet_address_short=short_address(api_wallet),
            error="Aster è disabilitato (ASTER_ENABLED=false). Abilitalo nel .env per usare il venue perp.",
        )

    now = time.monotonic()
    cached = _cache.get("value")
    if cached is not None and not force_refresh and (now - _cache["at"]) < _CACHE_TTL_SECONDS:
        return cached

    view = AsterWalletView(
        configured=True,
        subaccount_name=name,
        subaccount_address=account,
        api_wallet_address_short=short_address(api_wallet),
    )

    client = AsterClient(
        base_url=getattr(settings, "aster_base_url", ""),
        account_address=account,
        api_wallet_address=api_wallet,
        api_wallet_private_key=key,
    )

    # Aster answers -1000 ("Signature check failed") on /fapi/v3/balance and
    # /fapi/v3/positionRisk for this account, with credentials it accepts on every
    # other endpoint moments earlier — verified with two distinct API wallets, and
    # both before and after the account was funded. The account snapshot carries
    # the same numbers and does answer, so read them from there.
    try:
        snapshot = await client.account()
    except AsterError as exc:
        view.error = "Impossibile leggere il saldo da Aster in questo momento."
        logger.warning("aster_wallet_snapshot_failed", code=exc.code, status=exc.status)
        _cache.update(at=now, value=view)
        return view

    if not isinstance(snapshot, dict):
        view.error = "Aster ha restituito una risposta inattesa per il conto."
        logger.warning("aster_wallet_snapshot_malformed")
        _cache.update(at=now, value=view)
        return view

    for item in snapshot.get("assets") or []:
        amount = _as_float(item.get("walletBalance"))
        if amount <= 0:
            continue
        view.balances.append(
            AsterAssetBalance(
                asset=str(item.get("asset", "?")),
                balance=str(item.get("walletBalance", "0")),
                available=str(item.get("maxWithdrawAmount", item.get("walletBalance", "0"))),
            )
        )

    # Aster already values the whole account in USD: summing the asset rows would
    # mean adding 0.003 BNB to a dollar figure.
    view.total_balance_usdt = f"{_as_float(snapshot.get('totalWalletBalance')):.2f}"
    view.open_positions = len(
        [p for p in (snapshot.get("positions") or []) if _as_float(p.get("positionAmt")) != 0]
    )
    view.reachable = True

    _cache.update(at=now, value=view)
    return view
