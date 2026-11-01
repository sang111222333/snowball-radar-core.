import pytest

from snowball_radar import indicators as ind


def test_sma_and_ema_basic():
    vals = [1, 2, 3, 4, 5]
    assert ind.sma(vals, 3) == [None, None, 2.0, 3.0, 4.0]
    e = ind.ema(vals, 3)
    assert e[:2] == [None, None]
    assert e[2] == pytest.approx(2.0)
    assert e[3] == pytest.approx(3.0)
    assert e[4] == pytest.approx(4.0)


def test_ema_short_input_is_all_none():
    assert ind.ema([1, 2], 5) == [None, None]


def test_rsi_extremes():
    up = list(range(1, 40))
    assert ind.last(ind.rsi(up, 14)) == 100.0
    down = list(range(40, 1, -1))
    assert ind.last(ind.rsi(down, 14)) == pytest.approx(0.0)
    flat = [5.0] * 30
    assert ind.last(ind.rsi(flat, 14)) == 50.0


def test_atr_constant_range():
    highs = [11.0] * 30
    lows = [9.0] * 30
    closes = [10.0] * 30
    assert ind.last(ind.atr(highs, lows, closes, 14)) == pytest.approx(2.0)


def test_roc_and_zscore():
    assert ind.roc([100, 110, 121], 2) == pytest.approx(21.0)
    assert ind.roc([1], 5) is None
    vals = [10, 12, 8, 10, 12, 8, 10, 30]
    assert ind.zscore_last(vals, 6) > 3


def test_linreg_slope_and_percentile():
    assert ind.linreg_slope_pct([1, 2, 3, 4, 5]) == pytest.approx(100 / 3)
    assert ind.percentile_rank([1, 2, 3, 4], 2) == 0.5


def test_swing_lows():
    lows = [5, 4, 3, 4, 5, 4, 3.5, 4, 5]
    assert ind.swing_lows(lows, 2) == [3, 3.5]


def test_bad_period():
    with pytest.raises(ValueError):
        ind.sma([1, 2], 0)
