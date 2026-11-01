"""Full-radar orchestration: universe -> fetch -> score -> rank."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from .config import RadarConfig
from .models import MarketData, RadarResult
from .scoring import InsufficientData, score_market
from .sources.base import DataSource, DataSourceError

log = logging.getLogger(__name__)


@dataclass
class ScanReport:
    results: list[RadarResult]
    errors: dict[str, str] = field(default_factory=dict)
    scanned: int = 0
    source: str = ""
    interval: str = ""
    started_at: float = 0.0
    duration_s: float = 0.0

    def top(self, n: int) -> list[RadarResult]:
        return self.results[:n]

    def filter(self, min_score: float = 0.0, grades: Optional[set[str]] = None,
               require_flags: Optional[set[str]] = None) -> list[RadarResult]:
        out = []
        for r in self.results:
            if r.score < min_score:
                continue
            if grades and r.grade not in grades:
                continue
            if require_flags and not require_flags.issubset(r.flags):
                continue
            out.append(r)
        return out


class Radar:
    def __init__(self, source: DataSource, config: Optional[RadarConfig] = None) -> None:
        self.source = source
        self.cfg = config or RadarConfig()

    def scan_symbol(self, symbol: str, quote_volume: Optional[float] = None) -> RadarResult:
        cfg = self.cfg
        candles = self.source.candles(symbol, cfg.interval, cfg.candles)
        deriv = None
        if cfg.use_derivatives:
            try:
                deriv = self.source.derivatives(symbol, cfg.interval)
            except DataSourceError as e:  # derivatives are optional context
                log.debug("derivatives unavailable for %s: %s", symbol, e)
        return score_market(MarketData(symbol, candles, quote_volume, deriv), cfg)

    def scan(self, symbols: Optional[list[str]] = None) -> ScanReport:
        started = time.time()
        if symbols:
            universe: list[tuple[str, Optional[float]]] = [(s.upper(), None) for s in symbols]
        else:
            universe = self.source.universe(self.cfg)

        results: list[RadarResult] = []
        errors: dict[str, str] = {}
        workers = max(1, min(self.cfg.workers, len(universe) or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.scan_symbol, s, qv): s for s, qv in universe}
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    results.append(fut.result())
                except (InsufficientData, DataSourceError, KeyError, ValueError) as e:
                    errors[sym] = str(e)
                    log.info("skip %s: %s", sym, e)

        results.sort(key=lambda r: (-r.score, r.symbol))
        return ScanReport(
            results=results, errors=errors, scanned=len(universe),
            source=self.source.name, interval=self.cfg.interval,
            started_at=started, duration_s=round(time.time() - started, 3),
        )
