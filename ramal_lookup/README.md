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
```

`build_ramal_map.py` se puede volver a correr cuando hay datos nuevos — es
idempotente y eficiente: lee GPS solo en los días con route_ids pendientes,
el resto es un scan barato de IDs. Para 60 días con 3 rotaciones: ~6 días de
GPS real, 54 de scan.

---

## Algoritmo (Enfoque C)

Ver `research_ramal_id_approaches.md` para la comparación completa de enfoques.

### Discriminadores

**Entre completos (A vs B vs C) — tramos similares con ~5% de zona exclusiva:**

- **Cuantil p95 del perp** (discriminador principal): en la zona exclusiva de B,
  el p95 del error perpendicular sobre el shape incorrecto es 300-900m; sobre el
  correcto es ~15m (solo ruido GPS). El margen relativo `(q_second - q_best) / q_second`
  es decisivo incluso con zonas exclusivas pequeñas. Umbral: 0.40.

- **Voto-por-punto** (fallback): cada GPS vota al shape con menor perp. El margen
  de votos en la zona exclusiva discrimina correctamente. Umbral: 0.15.

**Entre completo y fraccionado (A vs D, donde D ⊆ A):**

- **Coverage p2/p98**: rango efectivo del bus sobre el shape padre.
  Un fraccionado cubre ~77% del completo; un completo cubre ~100%.
  Gap típico: ~22%. Umbral: 0.20.
  
  *p2/p98 en lugar de min/max*: robusto a outliers GPS (teletransporte, salidas
  de depósito) que de otro modo arrastran el rango y reducen el gap artificialmente.

- **Containment**: fracción de puntos con perp < 30m. Filtra shapes donde el bus
  claramente se sale del recorrido.

### Decisión por route_id

```
candidatos = shapes con direction == route_id.direction_id

cov_winner = argmax(coverage × containment) entre candidatos con containment ≥ 0.6

Si cov_winner es fraccionado:
  gap = coverage(fraccionado) - coverage(padre)  → umbral 0.20

Si cov_winner es completo:
  q95_margin = (q_second - q_best) / q_second   → umbral 0.40
  vote_margin = vote_winner - vote_second        → umbral 0.15
  (cualquiera que pase su umbral resuelve)

Gate cold-start: n_trips < 3 → pending
```

### Fraccionados

Ramales que recorren solo parte del completo correspondiente. El mapa de familias
es fijo por línea (geometría conocida, no se detecta automáticamente):

```json
// families_39.json
{ "39A": ["39D"], "39B": ["39E"], "39C": ["39F"] }
```

Para agregar una línea nueva: crear `families_{line}.json` (vacío `{}` si no
tiene fraccionados) y `build_ramal_map.py` la resuelve automáticamente.

---

## Resultados — línea 39 (62 días, 3 períodos)

| Período | Fechas | Route IDs | Resueltos | Días de GPS leídos |
|---------|--------|-----------|-----------|-------------------|
| 1 | Mar 29 – May 8 | 12 | 12/12 | ~2 |
| 2 | May 8 – May 23 | 12 | 12/12 | ~2 |
| 3 | May 23 – hoy | 12 | 12/12 | 1 |

Confianza completos (A/B/C): q95_margin 0.89–0.98.
Confianza fraccionados (D/E/F): coverage_gap 0.21–0.23.

---

## Escalar a otras líneas

Las líneas 26, 42, 92, 124, 151, 168 están en `line_shapes.json`.
Para resolver cada una: crear `families_{line}.json` y volver a correr
`build_ramal_map.py`. Las líneas sin fraccionados usan `{}` como families.
