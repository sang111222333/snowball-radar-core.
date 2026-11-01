import math

import pytest

from snowball_radar.models import Candle


def make_candles(closes, volumes=None, spread=0.01, start=1_700_000_000_000, step=3_600_000):
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        v = volumes[i] if volumes else 1000.0
        out.append(Candle(start + i * step, o, max(o, c) * (1 + spread), min(o, c) * (1 - spread), c, v))
        prev = c
    return out


@pytest.fixture
def uptrend():
    # steady uptrend with small wiggles and rising, green-heavy volume
    closes = [100 * (1.004 ** i) * (1 + 0.01 * math.sin(i / 3)) for i in range(300)]
    vols = [1000 + i * 5 for i in range(300)]
    return make_candles(closes, vols)


@pytest.fixture
def downtrend():
    closes = [100 * (0.996 ** i) * (1 + 0.01 * math.sin(i / 3)) for i in range(300)]
    vols = [3000 - i * 5 for i in range(300)]
    return make_candles(closes, vols)
