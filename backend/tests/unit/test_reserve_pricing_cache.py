"""Reserve price fetch: short shared cache + stale-on-error (perf/robustness)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.domain.reserve import pricing


class _Feed:
    def __init__(self, price="60000"):
        self.calls = 0
        self._price = price

    async def fetch_prices(self, *, symbols, market):
        self.calls += 1
        if self._price is None:
            raise RuntimeError("binance unreachable")
        return {s.upper(): Decimal(self._price) for s in symbols}


def _settings():
    return SimpleNamespace(
        reserve=SimpleNamespace(assets=[SimpleNamespace(symbol="BTC"), SimpleNamespace(symbol="ETH")])
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    pricing._price_cache.clear()
    yield
    pricing._price_cache.clear()


async def test_second_call_within_ttl_is_served_from_cache():
    feed = _Feed()
    s = _settings()
    a = await pricing.fetch_reserve_prices(s, feed=feed)
    b = await pricing.fetch_reserve_prices(s, feed=feed)
    assert a == b == {"BTC": Decimal("60000"), "ETH": Decimal("60000")}
    assert feed.calls == 1  # cache hit, no second upstream call


async def test_use_cache_false_forces_refresh():
    feed = _Feed()
    s = _settings()
    await pricing.fetch_reserve_prices(s, feed=feed)
    await pricing.fetch_reserve_prices(s, feed=feed, use_cache=False)
    assert feed.calls == 2


async def test_failed_refresh_serves_stale_table():
    s = _settings()
    good = _Feed("42000")
    await pricing.fetch_reserve_prices(s, feed=good)
    pricing._price_cache[",".join(sorted(["BTC", "ETH"]))] = (
        0.0,  # force "expired"
        {"BTC": Decimal("42000"), "ETH": Decimal("42000")},
    )
    down = _Feed(None)
    out = await pricing.fetch_reserve_prices(s, feed=down)
    assert out == {"BTC": Decimal("42000"), "ETH": Decimal("42000")}  # stale, not empty


async def test_error_with_no_cache_returns_none_table():
    pricing._price_cache.clear()
    out = await pricing.fetch_reserve_prices(_settings(), feed=_Feed(None))
    assert out == {"BTC": None, "ETH": None}
