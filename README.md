# leadlagobot

Bot de lead-lag en **paper trading** orientado a Binance (líder) y Bybit (seguidor), diseñado para acercarse lo más posible a un bot real sin usar dinero real.

## Estado actual

MVP inicial en **Python** con:
- motor de estrategia
- ejecución paper
- comisiones
- slippage configurable
- slippage dinámico por profundidad visible
- posiciones abiertas/cerradas
- logging de trades
- feeds reales por websocket para Binance Futures y Bybit Linear
- top-of-book (`bid/ask`) y tamaños (`bid_size/ask_size`)
- filtro básico por calidad de señal
- tracking de edad de señal / latencia relativa
- métricas persistidas por par en `data/pair_metrics.json`
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

## Próximos pasos

1. persistir snapshots de oportunidades rechazadas
2. paper fills parciales y cancelaciones simuladas
3. agregar snapshots de order book más profundos
4. ranking dinámico automático de pares
5. preparar capa de ejecución real separada
6. dashboard / métricas en vivo
