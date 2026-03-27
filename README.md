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

## Próximos pasos

1. conectar `RealExecutionAdapter` a APIs reales con firma/autenticación
2. reemplazar reglas default por exchange metadata real
3. automatizar rotación/adaptación de universo de pares
4. añadir replay/backtest sobre logs históricos más ricos
5. exponer dashboard web con charts más avanzados
6. sumar persistencia histórica de snapshots de mercado
