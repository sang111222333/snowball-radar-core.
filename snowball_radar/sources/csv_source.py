"""Offline source: one ``<SYMBOL>.csv`` per coin in a directory.

Required columns: ``open_time,open,high,low,close,volume`` (open_time in epoch
ms or ISO-8601). Optional columns ``funding_rate`` (last non-empty value used)
and ``open_interest`` (series).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import RadarConfig
from ..models import Candle, DerivativesSnapshot
from .base import DataSource, DataSourceError, apply_universe_filters


class CsvSource(DataSource):
    name = "csv"

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)
        if not self.dir.is_dir():
            raise DataSourceError(f"CSV directory not found: {self.dir}")
        self._cache: dict[str, tuple[list[Candle], Optional[DerivativesSnapshot]]] = {}

    def _load(self, symbol: str):
        if symbol in self._cache:
            return self._cache[symbol]
        path = self.dir / f"{symbol}.csv"
        if not path.exists():
            raise DataSourceError(f"no CSV for {symbol}")
        candles: list[Candle] = []
        funding: Optional[float] = None
        oi: list[float] = []
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                candles.append(Candle(
                    _parse_time(row["open_time"]), float(row["open"]), float(row["high"]),
                    float(row["low"]), float(row["close"]), float(row["volume"]),
                ))
                if row.get("funding_rate"):
                    funding = float(row["funding_rate"])
                if row.get("open_interest"):
                    oi.append(float(row["open_interest"]))
        candles.sort(key=lambda c: c.open_time)
        deriv = DerivativesSnapshot(funding, oi) if (funding is not None or oi) else None
        self._cache[symbol] = (candles, deriv)
        return self._cache[symbol]

    def universe(self, cfg: RadarConfig) -> list[tuple[str, Optional[float]]]:
        pairs = []
        for p in sorted(self.dir.glob("*.csv")):
            sym = p.stem.upper()
            if cfg.quote and not sym.endswith(cfg.quote.upper()):
                continue
            candles, _ = self._load(p.stem)
            # approximate 24h quote volume from the last 24h of bars
            if candles:
                cutoff = candles[-1].open_time - 86_400_000
                qv = sum(c.close * c.volume for c in candles if c.open_time > cutoff)
            else:
                qv = 0.0
            pairs.append((p.stem, qv))
        return apply_universe_filters(pairs, cfg)

    def candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        return self._load(symbol)[0][-limit:]

    def derivatives(self, symbol: str, interval: str) -> Optional[DerivativesSnapshot]:
        return self._load(symbol)[1]


def _parse_time(v: str) -> int:
    v = v.strip()
    try:
        return int(float(v))
    except ValueError:
        return int(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() * 1000)
