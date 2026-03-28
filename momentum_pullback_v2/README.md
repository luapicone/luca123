# Momentum Pullback v2

Paper-first multi-asset continuation strategy for perpetual futures.

## Run

```bash
pip install -r momentum_pullback_v2/requirements.txt
PYTHONPATH=. python3 -m momentum_pullback_v2.main --dry-run
```

## Backtest

Prepare Binance OHLCV CSV files per symbol and timeframe using this naming:

- `BTCUSDT_5m.csv`
- `BTCUSDT_15m.csv`
- etc.

Each CSV must contain headers:

```text
timestamp,open,high,low,close,volume
```

Run:

```bash
PYTHONPATH=. python3 -m momentum_pullback_v2.backtest --data-dir /path/to/csvs
```

The backtester writes:
- `momentum_pullback_v2_backtest_report.txt`
- `momentum_pullback_v2_equity_curve.csv`

No live trading is enabled here.
