"""Radar configuration (weights, thresholds, universe filters)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path
from typing import Any

DEFAULT_WEIGHTS: dict[str, float] = {
    "trend": 0.25,
    "momentum": 0.20,
    "volume": 0.20,
    "structure": 0.20,
    "derivatives": 0.15,
}

# grade -> minimum composite score (checked in order)
DEFAULT_GRADES: list[tuple[str, float]] = [
    ("A1", 85.0),
    ("A2", 75.0),
    ("B", 60.0),
    ("C", 45.0),
    ("D", 0.0),
]

STABLECOINS = frozenset({
    "USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "USDD", "PYUSD",
    "EUR", "EURI", "AEUR", "GBP", "TRY", "BRL", "USDE", "USD1", "XUSD", "BFUSD",
})


@dataclass
class RadarConfig:
    # universe
    quote: str = "USDT"
    interval: str = "4h"
    candles: int = 300
    top_n_universe: int = 100
    min_quote_volume: float = 5_000_000.0
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    use_derivatives: bool = True

    # indicator periods
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    roc_short: int = 6
    roc_long: int = 42
    volume_lookback: int = 30
    volume_recent: int = 6
    structure_lookback: int = 60
    squeeze_lookback: int = 120

    # scoring
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    grades: list[tuple[str, float]] = field(default_factory=lambda: list(DEFAULT_GRADES))
    overbought_rsi: float = 78.0
    crowded_funding: float = 0.0005  # 0.05% per funding period
    max_atr_pct: float = 12.0  # ATR% above this is penalised as too wild

    # runtime
    workers: int = 8

    def grade_for(self, score: float) -> str:
        for name, threshold in self.grades:
            if score >= threshold:
                return name
        return self.grades[-1][0]

    @property
    def min_candles(self) -> int:
        return max(self.ema_mid, self.structure_lookback, self.volume_lookback + self.volume_recent) + 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RadarConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        data = dict(data)
        if "weights" in data:
            w = dict(DEFAULT_WEIGHTS)
            bad = set(data["weights"]) - set(DEFAULT_WEIGHTS)
            if bad:
                raise ValueError(f"unknown weight components: {sorted(bad)}")
            w.update({k: float(v) for k, v in data["weights"].items()})
            data["weights"] = w
        if "grades" in data:
            data["grades"] = sorted(
                ((str(g), float(t)) for g, t in data["grades"]), key=lambda x: -x[1]
            )
        return cls(**data)

    @classmethod
    def load(cls, path: str | Path) -> "RadarConfig":
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".toml":
            import tomllib

            data = tomllib.loads(text)
        else:
            data = json.loads(text)
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
