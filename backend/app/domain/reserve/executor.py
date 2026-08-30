"""Executes reserve buys/sells.

Two branches:

* **simulated** (R3) — trades are recorded at the live market-data price with a
  modelled fee, no on-chain transaction.
* **live** (R10 scaffold) — each buy/sell is delegated to a ``live_backend``
  (``PancakeSwapReserveBackend``), which is hard-gated to BSC testnet. Without a
  backend the live branch raises ``ReserveExecutionError`` (fail-closed).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from backend.app.core.config import Settings
from backend.app.core.logging import get_logger
from backend.app.execution.spot_fees import compute_spot_costs

logger = get_logger("domain.reserve.executor")

#: Flat gas cost per simulated swap on BSC (cents). The fixed component that
#: makes tiny buys wasteful and justifies ``deploy_min_buy_usd``.
SIM_GAS_USD = Decimal("0.15")

PriceSource = Callable[[str], Awaitable[Decimal | None]]


class ReserveExecutionError(RuntimeError):
    """The reserve executor could not price or execute a leg."""


@dataclass(frozen=True, slots=True)
class Fill:
    """Result of one simulated buy or sell."""

    asset: str
    quantity: Decimal      # asset units traded (positive)
    price_usd: Decimal     # execution price
    gross_usd: Decimal     # notional before fee
    fee_usd: Decimal       # swap + slippage + gas
    net_usd: Decimal       # gross − fee (asset value in on a buy / cash out on a sell)


class ReserveLiveBackend(Protocol):
    """On-chain execution backend the live branch delegates to."""

    async def buy(self, asset: str, usd_amount: Decimal) -> Fill: ...

    async def sell(self, asset: str, quantity: Decimal) -> Fill: ...


class ReserveExecutor:
    def __init__(
        self,
        settings: Settings,
        *,
        price_source: PriceSource,
        live: bool = False,
        live_backend: ReserveLiveBackend | None = None,
    ) -> None:
        self._settings = settings
        self._price_source = price_source
        self._live = live
        self._live_backend = live_backend

    async def price(self, asset: str) -> Decimal:
        try:
            value = await self._price_source(asset)
        except Exception as exc:  # noqa: BLE001 - surfaced as a domain error
            raise ReserveExecutionError(f"price lookup failed for {asset}: {exc}") from exc
        if value is None or value <= 0:
            raise ReserveExecutionError(f"no price for {asset}")
        return Decimal(str(value))

    def _fee(self, notional_usd: Decimal) -> Decimal:
        costs = compute_spot_costs(notional_usd, "all")
        return Decimal(costs["applied_fee_usd"]) + SIM_GAS_USD

    async def buy(self, asset: str, usd_amount: Decimal) -> Fill:
        """Spend ``usd_amount`` of USDC on ``asset``. Fee comes out of the notional."""
        if self._live:
            return await self._live_leg("buy", asset, usd_amount)
        if usd_amount <= 0:
            raise ReserveExecutionError("buy amount must be positive")
        price = await self.price(asset)
        fee = self._fee(usd_amount)
        net = usd_amount - fee
        if net <= 0:
            raise ReserveExecutionError(f"buy amount {usd_amount} does not cover the fee")
        qty = net / price
        return Fill(asset, qty, price, usd_amount, fee, net)

    async def sell(self, asset: str, quantity: Decimal) -> Fill:
        """Sell ``quantity`` units of ``asset`` for USDC. Fee comes out of the proceeds."""
        if self._live:
            return await self._live_leg("sell", asset, quantity)
        if quantity <= 0:
            raise ReserveExecutionError("sell quantity must be positive")
        price = await self.price(asset)
        gross = quantity * price
        fee = self._fee(gross)
        net = gross - fee
        if net <= 0:
            raise ReserveExecutionError(f"sell proceeds {gross} do not cover the fee")
        return Fill(asset, quantity, price, gross, fee, net)

    async def _live_leg(self, side: str, asset: str, amount: Decimal) -> Fill:
        if self._live_backend is None:
            raise ReserveExecutionError(
                "live reserve execution requested but no on-chain backend is configured"
            )
        if side == "buy":
            return await self._live_backend.buy(asset, amount)
        return await self._live_backend.sell(asset, amount)
