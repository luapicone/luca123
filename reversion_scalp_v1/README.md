# Reversion Scalp v1

Nueva variante enfocada en subir win rate en lugar de perseguir continuación de momentum.

## Idea
Busca reversiones intradía de corto alcance cuando hay:
- estiramiento respecto a VWAP
- desvío respecto a Bollinger bands / media
- RSI extremo en 5m
- contexto 15m todavía extremo pero apto para rebote/reversión
- vela de giro mínima en 5m

## Objetivo
Priorizar setups más defensivos y de menor recorrido esperado, pero con mejor probabilidad de resolución positiva que `momentum_pullback_v2`.

## Run
```bash
PYTHONPATH=. python3 -m reversion_scalp_v1.main --dry-run
```

## Summary
```bash
python3 reversion_scalp_v1/make_summary_report.py && cat reversion_scalp_v1_summary.txt
```
