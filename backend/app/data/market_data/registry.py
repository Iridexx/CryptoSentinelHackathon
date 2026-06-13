"""Global manual provider selector with no automatic fallback."""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
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
        resolved = await self.active.resolve_asset_identities(asset_ids)
        if self._active is not ProviderName.CMC:
            return resolved
        resolved_ids = {identity.app_id for identity in resolved}
        unresolved = [asset_id for asset_id in asset_ids if asset_id not in resolved_ids]
        if not unresolved:
            return resolved
        identity_source = self._providers[ProviderName.COINGECKO]
        try:
            hints = await identity_source.resolve_asset_identities(unresolved)
        except ProviderError:
            return resolved
        return resolved + await self.active.resolve_asset_identities(unresolved, hints)

    async def get_market_list(
        self,
        currency: str,
        limit: int,
        page: int = 1,
        asset_ids: list[str] | None = None,
    ) -> list[MarketAsset]:
        if not asset_ids:
            return await self.active.get_market_list(currency, limit, page)
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
        return [
            item.model_copy(update={"id": app_id_by_provider_id.get(item.id, item.id)})
            for item in items
        ]

    async def get_prices(
        self,
        asset_ids: list[str],
        currencies: list[str],
    ) -> list[PriceQuote]:
        identities = await self._active_identities(asset_ids)
        app_id_by_provider_id = {
            identity.provider_id: identity.app_id for identity in identities
        }
        quotes = await self.active.get_prices(list(app_id_by_provider_id), currencies)
        return [
            quote.model_copy(
                update={"asset_id": app_id_by_provider_id.get(quote.asset_id, quote.asset_id)}
            )
            for quote in quotes
        ]

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
