# Tick Vampire v3

Bot paper-first de scalping para futuros.

## Ejecutar

```bash
pip install -r requirements.txt
PYTHONPATH=. python3 -m tick_vampire_v3.main --dry-run
```

## Estado

- Block 1: scaffold modular
- Block 2: loop paper básico
- Block 3: snapshot market loop + DB logging + scheduler de sesiones

## Advertencias

- Solo paper/dry-run por ahora
- No live real habilitado
- Validar varios días antes de considerar siguiente paso

## Reporte rápido Tick Vampire v3

```bash
python3 tick_vampire_v3/make_report.py
cat tick_vampire_v3_report.txt
```


Para testing rápido, Tick Vampire v3 viene con `IGNORE_SESSIONS = True` por defecto en `tick_vampire_v3/config.py`, así puede correr a cualquier hora.


## Paper calibration note

Current paper defaults were widened after the first live observation round so that take-profit distance can exceed modeled costs and the research loop is not halted too aggressively by early drawdown.


## Research note

Current development is explicitly paper-first. The bot is being tightened toward a *no-trade-is-better-than-bad-trade* posture because the early versions proved that frequent low-quality entries were structurally unprofitable after fees.


## Multi-asset paper mode

Tick Vampire v3 now scans a curated liquid futures basket and only opens the highest-scoring setup at a time instead of forcing trades on a single market.
