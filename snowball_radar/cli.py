"""Command line entry point: ``snowball-radar scan ...``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .config import RadarConfig
from .radar import Radar
from .report import RENDERERS
from .sources import BinanceSource, CsvSource, DataSource, DataSourceError, SyntheticSource


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="snowball-radar", description="A1 full crypto radar")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="scan the universe and rank setups")
    s.add_argument("--source", choices=["binance", "csv", "synthetic"], default="binance")
    s.add_argument("--csv-dir", help="directory of <SYMBOL>.csv files (for --source csv)")
    s.add_argument("--spot-base", help="override Binance spot base URL")
    s.add_argument("--futures-base", help="override Binance futures base URL")
    s.add_argument("--config", help="JSON/TOML config file")
    s.add_argument("--symbols", help="comma-separated symbols to scan instead of the auto universe")
    s.add_argument("--quote", help="quote asset (default USDT)")
    s.add_argument("--interval", help="candle interval, e.g. 1h, 4h, 1d")
    s.add_argument("--candles", type=int, help="candles per symbol")
    s.add_argument("--universe", type=int, help="max symbols in the auto universe")
    s.add_argument("--min-volume", type=float, help="min 24h quote volume")
    s.add_argument("--no-derivatives", action="store_true", help="skip funding/OI")
    s.add_argument("--top", type=int, default=25, help="rows to show")
    s.add_argument("--min-score", type=float, default=0.0)
    s.add_argument("--grade", action="append", help="only these grades (repeatable)")
    s.add_argument("--flag", action="append", help="require these flags (repeatable)")
    s.add_argument("--format", choices=sorted(RENDERERS), default="table")
    s.add_argument("--output", "-o", help="write to file instead of stdout")
    s.add_argument("--workers", type=int)
    s.add_argument("-v", "--verbose", action="store_true")
    return p


def _make_config(args) -> RadarConfig:
    cfg = RadarConfig.load(args.config) if args.config else RadarConfig()
    for attr, val in (("quote", args.quote), ("interval", args.interval), ("candles", args.candles),
                      ("top_n_universe", args.universe), ("min_quote_volume", args.min_volume),
                      ("workers", args.workers)):
        if val is not None:
            setattr(cfg, attr, val)
    if args.no_derivatives:
        cfg.use_derivatives = False
    return cfg


def _make_source(args) -> DataSource:
    if args.source == "csv":
        if not args.csv_dir:
            raise SystemExit("--csv-dir is required with --source csv")
        return CsvSource(args.csv_dir)
    if args.source == "synthetic":
        return SyntheticSource()
    return BinanceSource(spot_base=args.spot_base, futures_base=args.futures_base)


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    cfg = _make_config(args)
    try:
        source = _make_source(args)
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
        report = Radar(source, cfg).scan(symbols)
    except DataSourceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    shown = report.filter(
        min_score=args.min_score,
        grades={g.upper() for g in args.grade} if args.grade else None,
        require_flags={f.upper() for f in args.flag} if args.flag else None,
    )[: args.top]
    text = RENDERERS[args.format](report, shown)
    if args.output:
        Path(args.output).write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
    else:
        print(text)
    if report.errors and (args.verbose or not report.results):
        for sym, err in sorted(report.errors.items()):
            print(f"skipped {sym}: {err}", file=sys.stderr)
    return 0 if report.results or not report.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
