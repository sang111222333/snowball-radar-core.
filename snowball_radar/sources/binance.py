"""Binance public REST data source (no API key needed).

Spot klines/tickers come from ``spot_base`` and perpetual funding / open
interest from ``futures_base``. Both are configurable so mirrors such as
``https://data-api.binance.vision`` can be used where the main host is blocked.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..config import RadarConfig
from ..models import Candle, DerivativesSnapshot
from .base import DataSource, DataSourceError, apply_universe_filters, is_tradeable_base

# Binance futures OI history supports these periods only.
_OI_PERIODS = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}


class BinanceSource(DataSource):
    name = "binance"

    def __init__(
        self,
        spot_base: Optional[str] = None,
        futures_base: Optional[str] = None,
        timeout: float = 15.0,
        retries: int = 3,
        oi_points: int = 30,
    ) -> None:
        self.spot_base = (spot_base or os.environ.get("SNOWBALL_BINANCE_SPOT", "https://api.binance.com")).rstrip("/")
        self.futures_base = (futures_base or os.environ.get("SNOWBALL_BINANCE_FUTURES", "https://fapi.binance.com")).rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.oi_points = oi_points
        self._perp_symbols: Optional[set[str]] = None

    # ------------------------------------------------------------------ http
    def _get(self, base: str, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = f"{base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        last_err: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "snowball-radar/0.1"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (418, 429):  # rate limited: back off harder
                    time.sleep(2 ** (attempt + 2))
                    continue
                if 400 <= e.code < 500:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
            time.sleep(0.5 * 2 ** attempt)
        raise DataSourceError(f"GET {url} failed: {last_err}")

    # -------------------------------------------------------------- universe
    def universe(self, cfg: RadarConfig) -> list[tuple[str, Optional[float]]]:
        tickers = self._get(self.spot_base, "/api/v3/ticker/24hr")
        quote = cfg.quote.upper()
        pairs: list[tuple[str, Optional[float]]] = []
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith(quote):
                continue
            if not is_tradeable_base(sym[: -len(quote)]):
                continue
            try:
                qv = float(t.get("quoteVolume", 0.0))
            except (TypeError, ValueError):
                continue
            if qv <= 0:
                continue  # delisted / halted
            pairs.append((sym, qv))
        return apply_universe_filters(pairs, cfg)

    # --------------------------------------------------------------- candles
    def candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        out: list[Candle] = []
        end_time: Optional[int] = None
        remaining = limit
        while remaining > 0:
            params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": min(1000, remaining)}
            if end_time is not None:
                params["endTime"] = end_time
            rows = self._get(self.spot_base, "/api/v3/klines", params)
            if not rows:
                break
            batch = [
                Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
                for r in rows
            ]
            out = batch + out
            remaining -= len(batch)
            if len(batch) < params["limit"]:
                break
            end_time = batch[0].open_time - 1
        # drop the still-forming last candle so signals are based on closed bars
        if out and out[-1].open_time + _interval_ms(interval) > int(time.time() * 1000):
            out = out[:-1]
        return out

    # ----------------------------------------------------------- derivatives
    def _perps(self) -> set[str]:
        if self._perp_symbols is None:
            try:
                info = self._get(self.futures_base, "/fapi/v1/exchangeInfo")
                self._perp_symbols = {
                    s["symbol"] for s in info.get("symbols", [])
                    if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING"
                }
            except DataSourceError:
                self._perp_symbols = set()
        return self._perp_symbols

    def derivatives(self, symbol: str, interval: str) -> Optional[DerivativesSnapshot]:
        if symbol not in self._perps():
            return None
        funding: Optional[float] = None
        oi: list[float] = []
        try:
            prem = self._get(self.futures_base, "/fapi/v1/premiumIndex", {"symbol": symbol})
            funding = float(prem["lastFundingRate"])
        except (DataSourceError, KeyError, TypeError, ValueError):
            pass
        period = interval if interval in _OI_PERIODS else "4h"
        try:
            hist = self._get(
                self.futures_base, "/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "limit": self.oi_points},
            )
            oi = [float(h["sumOpenInterestValue"]) for h in hist]
        except (DataSourceError, KeyError, TypeError, ValueError):
            pass
        if funding is None and not oi:
            return None
        return DerivativesSnapshot(funding_rate=funding, open_interest=oi)


def _interval_ms(interval: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000, "M": 2_592_000_000}
    try:
        return int(interval[:-1]) * units[interval[-1]]
    except (KeyError, ValueError):
        raise ValueError(f"unsupported interval: {interval!r}") from None
