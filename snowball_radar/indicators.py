"""Pure-Python technical indicators.

All functions take sequences ordered oldest -> newest. Series outputs have the
same length as the input, with ``None`` where the indicator is not yet defined.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

Series = list[Optional[float]]


def sma(values: Sequence[float], period: int) -> Series:
    _check_period(period)
    out: Series = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: Sequence[float], period: int) -> Series:
    """EMA seeded with the SMA of the first ``period`` values."""
    _check_period(period)
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: Sequence[float], period: int = 14) -> Series:
    """Wilder's RSI."""
    _check_period(period)
    out: Series = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / period, losses / period
    out[period] = _rsi_value(avg_g, avg_l)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        out[i] = _rsi_value(avg_g, avg_l)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    out = []
    for i in range(len(closes)):
        if i == 0:
            out.append(highs[0] - lows[0])
        else:
            pc = closes[i - 1]
            out.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return out


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> Series:
    """Wilder's ATR."""
    _check_period(period)
    tr = true_range(highs, lows, closes)
    out: Series = [None] * len(tr)
    if len(tr) < period:
        return out
    prev = sum(tr[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(tr)):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def roc(values: Sequence[float], period: int) -> Optional[float]:
    """Percent rate of change of the last value vs ``period`` bars ago."""
    if len(values) <= period or values[-1 - period] == 0:
        return None
    return (values[-1] / values[-1 - period] - 1.0) * 100.0


def stdev(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = sum(values) / n
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def zscore_last(values: Sequence[float], lookback: int) -> Optional[float]:
    """Z-score of the last value against the preceding ``lookback`` values."""
    if len(values) < lookback + 1:
        return None
    base = values[-1 - lookback:-1]
    sd = stdev(base)
    mean = sum(base) / len(base)
    if sd == 0:
        return 0.0
    return (values[-1] - mean) / sd


def bollinger_width(closes: Sequence[float], period: int = 20, mult: float = 2.0) -> Series:
    """(upper - lower) / middle for each bar."""
    _check_period(period)
    out: Series = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        mid = sum(window) / period
        if mid == 0:
            continue
        out[i] = (2 * mult * stdev_population(window)) / mid
    return out


def stdev_population(values: Sequence[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    m = sum(values) / n
    return math.sqrt(sum((v - m) ** 2 for v in values) / n)


def percentile_rank(values: Sequence[float], value: float) -> float:
    """Fraction (0..1) of ``values`` that are <= ``value``."""
    if not values:
        return 0.5
    return sum(1 for v in values if v <= value) / len(values)


def linreg_slope_pct(values: Sequence[float]) -> Optional[float]:
    """Least-squares slope per bar, expressed as % of the mean value."""
    n = len(values)
    if n < 2:
        return None
    xm = (n - 1) / 2.0
    ym = sum(values) / n
    num = sum((i - xm) * (v - ym) for i, v in enumerate(values))
    den = sum((i - xm) ** 2 for i in range(n))
    if den == 0 or ym == 0:
        return None
    return (num / den) / ym * 100.0


def swing_lows(lows: Sequence[float], window: int = 2) -> list[float]:
    """Pivot lows: a bar whose low is the minimum of +/- ``window`` neighbours."""
    out = []
    for i in range(window, len(lows) - window):
        seg = lows[i - window:i + window + 1]
        if lows[i] == min(seg):
            out.append(lows[i])
    return out


def last(series: Series) -> Optional[float]:
    for v in reversed(series):
        if v is not None:
            return v
    return None


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _check_period(period: int) -> None:
    if period < 1:
        raise ValueError("period must be >= 1")
