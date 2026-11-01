"""Snowball Radar core — A1 full crypto radar."""

from .config import RadarConfig
from .models import Candle, DerivativesSnapshot, MarketData, RadarResult
from .radar import Radar, ScanReport
from .scoring import InsufficientData, score_market

__all__ = [
    "Candle", "DerivativesSnapshot", "MarketData", "RadarResult",
    "RadarConfig", "Radar", "ScanReport", "score_market", "InsufficientData",
]
__version__ = "0.1.0"
