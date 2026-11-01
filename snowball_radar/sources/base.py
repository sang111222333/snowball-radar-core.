from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..config import STABLECOINS, RadarConfig
from ..models import Candle, DerivativesSnapshot


class DataSourceError(RuntimeError):
    pass


class DataSource(ABC):
    """Interface every market-data provider implements."""

    name: str = "base"

    @abstractmethod
    def universe(self, cfg: RadarConfig) -> list[tuple[str, Optional[float]]]:
        """Return ``[(symbol, quote_volume_24h_or_None), ...]`` sorted by liquidity."""

    @abstractmethod
    def candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        ...

    def derivatives(self, symbol: str, interval: str) -> Optional[DerivativesSnapshot]:
        return None


LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def is_tradeable_base(base: str) -> bool:
    if not base or base in STABLECOINS:
        return False
    if any(base.endswith(s) and len(base) > len(s) for s in LEVERAGED_SUFFIXES):
        return False
    return True


def apply_universe_filters(
    pairs: list[tuple[str, Optional[float]]], cfg: RadarConfig
) -> list[tuple[str, Optional[float]]]:
    """Include/exclude lists, liquidity floor and top-N cap."""
    include = {s.upper() for s in cfg.include}
    exclude = {s.upper() for s in cfg.exclude}
    out = []
    for sym, qv in pairs:
        if sym in exclude:
            continue
        if include and sym not in include:
            continue
        if not include and qv is not None and qv < cfg.min_quote_volume:
            continue
        out.append((sym, qv))
    out.sort(key=lambda x: -(x[1] or 0.0))
    if not include:
        out = out[: cfg.top_n_universe]
    return out
