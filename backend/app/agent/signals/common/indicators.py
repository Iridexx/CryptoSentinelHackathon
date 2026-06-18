"""Shared technical-indicator helpers for agent signal modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class Candle:
    """Normalized OHLCV candle used by the signal engine."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def sanitize_candles(raw: Iterable[object]) -> list[Candle]:
    """Convert dict/model candle-like values into validated candles."""

    candles: list[Candle] = []
    for item in raw:
        getter = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
        timestamp = getter("timestamp")
        if not isinstance(timestamp, datetime):
            continue
        try:
            candle = Candle(
                timestamp=timestamp,
                open=float(getter("open")),
                high=float(getter("high")),
                low=float(getter("low")),
                close=float(getter("close")),
                volume=max(0.0, float(getter("volume") or 0.0)),
            )
        except (TypeError, ValueError):
            continue
        if all(isfinite(value) and value > 0 for value in (candle.open, candle.high, candle.low, candle.close)):
            candles.append(candle)
    return sorted(candles, key=lambda candle: candle.timestamp)


def ema(values: list[float], period: int) -> float | None:
    """Return the latest exponential moving average."""

    if period <= 0 or len(values) < period:
        return None
    alpha = 2 / (period + 1)
    current = sum(values[:period]) / period
    for value in values[period:]:
        current = value * alpha + current * (1 - alpha)
    return current


def vwap(candles: list[Candle]) -> float | None:
    """Return volume-weighted average price using typical price."""

    total_volume = sum(candle.volume for candle in candles)
    if total_volume <= 0:
        return None
    weighted = sum(((candle.high + candle.low + candle.close) / 3) * candle.volume for candle in candles)
    return weighted / total_volume


def atr(candles: list[Candle], period: int = 14) -> float | None:
    """Return latest Average True Range."""

    if len(candles) < period + 1:
        return None
    true_ranges: list[float] = []
    previous_close = candles[0].close
    for candle in candles[1:]:
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
        previous_close = candle.close
    return sum(true_ranges[-period:]) / period


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Return latest Relative Strength Index."""

    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes[-period - 1 : -1], closes[-period:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0
    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def relative_volume(candles: list[Candle], lookback: int = 100) -> float | None:
    """Return current candle volume divided by recent average volume."""

    if len(candles) < 2:
        return None
    previous = candles[-lookback - 1 : -1] if len(candles) > lookback else candles[:-1]
    average = sum(candle.volume for candle in previous) / len(previous)
    if average <= 0:
        return None
    return candles[-1].volume / average


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))
