"""Render scan results as a text table, Markdown, JSON or CSV."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from .models import RadarResult
from .radar import ScanReport

COMPONENTS = ("trend", "momentum", "volume", "structure", "derivatives")
_ABBR = {"trend": "TRD", "momentum": "MOM", "volume": "VOL", "structure": "STR", "derivatives": "DRV"}


def _comp(r: RadarResult, name: str) -> str:
    c = r.components.get(name)
    return f"{c.score:.0f}" if c else "-"


def _fmt_price(p: float) -> str:
    if p >= 1000:
        return f"{p:,.0f}"
    if p >= 1:
        return f"{p:.3f}"
    return f"{p:.6g}"


def _fmt_vol(v) -> str:
    if v is None:
        return "-"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= div:
            return f"{v / div:.1f}{unit}"
    return f"{v:.0f}"


def _rows(results: list[RadarResult]) -> list[list[str]]:
    rows = []
    for i, r in enumerate(results, 1):
        rows.append([
            str(i), r.symbol, _fmt_price(r.price), f"{r.score:.1f}", r.grade,
            *(_comp(r, c) for c in COMPONENTS),
            _fmt_vol(r.quote_volume_24h), ",".join(r.flags),
        ])
    return rows


def _header() -> list[str]:
    return ["#", "SYMBOL", "PRICE", "SCORE", "GRADE", *(_ABBR[c] for c in COMPONENTS), "VOL24H", "FLAGS"]


def to_table(report: ScanReport, results: list[RadarResult]) -> str:
    header = _header()
    rows = _rows(results)
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(header)]
    def line(cells):
        return "  ".join(c.ljust(w) if i in (1, len(cells) - 1) else c.rjust(w)
                         for i, (c, w) in enumerate(zip(cells, widths))).rstrip()
    ts = datetime.fromtimestamp(report.started_at or 0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        f"Snowball Radar A1 | source={report.source} interval={report.interval} | {ts}",
        f"scanned={report.scanned} scored={len(report.results)} skipped={len(report.errors)} shown={len(results)} ({report.duration_s}s)",
        "",
        line(header),
        line(["-" * w for w in widths]),
        *(line(r) for r in rows),
    ]
    return "\n".join(out)


def to_markdown(report: ScanReport, results: list[RadarResult]) -> str:
    header = _header()
    lines = [
        f"## Snowball Radar A1 — {report.source} {report.interval}",
        "",
        f"Scanned {report.scanned}, scored {len(report.results)}, skipped {len(report.errors)}.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    for r in _rows(results):
        r[-1] = r[-1].replace(",", ", ")
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def to_json(report: ScanReport, results: list[RadarResult]) -> str:
    return json.dumps({
        "source": report.source,
        "interval": report.interval,
        "started_at": report.started_at,
        "duration_s": report.duration_s,
        "scanned": report.scanned,
        "errors": report.errors,
        "results": [r.to_dict() for r in results],
    }, indent=2)


def to_csv(report: ScanReport, results: list[RadarResult]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "symbol", "price", "score", "grade", *COMPONENTS, "quote_volume_24h", "flags"])
    for i, r in enumerate(results, 1):
        w.writerow([
            i, r.symbol, r.price, r.score, r.grade,
            *((round(r.components[c].score, 2) if c in r.components else "") for c in COMPONENTS),
            r.quote_volume_24h if r.quote_volume_24h is not None else "", "|".join(r.flags),
        ])
    return buf.getvalue()


RENDERERS = {"table": to_table, "markdown": to_markdown, "json": to_json, "csv": to_csv}
