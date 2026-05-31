# ramal_lookup — Identificación offline de route_id → shape

Módulo que construye y mantiene la lookup `route_id → shape` para las líneas
de colectivo de CABA/GBA. Es el prerequisito del pipeline de ETA: en tiempo
real, identificar el ramal de un vehículo es un O(1) lookup en `ramal_map.json`.

---

## El problema

La API entrega `route_id`, `direction_id` y GPS por vehículo. Cada línea tiene
varios ramales, cada ramal un shape (polilínea). El `route_id` mapea 1:1 a un
shape dentro de un período de ~2-3 semanas, pero se resetea en cada rotación:
los mismos ramales físicos reciben números nuevos. El mismo número puede volver
en el futuro representando un ramal distinto. `ramal_map.json` guarda
`first_seen`/`last_seen` por cada entrada para manejar esto sin ambigüedad.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `build_ramal_map.py` | **Script principal.** Procesa todos los NDJSON disponibles y genera `ramal_map.json`. |
| `route_lookup.py` | Algoritmo core. No se corre directamente — lo usan los runners. |
| `families_{line}.json` | Mapa fijo de fraccionados por línea. Requerido para resolver. |
| `ramal_map.json` | **Output definitivo.** Lookup route_id → shape con historial completo. |
| `build_lookup.py` | Runner de validación/debug con control de fechas y parámetros. No para producción. |

---

## Uso

```bash
# Construir o reconstruir ramal_map.json desde todos los datos disponibles:
python ramal_lookup/build_ramal_map.py --data-dir Z:\grabaciones

# Solo una línea:
python ramal_lookup/build_ramal_map.py --data-dir Z:\grabaciones --line 39

# Debug con control de parámetros del algoritmo:
python ramal_lookup/build_lookup.py --data-dir Z:\grabaciones --line 39 --quantile-margin 0.15
python ramal_lookup/build_lookup.py --data-dir Z:\grabaciones --line 39 --fraccionado-margin 0.10
```

`build_ramal_map.py` se puede volver a correr cuando hay datos nuevos — es
idempotente y eficiente: lee GPS solo en los días con route_ids pendientes,
el resto es un scan de IDs. Para 60 días con 3 rotaciones: ~6 días de GPS
real, 54 de scan.

### Costo real del scan

Cada día de scan lee el archivo NDJSON.gz completo (~20-40 MB comprimido),
lo descomprime y parsea todos los frames JSON para reconstruir snapshots
cada 30 s. El estado de la flota tiene ~4000-10000 vehículos, pero gracias
a `reconstruct_line_snapshots()` en `reader.py` solo se copian los ~50-100
vehículos de la línea de interés (reducción de 100× en el tamaño del snapshot
yieldeado). El cuello de botella real es la I/O de descompresión + parseo JSON.

---

## Optimizaciones de rendimiento

### orjson (parseo JSON)
Si `orjson` está instalado (`pip install orjson`), `reader.py` lo usa
automáticamente con fallback transparente a `json` estándar. orjson es 3-4×
más rápido que el módulo `json` de la stdlib para este tipo de payloads.
Representa ~26% del tiempo total según profiling.

### isal (descompresión gzip)
Si `isal` está instalado (`pip install isal`), `reader.py` usa `isal.igzip`
para descompresión, que es ~2× más rápido que `gzip` estándar (Intel ISA-L).
Representa ~12% del tiempo total. Solo se activa si está disponible; sin él
se usa el módulo `gzip` estándar.

### project_many (proyección vectorizada)
`ShapeIndex.project_many(lats, lons)` proyecta N puntos sobre el shape en una
sola operación numpy con broadcast (O(M×S) en Python puro vs O(M×S) con un
loop Python externo). `route_lookup.py` lo usa para proyectar todos los puntos
de un route_id sobre cada shape candidato en una sola llamada. Esto elimina el
loop Python por-punto que representaba ~20% del tiempo total (~2.25M llamadas).
Los resultados son numéricamente idénticos a los del loop punto-a-punto.

### reconstruct_line_snapshots (filtrado de flota)
`reader.py` expone `reconstruct_line_snapshots(filepath, label_line_map, line)`
que mantiene en `state` únicamente los vehículos de la línea de interés. Los
consumidores de `ramal_lookup` (`scan_route_ids`, `scan_with_gps`,
`build_lookup.py`) ya no necesitan filtrar por label en el loop interno.
Elimina el 11% de CPU de `dict.get + str.split` sobre la flota completa.

---

## Algoritmo (Enfoque C)

Ver `research_ramal_id_approaches.md` para la comparación completa de enfoques.

### Discriminadores

**Entre completos (A vs B vs C) — tramos similares con ~5% de zona exclusiva:**

- **Cuantil p95 del perp** y **voto-por-punto** son discriminadores simétricos:
  cualquiera que supere su umbral puede resolver la asignación. No hay un
  discriminador "principal" y uno "fallback" — ambos son señales independientes
  y ambas se usan si están disponibles.

  - p95 del perp: en la zona exclusiva del shape incorrecto, el p95 del error
    perpendicular es 300-900m; sobre el correcto es ~15m. Margen relativo
    `(q_second - q_best) / q_second`. Umbral: 0.40.

  - Voto-por-punto: cada GPS vota al shape con menor perp. En la zona exclusiva
    el ganador acumula la mayoría. Umbral de margen: 0.15.

  Si ambos coinciden en el ganador → ese shape. Si difieren → se prefiere p95
  (señal más limpia en los datos observados).

**Entre completo y fraccionado (A vs D, donde D ⊆ A):**

- **Coverage gap relativo**: `gap_rel = (cov_frac - cov_padre) / cov_frac`.
  Se usa gap RELATIVO (no absoluto) para ser robusto cuando cov_frac < 1.0
  por GPS noise o outliers.
  En la línea 39: cov_frac ≈ 1.0, cov_padre ≈ 0.77-0.78 → gap_rel ≈ 0.22-0.23.
  Umbral default: 0.15 (margen cómodo de ~0.07 sobre el gap observado).
  Limitación conocida: fraccionados que cubren >85% del padre (gap_rel < 0.15)
  quedan pending; ajustar con `--coverage-gap` si se necesita.

  *p2/p98 en lugar de min/max*: robusto a outliers GPS que arrastran el rango.

- **Containment**: fracción de puntos con perp < 30m. Filtra shapes donde el bus
  claramente se sale del recorrido.

- **Margen entre fraccionados**: `(score_best - score_2nd) / score_best` entre
  fraccionados candidatos con containment alto. Default 0.05; subir a 0.10-0.15
  con `--fraccionado-margin` si se observan falsas resoluciones.

### Decisión por route_id

```
candidatos = shapes con direction == route_id.direction_id

cov_winner = argmax(coverage × containment) entre candidatos con containment >= 0.6

Si cov_winner es fraccionado:
  gap_rel = (coverage(frac) - coverage(padre)) / coverage(frac)
  Si gap_rel >= 0.15 → resolved "fraccionado" (confianza = gap_rel)

Si cov_winner es completo:
  q95_margin = (q_second - q_best) / q_second   → umbral 0.40
  vote_margin = vote_winner - vote_second        → umbral 0.15
  Si cualquiera supera su umbral → resolved "completo"

Gate cold-start: n_trips < 3 → pending
```

### Fraccionados

Ramales que recorren solo parte del completo correspondiente. El mapa de familias
es fijo por línea (geometría conocida, no se detecta automáticamente):

```json
// families_39.json
{ "families": { "39A": ["39D"], "39B": ["39E"], "39C": ["39F"] } }
```

Para agregar una línea nueva: crear `families_{line}.json` (vacío `{"families":{}}` si no
tiene fraccionados) y `build_ramal_map.py` la resuelve automáticamente.

---

## Resultados — línea 39 (63 días, 3 períodos)

| Período | Fechas | Route IDs | Resueltos | Días de GPS leídos |
|---------|--------|-----------|-----------|-------------------|
| 1 | Mar 29 – May 7 | 12 | 12/12 | ~2 |
| 2 | May 8 – May 22 | 12 | 12/12 | ~4 |
| 3 | May 23 – May 30 | 12 | 12/12 | ~5 |

Confianza completos (A/B/C): q95_margin 0.89–0.98.
Confianza fraccionados (D/E/F): coverage_gap_relative 0.21–0.23.

---

## Tiempos de procesamiento (referencia)

| Versión | Configuración | Tiempo (63 días, línea 39) |
|---------|--------------|---------------------------|
| Original | json + gzip + loop por punto | ~20 min (estimado) |
| Optimizado | orjson + isal + project_many + line-filtered snapshots | ~7.5 min |

Las optimizaciones apiladas reducen el tiempo total ~2.5-3× según profiling
(JSON 26% → orjson 3-4×, proyección 20% → batch numpy, filtrado 11% → 100×
menos vehículos a copiar, gzip 12% → isal ~2×).

---

## Escalar a otras líneas

Las líneas 26, 42, 92, 124, 151, 168 están en `line_shapes.json`.
Para resolver cada una: crear `families_{line}.json` y volver a correr
`build_ramal_map.py`. Las líneas sin fraccionados usan `{"families":{}}`.
