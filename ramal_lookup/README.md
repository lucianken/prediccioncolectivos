# ramal_lookup — Identificación offline de route_id → shape

Módulo que construye y mantiene la lookup table `route_id → shape` para las
líneas de colectivo de CABA/GBA. Es el prerequisito del pipeline de ETA:
en tiempo real, identificar el ramal de un vehículo es un O(1) lookup en
`ramal_map.json`.

---

## El problema

La API de posiciones entrega `route_id`, `direction_id` y GPS por vehículo.
Cada línea tiene varios ramales, cada ramal un shape (polilínea). El `route_id`
mapea 1:1 a un shape dentro de un período de ~2-3 semanas, pero se resetea en
cada rotación: los mismos ramales físicos reciben nuevos números.

**No se puede hardcodear el mapeo.** Hay que reconstruirlo offline cada período.

---

## Enfoque C — Algoritmo implementado

Descartados el Transformer (Enfoque A, requiere labels) y la eliminación
iterativa (Enfoque B, se traba con fraccionados). Ver `research_ramal_id_approaches.md`.

### Discriminadores

**Entre completos (A vs B vs C):**
- **Voto-por-punto**: cada GPS vota al shape con menor perp (argmin). En el
  tramo exclusivo de B los votos van todos a B; en el tramo compartido se
  reparten. El margen del voto discrimina sin necesitar zonas únicas amplias.
- **Cuantil p95 del perp**: en vez del promedio (que se diluye en el troncal
  compartido), usar la cola. En el tramo exclusivo, el shape incorrecto tiene
  p95 >> GPS noise; el correcto tiene p95 ≈ GPS noise. Señal enorme incluso
  con tramos exclusivos pequeños.

**Entre completo y fraccionado (A vs D, donde D ⊆ A):**
- **Coverage p2/p98**: rango efectivo del bus sobre el shape padre,
  robusto a outliers GPS (teletransporte, salida de depósito).
  Un bus fraccionado (D) solo cubre ~77% de A; un bus completo cubre ~100%.
  El coverage_gap separa los casos con margen ~22%.
- **Containment**: fracción de puntos con perp < 30m. Si el bus excede el
  shape (completo vs fraccionado), containment cae → filtro previo.

### Decisión

```
Para cada route_id R con direction_id D:
  candidatos = shapes con direction == D  (6 de 12 para línea 39)

  cov_winner = argmax(coverage × containment) entre candidatos con containment ≥ 0.6
  
  Si cov_winner es fraccionado:
    gap = coverage(fraccionado) - coverage(padre)
    si gap ≥ 0.20 → asignar como fraccionado
    si no → pending
  
  Si cov_winner es completo:
    q95_winner = argmin(p95_perp) entre candidatos con containment alto
    vote_winner = argmax(vote_frac) entre candidatos con containment alto
    si q95_margin ≥ 0.40 o vote_margin ≥ 0.15 → asignar como completo
    si no → pending
  
  Gate de cold-start: si n_trips < 3 → pending
```

### Fix crítico: p2/p98 en coverage

`min()` y `max()` de dist_along son sensibles a un solo punto GPS outlier
(teletransporte). Con más días de datos se acumulan más outliers y la métrica
**degrada**. Reemplazados por `np.percentile(ds, 2)` y `np.percentile(ds, 98)`,
que ignoran el 4% de cola. Verificado: 2 puntos outlier de 3934 causaban
gap = 13.5% en vez del real 22.2% para route_id 1340 (39F-d0).

---

## Fraccionados

Algunos ramales son "fraccionados": recorren solo una parte del recorrido del
completo correspondiente (mismo inicio o fin, pega la vuelta antes/después).

Para línea 39, el mapa de familias es fijo (geometría conocida):
- 39A (completo) → 39D (fraccionado)
- 39B → 39E
- 39C → 39F

Archivo: `families_39.json`. Para otras líneas, crear el equivalente.

La detección completo/fraccionado es automática via coverage_gap. El mapa de
familias solo indica qué shapes son fraccionados de cuál padre — sin él el
algoritmo no sabe a quién comparar el coverage.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `route_lookup.py` | Algoritmo core. Importar `build_lookup()`, `build_shape_entries()`, `load_families()`. |
| `build_lookup.py` | Runner batch: procesa N días y genera `lookup_results_{line}.json`. Útil para backfill o validación. |
| `run_daily.py` | Runner incremental: procesa un día, detecta rotaciones, mantiene `ramal_map.json`. Para uso en producción. |
| `families_{line}.json` | Mapa fijo de fraccionados por línea. |
| `ramal_map.json` | **Output definitivo**: lookup route_id → shape con historial temporal completo. |
| `lookup_state/state_{line}.json` | Estado interno del runner incremental (resolved/pending por línea). |
| `visualizar_fraccionados.py` | Herramienta de diagnóstico: genera mapa Leaflet con GPS + shapes. |

---

## Uso

### Producción — correr diariamente

```bash
# Procesar el día de hoy para todas las líneas:
python ramal_lookup/run_daily.py --data-dir Z:\grabaciones

# Solo una línea:
python ramal_lookup/run_daily.py --data-dir Z:\grabaciones --line 39

# Backfill de un día específico:
python ramal_lookup/run_daily.py --data-dir Z:\grabaciones --day 2026-05-08
```

El runner:
1. Lee el NDJSON del día → detecta route_ids activos
2. Nuevos route_ids → agrega como pending
3. Pending → acumula evidencia desde su first_seen y resuelve
4. Resueltos → bloqueados, nunca se retocan
5. Desaparecidos (> 7 días) → marcados como retired en ramal_map

### Validación / debug

```bash
# Batch con control de parámetros:
python ramal_lookup/build_lookup.py --data-dir Z:\grabaciones --line 39

# Ajustar umbrales si hay pending:
python ramal_lookup/build_lookup.py --data-dir Z:\grabaciones --line 39 \
    --quantile-margin 0.15 --coverage-gap 0.15

# Visualizar GPS de fraccionados:
python ramal_lookup/visualizar_fraccionados.py --data-dir Z:\grabaciones --day 2026-03-31
```

---

## Resultados — línea 39

| Período | Route IDs | Resueltos | Días necesarios |
|---------|-----------|-----------|-----------------|
| Mar 29 – May 8 (p1) | 12 | 12/12 | 5 |
| May 8 – May 23 (p2) | 12 | 12/12 | 14 (backfill) |
| May 23 – hoy (p3) | 12 | 12/12 | 1 |

Confianza típica: completos (A/B/C) q95_margin 0.89-0.98, fraccionados
(D/E/F) coverage_gap 0.21-0.23.

**36/36 route_ids históricos resueltos.** En producción desde el runner
incremental: período 3 resuelto en 1 día de datos.

---

## Rotaciones

Cada ~2-3 semanas los route_ids se resetean (rotación). El runner detecta
automáticamente cuando aparecen route_ids nuevos y los procesa. Los viejos
quedan como `retired` con su historial completo en `ramal_map.json`.

Un mismo número puede reaparecer en un período futuro representando un ramal
distinto. Por eso `ramal_map.json` guarda `first_seen` / `last_seen` por
cada entrada: nunca se asume que el mismo route_id implica el mismo ramal.

---

## Pendiente

- Shapes y families para líneas 26, 42, 92, 124, 151, 168
- Runner incremental ya funciona para 39; al agregar families_{line}.json
  automáticamente empieza a resolver esas líneas también
