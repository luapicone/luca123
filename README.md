# leadlagobot

Bot de lead-lag en **paper trading** orientado a Binance (líder) y Bybit (seguidor), diseñado para acercarse lo más posible a un bot real sin usar dinero real.

## Estado actual

MVP inicial en **Python** con:
- motor de estrategia
- ejecución paper
- comisiones
- slippage configurable
- slippage dinámico por profundidad visible
- profundidad multi-nivel inicial por websocket (`depth5` en Binance + `orderbook.50` en Bybit)
- parámetro base para ampliar la profundidad efectiva modelada (`DEPTH_LEVELS_ASSUMED`)
- fills parciales simulados según profundidad visible agregada multi-nivel
- cancelaciones paper por profundidad insuficiente
- posiciones abiertas/cerradas
- logging de trades
- feeds reales por websocket para Binance Futures y Bybit Linear
- top-of-book (`bid/ask`) y tamaños (`bid_size/ask_size`)
- filtro básico por calidad de señal
- tracking de edad de señal / latencia relativa
- métricas persistidas por par en `data/pair_metrics.json`
- ranking dinámico por par en `data/pair_ranking.json`
- selección automática de top pares según ranking
- registro de oportunidades rechazadas en `data/rejected_opportunities.jsonl`
- registro de órdenes canceladas en `data/cancelled_orders.jsonl`
- snapshot de estado en vivo en `data/status.json`
- dashboard CLI en vivo
- dashboard web liviano con filtro por símbolo y chart básico de balance
- replay / backtest enriquecido sobre logs
- persistencia histórica de snapshots de estado en `data/status_history.jsonl`
- capa base separada de adapters de ejecución (`PaperExecutionAdapter` / `RealExecutionAdapter`)
- guard de seguridad para bloquear ejecución real salvo habilitación explícita (`REAL_EXECUTION_ENABLED=true`)
- interface de ejecución real preparada para intents con `side`, `qty`, `reference_price` y `order_type`
- hints de endpoints reales por exchange para el wiring futuro
- modo `mock` opcional para desarrollo

## Estructura

```bash
src/leadlagobot/
  config/
  exchanges/
  engine/
  models/
  utils/
```

## Variables

Copiar:

```bash
cp .env.example .env
```

## Instalar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecutar

```bash
PYTHONPATH=src python -m leadlagobot.main
```

## Dashboard CLI

En otra terminal:

```bash
PYTHONPATH=src python -m leadlagobot.dashboard
```

## Dashboard web liviano

```bash
PYTHONPATH=src python -m leadlagobot.web_dashboard
```

Después abrir:

```text
http://localhost:8080
```

## Replay / Backtest básico

```bash
PYTHONPATH=src python -m leadlagobot.backtest
```

## Runner de experimentos

Para probar varias configuraciones live en tandas secuenciales y comparar resultados. El runner guarda también métricas de edge esperado vs edge realizado para auditar si el modelo de costos está destruyendo el PnL neto:

```bash
EXPERIMENT_DURATION_SECONDS=1800 python3 scripts/run_experiments.py
python3 scripts/make_experiment_report.py
cat experiment_report.txt
```

### Modo de feed

- `FEED_MODE=live` → websockets reales de Binance y Bybit
- `FEED_MODE=mock` → simulación local para desarrollo

## Archivos de salida

- `data/paper_trades.jsonl` → trades cerrados
- `data/pair_metrics.json` → métricas agregadas por símbolo
- `data/pair_ranking.json` → ranking dinámico por símbolo
- `data/rejected_opportunities.jsonl` → oportunidades descartadas y razón
- `data/cancelled_orders.jsonl` → órdenes canceladas por falta de fill suficiente
- `data/status.json` → estado vivo del bot
- `data/status_history.jsonl` → historial de snapshots para replay/dashboard

## Bloque 1 incorporado

Se agregó una base seria antes de ejecución real:

- `RiskEngine` con límites operativos
- kill switch por archivo (`data/KILL_SWITCH`)
- límites de pérdida diaria
- límite de pérdida por trade
- límite de posiciones abiertas
- límite de exposición total
- control de tasa de cancelaciones
- `ReconciliationStore` con snapshot persistido de posiciones/ticks
- estado de riesgo visible en `status.json`

## Bloque 2 incorporado

Se agregó una base operativa pre-real para validación:

- validación de reglas por símbolo (`tick_size`, `qty_step`, `min_qty`, `min_notional`)
- chequeo base de margen disponible y exposición
- reasons explícitos en `status.json` para riesgo / margen / reglas
- snapshot visible de reglas activas del símbolo

## Bloque 3 incorporado

Se agregó una base seria pre-ejecución real:

- sincronización de metadata real de Binance/Bybit (`metadata_sync.py`)
- reemplazo de reglas default por metadata real cuando está disponible
- preparación de firma HMAC para Binance y Bybit
- dry-run de órdenes con auditoría en `data/execution_dry_run.jsonl`
- variables de API y `DRY_RUN_ENABLED`

## Bloque 4 incorporado

Se agregó una base más cercana a producción, todavía protegida:

- boot con metadata real automática
- `REAL_CONFIRM_TOKEN` como guard adicional para ejecución real
- snapshot de cuenta/posiciones en modo dry-run (`account_sync.py`)
- reconciliación extendida con `account_snapshot`
- payloads firmados preparados y auditados, pero no enviados por defecto

## Bloque 5 incorporado

Se agregó un paso más cercano a producción, todavía controlado:

- consultas reales de solo lectura para balance/posiciones si hay credenciales
- snapshot de cuenta enriquecido en `status.json`
- reconciliación `internal_vs_account` para comparar posiciones internas vs exchange
- guard doble para ejecución real (`REAL_EXECUTION_ENABLED` + `REAL_CONFIRM_TOKEN`)

## Bloque 6 incorporado

Se agregó un paso más para acercarse a respuestas reales de ejecución, todavía en dry-run:

- previews de respuesta de orden por exchange en `RealExecutionAdapter`
- auditoría de payload firmado + respuesta simulada de exchange
- reconciliación extendida con `execution_snapshot`

## Bloque 7 incorporado

Se integró el preview de ejecución dry-run dentro del loop principal:

- `execution_snapshot` visible en `status.json`
- `execution_snapshot` persistido en `reconciliation.json`
- preview de entry/exit por símbolo antes de ejecución paper

## Calibración paper trading

Se recalibraron los defaults con evidencia real de paper trading para evitar edge demasiado chico, concentración excesiva en BRUSDT y fills de baja calidad.

Para generar un reporte resumido compartible por Discord: `python3 scripts/make_discord_report.py` (genera `discord_report.txt`).

- `MIN_FILL_RATIO=0.45`
- `ENTRY_THRESHOLD_PCT=0.24`
- `EXIT_THRESHOLD_PCT=0.08`
- `MIN_QUALITY_SCORE=0.02`
- `MAX_SIGNAL_AGE_MS=5000`
- `TOP_PAIRS_LIMIT=10`
- `RANKING_MIN_SIGNALS=40`
- `MAX_CANCEL_RATE=0.95`
- universo sugerido sin `BRUSDT` ni `BEATUSDT` para esta fase de calibración

## Bloque B incorporado (calibración de lógica)

Se agregó una mejora de lógica basada en reportes reales de paper trading:

- filtro de `expected_net_edge_pct` antes de abrir trades
- estimación explícita de costo esperado (`expected_cost_pct`) en `status.json`
- salida más racional usando captura mínima relativa al gap de entrada
- confirmación simple de reversión antes de entrar
- mínimo y máximo de hold
- stop-loss relativo al gap de entrada
- ranking menos secuestrable por símbolos con volumen masivo de señales
- nuevos parámetros de lógica: `EXPECTED_NET_EDGE_MARGIN_PCT`, `MIN_EXPECTED_NET_EDGE_PCT`, `ENTRY_CONFIRMATION_DROP_PCT`, `MIN_HOLD_MS`, `MAX_HOLD_MS`, `STOP_LOSS_GAP_MULTIPLIER`, `MIN_EXIT_CAPTURE_RATIO`, `MAX_CROSS_EXCHANGE_TICK_AGE_MS`, `RANKING_SIGNAL_SATURATION`, `RANKING_REJECTION_PENALTY_CAP`, `RANKING_CANCEL_PENALTY_CAP`

## Bloque 8 incorporado

Se agregó un subbloque seguro previo a activación real:

- lectura real de órdenes abiertas por exchange en modo solo lectura
- chequeo de activación segura (`activation_check.py`)
- reconciliación extendida con órdenes abiertas del exchange

## Mean reversion intradía

Ahora el bot soporta un pivot a estrategia de **mean reversion intradía** usando `STRATEGY_MODE=mean_reversion`.

Parámetros base:

- `MR_LOOKBACK`
- `MR_ENTRY_ZSCORE`
- `MR_EXIT_ZSCORE`
- `MR_MIN_HOLD_MS`
- `MR_MAX_HOLD_MS`

## Research de señales

Ahora también se guarda un dataset liviano de research en:

- `data/research_signals.jsonl`
- `data/research_summary.json`

Para resumirlo:

```bash
python3 scripts/make_research_report.py
cat research_report.txt
```

## Próximos pasos

1. enviar órdenes reales firmadas con confirmaciones y límites fuertes
2. endurecer reconciliación con respuestas reales de órdenes
3. automatizar rotación/adaptación de universo de pares
4. añadir replay/backtest sobre logs históricos más ricos
5. exponer dashboard web con charts más avanzados
6. sumar persistencia histórica de snapshots de mercado

## Tick Vampire v3 (paper-first scaffold)

Se agregó una base modular y segura en `tick_vampire_v3/` para evolucionar a un bot de scalping de futuros en modo paper/dry-run first.

Ejecutar:

```bash
python3 tick_vampire_v3/main.py --dry-run
```

Esta versión Block 2 ya corre un loop paper en tiempo real con snapshot de mercado, filtros básicos, apertura/cierre simulado y logging a SQLite.
