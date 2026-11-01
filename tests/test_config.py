import json

import pytest

from snowball_radar.config import RadarConfig


def test_load_json_and_toml(tmp_path):
    j = tmp_path / "c.json"
    j.write_text(json.dumps({"interval": "1d", "weights": {"trend": 0.5}, "grades": [["X", 10], ["S", 90]]}))
    cfg = RadarConfig.load(j)
    assert cfg.interval == "1d"
    assert cfg.weights["trend"] == 0.5 and cfg.weights["volume"] == 0.20
    assert cfg.grades[0] == ("S", 90.0)
    assert cfg.grade_for(50) == "X"

    t = tmp_path / "c.toml"
    t.write_text('quote = "BTC"\nmin_quote_volume = 0\n')
    cfg = RadarConfig.load(t)
    assert cfg.quote == "BTC" and cfg.min_quote_volume == 0


def test_unknown_keys_rejected():
    with pytest.raises(ValueError):
        RadarConfig.from_dict({"nope": 1})
    with pytest.raises(ValueError):
        RadarConfig.from_dict({"weights": {"magic": 1}})
