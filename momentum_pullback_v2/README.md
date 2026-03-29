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


No API keys are required for the current dry-run mode. It only fetches public market data and simulates trades locally; it does not send real orders.


## One-command summary report

```bash
python3 momentum_pullback_v2/make_summary_report.py
cat momentum_pullback_v2_summary.txt
```


Current default variant is `balanced`: less strict than the original v2 launch so the bot can produce paper opportunities while still keeping structural filters and rejection diagnostics.


Micro-account protection was added: per-trade notional is now capped by account balance and per-symbol ceilings so small balances do not create oversized paper positions.


Balanced mode was further relaxed for live paper research: deeper pullbacks can pass when trend strength remains supportive, and impulse-volume validation now allows small tolerance around the moving average instead of demanding a clearly above-average spike every time.

Recent research upgrades added trade-quality telemetry (MFE/MAE, hold time, peak progress, score snapshot) and more aggressive protective exits for non-expanding trades, so paper sessions can reveal whether lack of edge comes from entries, targets, or hold management.


Balanced mode now also accepts certain pullbacks in progress (including one-candle pullbacks that have not yet printed a fully opposite close) when structure and retrace remain controlled, so the scanner is less likely to miss valid setups during fast markets.
