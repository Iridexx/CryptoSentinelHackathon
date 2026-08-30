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


async def build_reserve_service(
    session: AsyncSession,
    settings: Settings,
    *,
    feed: BinanceKlineFeed | None = None,
    now_fn=None,
) -> ReserveService:
    table = await fetch_reserve_prices(settings, feed=feed)
    executor = ReserveExecutor(settings, price_source=price_source_from_map(table))
    kwargs: dict = {"executor": executor, "settings": settings}
    if now_fn is not None:
        kwargs["now_fn"] = now_fn
    return ReserveService(session, **kwargs)
