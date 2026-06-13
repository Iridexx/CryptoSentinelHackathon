"""Shared HTTP provider plumbing with cache, throttling, and credit accounting."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.app.data.market_data.base import ProviderError
from backend.app.data.market_data.cache import TTLCache
from backend.app.data.market_data.rate_limit import AsyncRateLimiter


class CachedHttpProvider:
    """Base helper for provider adapters."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        requests_per_minute: int,
        cache_ttl_seconds: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.rate_limiter = AsyncRateLimiter(requests_per_minute)
        self.cache = TTLCache(cache_ttl_seconds)
        self._client = client
        self.credits_used = 0
        self.requests_made = 0

    @staticmethod
    def _cache_key(path: str, params: Mapping[str, Any]) -> str:
        normalized = sorted((key, str(value)) for key, value in params.items() if value is not None)
        return f"{path}?{urlencode(normalized)}"

    async def _request_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
        estimated_credits: int = 0,
        cache_ttl_seconds: int | None = None,
    ) -> Any:
        key = self._cache_key(path, params)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        await self.rate_limiter.acquire()
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        owns_client = self._client is None
        try:
            response = await client.get(f"{self.base_url}{path}", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Provider request failed for {path}: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        self.requests_made += 1
        status = payload.get("status", {}) if isinstance(payload, dict) else {}
        self.credits_used += int(status.get("credit_count") or estimated_credits)
        self.cache.set(key, payload, cache_ttl_seconds)
        return payload
