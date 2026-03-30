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
