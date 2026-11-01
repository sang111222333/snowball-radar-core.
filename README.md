# snowball-radar-core

**A1 Full Radar** — quét toàn bộ universe crypto, chấm điểm từng coin theo 5 thành phần và xếp hạng các setup "snowball" (xu hướng + dòng tiền + cấu trúc cùng tích luỹ, chưa quá nóng).

Pure Python (≥3.10), không phụ thuộc thư viện ngoài.

## Cài đặt

```bash
pip install -e ".[dev]"
```

## Sử dụng

```bash
# Quét live Binance (top 100 cặp USDT theo volume, nến 4h, có funding/OI futures)
snowball-radar scan

# Chỉ hiện setup hạng A, nến 1d, xuất Markdown
snowball-radar scan --interval 1d --grade A1 --grade A2 --format markdown

# Coin cụ thể, bỏ dữ liệu phái sinh, xuất JSON ra file
snowball-radar scan --symbols BTCUSDT,ETHUSDT,SOLUSDT --no-derivatives --format json -o radar.json

# Lọc theo flag
snowball-radar scan --flag BREAKOUT --flag VOLUME_SURGE

# Offline: thư mục CSV (<SYMBOL>.csv) hoặc dữ liệu synthetic để demo
snowball-radar scan --source csv --csv-dir ./data
snowball-radar scan --source synthetic --min-volume 0
```

Nếu `api.binance.com` bị chặn, dùng mirror: `--spot-base https://data-api.binance.vision` (hoặc biến môi trường `SNOWBALL_BINANCE_SPOT` / `SNOWBALL_BINANCE_FUTURES`).

Dùng như thư viện:

```python
from snowball_radar import Radar, RadarConfig
from snowball_radar.sources import BinanceSource

report = Radar(BinanceSource(), RadarConfig(interval="1d")).scan()
for r in report.filter(min_score=75):
    print(r.symbol, r.score, r.grade, r.flags)
```

## Mô hình chấm điểm

Mỗi thành phần cho điểm 0–100; điểm tổng là trung bình có trọng số của các thành phần tính được (coin không có perp → bỏ `derivatives`, trọng số được chia lại).

| Thành phần | Trọng số | Nội dung |
|---|---|---|
| `trend` | 0.25 | Xếp chồng giá > EMA20 > EMA50 > EMA200, độ dốc EMA20 |
| `momentum` | 0.20 | ROC ngắn/dài, RSI vùng 55–70 (phạt quá mua) |
| `volume` | 0.20 | Volume tương đối gần đây, tỉ lệ volume nến xanh (tích luỹ) |
| `structure` | 0.20 | Vị trí trong range, đáy cao dần, nén biến động (Bollinger width percentile) |
| `derivatives` | 0.15 | Funding (phạt long quá đông), OI tăng cùng giá |

Phạt thêm khi ATR% > `max_atr_pct` (flag `HIGH_VOLATILITY`).

**Hạng:** `A1` ≥ 85 · `A2` ≥ 75 · `B` ≥ 60 · `C` ≥ 45 · `D`.

**Flags:** `FULL_UPTREND`, `MOMENTUM_BUILDING`, `OVERBOUGHT`, `VOLUME_SURGE`, `ACCUMULATION`, `DISTRIBUTION`, `BREAKOUT`, `NEAR_HIGH`, `SQUEEZE`, `HIGHER_LOWS`, `CROWDED_LONG`, `SHORT_SQUEEZE_FUEL`, `OI_CONFIRM`, `HIGH_VOLATILITY`, `LOW_LIQUIDITY`.

## Cấu hình

Truyền `--config radar.toml` (hoặc `.json`); mọi field của `RadarConfig` đều ghi đè được:

```toml
interval = "1d"
top_n_universe = 150
min_quote_volume = 10_000_000
exclude = ["PEPEUSDT"]
grades = [["A1", 88], ["A2", 78], ["B", 62], ["C", 45], ["D", 0]]

[weights]
trend = 0.30
derivatives = 0.10
```

## Cấu trúc

```
snowball_radar/
  indicators.py   # SMA/EMA/RSI/ATR/ROC/Bollinger/z-score/swing lows
  scoring.py      # 5 thành phần + điểm tổng, hạng, flags
  radar.py        # điều phối: universe -> fetch song song -> chấm -> xếp hạng
  report.py       # table / markdown / json / csv
  config.py       # RadarConfig
  sources/        # binance, csv, synthetic
  cli.py
```

## Test

```bash
pytest
```

> Công cụ sàng lọc kỹ thuật, không phải lời khuyên đầu tư.
