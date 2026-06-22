"""Spot V1 momentum, structure, VWAP, ATR and relative-volume signal."""

from __future__ import annotations

from backend.app.agent.signals.base import SignalModule, SignalPayload, SignalResult
from backend.app.agent.signals.common.indicators import (
    Candle,
    atr,
    clamp,
    ema,
    relative_volume,
    rsi,
    sanitize_candles,
    vwap,
)
from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger

logger = get_logger("agent.signals.spot")
MIN_SPOT_CANDLES = 50
SPOT_WARMUP_CANDLES = 100
# Distanza minima dello stop-loss dall'entry: evita stop troppo stretti quando l'ATR su 5m e' minimo.
SPOT_MIN_STOP_DISTANCE_PCT = 1.0


class SpotMomentumSignal(SignalModule[SignalPayload, SignalResult]):
    """Evaluate the Spot V1 plan: momentum plus price structure."""

    name = "spot_momentum_v1"

    def __init__(self, settings: Settings | None = None, feed: BinanceKlineFeed | None = None) -> None:
        self.settings = settings or get_settings()
        self.feed = feed or BinanceKlineFeed(timeout_seconds=self.settings.market_data_request_timeout_seconds)

    async def evaluate(self, payload: SignalPayload) -> SignalResult:
        candles = sanitize_candles(payload.get("candles", []))
        if len(candles) < MIN_SPOT_CANDLES:
            candles = await self._warmup_candles(payload, existing=candles)

        if len(candles) < MIN_SPOT_CANDLES:
            return {
                "signal_id": payload.get("signal_id"),
                "market": "spot",
                "asset": payload.get("asset"),
                "action": "skip",
                "quality": 0.0,
                "reason": "insufficient_ohlcv_history",
                "components": {"candle_count": len(candles), "required_candles": MIN_SPOT_CANDLES},
            }

        closes = [candle.close for candle in candles]
        current = candles[-1].close
        previous = candles[-2].close
        current_vwap = vwap(candles[-100:])
        current_atr = atr(candles)
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        current_rsi = rsi(closes)
        rel_volume = relative_volume(candles)
        volatility_pct = abs(current - previous) / previous * 100 if previous > 0 else 0.0

        trend_score = 0.0
        if current_vwap and current > current_vwap:
            trend_score += 0.45
        if ema20 and ema50 and ema20 > ema50:
            trend_score += 0.35
        if current > max(candle.high for candle in candles[-20:-1]):
            trend_score += 0.20

        volume_threshold = max(0.1, self.settings.spot_relative_volume_threshold)
        volume_score = clamp((rel_volume or 0.0) / volume_threshold)
        rsi_score = _rsi_score(current_rsi)
        btc_context_score = clamp(float(payload.get("btc_context_score", 0.5)))
        sentiment_score = clamp(float(payload.get("sentiment_score", 0.5)))
        extension_ratio = (
            (current - current_vwap) / current_atr
            if current_vwap and current_atr and current_atr > 0
            else 0.0
        )
        extension_ok = extension_ratio <= self.settings.spot_vwap_atr_extension_limit

        weights = {
            "trend_structure": self.settings.spot_trend_structure_weight_pct,
            "relative_volume": self.settings.spot_relative_volume_weight_pct,
            "btc_context": self.settings.spot_btc_context_weight_pct,
            "rsi": self.settings.spot_rsi_weight_pct,
            "sentiment": self.settings.spot_sentiment_weight_pct,
        }
        weight_total = sum(weights.values()) or 1.0
        quality = (
            trend_score * weights["trend_structure"]
            + volume_score * weights["relative_volume"]
            + btc_context_score * weights["btc_context"]
            + rsi_score * weights["rsi"]
            + sentiment_score * weights["sentiment"]
        ) / weight_total

        trigger = (
            volatility_pct >= self.settings.spot_volatility_trigger_pct
            and (rel_volume or 0.0) >= self.settings.spot_relative_volume_threshold
            and trend_score >= 0.55
            and extension_ok
        )
        action = "enter_long" if trigger and quality >= self.settings.spot_confidence_threshold else "skip"
        atr_stop = current - (current_atr or 0.0) * self.settings.spot_atr_stop_multiplier
        min_stop = current * (1 - SPOT_MIN_STOP_DISTANCE_PCT / 100)
        stop_loss = min(atr_stop, min_stop)
        take_profit_1 = current * (1 + self.settings.spot_partial_take_profit_pct / 100)
        # TP2 (uscita finale) a distanza doppia rispetto a TP1: lascia correre il residuo.
        take_profit_2 = current * (1 + 2 * self.settings.spot_partial_take_profit_pct / 100)
        trailing_stop = current * (1 - self.settings.spot_trailing_distance_pct / 100)

        return {
            "signal_id": payload.get("signal_id"),
            "market": "spot",
            "asset": payload.get("asset"),
            "action": action,
            "quality": round(quality, 4),
            "confidence": round(quality, 4),
            "price": current,
            "stop_loss": stop_loss if stop_loss > 0 else None,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "trailing_stop": trailing_stop,
            "reason": "momentum_confirmed" if action == "enter_long" else "spot_filters_not_satisfied",
            "components": {
                "trend_structure": round(trend_score, 4),
                "relative_volume": round(rel_volume or 0.0, 4),
                "volume_score": round(volume_score, 4),
                "rsi": round(current_rsi, 2) if current_rsi is not None else None,
                "rsi_score": round(rsi_score, 4),
                "vwap": current_vwap,
                "atr": current_atr,
                "ema20": ema20,
                "ema50": ema50,
                "volatility_pct": round(volatility_pct, 4),
                "vwap_atr_extension": round(extension_ratio, 4),
                "extension_ok": extension_ok,
            },
        }

    async def _warmup_candles(self, payload: SignalPayload, *, existing: list[Candle]) -> list[Candle]:
        existing_count = len(existing)
        symbol = _spot_symbol(payload)
        if not symbol:
            logger.info("spot_ohlcv_warmup_skipped", reason="symbol_unavailable", existing_count=existing_count)
            return existing
        try:
            candles = await self.feed.fetch(
                symbol=symbol,
                interval="5m",
                limit=SPOT_WARMUP_CANDLES,
                market="spot",
            )
        except Exception as exc:
            logger.warning("spot_ohlcv_warmup_failed", symbol=symbol, error=str(exc), existing_count=existing_count)
            return existing
        logger.info("spot_ohlcv_warmup_loaded", symbol=symbol, candle_count=len(candles), existing_count=existing_count)
        return candles


def _spot_symbol(payload: SignalPayload) -> str | None:
    raw_symbol = payload.get("symbol") or payload.get("binance_symbol")
    if raw_symbol:
        return str(raw_symbol).strip().upper()
    asset = str(payload.get("asset") or "").strip().upper()
    if not asset:
        return None
    quote = str(payload.get("quote_asset") or "USDT").strip().upper()
    return f"{asset}{quote}"


def _rsi_score(value: float | None) -> float:
    if value is None:
        return 0.0
    if 45 <= value <= 72:
        return 1.0
    if 35 <= value < 45 or 72 < value <= 80:
        return 0.55
    return 0.15
