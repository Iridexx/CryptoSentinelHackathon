"""Global manual provider selector with no automatic fallback."""

from __future__ import annotations

from functools import lru_cache
from time import perf_counter

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.data.market_data.base import (
    AssetIdentity,
    MarketAsset,
    MarketDataProvider,
    OHLCVBar,
    PriceQuote,
    ProviderName,
    ProviderError,
    ProviderRuntimeStatus,
)
from backend.app.data.market_data.cmc import CMCProvider
from backend.app.data.market_data.coingecko import CoinGeckoProvider

logger = get_logger("market_data.registry")


class MarketDataRegistry:
    """Own provider instances and expose one global active provider."""

    def __init__(
        self,
        settings: Settings,
        providers: dict[ProviderName, MarketDataProvider] | None = None,
    ) -> None:
        self.settings = settings
        self._providers = providers or {
            ProviderName.CMC: CMCProvider(settings),
            ProviderName.COINGECKO: CoinGeckoProvider(settings),
        }
        self._active = ProviderName(settings.market_data_provider)

    @property
    def active_name(self) -> ProviderName:
        return self._active

    @property
    def active(self) -> MarketDataProvider:
        return self._providers[self._active]

    def select(self, provider: ProviderName) -> ProviderRuntimeStatus:
        """Apply an explicit global selection; never fall back automatically."""

        if provider not in self._providers:
            raise ValueError(f"Unsupported market data provider: {provider}")
        self._active = provider
        return self.active.status()

    def statuses(self) -> list[ProviderRuntimeStatus]:
        return [provider.status() for provider in self._providers.values()]

    async def _active_identities(self, asset_ids: list[str]) -> list[AssetIdentity]:
        started = perf_counter()
        if self._active is not ProviderName.CMC:
            identities = await self.active.resolve_asset_identities(asset_ids)
            logger.info(
                "identity_resolution_completed",
                provider=self._active.value,
                requested_count=len(asset_ids),
                resolved_count=len(identities),
                unresolved_ids=[asset_id for asset_id in asset_ids if asset_id not in {item.app_id for item in identities}],
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
            )
            return identities
        identity_source = self._providers[ProviderName.COINGECKO]
        try:
            hints = await identity_source.resolve_asset_identities(asset_ids)
        except ProviderError as exc:
            logger.warning(
                "identity_hint_failed",
                requested_count=len(asset_ids),
                error_type=type(exc).__name__,
            )
            hints = []
        identities = await self.active.resolve_asset_identities(asset_ids, hints)
        resolved_ids = {item.app_id for item in identities}
        logger.info(
            "identity_resolution_completed",
            provider=self._active.value,
            requested_count=len(asset_ids),
            hint_count=len(hints),
            resolved_count=len(identities),
            unresolved_ids=[asset_id for asset_id in asset_ids if asset_id not in resolved_ids],
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
        )
        return identities

    async def get_market_list(
        self,
        currency: str,
        limit: int,
        page: int = 1,
        asset_ids: list[str] | None = None,
    ) -> list[MarketAsset]:
        started = perf_counter()
        if not asset_ids:
            items = await self.active.get_market_list(currency, limit, page)
            logger.info(
                "market_list_completed",
                provider=self._active.value,
                mode="ranked",
                requested_count=limit,
                returned_count=len(items),
                page=page,
                currency=currency.lower(),
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
            )
            return items
        identities = await self._active_identities(asset_ids)
        app_id_by_provider_id = {
            identity.provider_id: identity.app_id for identity in identities
        }
        items = await self.active.get_market_list(
            currency,
            limit,
            page,
            list(app_id_by_provider_id),
        )
        normalized = [
            item.model_copy(update={"id": app_id_by_provider_id.get(item.id, item.id)})
            for item in items
        ]
        logger.info(
            "market_list_completed",
            provider=self._active.value,
            mode="ids",
            requested_count=len(asset_ids),
            identity_count=len(identities),
            returned_count=len(normalized),
            missing_ids=[asset_id for asset_id in asset_ids if asset_id not in {item.id for item in normalized}],
            currency=currency.lower(),
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
        )
        return normalized

    async def get_prices(
        self,
        asset_ids: list[str],
        currencies: list[str],
    ) -> list[PriceQuote]:
        started = perf_counter()
        identities = await self._active_identities(asset_ids)
        app_id_by_provider_id = {
            identity.provider_id: identity.app_id for identity in identities
        }
        quotes = await self.active.get_prices(list(app_id_by_provider_id), currencies)
        normalized = [
            quote.model_copy(
                update={"asset_id": app_id_by_provider_id.get(quote.asset_id, quote.asset_id)}
            )
            for quote in quotes
        ]
        logger.info(
            "price_list_completed",
            provider=self._active.value,
            requested_asset_count=len(asset_ids),
            identity_count=len(identities),
            returned_quote_count=len(normalized),
            currencies=currencies,
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
        )
        return normalized

    async def search(self, query: str, currency: str, limit: int) -> list[MarketAsset]:
        started = perf_counter()
        items = await self.active.search(query, currency, limit)
        logger.info(
            "market_search_completed",
            provider=self._active.value,
            query=query,
            requested_count=limit,
            returned_count=len(items),
            currency=currency.lower(),
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
        )
        return items

    async def get_ohlcv(
        self,
        asset_id: str,
        currency: str,
        days: int,
        interval: str | None = None,
    ) -> list[OHLCVBar]:
        identities = await self._active_identities([asset_id])
        if not identities:
            return []
        return await self.active.get_ohlcv(
            identities[0].provider_id,
            currency,
            days,
            interval,
        )


@lru_cache
def get_market_data_registry() -> MarketDataRegistry:
    """Return the process-wide provider selector."""

    return MarketDataRegistry(get_settings())
