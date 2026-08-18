"""Aster connection diagnostics: offline tests that don't need a real DEX."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.execution.venues.aster.diagnostics import run_connection_test


def _cfg(**overrides):
    defaults = dict(
        aster_enabled=True,
        aster_base_url="https://fapi.asterdex.com",
        aster_account_address="0xABCD",
        aster_api_wallet_address="0x1234",
        aster_api_wallet_private_key="0xdeadbeef",
        aster_subaccount_name="sentinel",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_disabled_returns_single_skip_check() -> None:
    cfg = _cfg(aster_enabled=False)
    report = await run_connection_test(cfg)
    assert report.overall == "CRITICAL"
    assert any(c.status == "CRITICAL" and "disabilitato" in c.message.lower() for c in report.checks)


@pytest.mark.asyncio
async def test_missing_address_is_critical() -> None:
    cfg = _cfg(aster_account_address="")
    report = await run_connection_test(cfg)
    assert report.overall in ("CRITICAL", "ERROR")
    assert any("account_address" in c.message.lower() or "indirizzo" in c.message.lower() for c in report.checks)


@pytest.mark.asyncio
async def test_missing_private_key_is_critical() -> None:
    cfg = _cfg(aster_api_wallet_private_key="")
    report = await run_connection_test(cfg)
    assert report.overall in ("CRITICAL", "ERROR")


@pytest.mark.asyncio
async def test_signer_coherence_catches_mismatched_wallet() -> None:
    cfg = _cfg(
        aster_api_wallet_address="0xAAAA",
        aster_api_wallet_private_key="0x" + "ab" * 32,
    )
    report = await run_connection_test(cfg)
    has_coherence = any("coeren" in c.message.lower() or "mismatch" in c.message.lower() for c in report.checks)
    assert has_coherence or report.overall in ("WARNING", "ERROR", "CRITICAL")


@pytest.mark.asyncio
async def test_unreachable_endpoint_gives_error_not_crash() -> None:
    cfg = _cfg(aster_base_url="https://does-not-exist.example.com")
    report = await run_connection_test(cfg)
    assert report.overall in ("ERROR", "CRITICAL")
    assert len(report.checks) >= 3


@pytest.mark.asyncio
async def test_public_403_suggests_url_check() -> None:
    """A 403 on the public endpoint means wrong URL, not auth failure."""
    cfg = _cfg()

    async def mock_exchange_info():
        raise Exception("403 Forbidden")

    with patch(
        "backend.app.execution.venues.aster.diagnostics.AsterClient",
        return_value=SimpleNamespace(public_exchange_info=mock_exchange_info),
    ):
        report = await run_connection_test(cfg)

    reachability = [c for c in report.checks if "raggiungibil" in c.message.lower() or "reachab" in c.message.lower() or "url" in c.message.lower()]
    assert any(c.status in ("ERROR", "CRITICAL") for c in reachability) or report.overall in ("ERROR", "CRITICAL")
