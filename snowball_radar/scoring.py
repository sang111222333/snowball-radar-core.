"""Component scoring for a single symbol.

Each component returns a 0..100 score. The composite is the weighted average of
the components that could be computed (e.g. derivatives is skipped for coins
without a perpetual market and its weight is redistributed).

The "snowball" idea: a coin whose trend, participation (volume) and structure
(higher lows, compression near highs) all build on each other, without being
overheated (extreme RSI, crowded funding).
"""

from __future__ import annotations

from typing import Optional

from . import indicators as ind
from .config import RadarConfig
from .models import ComponentScore, MarketData, RadarResult


class InsufficientData(ValueError):
    pass


def score_market(data: MarketData, cfg: RadarConfig) -> RadarResult:
    candles = data.candles
    if len(candles) < cfg.min_candles:
        raise InsufficientData(
            f"{data.symbol}: need >= {cfg.min_candles} candles, got {len(candles)}"
        )

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    vols = [c.volume for c in candles]
    price = closes[-1]

    flags: list[str] = []
    metrics: dict[str, Optional[float]] = {}

    components = {
        "trend": _trend(closes, cfg, metrics, flags),
        "momentum": _momentum(closes, cfg, metrics, flags),
        "volume": _volume(candles, vols, cfg, metrics, flags),
        "structure": _structure(closes, highs, lows, cfg, metrics, flags),
    }
    if cfg.use_derivatives and data.derivatives is not None:
        deriv = _derivatives(data, closes, cfg, metrics, flags)
        if deriv is not None:
            components["derivatives"] = deriv

    # volatility risk penalty (applied to composite, not a component)
    atr_v = ind.last(ind.atr(highs, lows, closes, cfg.atr_period))
    atr_pct = (atr_v / price * 100.0) if atr_v and price else None
    metrics["atr_pct"] = atr_pct

    total_w = sum(c.weight for c in components.values())
    composite = sum(c.score * c.weight for c in components.values()) / total_w if total_w else 0.0
    if atr_pct is not None and atr_pct > cfg.max_atr_pct:
        penalty = min(20.0, (atr_pct - cfg.max_atr_pct) * 2.0)
        composite -= penalty
        flags.append("HIGH_VOLATILITY")
        metrics["volatility_penalty"] = penalty

    if data.quote_volume_24h is not None and data.quote_volume_24h < cfg.min_quote_volume:
        flags.append("LOW_LIQUIDITY")

    composite = round(ind.clamp(composite), 2)
    return RadarResult(
        symbol=data.symbol,
        price=price,
        score=composite,
        grade=cfg.grade_for(composite),
        components=components,
        flags=sorted(set(flags)),
        metrics={k: (round(v, 6) if isinstance(v, float) else v) for k, v in metrics.items()},
        quote_volume_24h=data.quote_volume_24h,
    )


# --------------------------------------------------------------------------- trend
def _trend(closes, cfg: RadarConfig, metrics, flags) -> ComponentScore:
    price = closes[-1]
    e_fast_s = ind.ema(closes, cfg.ema_fast)
    e_fast = ind.last(e_fast_s)
    e_mid = ind.last(ind.ema(closes, cfg.ema_mid))
    e_slow = ind.last(ind.ema(closes, cfg.ema_slow)) if len(closes) >= cfg.ema_slow else None

    score = 0.0
    details: dict[str, float] = {}

    # price/EMA stack (60 pts)
    checks = [price > e_fast, e_fast > e_mid]
    if e_slow is not None:
        checks += [e_mid > e_slow, price > e_slow]
    stack = sum(checks) / len(checks)
    score += 60.0 * stack
    details["ema_stack"] = stack

    # fast EMA slope over last 10 bars (40 pts): +1.5%/bar-ish of slope saturates
    recent = [v for v in e_fast_s[-10:] if v is not None]
    slope = ind.linreg_slope_pct(recent) if len(recent) >= 2 else None
    if slope is not None:
        score += 40.0 * ind.clamp((slope + 0.25) / 1.0, 0.0, 1.0)
        details["ema_fast_slope_pct"] = slope

    if stack == 1.0:
        flags.append("FULL_UPTREND")

    metrics.update(ema_fast=e_fast, ema_mid=e_mid, ema_slow=e_slow,
                   dist_ema_fast_pct=(price / e_fast - 1) * 100 if e_fast else None)
    return ComponentScore("trend", ind.clamp(score), cfg.weights["trend"], details)


# ------------------------------------------------------------------------ momentum
def _momentum(closes, cfg: RadarConfig, metrics, flags) -> ComponentScore:
    r_short = ind.roc(closes, cfg.roc_short)
    r_long = ind.roc(closes, cfg.roc_long)
    rsi_v = ind.last(ind.rsi(closes, cfg.rsi_period))

    score = 0.0
    details: dict[str, float] = {}

    # long ROC: -10% -> 0, +40% -> full (35 pts)
    if r_long is not None:
        score += 35.0 * ind.clamp((r_long + 10.0) / 50.0, 0.0, 1.0)
        details["roc_long"] = r_long
    # short ROC: -5% -> 0, +10% -> full (25 pts)
    if r_short is not None:
        score += 25.0 * ind.clamp((r_short + 5.0) / 15.0, 0.0, 1.0)
        details["roc_short"] = r_short
    # RSI sweet spot 55..70 (40 pts), fades towards 40 and towards overbought
    if rsi_v is not None:
        if 55.0 <= rsi_v <= 70.0:
            rsi_pts = 1.0
        elif rsi_v < 55.0:
            rsi_pts = ind.clamp((rsi_v - 40.0) / 15.0, 0.0, 1.0)
        else:
            rsi_pts = ind.clamp(1.0 - (rsi_v - 70.0) / (90.0 - 70.0), 0.0, 1.0)
        score += 40.0 * rsi_pts
        details["rsi"] = rsi_v
        if rsi_v >= cfg.overbought_rsi:
            flags.append("OVERBOUGHT")
        if r_short is not None and r_long is not None and r_long > 0 and r_short > 0 and 50 <= rsi_v < cfg.overbought_rsi:
            flags.append("MOMENTUM_BUILDING")

    metrics.update(roc_short=r_short, roc_long=r_long, rsi=rsi_v)
    return ComponentScore("momentum", ind.clamp(score), cfg.weights["momentum"], details)


# -------------------------------------------------------------------------- volume
def _volume(candles, vols, cfg: RadarConfig, metrics, flags) -> ComponentScore:
    n_recent, n_base = cfg.volume_recent, cfg.volume_lookback
    recent = vols[-n_recent:]
    base = vols[-(n_recent + n_base):-n_recent]
    base_mean = sum(base) / len(base) if base else 0.0
    rel_vol = (sum(recent) / len(recent)) / base_mean if base_mean > 0 else 1.0
    vol_z = ind.zscore_last(vols, n_base)

    window = candles[-n_base:]
    up_vol = sum(c.volume for c in window if c.is_green)
    tot_vol = sum(c.volume for c in window)
    up_ratio = up_vol / tot_vol if tot_vol > 0 else 0.5

    score = 0.0
    # relative volume 0.7x -> 0, 2.0x -> full (45 pts)
    score += 45.0 * ind.clamp((rel_vol - 0.7) / 1.3, 0.0, 1.0)
    # up-volume dominance 0.4 -> 0, 0.7 -> full (55 pts): accumulation
    score += 55.0 * ind.clamp((up_ratio - 0.4) / 0.3, 0.0, 1.0)

    if rel_vol >= 2.0 or (vol_z is not None and vol_z >= 3.0):
        flags.append("VOLUME_SURGE")
    if up_ratio >= 0.62:
        flags.append("ACCUMULATION")
    elif up_ratio <= 0.38:
        flags.append("DISTRIBUTION")

    metrics.update(rel_volume=rel_vol, volume_z=vol_z, up_volume_ratio=up_ratio)
    return ComponentScore(
        "volume", ind.clamp(score), cfg.weights["volume"],
        {"rel_volume": rel_vol, "up_volume_ratio": up_ratio},
    )


# ----------------------------------------------------------------------- structure
def _structure(closes, highs, lows, cfg: RadarConfig, metrics, flags) -> ComponentScore:
    lb = cfg.structure_lookback
    price = closes[-1]
    hh = max(highs[-lb:])
    ll = min(lows[-lb:])
    range_pos = (price - ll) / (hh - ll) if hh > ll else 0.5
    dist_high_pct = (hh / price - 1.0) * 100.0 if price else 0.0

    # higher-lows: share of consecutive swing lows that rose
    piv = ind.swing_lows(lows[-lb:], window=2)
    if len(piv) >= 2:
        rises = sum(1 for a, b in zip(piv, piv[1:]) if b > a)
        hl_ratio = rises / (len(piv) - 1)
    else:
        hl_ratio = 0.5

    # volatility squeeze: current BB width percentile vs history
    bbw = [v for v in ind.bollinger_width(closes, 20) if v is not None]
    hist = bbw[-cfg.squeeze_lookback:]
    bbw_pct = ind.percentile_rank(hist, hist[-1]) if hist else 0.5

    score = 0.0
    score += 35.0 * range_pos                      # trading near top of range
    score += 35.0 * hl_ratio                       # higher lows
    # compression is constructive if price sits in the upper half
    if range_pos >= 0.5:
        score += 30.0 * (1.0 - bbw_pct)
    else:
        score += 10.0 * (1.0 - bbw_pct)

    prev_high = max(highs[-lb:-1]) if lb > 1 else hh
    if closes[-1] > prev_high:
        flags.append("BREAKOUT")
    elif dist_high_pct <= 3.0:
        flags.append("NEAR_HIGH")
    if bbw_pct <= 0.15:
        flags.append("SQUEEZE")
    if hl_ratio >= 0.75 and len(piv) >= 3:
        flags.append("HIGHER_LOWS")

    metrics.update(range_position=range_pos, dist_to_high_pct=dist_high_pct,
                   higher_low_ratio=hl_ratio, bb_width_pctile=bbw_pct)
    return ComponentScore(
        "structure", ind.clamp(score), cfg.weights["structure"],
        {"range_position": range_pos, "higher_low_ratio": hl_ratio, "bb_width_pctile": bbw_pct},
    )


# --------------------------------------------------------------------- derivatives
def _derivatives(data: MarketData, closes, cfg: RadarConfig, metrics, flags) -> Optional[ComponentScore]:
    d = data.derivatives
    assert d is not None
    fr = d.funding_rate
    oi_chg = d.oi_change_pct
    if fr is None and oi_chg is None:
        return None

    parts: list[tuple[float, float]] = []  # (points 0..1, weight)
    details: dict[str, float] = {}

    if fr is not None:
        details["funding_rate"] = fr
        # neutral / mildly positive funding is healthiest; negative = short fuel
        if fr < 0:
            f_pts = 0.8
            if fr <= -cfg.crowded_funding / 2:
                flags.append("SHORT_SQUEEZE_FUEL")
        elif fr <= cfg.crowded_funding / 2:
            f_pts = 1.0
        else:
            f_pts = ind.clamp(1.0 - (fr - cfg.crowded_funding / 2) / (cfg.crowded_funding * 1.5), 0.0, 1.0)
        if fr >= cfg.crowded_funding:
            flags.append("CROWDED_LONG")
        parts.append((f_pts, 0.4))

    if oi_chg is not None:
        details["oi_change_pct"] = oi_chg
        n = max(2, len(d.open_interest))
        price_chg = ind.roc(closes, min(n - 1, len(closes) - 1)) or 0.0
        if oi_chg > 0 and price_chg > 0:
            o_pts = ind.clamp(0.5 + oi_chg / 40.0, 0.5, 1.0)  # new money confirming the move
            if oi_chg >= 10:
                flags.append("OI_CONFIRM")
        elif oi_chg > 0 >= price_chg:
            o_pts = 0.35  # OI up while price stalls: contested
        elif oi_chg <= 0 < price_chg:
            o_pts = 0.55  # short covering rally
        else:
            o_pts = 0.2  # deleveraging
        parts.append((o_pts, 0.6))

    tw = sum(w for _, w in parts)
    score = 100.0 * sum(p * w for p, w in parts) / tw
    metrics.update(funding_rate=fr, oi_change_pct=oi_chg)
    return ComponentScore("derivatives", ind.clamp(score), cfg.weights["derivatives"], details)
