# reversion_scalp_v1_aggressive

Aggressive side-by-side variant of the main SOL scalper. Same core logic, but slightly looser frequency settings for comparative live paper evaluation.

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

## Live-safe prep
Create a local `.env` (never commit it) with:
```env
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
LIVE_TRADING=false
MAX_LIVE_CONCURRENT_TRADES=1
MAX_LIVE_SYMBOL_NOTIONAL=10
REQUIRE_MANUAL_POST_ONLY_REVIEW=true
```

To test credential reading and futures balance access without enabling live trading logic:
```bash
python3 -m reversion_scalp_v1_aggressive.test_live_connection
```

To run a preflight check against Binance Futures USDT-M without sending orders:
```bash
python3 -m reversion_scalp_v1_aggressive.live_preflight
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


Latest rollback refinement: restored the pre-overhardening scalper base, then made only two surgical adjustments for the next validation run: SOL max notional was reduced from 20 to 16 to limit its contamination, and dead-trade handling was made slightly more aggressive (fast-fail 4→3 minutes, min progress 0.10→0.12, scratch threshold 0.0006→0.00045).


Latest focused refinement: after a profitable 24h run showed SOL carrying the edge and XRP dragging results, the scalper was narrowed to SOL-only for the next validation pass. Profit capture was also loosened slightly to test a bit more upside on winning SOL trades (TP ATR 0.80→0.85, trailing activation 0.22→0.24, trailing distance 0.22→0.24).


Latest paper-sizing refinement: initial paper balance was increased from 20 USD to 100 USD to make the next validation run more representative and reduce distortions from tiny nominal sizing, while preserving the single-position design.


Historical-frequency refinement: after backtest coverage was verified, the next iteration modestly relaxed the reversion gate to recover frequency on longer windows without changing the SOL-only research universe. RSI extremes were softened slightly (39/61 -> 41/59), z-score threshold lowered (0.55 -> 0.48), and minimum VWAP stretch eased (0.00035 -> 0.00028).
