"""Global manual provider selector with no automatic fallback."""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
from backend.app.data.market_data.base import MarketDataProvider, ProviderName, ProviderRuntimeStatus
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


@lru_cache
def get_market_data_registry() -> MarketDataRegistry:
    """Return the process-wide provider selector."""

    return MarketDataRegistry(get_settings())
