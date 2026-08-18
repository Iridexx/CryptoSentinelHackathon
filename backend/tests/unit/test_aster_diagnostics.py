"""Aster connection diagnostics: offline tests that don't need a real DEX."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.execution.venues.aster.client import AsterError
from backend.app.execution.venues.aster.diagnostics import (
    CRITICAL,
    ERROR,
    OK,
    WARNING,
    run_connection_test,
)

# A throwaway key and the address it derives: the coherence check must pass on it.
_KEY = "0x" + "11" * 32
_SIGNER = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"


def _cfg(**overrides):
    defaults = dict(
        aster_enabled=True,
        aster_base_url="https://fapi.asterdex.com",
        aster_account_address="0xAbCd000000000000000000000000000000001234",
        aster_api_wallet_address=_SIGNER,
        aster_api_wallet_private_key=_KEY,
        aster_subaccount_name="sentinel",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _check(report, key):
    return next((c for c in report.checks if c.key == key), None)


class _FakeClient:
    """Stands in for AsterClient: every endpoint is a canned answer or a raiser."""

    def __init__(self, cfg, **responses):
        self._cfg = cfg
        self._responses = responses

    def signer_matches_key(self) -> bool:
        return self._responses.get("signer_matches", True)

    async def _reply(self, name, default):
        value = self._responses.get(name, default)
        if isinstance(value, Exception):
            raise value
        return value

    async def public_exchange_info(self):
        return await self._reply("exchange_info", {"symbols": [{"symbol": "BTCUSDT"}]})

    async def agents(self):
        return await self._reply("agents", [{
            "agentAddress": self._cfg.aster_api_wallet_address.lower(),
            "agentName": "sentinel",
            "expired": 4102444800000,  # 2100
            "canRead": True,
            "canSpotTrade": True,
            "canPerpTrade": True,
            "canWithdraw": False,
        }])

    async def sub_accounts(self):
        return await self._reply("sub_accounts", [{
            "address": self._cfg.aster_account_address,
            "accountId": 1,
            "parentAccount": True,
        }])

    async def account(self):
        return await self._reply("account", {
            "totalWalletBalance": "100.0",
            "assets": [{"asset": "USDT", "walletBalance": "100.0", "maxWithdrawAmount": "100.0"}],
            "positions": [],
        })

    async def commission_rate(self, symbol):
        return await self._reply(
            "commission_rate",
            {"makerCommissionRate": "0.0002", "takerCommissionRate": "0.0005"},
        )


def _patched(cfg, **responses):
    return patch(
        "backend.app.execution.venues.aster.diagnostics.AsterClient",
        return_value=_FakeClient(cfg, **responses),
    )


@pytest.mark.asyncio
async def test_disabled_returns_single_check() -> None:
    report = await run_connection_test(_cfg(aster_enabled=False))
    assert report.overall == CRITICAL
    assert len(report.checks) == 1
    assert "disabilitato" in report.checks[0].detail.lower()


@pytest.mark.asyncio
async def test_missing_address_is_error() -> None:
    report = await run_connection_test(_cfg(aster_account_address=""))
    assert report.overall == ERROR
    assert "indirizzo account" in _check(report, "config").detail.lower()


@pytest.mark.asyncio
async def test_missing_private_key_is_error() -> None:
    report = await run_connection_test(_cfg(aster_api_wallet_private_key=""))
    assert report.overall == ERROR
    assert "chiave di firma" in _check(report, "config").detail.lower()


@pytest.mark.asyncio
async def test_signer_coherence_catches_mismatched_wallet() -> None:
    """Address and key from two different wallets: caught before any request."""
    cfg = _cfg(aster_api_wallet_address="0x" + "aa" * 20)
    report = await run_connection_test(cfg)
    assert report.overall == ERROR
    assert _check(report, "signer").status == ERROR


@pytest.mark.asyncio
async def test_public_403_points_at_the_url_not_the_credentials() -> None:
    cfg = _cfg()
    with _patched(cfg, exchange_info=AsterError("forbidden", status=403)):
        report = await run_connection_test(cfg)
    reachability = _check(report, "reachability")
    assert reachability.status == ERROR
    assert "ASTER_BASE_URL" in reachability.detail


@pytest.mark.asyncio
async def test_happy_path_is_ok() -> None:
    cfg = _cfg()
    with _patched(cfg):
        report = await run_connection_test(cfg)
    assert report.overall == OK, [c.detail for c in report.checks if c.status != OK]
    assert _check(report, "auth").status == OK
    assert _check(report, "permissions").status == OK
    assert _check(report, "identity").status == OK


@pytest.mark.asyncio
async def test_auth_failure_stops_the_sequence() -> None:
    cfg = _cfg()
    with _patched(cfg, agents=AsterError("nope", code="-1000", status=400)):
        report = await run_connection_test(cfg)
    assert report.overall == ERROR
    assert _check(report, "auth").status == ERROR
    assert _check(report, "balance") is None


@pytest.mark.asyncio
async def test_unregistered_api_wallet_is_critical_and_blocks() -> None:
    """The signature is valid, but this wallet is not authorised on the account."""
    cfg = _cfg()
    with _patched(cfg, agents=[{"agentAddress": "0x" + "bb" * 20, "canRead": True}]):
        report = await run_connection_test(cfg)
    assert report.overall == CRITICAL
    assert report.blocked is True
    assert "non risulta registrato" in _check(report, "permissions").detail


@pytest.mark.asyncio
async def test_expired_api_wallet_is_critical() -> None:
    cfg = _cfg()
    expired = [{
        "agentAddress": _SIGNER.lower(), "agentName": "old", "expired": 1_600_000_000_000,
        "canRead": True, "canPerpTrade": True,
    }]
    with _patched(cfg, agents=expired):
        report = await run_connection_test(cfg)
    assert report.overall == CRITICAL
    assert "scaduto" in _check(report, "permissions").detail


@pytest.mark.asyncio
async def test_wrong_account_is_critical_and_blocks() -> None:
    cfg = _cfg()
    other = [{"address": "0x" + "cc" * 20, "accountId": 2, "parentAccount": True}]
    with _patched(cfg, sub_accounts=other):
        report = await run_connection_test(cfg)
    assert report.overall == CRITICAL
    assert report.blocked is True


@pytest.mark.asyncio
async def test_asters_own_minus_1000_is_a_warning_not_an_error() -> None:
    """Aster answers -1000 on some endpoints with credentials it accepts elsewhere.

    Auth passed two steps earlier, so this must not be reported as a connection
    failure — and the wording must not blame the configuration.
    """
    cfg = _cfg()
    unsupported = AsterError("Signature check failed", code="-1000", status=400)
    with _patched(cfg, commission_rate=unsupported):
        report = await run_connection_test(cfg)
    assert report.overall == WARNING
    assert report.blocked is False
    perp = _check(report, "perp")
    assert perp.status == WARNING
    assert "limitazione lato Aster" in perp.detail


@pytest.mark.asyncio
async def test_balance_and_positions_come_from_the_account_snapshot() -> None:
    cfg = _cfg()
    snapshot = {
        "totalWalletBalance": "1.72",
        "assets": [
            {"asset": "BNB", "walletBalance": "0.003", "maxWithdrawAmount": "0.003"},
            {"asset": "USDT", "walletBalance": "0"},
        ],
        "positions": [{"positionAmt": "0.5"}, {"positionAmt": "0"}],
    }
    with _patched(cfg, account=snapshot):
        report = await run_connection_test(cfg)
    assert _check(report, "balance").status == OK
    assert "1.72 USD su 1 asset (BNB)" in _check(report, "balance").detail
    assert "1 aperte" in _check(report, "positions").detail


@pytest.mark.asyncio
async def test_genuine_snapshot_failure_is_still_an_error() -> None:
    cfg = _cfg()
    with _patched(cfg, account=AsterError("boom", code="-1021", status=400)):
        report = await run_connection_test(cfg)
    assert report.overall == ERROR
    assert _check(report, "balance").status == ERROR
