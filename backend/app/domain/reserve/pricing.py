"""Price source for reserve assets + a ready-to-use ReserveService factory.

The reserve values BTC/ETH/BNB/SOL/TRX with the Binance **spot** ticker (the same
family of feeds the signal engine uses). One batch call per operation; the result
backs a dict price source so ``ReserveExecutor`` never hits the network per asset.
Shared by the API routes (R5) and the slow tick (R6).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed
from backend.app.core.config import Settings
from backend.app.core.logging import get_logger
from backend.app.domain.reserve.executor import ReserveExecutor
from backend.app.domain.reserve.service import ReserveService

logger = get_logger("domain.reserve.pricing")


async def fetch_reserve_prices(
    settings: Settings, *, feed: BinanceKlineFeed | None = None
) -> dict[str, Decimal | None]:
    """Current USD price per configured reserve asset (``{ "BTC": Decimal, ... }``)."""
    assets = [a.symbol for a in settings.reserve.assets]
    if not assets:
        return {}
    feed = feed or BinanceKlineFeed()
    try:
        got = await feed.fetch_prices(symbols=[f"{s}USDT" for s in assets], market="spot")
    except Exception as exc:  # noqa: BLE001 - degrade to "no price"
        logger.warning("reserve_prices_unavailable", error_type=type(exc).__name__)
        got = {}
    return {s: got.get(f"{s}USDT") for s in assets}


def price_source_from_map(
    table: dict[str, Decimal | None],
) -> Callable[[str], Awaitable[Decimal | None]]:
    async def _src(asset: str) -> Decimal | None:
        return table.get(asset.upper())

    return _src


def _live_enabled(settings: Settings) -> bool:
    """Live reserve execution only when the agent runs live *and* on BSC testnet.

    ``execution_mode == "live"`` already forces testnet at config load; the extra
    check keeps the reserve fail-closed if that guard is ever relaxed.
    """
    if not settings.reserve.execution_mode_inherit:
        return False
    return settings.execution_mode == "live" and settings.bsc_network == "testnet"


async def build_reserve_service(
    session: AsyncSession,
    settings: Settings,
    *,
    feed: BinanceKlineFeed | None = None,
    now_fn=None,
) -> ReserveService:
    table = await fetch_reserve_prices(settings, feed=feed)
    live = _live_enabled(settings)
    live_backend = None
    if live:
        from backend.app.domain.reserve.live_backend import PancakeSwapReserveBackend

        async def _bnb_price() -> Decimal | None:
            return table.get("BNB")

        live_backend = PancakeSwapReserveBackend(settings, bnb_price_source=_bnb_price)
    executor = ReserveExecutor(
        settings,
        price_source=price_source_from_map(table),
        live=live,
        live_backend=live_backend,
    )
    kwargs: dict = {"executor": executor, "settings": settings}
    if now_fn is not None:
        kwargs["now_fn"] = now_fn
    return ReserveService(session, **kwargs)
