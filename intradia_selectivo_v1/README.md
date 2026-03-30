# Intradia Selectivo v1

Bot intradía selectivo para correr en paralelo al scalper/reversion bot.

## Filosofía
- menos operaciones
- contexto más fuerte
- objetivo de profit más amplio
- menos dependencia del micro-ruido

## Lógica base
- contexto 1h con EMA fast/slow + RSI
- entrada 15m
- continuación intradía con pullback controlado y reclaim
- exits conservadores con trailing y break-even

## Run
```bash
PYTHONPATH=. python3 -m intradia_selectivo_v1.main --dry-run
```

## Summary
```bash
python3 intradia_selectivo_v1/make_summary_report.py && cat intradia_selectivo_v1_summary.txt
```


Latest conservative refinement: LINK was removed after being the only clearly negative symbol in the first 12h sample. Core signal/exit logic was intentionally left unchanged. Summary reporting was expanded with symbol+direction PnL, exit reasons by symbol, and per-symbol quality diagnostics (score / hold / MFE / MAE / peak progress) so future tuning can stay evidence-driven.


Latest regime upgrade: the bot now explicitly supports both LONG and SHORT continuation flows instead of behaving as a mostly long-biased selective trend bot. This is meant to survive bearish regime shifts better while preserving the selective intraday architecture.


Latest analytics refinement: the summary now includes an explicit PnL-by-direction section so LONG vs SHORT behavior can be audited directly before making larger regime changes.
