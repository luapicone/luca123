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


The current tuning was relaxed from extreme-reversion mode toward moderate reversion: smaller VWAP/Bollinger dislocations and softer RSI extremes can now qualify, while the score and reversal-candle confirmation still try to keep quality acceptable.


The entry trigger was later softened so the strategy can enter on partial reversal confirmation too, not only on a very clean final candle. Context stretch/RSI/z-score still dominate; the last candle is now a softer gate instead of a hard blocker.


Trade management was later tightened to protect favorable excursion earlier: break-even/trailing now activate sooner and a giveback-style exit can close trades that advanced meaningfully but then start returning too much of the move.


Anti-overtrading protections were added: after each trade the same symbol+direction enters cooldown, with a longer cooldown after losses. ETH and BTC also use smaller notional caps to reduce damage from repeated counter-trend attempts.


For research runs, the daily trade cap was effectively removed so overnight sessions can collect a fuller sample. Other protections remain in place (drawdown, cooldowns, consecutive-loss pause, per-symbol cooldown discipline). Summary reporting now also includes PnL by symbol and exit-reason breakdowns.


Current refinement after the latest 12h session: the active research universe was narrowed to SOL/LINK/XRP, removing ETH and BNB due to clearly negative symbol-level contribution. Exit protection was also tightened slightly (earlier fast-fail, stronger BE lock, earlier giveback/momentum decay response) to prioritize win rate and net PnL quality over trade count.


Latest refinement: LINK was removed after repeated contamination. GIVEBACK_EXIT now requires enough gross room to cover fees and leave real net edge before closing, and the global loss-pause was shortened for faster research iteration.


Latest safe refinement: before opening a trade, the scalper now requires the projected gross move to TP to exceed modeled fees/slippage by a minimum multiplier. This is meant to avoid structurally weak trades that cannot realistically leave enough net edge after costs.


Latest 12h-sample refinement: the scalper net-edge floor was relaxed slightly and the score threshold lowered a bit to recover enough trade frequency for evaluation, while preserving the cleaner SOL/XRP universe and the safer post-fee entry discipline.

Latest protection-focused refinement: the scalper now requires a cleaner reversal candle (minimum body + reclaim quality), uses stricter symbol-specific score thresholds, cuts losing room slightly, and protects winners earlier. Trade management now also supports a small early partial take-profit with stop-locking on the remainder, plus more aggressive fast-fail / momentum-decay handling to reduce dead trades and oversized losers.

Latest directional refinement: XRP was loosened slightly to restore sample flow, while `SOL SHORT` was made harder on purpose. Shorts now need clearer signs of actual exhaustion instead of simple overextension: stronger rejection structure, usable upper wick, and less evidence of ongoing continuation before a short can trigger.
