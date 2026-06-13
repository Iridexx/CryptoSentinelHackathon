from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.data.market_data.base import (
    MarketAsset,
    MarketDataProvider,
    OHLCVBar,
    PriceQuote,
    ProviderName,
)
from backend.app.data.market_data.cmc import CMCProvider
from backend.app.data.market_data.coingecko import CoinGeckoProvider
from backend.app.data.market_data.credits import CreditBudget
from backend.app.data.market_data.registry import MarketDataRegistry


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "eligible_tokens": [f"TOKEN_{index}" for index in range(149)],
        "cmc_api_key": "test-key",
        "cmc_base_url": "https://cmc.test",
        "coingecko_base_url": "https://coingecko.test",
        "market_data_cache_ttl_seconds": 60,
    }
    values.update(overrides)
    return Settings.model_construct(**values)


class StubProvider(MarketDataProvider):
    def __init__(self, name: ProviderName) -> None:
        self.name = name
        self.calls = 0

    async def get_prices(self, asset_ids: list[str], currencies: list[str]) -> list[PriceQuote]:
        self.calls += 1
        return [
            PriceQuote(
                asset_id=asset_ids[0],
                currency=currencies[0],
                price=1.0,
                provider=self.name,
                provider_id="1",
            )
        ]

    async def get_ohlcv(
        self,
        asset_id: str,
        currency: str,
        days: int,
        interval: str | None = None,
    ) -> list[OHLCVBar]:
        del days, interval
        return [
            OHLCVBar(
                timestamp=datetime.now(UTC),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=10,
                currency=currency,
                provider=self.name,
            )
        ]

    async def search(self, query: str, currency: str, limit: int = 25) -> list[MarketAsset]:
        del query, limit
        return await self.get_market_list(currency, 1)

    async def get_market_list(
        self,
        currency: str,
        limit: int,
        page: int = 1,
        asset_ids: list[str] | None = None,
    ) -> list[MarketAsset]:
        del limit, page, asset_ids
        self.calls += 1
        return [
            MarketAsset(
                id="bitcoin",
                symbol="BTC",
                name="Bitcoin",
                price=100,
                volume_24h=50,
                currency=currency,
                provider=self.name,
                provider_id="1",
            )
        ]

    def status(self):
        from backend.app.data.market_data.base import ProviderRuntimeStatus

        return ProviderRuntimeStatus(
            name=self.name,
            configured=True,
            cache_entries=0,
            credits_used=0,
            requests_made=self.calls,
            requests_per_minute=60,
        )


@pytest.mark.asyncio
async def test_global_selector_routes_calls_to_selected_provider() -> None:
    cmc = StubProvider(ProviderName.CMC)
    coingecko = StubProvider(ProviderName.COINGECKO)
    registry = MarketDataRegistry(
        settings(),
        providers={ProviderName.CMC: cmc, ProviderName.COINGECKO: coingecko},
    )

    await registry.active.get_market_list("usd", 1)
    assert cmc.calls == 1
    assert coingecko.calls == 0

    registry.select(ProviderName.COINGECKO)
    await registry.active.get_market_list("usd", 1)
    assert cmc.calls == 1
    assert coingecko.calls == 1


@pytest.mark.asyncio
async def test_cmc_and_coingecko_normalize_to_same_market_asset_shape() -> None:
    def cmc_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-CMC_PRO_API_KEY"] == "test-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "name": "Bitcoin",
                        "symbol": "BTC",
                        "slug": "bitcoin",
                        "cmc_rank": 1,
                        "quote": {
                            "USD": {
                                "price": 100,
                                "volume_24h": 50,
                                "market_cap": 1000,
                                "percent_change_24h": 2,
                            }
                        },
                    }
                ],
                "status": {"credit_count": 1},
            },
        )

    def gecko_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "bitcoin",
                    "name": "Bitcoin",
                    "symbol": "btc",
                    "current_price": 100,
                    "total_volume": 50,
                    "market_cap": 1000,
                    "market_cap_rank": 1,
                    "price_change_percentage_24h": 2,
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(cmc_handler)) as cmc_client:
        cmc_items = await CMCProvider(settings(), cmc_client).get_market_list("usd", 1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(gecko_handler)) as gecko_client:
        gecko_items = await CoinGeckoProvider(settings(), gecko_client).get_market_list("usd", 1)

    assert cmc_items[0].model_fields_set >= {"id", "symbol", "name", "price", "volume_24h", "provider"}
    assert gecko_items[0].model_fields_set >= {"id", "symbol", "name", "price", "volume_24h", "provider"}
    assert cmc_items[0].id == gecko_items[0].id == "bitcoin"
    assert cmc_items[0].symbol == gecko_items[0].symbol == "BTC"


@pytest.mark.asyncio
async def test_cmc_cache_avoids_duplicate_credit_consumption() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "data": [{
                    "id": 1,
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "slug": "bitcoin",
                    "quote": {"USD": {"price": 100}},
                }],
                "status": {"credit_count": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CMCProvider(settings(), client)
        await provider.get_market_list("usd", 1)
        remaining_after_first = provider.credit_budget.remaining
        await provider.get_market_list("usd", 1)

    assert calls == 1
    assert provider.credits_used == 1
    assert provider.credit_budget.remaining == remaining_after_first


def test_cmc_credit_thresholds() -> None:
    budget = CreditBudget(monthly_limit=100, warning_threshold_pct=20, critical_threshold_pct=10)
    budget.consume(80)
    assert budget.level == "warning"
    budget.consume(10)
    assert budget.level == "critical"
    budget.consume(10)
    assert budget.level == "exhausted"


@pytest.mark.asyncio
async def test_cmc_v3_quote_array_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map"):
            return httpx.Response(
                200,
                json={"data": [{"id": 1, "name": "Bitcoin", "symbol": "BTC", "slug": "bitcoin"}]},
            )
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "slug": "bitcoin",
                    "quote": [{"symbol": "USD", "price": 100.0, "volume_24h": 50.0}],
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quotes = await CMCProvider(settings(), client).get_prices(["bitcoin"], ["usd"])

    assert len(quotes) == 1
    assert quotes[0].asset_id == "bitcoin"
    assert quotes[0].currency == "usd"
    assert quotes[0].price == 100.0


@pytest.mark.asyncio
async def test_cmc_historical_ohlcv_is_split_into_30_day_windows() -> None:
    requested_windows: list[tuple[datetime, datetime]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map"):
            return httpx.Response(
                200,
                json={"data": [{"id": 1, "name": "Bitcoin", "symbol": "BTC", "slug": "bitcoin"}]},
            )
        assert request.url.path == "/v2/cryptocurrency/ohlcv/historical"
        start = datetime.fromisoformat(request.url.params["time_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(request.url.params["time_end"].replace("Z", "+00:00"))
        requested_windows.append((start, end))

        def point(timestamp: datetime) -> dict:
            iso = timestamp.isoformat().replace("+00:00", "Z")
            return {
                "time_open": iso,
                "quote": {
                    "USD": {
                        "open": 100,
                        "high": 110,
                        "low": 90,
                        "close": 105,
                        "volume": 50,
                        "timestamp": iso,
                    }
                },
            }

        return httpx.Response(
            200,
            json={
                "data": {
                    "id": 1,
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "quotes": [point(start), point(end)],
                },
                "status": {"credit_count": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bars = await CMCProvider(settings(), client).get_ohlcv("bitcoin", "usd", 75, "daily")

    assert len(requested_windows) == 3
    assert all((end - start).total_seconds() <= 30 * 24 * 3600 for start, end in requested_windows)
    assert requested_windows[0][1] == requested_windows[1][0]
    assert requested_windows[1][1] == requested_windows[2][0]
    assert len(bars) == 4
    assert bars == sorted(bars, key=lambda bar: bar.timestamp)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_coingecko_smoke() -> None:
    provider = CoinGeckoProvider(
        settings(
            coingecko_base_url="https://api.coingecko.com/api/v3",
            coingecko_requests_per_minute=10,
        )
    )
    items = await provider.get_market_list("usd", 1)
    assert items and items[0].price > 0
    assert items[0].provider is ProviderName.COINGECKO


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_cmc_smoke() -> None:
    api_key = os.getenv("CMC_API_KEY")
    if not api_key:
        pytest.skip("CMC_API_KEY is not present in the test process; real CMC call not executed")
    provider = CMCProvider(
        settings(
            cmc_api_key=api_key,
            cmc_base_url="https://pro-api.coinmarketcap.com",
        )
    )
    items = await provider.get_market_list("usd", 1)
    assert items and items[0].price > 0
    assert items[0].provider is ProviderName.CMC


def test_frontend_has_no_direct_coingecko_api_calls() -> None:
    root = Path(__file__).resolve().parents[3]
    offenders = []
    for path in (root / "src").rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if "api.coingecko.com" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(root).as_posix())
    assert offenders == []


def test_notification_checker_depends_on_registry() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "backend/app/notifications/price_checker.py").read_text(encoding="utf-8")
    assert "get_market_data_registry" in source
    assert "api.coingecko.com" not in source
