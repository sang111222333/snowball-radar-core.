"""Deterministic synthetic market for demos and tests (no network)."""

from __future__ import annotations

import random
import zlib
from typing import Optional

from ..config import RadarConfig
from ..models import Candle, DerivativesSnapshot
from .base import DataSource, apply_universe_filters

# symbol -> (drift per bar, volatility, volume trend)
DEFAULT_PROFILES: dict[str, tuple[float, float, float]] = {
    "BTCUSDT": (0.0015, 0.012, 0.002),
    "ETHUSDT": (0.0008, 0.016, 0.001),
    "SOLUSDT": (0.0030, 0.022, 0.004),
    "BNBUSDT": (0.0002, 0.010, 0.0),
    "XRPUSDT": (-0.0010, 0.018, -0.002),
    "DOGEUSDT": (0.0000, 0.030, 0.0),
    "ADAUSDT": (-0.0020, 0.020, -0.003),
    "LINKUSDT": (0.0020, 0.020, 0.003),
    "AVAXUSDT": (-0.0005, 0.025, 0.0),
    "SUIUSDT": (0.0040, 0.028, 0.005),
}


class SyntheticSource(DataSource):
    name = "synthetic"

    def __init__(self, profiles: Optional[dict[str, tuple[float, float, float]]] = None, seed: int = 7,
                 start_ms: int = 1_700_000_000_000, step_ms: int = 4 * 3_600_000) -> None:
        self.profiles = profiles or DEFAULT_PROFILES
        self.seed = seed
        self.start_ms = start_ms
        self.step_ms = step_ms

    def _rng(self, symbol: str) -> random.Random:
        return random.Random(zlib.crc32(symbol.encode()) ^ self.seed)

    def universe(self, cfg: RadarConfig) -> list[tuple[str, Optional[float]]]:
        pairs = []
        for sym in self.profiles:
            if not sym.endswith(cfg.quote.upper()):
                continue
            c = self.candles(sym, cfg.interval, 6)
            pairs.append((sym, sum(x.close * x.volume for x in c)))
        return apply_universe_filters(pairs, cfg)

    def candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        drift, vol, vtrend = self.profiles[symbol]
        rng = self._rng(symbol)
        price = 10 + rng.random() * 1000
        base_vol = 1e6 / price
        out = []
        for i in range(limit):
            ret = rng.gauss(drift, vol)
            o = price
            c = max(1e-9, o * (1 + ret))
            h = max(o, c) * (1 + abs(rng.gauss(0, vol / 2)))
            lo = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
            v = base_vol * (1 + vtrend) ** i * (1 + abs(ret) * 20 + (0.4 if c > o and drift > 0 else 0)) * rng.uniform(0.7, 1.3)
            out.append(Candle(self.start_ms + i * self.step_ms, o, h, lo, c, v))
            price = c
        return out

    def derivatives(self, symbol: str, interval: str) -> Optional[DerivativesSnapshot]:
        drift, _, _ = self.profiles[symbol]
        rng = self._rng(symbol + ":deriv")
        funding = 0.0001 + drift * 0.2 + rng.gauss(0, 0.00005)
        oi = [1e8]
        for _ in range(29):
            oi.append(oi[-1] * (1 + drift * 1.5 + rng.gauss(0, 0.01)))
        return DerivativesSnapshot(funding_rate=funding, open_interest=oi)
