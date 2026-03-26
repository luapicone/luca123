# leadlagobot

Bot de lead-lag en **paper trading** orientado a Binance (líder) y Bybit (seguidor), diseñado para acercarse lo más posible a un bot real sin usar dinero real.

## Estado actual

MVP inicial en **Python** con:
- motor de estrategia
- ejecución paper
- comisiones
- slippage configurable
- posiciones abiertas/cerradas
- logging de trades
- feeds reales por websocket para Binance Futures y Bybit Linear
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

## Próximos pasos

1. agregar order book / profundidad
2. mejorar modelo de slippage
3. paper trading con fills más realistas
4. incorporar filtros por latencia y calidad de convergencia
5. preparar capa de ejecución real separada
6. dashboard / métricas en vivo
