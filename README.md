# Tick Vampire v3

Bot paper-first de scalping para futuros.

## Ejecutar

```bash
pip install -r requirements.txt
PYTHONPATH=. python3 -m tick_vampire_v3.main --dry-run
```

## Estado

- Block 1: scaffold modular
- Block 2: loop paper básico
- Block 3: snapshot market loop + DB logging + scheduler de sesiones

## Advertencias

- Solo paper/dry-run por ahora
- No live real habilitado
- Validar varios días antes de considerar siguiente paso

## Reporte rápido Tick Vampire v3

```bash
python3 tick_vampire_v3/make_report.py
cat tick_vampire_v3_report.txt
```


Para testing rápido, Tick Vampire v3 viene con `IGNORE_SESSIONS = True` por defecto en `tick_vampire_v3/config.py`, así puede correr a cualquier hora.


## Paper calibration note

Current paper defaults were widened after the first live observation round so that take-profit distance can exceed modeled costs and the research loop is not halted too aggressively by early drawdown.


## Research note

Current development is explicitly paper-first. The bot is being tightened toward a *no-trade-is-better-than-bad-trade* posture because the early versions proved that frequent low-quality entries were structurally unprofitable after fees.


## Multi-asset paper mode

Tick Vampire v3 now scans a curated liquid futures basket and only opens the highest-scoring setup at a time instead of forcing trades on a single market.


Recent tuning added faster break-even, tighter trailing, shorter max hold and a momentum-decay exit to reduce the number of small time-based losers.


## Research workflow

```bash
python3 tick_vampire_v3/make_research_report.py
cat tick_vampire_v3_research_report.txt
```


## Reversion scalper backtest

Se agregó `reversion_scalp_v1/backtest.py` para simular la lógica del scalper con velas históricas, una sola posición abierta, fees/slippage y outputs de reporte/CSV/equity curve. Uso sugerido:

```bash
python3.12 -m reversion_scalp_v1.backtest --days 30
python3.12 -m reversion_scalp_v1.backtest --symbol SOL/USDT:USDT --days 30
```


Backtest correction: the scalper backtest now stages entries for the next 5m candle and does not allow trade management on the same candle that generated the signal. This makes the simulation more aligned with the live runtime and avoids same-bar entry/exit distortion.


Backtest coverage refinement: the historical fetcher now paginates with explicit timeframe steps and the report includes candle counts plus first/last timestamps for 5m and 15m data, so long-window runs (30d vs 100d) can be audited for missing history instead of silently under-sampling.


Backtest execution refinement: exit management now approximates intrabar behavior instead of evaluating only the final candle close. Each 5m bar is replayed through a simple directional path (open-low-high-close for longs, open-high-low-close for shorts) so the backtest behaves more like the live scalper, which checks the active candle repeatedly during the trade.


Backtest live-alignment refinement: signal generation now also tests a synthetic partial 5m candle (mid-candle snapshot plus full close) before queuing an entry. This approximates the real bot polling every ~20s, where setups can appear before the final 5m close instead of only at strict bar close.


## Reversion scalper signal replay

Como complemento al backtest, se agregó `reversion_scalp_v1/signal_replay.py` para estudiar la hipótesis sin depender de una simulación de ejecución 1:1. Mide cuántas señales aparecen y qué MFE/MAE tienen en las velas siguientes. Uso sugerido:

```bash
python3.12 -m reversion_scalp_v1.signal_replay --days 30
python3.12 -m reversion_scalp_v1.signal_replay --symbol SOL/USDT:USDT --days 30 --lookahead-bars 6
```


Backtest calibration refinement: partial-candle signal synthesis now evaluates multiple intra-candle snapshots instead of just one midpoint and the exit path also uses a denser synthetic sequence. This is intended to better mimic the real bot polling every ~20 seconds and improve 1-day calibration against paper-live behavior.


Signal replay upgrade: `reversion_scalp_v1/signal_replay.py` now reports scenario scores to compare signal quality under different interpretations (`strict_tp_first`, `strict_sl_first`, `mfe_gt_mae`, `balanced`). This makes it usable as a strategy-comparison lab even when full execution backtesting is still imperfect.


Signal replay comparison upgrade: the replay tool can now compare multiple filter variants (`baseline`, `higher_score`, `deeper_stretch`, `stronger_zscore`) and report how each one changes signal count plus scenario-quality percentages. This is the main research surface for deciding whether a stricter filter is worth carrying into the real bot.


Signal replay segmentation upgrade: the report now includes buckets for score, stretch and zscore, showing signal count plus TP-hit / SL-hit / MFE>MAE percentages in each band. This is meant to find where signal quality is actually concentrated instead of relying only on simple global filter toggles.
