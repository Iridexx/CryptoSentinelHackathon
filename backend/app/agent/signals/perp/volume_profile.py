"""Perpetual V1 rolling Volume Profile signal."""

from __future__ import annotations

from collections import defaultdict

from backend.app.agent.signals.base import SignalModule, SignalPayload, SignalResult
from backend.app.agent.signals.common.indicators import atr, sanitize_candles, vwap
from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed
from backend.app.core.config import Settings, get_settings


class VolumeProfileSignal(SignalModule[SignalPayload, SignalResult]):
    """Build 24h Volume Profile and detect mean-reversion setups."""

    name = "perp_volume_profile_v1"

    def __init__(
        self,
        settings: Settings | None = None,
        feed: BinanceKlineFeed | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.feed = feed or BinanceKlineFeed(
            futures_base_url=self.settings.binance_futures_base_url,
            timeout_seconds=self.settings.market_data_request_timeout_seconds,
        )

    async def evaluate(self, payload: SignalPayload) -> SignalResult:
        candles = sanitize_candles(payload.get("candles", []))
        if not candles and payload.get("symbol"):
            candles = await self.feed.fetch(
                symbol=str(payload["symbol"]),
                interval=f"{self.settings.perp_volume_profile_candle_minutes}m",
                limit=int(self.settings.perp_volume_profile_window_hours * 60 / self.settings.perp_volume_profile_candle_minutes),
                market="futures",
            )
        window = int(self.settings.perp_volume_profile_window_hours * 60 / self.settings.perp_volume_profile_candle_minutes)
        candles = candles[-window:]
        if len(candles) < max(24, window // 4):
            return _skip(payload, "insufficient_binance_klines")
        total_quote_volume = sum(candle.close * candle.volume for candle in candles)
        if total_quote_volume < self.settings.perp_min_volume_profile_liquidity_usd:
            return _skip(payload, "volume_profile_liquidity_filter")

        profile = _build_profile(candles)
        poc, vah, val = _value_area(profile, self.settings.perp_value_area_pct / 100)
        current = candles[-1].close
        previous = candles[-2]
        current_vwap = vwap(candles)
        current_atr = atr(candles)
        trend_bias = "above_vwap" if current_vwap and current > current_vwap else "below_vwap"

        side: str | None = None
        trigger_price = current
        if previous.close < val and current > previous.high:
            side = "long"
        elif previous.close > vah and current < previous.low:
            side = "short"

        if side == "long" and current_vwap and current < current_vwap * 0.97:
            side = None
        if side == "short" and current_vwap and current > current_vwap * 1.03:
            side = None

        direction_allowed = self.settings.perp_direction_mode
        if side == "long" and direction_allowed == "short":
            side = None
        if side == "short" and direction_allowed == "long":
            side = None

        quality = _quality(side, current, poc, vah, val, current_vwap, current_atr)
        stop_loss = None
        take_profit_1 = None
        take_profit_2 = None
        trailing_stop = None
        if side == "long":
            stop_loss = previous.low - (current_atr or 0.0) * self.settings.perp_atr_stop_multiplier
            take_profit_1 = val
            take_profit_2 = poc
            trailing_stop = current * 0.99
        elif side == "short":
            stop_loss = previous.high + (current_atr or 0.0) * self.settings.perp_atr_stop_multiplier
            take_profit_1 = vah
            take_profit_2 = poc
            trailing_stop = current * 1.01

        leverage = _dynamic_leverage(
            default=self.settings.perp_default_leverage,
            maximum=self.settings.perp_max_leverage,
            enabled=self.settings.perp_dynamic_leverage_enabled,
            atr_value=current_atr,
            price=current,
        )
        action = f"enter_{side}" if side and quality >= 0.6 else "skip"
        return {
            "signal_id": payload.get("signal_id"),
            "market": "perp",
            "asset": payload.get("asset") or payload.get("symbol"),
            "action": action,
            "side": side,
            "quality": round(quality, 4),
            "confidence": round(quality, 4),
            "price": trigger_price,
            "leverage": leverage,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "trailing_stop": trailing_stop,
            "reason": "value_reentry_confirmed" if side else "perp_filters_not_satisfied",
            "components": {
                "poc": poc,
                "vah": vah,
                "val": val,
                "vwap": current_vwap,
                "atr": current_atr,
                "trend_bias": trend_bias,
                "total_quote_volume": round(total_quote_volume, 2),
                "value_area_pct": self.settings.perp_value_area_pct,
            },
        }


def _build_profile(candles) -> dict[float, float]:
    high = max(candle.high for candle in candles)
    low = min(candle.low for candle in candles)
    tick = max((high - low) / 80, high * 0.0005)
    buckets: dict[float, float] = defaultdict(float)
    for candle in candles:
        typical = (candle.high + candle.low + candle.close) / 3
        bucket = round(round(typical / tick) * tick, 8)
        buckets[bucket] += candle.volume
    return dict(buckets)


def _value_area(profile: dict[float, float], area_pct: float) -> tuple[float, float, float]:
    ordered = sorted(profile.items())
    poc = max(ordered, key=lambda item: item[1])[0]
    total = sum(volume for _, volume in ordered)
    target = total * area_pct
    selected = {poc}
    selected_volume = profile[poc]
    while selected_volume < target and len(selected) < len(ordered):
        candidates = [(price, volume) for price, volume in ordered if price not in selected]
        next_price, next_volume = max(candidates, key=lambda item: item[1])
        selected.add(next_price)
        selected_volume += next_volume
    return poc, max(selected), min(selected)


def _quality(side: str | None, price: float, poc: float, vah: float, val: float, current_vwap: float | None, current_atr: float | None) -> float:
    if side is None:
        return 0.0
    distance_to_poc = abs(price - poc) / price if price > 0 else 1.0
    map_score = max(0.0, 1.0 - distance_to_poc * 10)
    trend_score = 0.6
    if current_vwap:
        if side == "long" and price >= current_vwap:
            trend_score = 0.8
        elif side == "short" and price <= current_vwap:
            trend_score = 0.8
    atr_score = 0.7 if current_atr and current_atr > 0 else 0.4
    value_edge = 0.8 if (side == "long" and price <= poc) or (side == "short" and price >= poc) else 0.55
    return min(1.0, map_score * 0.35 + trend_score * 0.25 + atr_score * 0.15 + value_edge * 0.25)


def _dynamic_leverage(*, default: int, maximum: int, enabled: bool, atr_value: float | None, price: float) -> int:
    leverage = min(default, maximum)
    if not enabled or not atr_value or price <= 0:
        return max(1, leverage)
    atr_pct = atr_value / price * 100
    if atr_pct > 4:
        leverage = int(leverage * 0.5)
    elif atr_pct > 2:
        leverage = int(leverage * 0.7)
    return max(1, min(maximum, leverage))


def _skip(payload: SignalPayload, reason: str) -> SignalResult:
    return {
        "signal_id": payload.get("signal_id"),
        "market": "perp",
        "asset": payload.get("asset") or payload.get("symbol"),
        "action": "skip",
        "quality": 0.0,
        "reason": reason,
        "components": {},
    }
