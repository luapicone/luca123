# Reversion Scalp v1 — Tomorrow Decision Playbook

Este documento deja preparado el árbol de decisiones para actuar rápido mañana según el resultado de la sesión larga.

## Cómo leer el reporte mañana
Mirar primero, en este orden:
1. `win_rate_pct`
2. `total_pnl`
3. `PNL BY SYMBOL`
4. `EXIT REASONS`
5. `avg_mfe` vs `avg_mae`
6. `avg_peak_progress`
7. Trades concretos más recientes

---

# Escenarios y acción recomendada

## ESCENARIO A — Buen progreso real
### Señales
- win rate >= 45%
- pnl total cerca de break-even o positivo
- uno o más símbolos claramente positivos
- `TP` / `GIVEBACK_EXIT` / `NO_EXPANSION` dominan más que `SL`
- `avg_mfe >= avg_mae`

### Interpretación
La estrategia sí tiene una base útil. Ya no estamos buscando “si sirve”; estamos buscando cómo estabilizar y refinar.

### Acción recomendada
1. **No cambiar la entrada drásticamente**
2. Reducir ligeramente pérdidas residuales:
   - trailing todavía un poco antes
   - BE apenas más agresivo si hay mucho giveback
3. **Recortar el universe** a los símbolos con pnl positivo o menos ruido
4. Subir calidad del reporte:
   - win rate por símbolo
   - avg pnl por símbolo
   - exit reasons por símbolo

### Mejoras concretas posibles
- bajar un poco `TRAILING_DISTANCE_ATR`
- subir un poco cooldown en símbolos de peor performance
- remover del universe símbolos claramente negativos

---

## ESCENARIO B — Mejoró, pero sigue levemente negativo
### Señales
- win rate entre 35% y 45%
- pnl total negativo pequeño
- `avg_peak_progress` bueno
- `avg_mfe` razonable pero no se convierte suficiente en ganancia
- uno o dos símbolos destruyen el neto

### Interpretación
Hay edge parcial, pero está diluido por símbolos malos o por mala captura del movimiento.

### Acción recomendada
1. **Recortar symbols malos primero**, antes de tocar toda la estrategia
2. endurecer anti-overtrading en los símbolos perdedores
3. mantener símbolos que muestran capacidad de TP real
4. considerar menor exposición por símbolo flojo, no tocar los buenos

### Mejoras concretas posibles
- excluir `ETH` / `BTC` si están claramente negativos
- bajar `MAX_SYMBOL_NOTIONAL` de símbolos problemáticos
- cooldown por símbolo más largo tras pérdida
- añadir “max losses per symbol per day”

---

## ESCENARIO C — Win rate bajo, pero trades sí avanzan bastante
### Señales
- win rate <= 35%
- pnl negativo
- `avg_peak_progress` alto
- `avg_mfe` decente, `avg_mae` también alto
- muchas salidas por `SL` luego de haber avanzado

### Interpretación
La entrada no está muerta, pero la gestión del trade está perdiendo valor capturado.

### Acción recomendada
1. atacar **solo exits / management**
2. no reescribir entrada todavía
3. asegurar salida parcial/conservadora antes
4. dar más valor a `GIVEBACK_EXIT`

### Mejoras concretas posibles
- BE todavía más temprano
- `GIVEBACK_EXIT` con umbral más sensible
- `MOMENTUM_DECAY` antes
- trailing más apretado

---

## ESCENARIO D — Todos los símbolos pierden
### Señales
- pnl por símbolo negativo en casi todos
- win rate bajo
- `TP` escasos
- `SL` dominante
- `avg_mfe` pobre

### Interpretación
La hipótesis de entrada de reversion tampoco tiene edge suficiente para este marco.

### Acción recomendada
1. **No seguir tuneando fino esta misma lógica**
2. declarar esta variante como investigación fallida o incompleta
3. pivotear a otra familia:
   - compresión + breakout confirmado
   - mean reversion sobre VWAP con filtro horario
   - solo uno o dos símbolos específicos

### Mejoras concretas posibles
- crear `reversion_scalp_v2` solo si el problema fue configuración, no hipótesis
- si no, abrir estrategia nueva en carpeta paralela

---

## ESCENARIO E — Solo 1 o 2 símbolos sirven
### Señales
- PNL BY SYMBOL muestra claramente que 1–2 activos sostienen lo bueno
- resto destruye la curva

### Interpretación
El edge es **específico por símbolo**, no generalizable al universe completo.

### Acción recomendada
1. operar solo símbolos nobles
2. congelar el resto
3. recalibrar límites/notional solo en los símbolos buenos

### Mejoras concretas posibles
- `SYMBOLS = [...]` reducido
- `MAX_SYMBOL_NOTIONAL` más alto solo en símbolos ganadores
- cooldowns más cortos en símbolos buenos y más largos en malos

---

## ESCENARIO F — Casi no opera aunque corre toda la noche
### Señales
- muy pocos trades o cero
- reporte muy limpio pero inútil para inferencia

### Interpretación
Volvimos a una estrategia demasiado selectiva para el mercado actual.

### Acción recomendada
1. aflojar umbrales moderadamente
2. no tocar risk ni disciplina
3. relajar solo trigger/contexto un paso

### Mejoras concretas posibles
- bajar ligeramente `SCORE_MIN_THRESHOLD`
- bajar `Z_SCORE_MIN`
- aflojar contexto RSI sin destruir simetría

---

# Indicadores que importan y cómo interpretarlos

## `avg_mfe`
- alto: el trade sí tuvo recorrido favorable
- bajo: la idea ni siquiera engancha bien

## `avg_mae`
- alto: el mercado se va bastante en contra
- si es mayor que MFE con frecuencia, la entrada es mala o muy temprana/tardía

## `avg_peak_progress`
- > 1.0 sugiere que bastante trades llegan cerca o pasan el objetivo conceptual
- si eso pasa pero el pnl sigue flojo, el problema es **captura**, no necesariamente entrada

## `EXIT REASONS`
### mucho `SL`
- entrada todavía sucia o contratrend demasiado agresivo

### mucho `NO_EXPANSION`
- la idea está cerca, pero los trades no despegan; podría ser timing o targets

### mucho `GIVEBACK_EXIT`
- hay oportunidad, pero se devuelve demasiada ganancia; ajustar trailing/BE

### mucho `TP`
- excelente señal; conviene proteger lo que ya funciona y no sobreactuar

---

# Recomendaciones rápidas para mañana según el número principal

## Si win rate >= 45%
- refinar, no reescribir

## Si win rate 35–45%
- recortar símbolos malos + pulir exits

## Si win rate 25–35%
- revisar si MFE/peak_progress salvan la hipótesis
- si sí: tocar exits
- si no: tocar entrada o pivot

## Si win rate < 25%
- fuerte sospecha de hipótesis floja salvo que 1 símbolo destaque mucho

---

# Mi prioridad de toma de decisiones mañana
1. ¿Hay símbolos claramente rescatables?
2. ¿Los trades avanzan a favor o no?
3. ¿Las pérdidas vienen por mala entrada o mala gestión?
4. ¿Vale la pena seguir esta familia o pivotear otra vez?

---

# Comandos para mañana
## Generar resumen
```bash
python3 reversion_scalp_v1/make_summary_report.py && cat reversion_scalp_v1_summary.txt
```

## Buscar rápidamente pnl por símbolo / exits si hace falta revisar DB directo
```bash
sqlite3 reversion_scalp_v1/data/trades.db "select symbol, count(*), round(sum(pnl),6), round(avg(pnl),6) from trades group by symbol order by sum(pnl) desc;"
sqlite3 reversion_scalp_v1/data/trades.db "select exit_reason, count(*), round(sum(pnl),6) from trades group by exit_reason order by count(*) desc;"
```
