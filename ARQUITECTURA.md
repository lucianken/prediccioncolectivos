# Arquitectura de predicción — plan vigente (desde 2026-11-10)

**Este es el documento rector.** Si contradice a otro doc, manda este.
`prediccion_ml_plan.md` queda como **referencia histórica de diseño**: ahí está el porqué de muchas decisiones (§7, §7b, §9, §11), pero su estado y su plan de fases están desactualizados.
Copias de todos los docs anteriores a este cambio: `docs_old/2026-11-10/`. Tag git `pre-arquitectura-2026-11` = estado del código antes del cambio.

---

## 1. Objetivo y alcance

Predecir **cuándo pasa un colectivo por un punto** (parada o posición del usuario) en 30–40 líneas AMBA (1–199), y medirlo contra baselines (y más adelante contra Cuándo Subo).
Horizonte de trabajo: hasta mayo 2027. Recursos limitados: tokens y una RTX 3080. **Cada corrida de GPU tiene que responder una pregunta concreta.**

Fuera de alcance por ahora: producción/serving (se resuelve cuando el modelo sirva), identificación de ramal, las 129 líneas, el grabado de Cuándo Subo (lo hace el usuario aparte).

## 2. Reglas que no se negocian

- **La línea de un coche sale solo del sufijo del label** vía `LABEL_LINE_MAP.json` con vigencias (`shapes_io.load_label_line_map(path, on_date=día)`). **Nunca route_id** para identificar línea ni ramal. La identificación de ramal está muerta: `ramal_lookup/` y `ramal_map.json` no se usan en el pipeline nuevo.
- El modelo **no recibe el ramal**. El pipeline necesita *un recorrido* sobre el cual proyectar; se elige **por geometría** (§4.1).
- Sin datos que producción no vaya a tener: la flota de entrada es la de **la agencia** del coche (producción pide por `agency_id`), no la flota total.
- Tests de comportamiento observable, sin change detectors.

## 3. Datos disponibles (verificado 2026-11-10)

- Grabaciones: `Z:\grabaciones\YYYY-MM-DD.ndjson.gz` (SMB a la NUC). **2026-03-28 → 2026-10-15** y desde **2026-11-10**. Hueco 2026-10-15 → 2026-11-09 por caída de la API CABA. El 2026-10-15 está incompleto. Excluidos además 25–27/07 (`EXCLUDED_DAYS` en `build_dataset.py`).
- Pings reales cada **~60 s** por coche (no 30), aunque el grabador emite cada 30 s.
- El tamaño de la flota varía por día y hora (~14k hábil al mediodía, mucho menos de noche/fin de semana): normal.
- Cambio de flota AMBA mayo–junio 2026: lo resuelve el map con vigencias; no es un problema para el pipeline.
- Recorridos: **`../proyectoconsola/data/line_shapes/{N}.json`** (129 líneas, OSM; las 7 históricas con datos de junio 2026, el resto OSM 2026-10-20). Formato `{color, ramales:[{name, shortName, shapeId, points:[[lat,lon]...], stops:[{id,lat,lng,name}]}]}`. Es la **fuente única** para el pipeline nuevo (solo lectura). `prediccion/data/line_shapes.json` (7 líneas) queda como legacy.
- Líneas sin `trip_id` (4, 25: 100 % vacío) no son segmentables con el segmentador actual → fuera.
- Disco libre en C: ~106 GB (2026-11-10). El parquet actual de la 39 pesa 3,5 GB. Vigilar tamaño (§4.3).

## 4. Pipeline v2 (dataset)

Cambios respecto del actual (`prediccion/pipeline/build_dataset.py`), en orden de importancia:

### 4.1 Recorrido por geometría, sin route_id
Implementar la **opción A** de `research_a3w_proyeccion_geometrica.md`: `best_shape_for_trip(lats, lons, shapes_de_la_línea) → (shape_id, median_perp)` usando `ShapeIndex.project_many`. Se elige el recorrido con menor error perpendicular mediano sobre el viaje completo (en training se conoce el viaje entero). Se mantiene el filtro de puntos con `perp > 150 m` (`project_trip`), que corta solo los tramos donde el coche se aparta del recorrido elegido. Esto reemplaza a `route_shape_map`/`load_ramal_map()` y elimina el `skip if not sh_id`.
Consecuencias aceptadas (documentadas en ese research): en tramos compartidos la elección puede ser arbitraria → ruido de normalización, no sesgo; los labels siguen siendo válidos.

### 4.2 Máximo de pares por viaje
Hoy cada viaje aporta **todos** los pares (P, F) → O(n²) (~6.000 pares en un viaje de ~110 puntos; 71,5 M filas para la 39 en 10 semanas). Pasar a **K pares por viaje** (parámetro, default 64), con semilla determinística por viaje. Muestrear **estratificado por distancia restante** (buckets logarítmicos: 100–500 m, 0,5–1, 1–2, 2–5, 5+ km) para no sesgar hacia distancias largas, que es lo que domina hoy. Justificación: `research_training_performance.md` #3 (diversidad está en los viajes, no en los pares).

### 4.3 Unidad de trabajo = un día, idempotente
El diseño de `.claude/skills/ml_timeline.md` (§build_dataset): `process_day(date) → data/ml/v2/daily/YYYY-MM-DD.parquet` (skip si existe), carry al día siguiente, `manifest.json` con líneas por día, `assemble_dataset()` barato. Agregar una línea reprocesa solo los días que no la tienen. El NDJSON se lee **una vez por día para todas las líneas** (filter-first por label).
Columnas de flota (`fleet_flat`): **opcionales y apagadas por defecto** (las primeras corridas son sin flota y pesan ~1,2 KB/fila). Agregar columnas `line` y `shape_id` (para evaluar por línea).

### 4.4 Líneas
30–40 líneas: las 7 actuales (26, 39, 42, 92, 124, 151, 168) + otras elegidas por: recorrido OSM bueno (que los viajes proyecten con perp bajo), cobertura de `trip_id` alta, variedad geográfica (avenidas céntricas, barrios, zona norte/sur/oeste), varias agencias. Más **~8 líneas de control** que nunca entran al train (§5). La lista final y su justificación van en `data/ml/v2/lines.json`.

## 5. Vara de medir (antes de entrenar nada nuevo)

Hoy los números no son comparables: A3 72 s (16,5 M filas val, solo 39), A1 158 s (muestra de 500k), naive 672 s; y el MAE global lo domina el tramo de >5 km (7,1 M de 16,5 M filas, 204 s). Ojo: por bucket, **A1 da 59 s en 0–500 m y 91 s en 0,5–2 km**, comparable o mejor que A3 (68 / 77 s) — una tabla de 7 s de entrenamiento compite con el modelo de horas en distancia corta. Sin una vara única no se puede decidir nada.

- **Período de validación fijo:** 2026-09-15 → 2026-10-14. Train: todo lo anterior (menos excluidos). El 2026-10-15 y lo posterior a 2026-11-10 no se usan para esta vara (posterior = test futuro).
- **Dos conjuntos de evaluación congelados** (parquet con semilla, se generan una vez y no se regeneran):
  - `eval_seen`: líneas del train, período de validación.
  - `eval_heldout`: las ~8 líneas de control, período de validación.
- **Consulta de evaluación:** (coche en P a tiempo t, punto objetivo T adelante en el mismo viaje), con ETA real observada. Muestreo estratificado por ETA real para que cada bucket tenga suficientes casos.
- **Métricas, siempre por bucket** de ETA real (0–5, 5–10, 10–20, 20+ min) y de distancia (<500 m, 0,5–2, 2–5, 5+ km): MAE, P50, P90, sesgo, y **% de subestimaciones > 60 s** (el usuario pierde el colectivo). El MAE global se informa pero no decide.
- **Baselines en el mismo conjunto:** A0 naive (distancia / velocidad, con piso de velocidad razonable), A1 (reentrenado con el train v2; es barato), A3 actual ep21 (solo sobre la 39, como referencia histórica). Cuándo Subo se suma cuando exista su grabación.
- Script único `python -m prediccion.eval ...` que toma un modelo y escribe `data/ml/v2/eval/<modelo>_<fecha>.json` + tabla markdown. Resultados que importan se anotan en §7.

## 6. Escalera de experimentos (sin flota)

Cada escalón es una corrida nocturna y responde una pregunta. Se corta donde deja de haber mejora.

| # | Corrida | Pregunta | Decide |
|---|---|---|---|
| E0 | Baselines A0/A1/A3-actual en la vara | ¿Dónde estamos de verdad? | piso a superar |
| E1 | A3 no-fleet, solo 39, pipeline v2, K=64 | ¿El muestreo de pares y la geometría empeoran algo vs A3 actual? | si K=64 alcanza |
| E2 | A3 no-fleet, 30–40 líneas, K=64 | ¿Más líneas mejoran la 39? ¿Generaliza a las líneas de control? | si vale escalar |
| E3 | flota liviana (1 capa o mean pooling, N≤20) sobre E2 | ¿La flota de la agencia aporta? | si invertir en flota / compute |

Estimación de costo E2: ~1,5 M viajes × 64 ≈ 100 M filas ≈ dataset actual → ~12 min/época sin flota, ~5 h la corrida. La flota con el encoder actual es ~12× más lenta (§9 del plan): por eso va después y en versión liviana. **Comprar compute solo si E3 muestra que la flota vale y no entra en una noche.**

## 7. Resultados (se completa a medida que corren)

| Fecha | Experimento | eval_seen | eval_heldout | Notas |
|---|---|---|---|---|
| — | — | — | — | — |

## 8. Decisiones previas que siguen vigentes (no re-discutir sin dato nuevo)

Del plan histórico: modelo único para todas las líneas (§7); pinball asimétrica por distancia, q 0,5→0,8 bajo 1 km (§7b); distancia mínima 100 m (§7); `schedule_dev_norm` aporta poco pero positivo (Exp. 2); `time_since_last_bus_s` ambiguo (Exp. 2); umbral "llegando" `pred < 150 s OR dist < 300 m` (Exp. 1, reevaluar con el modelo nuevo); stop-to-stop y Transformer seq2seq postergados (§7, Fase 5); la flota de entrada es la de la agencia (§7).

## 9. Inconsistencias conocidas en docs viejos

- Modelo "en producción": `CLAUDE.md` decía ep24 (72,7 s), el plan dice ep21 (72,5 s). No hay modelo en producción real (`proyectoconsola/lib/eta_predict.js` está roto desde el rediseño).
- `research_a3w_proyeccion_geometrica.md` habla de 9.165 filas; el parquet real tiene 71,5 M.
- Split de validación: el código usa último 20 % de días (`build_dataset.py:423`); `ml_timeline.md` dice últimos 7 días. **Ahora manda §5.**
- `INFERENCE_GUIDE.md` no incluye `schedule_dev_norm` ni `time_since_last_bus_s`, y asume `shape_id` vía ramal_lookup.
- `has_active_bus` es siempre 1 en training (nunca se entrenó el caso sin coche visible).
