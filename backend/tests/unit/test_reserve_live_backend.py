"""R10 scaffold — live (PancakeSwap) reserve execution backend, testnet-gated."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.core.config import Settings, load_yaml_settings
from backend.app.domain.reserve import pricing
from backend.app.domain.reserve.executor import Fill, ReserveExecutionError, ReserveExecutor
from backend.app.domain.reserve.live_backend import PancakeSwapReserveBackend
from backend.app.execution.models import ExecutionStatus, TransactionResult

USER = "00000000-0000-0000-0000-000000000001"

_ASSETS = [
    SimpleNamespace(symbol="BTC", pancakeswap_address="0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", decimals=18),
    SimpleNamespace(symbol="BNB", pancakeswap_address="WBNB", decimals=18),
]


def _settings(**over) -> SimpleNamespace:
    base = dict(
        bsc_network="testnet",
        wallet_address="0x000000000000000000000000000000000000dEaD",
        spot_quote_token_address="0xUSDC",
        spot_quote_token_decimals=18,
        risk_max_slippage_pct=1.0,
        bnb_gas_reserve_pct=15.0,
        bnb_gas_reserve_min=0.05,
        execution_mode="live",
        reserve=SimpleNamespace(assets=_ASSETS, execution_mode_inherit=True),
    )
    base.update(over)
    return SimpleNamespace(**base)


class _StubRpc:
    async def call(self, method, params=None):
        return {
            "eth_gasPrice": hex(10**9),
            "eth_getBalance": hex(5 * 10**18),
        }[method]


class _StubProvider:
    def __init__(self, *, out_atomic=10**16, status=ExecutionStatus.CONFIRMED):
        self._out = out_atomic
        self._status = status
        self.swaps: list[dict] = []

    def _rpc_client(self):
        return _StubRpc()

    async def get_quote(self, **kw):
        return SimpleNamespace(amount_out_atomic=self._out, min_amount_out_atomic=int(self._out * 0.99))

    async def execute_swap(self, **kw):
        self.swaps.append(kw)
        return TransactionResult(
            status=self._status,
            transaction_hash="0xabc",
            gas_used=200_000,
            effective_gas_price_wei=10**9,
        )


async def _bnb_price() -> Decimal:
    return Decimal("600")


async def test_buy_delegates_to_pancakeswap_and_returns_fill():
    provider = _StubProvider(out_atomic=10**16)  # 0.01 BTC
    backend = PancakeSwapReserveBackend(_settings(), provider=provider, bnb_price_source=_bnb_price)

    fill = await backend.buy("BTC", Decimal("100"))

    assert isinstance(fill, Fill)
    assert fill.asset == "BTC"
    assert fill.quantity == Decimal("0.01")
    assert fill.gross_usd == Decimal("100")
    assert fill.fee_usd > 0
    assert fill.net_usd == Decimal("100") - fill.fee_usd
    assert provider.swaps and provider.swaps[0]["from_asset"] == "0xUSDC"


async def test_mainnet_is_hard_gated():
    backend = PancakeSwapReserveBackend(
        _settings(bsc_network="mainnet"), provider=_StubProvider(), bnb_price_source=_bnb_price
    )
    with pytest.raises(ReserveExecutionError, match="testnet"):
        await backend.buy("BTC", Decimal("100"))


async def test_skipped_swap_raises():
    provider = _StubProvider(status=ExecutionStatus.SKIPPED)
    backend = PancakeSwapReserveBackend(_settings(), provider=provider, bnb_price_source=_bnb_price)
    with pytest.raises(ReserveExecutionError, match="skipped"):
        await backend.buy("BTC", Decimal("100"))


async def test_wbnb_symbol_maps_to_native_sentinel():
    provider = _StubProvider()
    backend = PancakeSwapReserveBackend(_settings(), provider=provider, bnb_price_source=_bnb_price)
    await backend.buy("BNB", Decimal("50"))
    assert provider.swaps[0]["to_asset"].lower().startswith("0xeeee")


async def test_executor_live_branch_needs_a_backend():
    ex = ReserveExecutor(object(), price_source=lambda a: None, live=True)  # type: ignore[arg-type]
    with pytest.raises(ReserveExecutionError, match="no on-chain backend"):
        await ex.buy("BTC", Decimal("10"))


async def test_executor_live_branch_delegates_to_backend():
    sentinel = Fill("BTC", Decimal("1"), Decimal("2"), Decimal("2"), Decimal("0"), Decimal("2"))

    class _B:
        async def buy(self, asset, usd):
            return sentinel

        async def sell(self, asset, qty):
            return sentinel

    ex = ReserveExecutor(object(), price_source=lambda a: None, live=True, live_backend=_B())  # type: ignore[arg-type]
    assert await ex.buy("BTC", Decimal("10")) is sentinel
    assert await ex.sell("BTC", Decimal("1")) is sentinel


def test_build_reserve_service_stays_simulated_in_dry_run():
    settings = Settings(**{**load_yaml_settings(), "default_user_id": UUID(USER)})
    assert settings.execution_mode == "dry_run"
    assert pricing._live_enabled(settings) is False
