"""Provider-neutral market data access."""

from backend.app.data.market_data.base import (
    AssetIdentity,
    MarketAsset,
    MarketDataProvider,
    OHLCVBar,
    PriceQuote,
    ProviderCapabilityError,
    ProviderName,
)
from backend.app.data.market_data.registry import MarketDataRegistry, get_market_data_registry

__all__ = [
    "AssetIdentity",
    "MarketAsset",
    "MarketDataProvider",
    "MarketDataRegistry",
    "OHLCVBar",
    "PriceQuote",
    "ProviderCapabilityError",
    "ProviderName",
    "get_market_data_registry",
]
