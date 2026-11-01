"""Core data models used across the radar."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass(frozen=True)
class Candle:
    open_time: int  # epoch milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float  # base-asset volume

    @property
    def is_green(self) -> bool:
        return self.close >= self.open


@dataclass(frozen=True)
class DerivativesSnapshot:
    """Perpetual-futures context for a symbol (all fields optional)."""

    funding_rate: Optional[float] = None  # last funding rate, e.g. 0.0001 = 0.01%
    open_interest: list[float] = field(default_factory=list)  # OI value history, oldest first

    @property
    def oi_change_pct(self) -> Optional[float]:
        if len(self.open_interest) < 2 or self.open_interest[0] <= 0:
            return None
        return (self.open_interest[-1] / self.open_interest[0] - 1.0) * 100.0


@dataclass(frozen=True)
class MarketData:
    symbol: str
    candles: list[Candle]
    quote_volume_24h: Optional[float] = None
    derivatives: Optional[DerivativesSnapshot] = None


@dataclass
class ComponentScore:
    name: str
    score: float  # 0..100
    weight: float
    details: dict[str, float] = field(default_factory=dict)


@dataclass
class RadarResult:
    symbol: str
    price: float
    score: float  # composite 0..100
    grade: str
    components: dict[str, ComponentScore]
    flags: list[str]
    metrics: dict[str, Optional[float]]
    quote_volume_24h: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["components"] = {k: asdict(v) for k, v in self.components.items()}
        return d
