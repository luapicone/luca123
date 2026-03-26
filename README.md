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
- feeds mock en tiempo real para desarrollar la arquitectura

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

## Próximos pasos

1. reemplazar feeds mock por websockets reales de Binance y Bybit
2. usar pares filtrados por scanner real
3. agregar order book / profundidad
4. mejorar modelo de slippage
5. paper trading con fills más realistas
6. preparar capa de ejecución real separada
