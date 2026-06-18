"""Specialized Binance kline feed for the Perp Volume Profile signal."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import httpx

from backend.app.agent.signals.common.indicators import Candle

BinanceMarket = Literal["futures", "spot"]


class BinanceKlineFeedError(RuntimeError):
    """Raised when Binance klines cannot be fetched or parsed."""


class BinanceKlineFeed:
    """Fetch 5m OHLCV candles directly for the signal engine.

    This is intentionally not wired through ``MarketDataProvider`` because the
    Step 6 plan requires a specialized feed for Volume Profile.
    """

    def __init__(
        self,
        *,
        futures_base_url: str | None = None,
        spot_base_url: str = "https://api.binance.com",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.futures_base_url = (futures_base_url or "https://fapi.binance.com").rstrip("/")
        self.spot_base_url = spot_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def fetch(
        self,
        *,
        symbol: str,
        interval: str = "5m",
        limit: int = 288,
        market: BinanceMarket = "futures",
    ) -> list[Candle]:
        base_url = self.futures_base_url if market == "futures" else self.spot_base_url
        path = "/fapi/v1/klines" if market == "futures" else "/api/v3/klines"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{base_url}{path}",
                params={"symbol": symbol.upper(), "interval": interval, "limit": limit},
            )
        if response.status_code >= 400:
            raise BinanceKlineFeedError(f"binance_klines_http_{response.status_code}")
        try:
            payload = response.json()
            return [_parse_kline(row) for row in payload]
        except (TypeError, ValueError, IndexError) as exc:
            raise BinanceKlineFeedError("binance_klines_parse_failed") from exc


def _parse_kline(row: list) -> Candle:
    return Candle(
        timestamp=datetime.fromtimestamp(int(row[0]) / 1000, UTC),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )
