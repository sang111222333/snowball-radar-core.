import pytest

from snowball_radar.config import RadarConfig
from snowball_radar.models import DerivativesSnapshot, MarketData
from snowball_radar.scoring import InsufficientData, score_market

from .conftest import make_candles


def test_uptrend_beats_downtrend(uptrend, downtrend):
    cfg = RadarConfig()
    up = score_market(MarketData("UPUSDT", uptrend), cfg)
    down = score_market(MarketData("DNUSDT", downtrend), cfg)
    assert up.score > down.score + 30
    assert "FULL_UPTREND" in up.flags
    assert up.components["trend"].score > 80
    assert down.components["trend"].score < 20
    assert "derivatives" not in up.components
    assert 0 <= down.score <= 100


def test_grade_mapping():
    cfg = RadarConfig()
    assert cfg.grade_for(90) == "A1"
    assert cfg.grade_for(80) == "A2"
    assert cfg.grade_for(60) == "B"
    assert cfg.grade_for(10) == "D"


def test_insufficient_data():
    with pytest.raises(InsufficientData):
        score_market(MarketData("X", make_candles([1.0] * 10)), RadarConfig())


def test_derivatives_component_and_flags(uptrend):
    cfg = RadarConfig()
    healthy = DerivativesSnapshot(funding_rate=0.0001, open_interest=[100 + i for i in range(30)])
    crowded = DerivativesSnapshot(funding_rate=0.002, open_interest=[100 + i for i in range(30)])
    r1 = score_market(MarketData("A", uptrend, derivatives=healthy), cfg)
    r2 = score_market(MarketData("A", uptrend, derivatives=crowded), cfg)
    assert r1.components["derivatives"].score > r2.components["derivatives"].score
    assert "CROWDED_LONG" in r2.flags
    assert "OI_CONFIRM" in r1.flags


def test_derivatives_disabled(uptrend):
    cfg = RadarConfig(use_derivatives=False)
    d = DerivativesSnapshot(funding_rate=0.0001, open_interest=[1, 2])
    r = score_market(MarketData("A", uptrend, derivatives=d), cfg)
    assert "derivatives" not in r.components


def test_low_liquidity_flag(uptrend):
    r = score_market(MarketData("A", uptrend, quote_volume_24h=10.0), RadarConfig())
    assert "LOW_LIQUIDITY" in r.flags


def test_breakout_and_volume_surge():
    closes = [100.0 + (i % 4) * 0.5 for i in range(200)] + [110.0]
    vols = [1000.0] * 195 + [5000.0] * 6
    r = score_market(MarketData("B", make_candles(closes, vols, spread=0.002)), RadarConfig())
    assert "BREAKOUT" in r.flags
    assert "VOLUME_SURGE" in r.flags


def test_high_volatility_penalty(uptrend):
    cfg = RadarConfig(max_atr_pct=0.1)
    r = score_market(MarketData("A", uptrend), cfg)
    assert "HIGH_VOLATILITY" in r.flags
    assert r.metrics["volatility_penalty"] > 0
