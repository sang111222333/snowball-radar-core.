import pytest
import time

from snowball_radar.config import RadarConfig
from snowball_radar.sources import BinanceSource, CsvSource, SyntheticSource
from snowball_radar.sources.base import apply_universe_filters, is_tradeable_base


def test_tradeable_base():
    assert is_tradeable_base("BTC")
    assert not is_tradeable_base("USDC")
    assert not is_tradeable_base("BTCUP")
    assert not is_tradeable_base("ETHBEAR")
    assert is_tradeable_base("UP")  # a coin literally named UP is fine


def test_universe_filters():
    pairs = [("AUSDT", 10e6), ("BUSDT", 1e6), ("CUSDT", 50e6)]
    cfg = RadarConfig(min_quote_volume=5e6)
    assert [s for s, _ in apply_universe_filters(pairs, cfg)] == ["CUSDT", "AUSDT"]
    cfg = RadarConfig(include=["busdt"])
    assert [s for s, _ in apply_universe_filters(pairs, cfg)] == ["BUSDT"]
    cfg = RadarConfig(exclude=["CUSDT"], min_quote_volume=0, top_n_universe=1)
    assert [s for s, _ in apply_universe_filters(pairs, cfg)] == ["AUSDT"]


def test_synthetic_deterministic():
    a = SyntheticSource().candles("BTCUSDT", "4h", 50)
    b = SyntheticSource().candles("BTCUSDT", "4h", 50)
    assert a == b and len(a) == 50


def test_csv_source(tmp_path):
    rows = ["open_time,open,high,low,close,volume,funding_rate,open_interest"]
    for i in range(5):
        rows.append(f"{1_700_000_000_000 + i * 3_600_000},1,2,0.5,1.5,100,{'0.0001' if i == 4 else ''},{1000 + i}")
    (tmp_path / "ABCUSDT.csv").write_text("\n".join(rows))
    (tmp_path / "ABCBTC.csv").write_text(rows[0] + "\n")
    src = CsvSource(tmp_path)
    cfg = RadarConfig(min_quote_volume=0)
    assert [s for s, _ in src.universe(cfg)] == ["ABCUSDT"]
    assert len(src.candles("ABCUSDT", "1h", 3)) == 3
    d = src.derivatives("ABCUSDT", "1h")
    assert d.funding_rate == 0.0001 and d.open_interest == [1000, 1001, 1002, 1003, 1004]


class FakeBinance(BinanceSource):
    def __init__(self, routes):
        super().__init__(spot_base="http://spot", futures_base="http://fut", retries=1)
        self.routes = routes
        self.calls = []

    def _get(self, base, path, params=None):
        self.calls.append((base, path, params))
        r = self.routes[path]
        return r(params) if callable(r) else r


def test_binance_universe_and_candles():
    now = int(time.time() * 1000)
    hour = 3_600_000
    tickers = [
        {"symbol": "BTCUSDT", "quoteVolume": "900000000"},
        {"symbol": "ETHUSDT", "quoteVolume": "500000000"},
        {"symbol": "USDCUSDT", "quoteVolume": "800000000"},
        {"symbol": "BTCUPUSDT", "quoteVolume": "90000000"},
        {"symbol": "ETHBTC", "quoteVolume": "9000"},
        {"symbol": "DEADUSDT", "quoteVolume": "0"},
    ]
    # 3 closed hourly bars + 1 still forming
    klines = [[now - (4 - i) * hour + hour // 2, "1", "2", "0.5", "1.5", "10"] for i in range(4)]
    src = FakeBinance({"/api/v3/ticker/24hr": tickers, "/api/v3/klines": klines})
    uni = src.universe(RadarConfig())
    assert [s for s, _ in uni] == ["BTCUSDT", "ETHUSDT"]
    c = src.candles("BTCUSDT", "1h", 10)
    assert len(c) == 3  # forming candle dropped


def test_binance_derivatives():
    src = FakeBinance({
        "/fapi/v1/exchangeInfo": {"symbols": [{"symbol": "BTCUSDT", "contractType": "PERPETUAL", "status": "TRADING"}]},
        "/fapi/v1/premiumIndex": {"lastFundingRate": "0.0001"},
        "/futures/data/openInterestHist": [{"sumOpenInterestValue": "100"}, {"sumOpenInterestValue": "120"}],
    })
    d = src.derivatives("BTCUSDT", "4h")
    assert d.funding_rate == 0.0001
    assert d.oi_change_pct == pytest.approx(20.0)
    assert src.derivatives("NOPERPUSDT", "4h") is None
