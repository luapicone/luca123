# leadlagobot

Bot de lead-lag en **paper trading** orientado a Binance (líder) y Bybit (seguidor), diseñado para acercarse lo más posible a un bot real sin usar dinero real.

## Estado actual

MVP inicial en **Python** con:
- motor de estrategia
- ejecución paper
- comisiones
- slippage configurable
- slippage dinámico por profundidad visible
- fills parciales simulados según profundidad visible
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

## Próximos pasos

1. agregar snapshots de order book más profundos
2. dashboard visual sobre `status.json` y rankings
3. score de ranking más sofisticado
4. preparar capa de ejecución real separada
5. automatizar rotación/adaptación de universo de pares
6. añadir replay/backtest sobre logs históricos
