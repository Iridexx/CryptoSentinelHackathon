"""Live (on-chain) execution backend for the reserve — R10 scaffold.

Each reserve buy/sell is delegated to the PancakeSwap V2 provider, reusing every
shared guardrail (non-disablable BNB gas reserve, exact ERC-20 approval, bounded
submission, on-chain reconciliation). Nothing here can bypass them.

**Hard testnet gate.** ``bsc_network`` must be ``"testnet"``; a mainnet network
raises ``ReserveExecutionError`` before any transaction is built. This mirrors the
config-level guard (``execution_mode == "live"`` already forces testnet) and keeps
the reserve fail-closed even if that guard is ever relaxed. Real mainnet rollout
is a later step: verify the BEP20 addresses in ``configs/reserve.yaml`` on-chain,
measure Binance-Peg SOL/TRX liquidity on PancakeSwap, then remove this gate.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from backend.app.core.config import Settings
from backend.app.core.logging import get_logger
from backend.app.execution.base import NATIVE_EVM_ASSET
from backend.app.execution.gas import GasGuard
from backend.app.execution.models import ExecutionStatus
from backend.app.execution.providers import PancakeSwapProvider
from backend.app.execution.providers.pancakeswap_provider import DEFAULT_SWAP_GAS_LIMIT
from backend.app.domain.reserve.executor import Fill, ReserveExecutionError

logger = get_logger("domain.reserve.live_backend")

WEI_PER_BNB = Decimal(10**18)

#: PancakeSwap V2 pool fee (0.25%). The swap + slippage component of the modelled
#: cost; the on-chain gas is added separately from the receipt.
_POOL_FEE_PCT = Decimal("0.25")

BnbPriceSource = Callable[[], Awaitable[Decimal | None]]


class PancakeSwapReserveBackend:
    """Turns a reserve buy/sell into one guarded PancakeSwap V2 swap."""

    def __init__(
        self,
        settings: Settings,
        *,
        provider: PancakeSwapProvider | None = None,
        bnb_price_source: BnbPriceSource | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider or PancakeSwapProvider(settings)
        self._bnb_price_source = bnb_price_source

    # ── address resolution ───────────────────────────────────────────────────

    def _asset_address(self, symbol: str) -> str:
        for asset in self._settings.reserve.assets:
            if asset.symbol.upper() == symbol.upper():
                raw = (asset.pancakeswap_address or "").strip()
                if not raw:
                    raise ReserveExecutionError(f"no PancakeSwap address for {symbol}")
                if raw.upper() == "WBNB":
                    return NATIVE_EVM_ASSET
                return raw
        raise ReserveExecutionError(f"{symbol} is not a configured reserve asset")

    def _asset_decimals(self, symbol: str) -> int:
        for asset in self._settings.reserve.assets:
            if asset.symbol.upper() == symbol.upper():
                return int(asset.decimals)
        return 18

    def _quote_token(self) -> tuple[str, int]:
        address = self._settings.spot_quote_token_address
        if not address:
            raise ReserveExecutionError("spot_quote_token_address (USDC) is not configured")
        return address, int(self._settings.spot_quote_token_decimals)

    # ── gate ─────────────────────────────────────────────────────────────────

    def _require_testnet(self) -> None:
        if self._settings.bsc_network != "testnet":
            raise ReserveExecutionError(
                "reserve live execution is gated to BSC testnet "
                f"(bsc_network={self._settings.bsc_network!r})"
            )

    # ── public API (mirrors ReserveExecutor.buy/sell) ────────────────────────

    async def buy(self, asset: str, usd_amount: Decimal) -> Fill:
        if usd_amount <= 0:
            raise ReserveExecutionError("buy amount must be positive")
        quote_addr, quote_dec = self._quote_token()
        to_addr = self._asset_address(asset)
        to_dec = self._asset_decimals(asset)
        amount_in_atomic = int(usd_amount * (Decimal(10) ** quote_dec))
        out_atomic, gas_fee = await self._swap(
            from_asset=quote_addr,
            to_asset=to_addr,
            amount_in_atomic=amount_in_atomic,
            notional_usd=usd_amount,
        )
        qty = Decimal(out_atomic) / (Decimal(10) ** to_dec)
        if qty <= 0:
            raise ReserveExecutionError(f"live buy of {asset} returned no output")
        pool_fee = usd_amount * _POOL_FEE_PCT / Decimal(100)
        fee = pool_fee + gas_fee
        net = usd_amount - fee
        price = net / qty
        return Fill(asset, qty, price, usd_amount, fee, net)

    async def sell(self, asset: str, quantity: Decimal) -> Fill:
        if quantity <= 0:
            raise ReserveExecutionError("sell quantity must be positive")
        quote_addr, quote_dec = self._quote_token()
        from_addr = self._asset_address(asset)
        from_dec = self._asset_decimals(asset)
        amount_in_atomic = int(quantity * (Decimal(10) ** from_dec))
        out_atomic, gas_fee = await self._swap(
            from_asset=from_addr,
            to_asset=quote_addr,
            amount_in_atomic=amount_in_atomic,
            notional_usd=None,
        )
        gross = Decimal(out_atomic) / (Decimal(10) ** quote_dec)
        if gross <= 0:
            raise ReserveExecutionError(f"live sell of {asset} returned no output")
        pool_fee = gross * _POOL_FEE_PCT / Decimal(100)
        fee = pool_fee + gas_fee
        net = gross - fee
        if net <= 0:
            raise ReserveExecutionError(f"live sell proceeds {gross} do not cover the fee")
        price = gross / quantity
        return Fill(asset, quantity, price, gross, fee, net)

    # ── core swap ────────────────────────────────────────────────────────────

    async def _swap(
        self,
        *,
        from_asset: str,
        to_asset: str,
        amount_in_atomic: int,
        notional_usd: Decimal | None,
    ) -> tuple[int, Decimal]:
        """Submit one guarded swap. Returns ``(amount_out_atomic, gas_fee_usd)``."""
        self._require_testnet()
        wallet = self._settings.wallet_address
        if not wallet:
            raise ReserveExecutionError("wallet_address is not configured for live execution")

        provider = self._provider
        rpc = provider._rpc_client()  # noqa: SLF001 - shared multi-RPC client
        slippage = Decimal(str(self._settings.risk_max_slippage_pct))

        quote = await provider.get_quote(
            amount_in_atomic=amount_in_atomic,
            from_asset=from_asset,
            to_asset=to_asset,
            wallet_address=wallet,
            slippage_pct=slippage,
        )

        bnb_price = await self._bnb_price()
        gas_price_wei = int(await rpc.call("eth_gasPrice"), 16)
        balance_wei = int(await rpc.call("eth_getBalance", [wallet, "latest"]), 16)

        guard = GasGuard(
            Decimal(str(self._settings.bnb_gas_reserve_pct)),
            Decimal(str(self._settings.bnb_gas_reserve_min)),
        )
        # The reserve trades to hold, not to flip: there is no per-trade "profit".
        # Feed the notional so the cost-benefit guard keeps gas well below the
        # trade size; the non-disablable BNB reserve still applies in full.
        expected_profit = notional_usd if notional_usd is not None else (
            Decimal(quote.amount_out_atomic) / WEI_PER_BNB * bnb_price
        )
        decision = guard.evaluate(
            balance_wei=balance_wei,
            gas_limit=DEFAULT_SWAP_GAS_LIMIT,
            gas_price_wei=gas_price_wei,
            expected_profit_usd=expected_profit,
            bnb_price_usd=bnb_price,
        )
        if not decision.allowed:
            raise ReserveExecutionError(f"gas guard rejected the reserve swap: {decision.reason}")

        result = await provider.execute_swap(
            amount_in_atomic=amount_in_atomic,
            from_asset=from_asset,
            to_asset=to_asset,
            wallet_address=wallet,
            slippage_pct=slippage,
            gas_decision=decision,
        )
        if result.status == ExecutionStatus.SKIPPED:
            raise ReserveExecutionError(f"live reserve swap skipped: {result.reason}")
        if result.status not in (ExecutionStatus.CONFIRMED, ExecutionStatus.UNKNOWN):
            raise ReserveExecutionError(
                f"live reserve swap did not confirm: {result.status} ({result.reason})"
            )

        gas_used = result.gas_used or DEFAULT_SWAP_GAS_LIMIT
        gas_price = result.effective_gas_price_wei or gas_price_wei
        gas_fee_usd = Decimal(gas_used * gas_price) / WEI_PER_BNB * bnb_price
        logger.info(
            "reserve_live_swap",
            from_asset=from_asset,
            to_asset=to_asset,
            tx=result.transaction_hash,
            status=str(result.status),
        )
        return quote.amount_out_atomic, gas_fee_usd

    async def _bnb_price(self) -> Decimal:
        if self._bnb_price_source is not None:
            value = await self._bnb_price_source()
            if value and value > 0:
                return Decimal(str(value))
        raise ReserveExecutionError("no BNB price available for the gas guard")
