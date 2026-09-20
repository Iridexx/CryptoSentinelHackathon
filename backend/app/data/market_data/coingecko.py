"""CoinGecko adapter preserving the existing application data source."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from backend.app.core.config import Settings
from backend.app.data.market_data.aliases import coingecko_id_for_app_id
from backend.app.data.market_data.base import (
    AssetIdentity,
    MarketAsset,
    MarketDataProvider,
    OHLCVBar,
    PriceQuote,
    ProviderName,
    ProviderRuntimeStatus,
)
from backend.app.data.market_data.http import CachedHttpProvider


def _identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _timestamp_ms(value: int | float) -> datetime:
    return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)


class CoinGeckoProvider(CachedHttpProvider, MarketDataProvider):
    """Normalize CoinGecko REST responses behind MarketDataProvider."""

    name = ProviderName.COINGECKO

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(
            base_url=settings.coingecko_base_url,
            timeout_seconds=settings.market_data_request_timeout_seconds,
            requests_per_minute=settings.coingecko_requests_per_minute,
            cache_ttl_seconds=settings.market_data_cache_ttl_seconds,
            client=client,
        )

    async def resolve_asset_identities(
        self,
        asset_ids: list[str],
        identity_hints: list[AssetIdentity] | None = None,
    ) -> list[AssetIdentity]:
        del identity_hints
        if not asset_ids:
            return []
        provider_ids = [coingecko_id_for_app_id(asset_id) for asset_id in asset_ids]
        payload = await self._request_json(
            "/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ",".join(provider_ids),
                "order": "market_cap_desc",
                "per_page": min(len(provider_ids), 250),
                "page": 1,
                "sparkline": "false",
            },
            cache_ttl_seconds=86_400,
        )
        found = {str(item["id"]): item for item in payload}
        identities: list[AssetIdentity] = []
        for asset_id, provider_id in zip(asset_ids, provider_ids):
            item = found.get(provider_id)
            if item is None:
                continue
            identities.append(
                AssetIdentity(
                    app_id=asset_id,
                    provider_id=provider_id,
                    symbol=str(item.get("symbol", "")).upper(),
                    name=str(item.get("name", provider_id)),
                )
            )
        resolved = {identity.app_id for identity in identities}
        for asset_id in asset_ids:
            if asset_id not in resolved:
                identity = await self._search_identity(asset_id)
                if identity is not None:
                    identities.append(identity)
        return identities

    async def _search_identity(self, asset_id: str) -> AssetIdentity | None:
        """Resolve an ID unknown to CoinGecko (e.g. a CMC slug) by exact name match.

        Only a name equal to the slug is accepted, so a fuzzy hit never maps an
        alert onto the wrong asset; among homonyms the best-ranked one wins.
        """

        wanted = _identity_key(asset_id)
        payload = await self._request_json(
            "/search",
            params={"query": asset_id.replace("-", " ")},
            cache_ttl_seconds=86_400,
        )
        candidates = [
            coin
            for coin in payload.get("coins", [])
            if _identity_key(str(coin.get("name", ""))) == wanted
        ]
        if not candidates:
            return None
        best = min(candidates, key=lambda coin: coin.get("market_cap_rank") or 10**9)
        return AssetIdentity(
            app_id=asset_id,
            provider_id=str(best["id"]),
            symbol=str(best.get("symbol", "")).upper(),
            name=str(best.get("name", best["id"])),
        )

    @staticmethod
    def _asset(item: dict[str, Any], currency: str) -> MarketAsset:
        return MarketAsset(
            id=str(item["id"]),
            symbol=str(item.get("symbol", "")).upper(),
            name=str(item.get("name", item["id"])),
            image_url=item.get("image"),
            price=float(item.get("current_price") or 0.0),
            percent_change_1h=item.get("price_change_percentage_1h_in_currency"),
            percent_change_24h=item.get("price_change_percentage_24h"),
            percent_change_7d=item.get("price_change_percentage_7d_in_currency"),
            market_cap=item.get("market_cap"),
            market_cap_rank=item.get("market_cap_rank"),
            volume_24h=item.get("total_volume"),
            high_24h=item.get("high_24h"),
            low_24h=item.get("low_24h"),
            currency=currency.lower(),
            provider=ProviderName.COINGECKO,
            provider_id=str(item["id"]),
            last_updated=item.get("last_updated"),
        )

    async def get_prices(self, asset_ids: list[str], currencies: list[str]) -> list[PriceQuote]:
        if not asset_ids or not currencies:
            return []
        payload = await self._request_json(
            "/simple/price",
            params={
                "ids": ",".join(asset_ids),
                "vs_currencies": ",".join(currency.lower() for currency in currencies),
                "include_last_updated_at": "true",
            },
        )
        quotes: list[PriceQuote] = []
        for asset_id, values in payload.items():
            last_updated = values.get("last_updated_at")
            for currency in currencies:
                normalized_currency = currency.lower()
                value = values.get(normalized_currency)
                if value is None:
                    continue
                quotes.append(
                    PriceQuote(
                        asset_id=asset_id,
                        currency=normalized_currency,
                        price=float(value),
                        provider=self.name,
                        provider_id=asset_id,
                        last_updated=datetime.fromtimestamp(last_updated, tz=UTC) if last_updated else None,
                    )
                )
        return quotes

    async def get_ohlcv(
        self,
        asset_id: str,
        currency: str,
        days: int,
        interval: str | None = None,
    ) -> list[OHLCVBar]:
        del interval
        allowed_days = 1 if days <= 1 else 7 if days <= 7 else 30 if days <= 30 else 365
        payload = await self._request_json(
            f"/coins/{asset_id}/ohlc",
            params={"vs_currency": currency.lower(), "days": allowed_days},
        )
        return [
            OHLCVBar(
                timestamp=_timestamp_ms(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=None,
                currency=currency.lower(),
                provider=self.name,
            )
            for row in payload
        ]

    async def search(self, query: str, currency: str, limit: int = 25) -> list[MarketAsset]:
        search_payload = await self._request_json("/search", params={"query": query})
        ids = [str(item["id"]) for item in search_payload.get("coins", [])[:limit]]
        if not ids:
            return []
        return await self.get_market_list(currency, limit, asset_ids=ids)

    async def get_market_list(
        self,
        currency: str,
        limit: int,
        page: int = 1,
        asset_ids: list[str] | None = None,
    ) -> list[MarketAsset]:
        base_params = {
            "vs_currency": currency.lower(),
            "ids": ",".join(asset_ids) if asset_ids else None,
            "order": "market_cap_desc",
            "sparkline": "false",
            "price_change_percentage": "1h,24h,7d",
        }
        if asset_ids or limit <= 250:
            payload = await self._request_json(
                "/coins/markets",
                params={**base_params, "per_page": min(limit, 250), "page": page},
            )
            return [self._asset(item, currency) for item in payload]

        start_index = (page - 1) * limit
        end_index = start_index + limit
        first_api_page = start_index // 250 + 1
        last_api_page = (end_index - 1) // 250 + 1
        payload: list[dict[str, Any]] = []
        for api_page in range(first_api_page, last_api_page + 1):
            chunk = await self._request_json(
                "/coins/markets",
                params={**base_params, "per_page": 250, "page": api_page},
            )
            payload.extend(chunk)
        offset = start_index % 250
        return [self._asset(item, currency) for item in payload[offset : offset + limit]]

    def status(self) -> ProviderRuntimeStatus:
        return ProviderRuntimeStatus(
            name=self.name,
            configured=True,
            cache_entries=len(self.cache),
            credits_used=self.credits_used,
            requests_made=self.requests_made,
            requests_per_minute=self.rate_limiter.requests_per_minute,
        )
