import csv
import io
import json

from snowball_radar import Radar, RadarConfig
from snowball_radar.cli import main
from snowball_radar.report import RENDERERS
from snowball_radar.sources import SyntheticSource


def test_full_scan_ranked():
    rep = Radar(SyntheticSource(), RadarConfig(min_quote_volume=0)).scan()
    assert rep.scanned == 10 and len(rep.results) == 10 and not rep.errors
    scores = [r.score for r in rep.results]
    assert scores == sorted(scores, reverse=True)
    assert all("derivatives" in r.components for r in rep.results)
    assert rep.filter(min_score=101) == []


def test_scan_records_errors():
    rep = Radar(SyntheticSource(), RadarConfig(candles=20)).scan(["BTCUSDT", "MISSINGUSDT"])
    assert rep.results == []
    assert set(rep.errors) == {"BTCUSDT", "MISSINGUSDT"}


def test_renderers():
    rep = Radar(SyntheticSource(), RadarConfig(min_quote_volume=0)).scan()
    top = rep.top(3)
    for name, fn in RENDERERS.items():
        out = fn(rep, top)
        assert top[0].symbol in out, name
    data = json.loads(RENDERERS["json"](rep, top))
    assert len(data["results"]) == 3
    rows = list(csv.DictReader(io.StringIO(RENDERERS["csv"](rep, top))))
    assert rows[0]["rank"] == "1"


def test_cli_synthetic(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert main(["scan", "--source", "synthetic", "--min-volume", "0", "--top", "2", "--format", "json", "-o", str(out)]) == 0
    assert len(json.loads(out.read_text())["results"]) == 2
    assert main(["scan", "--source", "synthetic", "--min-volume", "0", "--flag", "full_uptrend"]) == 0
    text = capsys.readouterr().out
    assert "Snowball Radar A1" in text
