# Arquitectura de predicción — plan vigente (desde 2026-11-10)

**Este es el documento rector.** Si contradice a otro doc, manda este.
`prediccion_ml_plan.md` queda como **referencia histórica de diseño**: ahí está el porqué de muchas decisiones (§7, §7b, §9, §11), pero su estado y su plan de fases están desactualizados.
Copias de todos los docs anteriores a este cambio: `docs_old/2026-11-10/`. **Siguen vigentes sin cambios:** `.claude/skills/grabador_nuc.md` (grabador, formato NDJSON, monitoreo) y `analisis_grabacion_mensual.md`. Tag git `pre-arquitectura-2026-11` = estado del código antes del cambio.

---

## 1. Objetivo y alcance

Predecir **cuándo pasa un colectivo por un punto** (parada o posición del usuario) en 30–40 líneas AMBA (1–199), y medirlo contra baselines (y más adelante contra Cuándo Subo).
Horizonte de trabajo: hasta mayo 2027. Recursos limitados: tokens y una RTX 3080. **Cada corrida de GPU tiene que responder una pregunta concreta.**

Fuera de alcance por ahora: producción/serving (se resuelve cuando el modelo sirva), identificación de ramal, las 129 líneas, el grabado de Cuándo Subo (lo hace el usuario aparte).

## 2. Reglas que no se negocian

- **La línea de un coche sale solo del sufijo del label** vía `LABEL_LINE_MAP.json` con vigencias (`shapes_io.load_label_line_map(path, on_date=día)`). **Nunca route_id, trip_id ni start_time** para identificar línea, ramal ni viaje (son datos rotos: la 151 reporta trip_id en el 42 % de los pings, la 124 y la 4 en 0 %). La segmentación en viajes es geométrica. La identificación de ramal está muerta: `ramal_lookup/` y `ramal_map.json` no se usan en el pipeline nuevo.
- El modelo **no recibe el ramal**. El pipeline necesita *un recorrido* sobre el cual proyectar; se elige **por geometría** (§4.1).
- Sin datos que producción no vaya a tener: la flota de entrada es la de **la agencia** del coche (producción pide por `agency_id`), no la flota total.
- Tests de comportamiento observable, sin change detectors.

## 3. Datos disponibles (verificado 2026-11-10)

- Grabaciones: `Z:\grabaciones\YYYY-MM-DD.ndjson.gz` (SMB a la NUC). **2026-03-28 → 2026-10-15** y desde **2026-11-10**. Hueco 2026-10-15 → 2026-11-09 por caída de la API CABA. El 2026-10-15 está incompleto. Excluidos además 25–27/07 (`EXCLUDED_DAYS` en `build_dataset.py`).
- Pings reales cada **~60 s** por coche (no 30), aunque el grabador emite cada 30 s.
- El tamaño de la flota varía por día y hora (~14k hábil al mediodía, mucho menos de noche/fin de semana): normal.
- Cambio de flota AMBA mayo–junio 2026: lo resuelve el map con vigencias; no es un problema para el pipeline.
- Recorridos: **`../proyectoconsola/data/line_shapes/{N}.json`** (129 líneas, OSM; las 7 históricas con datos de junio 2026, el resto OSM 2026-10-20). Formato `{color, ramales:[{name, shortName, shapeId, points:[[lat,lon]...], stops:[{id,lat,lng,name}]}]}`. Es la **fuente única** para el pipeline nuevo (solo lectura). `prediccion/data/line_shapes.json` (7 líneas) queda como legacy.
- `trip_id` y `start_time` **no se usan** (cobertura 0–92 % según línea, inconsistentes). El v2 segmenta los viajes por geometría (`prediccion/v2/segmenter.py`): corta al llegar al final del recorrido, ante una inversión sostenida de sentido (>300 m por detrás del máximo durante 3 pings), tras >10 min detenido en una cabecera, al salirse del recorrido o con un hueco de datos >5 min; descarta los pings de depósito/garage (coches quietos y lejos de todo recorrido de su línea). El inicio del viaje es la salida de la cabecera, así que `time_since_start` es geométrico. Líneas sin `trip_id` (4, 25, 84, 102, 124) ya no se excluyen.
- Disco libre en C: ~106 GB (2026-11-10). El parquet actual de la 39 pesa 3,5 GB. Vigilar tamaño (§4.3).

## 4. Pipeline v2 (dataset)

Cambios respecto del actual (`prediccion/pipeline/build_dataset.py`), en orden de importancia:

### 4.1 Recorrido por geometría, sin route_id
Implementar la **opción A** de `research_a3w_proyeccion_geometrica.md`: `best_shape_for_trip(lats, lons, shapes_de_la_línea) → (shape_id, median_perp)` usando `ShapeIndex.project_many`. Se elige el recorrido con menor error perpendicular mediano sobre el viaje completo (en training se conoce el viaje entero). Se mantiene el filtro de puntos con `perp > 150 m` (`project_trip`), que corta solo los tramos donde el coche se aparta del recorrido elegido. Esto reemplaza a `route_shape_map`/`load_ramal_map()` y elimina el `skip if not sh_id`.
Consecuencias aceptadas (documentadas en ese research): en tramos compartidos la elección puede ser arbitraria → ruido de normalización, no sesgo; los labels siguen siendo válidos.

### 4.2 Máximo de pares por viaje
Hoy cada viaje aporta **todos** los pares (P, F) → O(n²) (~6.000 pares en un viaje de ~110 puntos; 71,5 M filas para la 39 en 10 semanas). Pasar a **K pares por viaje** (parámetro; default del build **32**, 64 solo para la comparación de E1), con semilla determinística por viaje. Muestrear **estratificado por distancia restante** (buckets logarítmicos: 100–500 m, 0,5–1, 1–2, 2–5, 5+ km) para no sesgar hacia distancias largas, que es lo que domina hoy. Justificación: `research_training_performance.md` #3 (diversidad está en los viajes, no en los pares).

### 4.3 Unidad de trabajo = un día, idempotente
El diseño de `.claude/skills/ml_timeline.md` (§build_dataset): `process_day(date) → data/ml/v2/daily/YYYY-MM-DD.parquet` (skip si existe), carry al día siguiente, `manifest.json` con líneas por día, `assemble_dataset()` barato. Agregar una línea reprocesa solo los días que no la tienen. El NDJSON se lee **una vez por día para todas las líneas** (filter-first por label).
Columnas de flota (`fleet_flat`): **opcionales y apagadas por defecto** (las primeras corridas son sin flota y pesan ~1,2 KB/fila). Agregar columnas `line` y `shape_id` (para evaluar por línea).

### 4.4 Líneas
**60 líneas: 48 de train y 12 de control** (decisión del usuario, 2ª tanda). Criterios: las **27 líneas de CABA** (`experiments/velocidades/lineas_caba.py`) están todas en el dataset, repartidas entre train y control; el resto salió de calidad de recorrido (perp bajo sobre pings en movimiento y viajes segmentados), volumen y variedad geográfica y de empresa. Sin criterio de `trip_id` (no se usa). Las 7 actuales (26, 39, 42, 92, 124, 151, 168) siguen en train; 124 y 151 se mantienen por decisión aunque sus datos sean peores.

Sobre el "recorrido incompleto" de 7, 44, 65, 76, 115 y 151 (10–20 % de pings a >150 m): **era en buena parte depósito/garage y traslados**, no un ramal faltante en OSM (esas líneas comparten depósito y se pasan unidades; el coche reporta igual estando guardado). Con pings en movimiento y viajes segmentados el ajuste a 150 m sube a 0,91–0,98 (tabla antes/después en `lines.json`, `depot_study`). Solo 7 (0,91 de pings en movimiento a ≤150 m), 84 (0,93) y 115 (0,87 de viajes con perp mediano ≤50 m) quedan algo por debajo y son las candidatas a ramal o desvío faltante en OSM.

La lista final, el motivo de cada línea, el reparto de las 9 de CABA que pasaron el filtro y las métricas de las 60 líneas van en `data/ml/v2/lines.json` (generado por `python -m prediccion.v2.lines_final`).

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

Estimación de costo E2 (medida, 60 líneas, K=32): ~147 M filas de train (~4,7 M solo la 39) y ~27 M de val; ~43 k viajes por día hábil. En la RTX 3080 el trainer actual rinde ~24 k filas/s con `--batch-size 256` y ~98 k filas/s con `--batch-size 1024` (limitado por lanzamiento de kernels, ~95 it/s en ambos): **~100 min por época con batch 256 y ~25 min con batch 1024** (+~2 min de val). Con K=64 serían el doble de filas y de disco. La estimación original de este documento (~1,5 M viajes, 100 M filas, 12 min/época) subestimaba los viajes ~4×. La flota con el encoder actual es ~12× más lenta (§9 del plan): por eso va después y en versión liviana. **Comprar compute solo si E3 muestra que la flota vale y no entra en una noche.**

## 7. Resultados (se completa a medida que corren)

MAE (s) por bucket de ETA real **0–5 / 5–10 / 10–20 / 20+ min**, y % de subestimaciones > 60 s en 0–5 min. Archivos en `data/ml/v2/eval/`.

| Fecha | Experimento | Conjunto | MAE por bucket | Subest. 0–5 | Notas |
|---|---|---|---|---|---|
| 2026-11-11 | E0 A0 naive | seen (100k) | 72 / 192 / 386 / 962 | 22 % | |
| 2026-11-11 | E0 A1 (`a1_v1794415690`) | seen (100k) | **42 / 89 / 134 / 213** | 12 % | piso a superar |
| 2026-11-11 | E0 A0 naive | heldout (100k) | 68 / 186 / 377 / 890 | 22 % | A1 sin tabla para heldout cae a 7 m/s (= a0c:7) |
| 2026-11-11 | E0 A1 | seen, solo 39 (3770) | **36 / 72 / 101 / 160** | 11 % | |
| 2026-11-11 | E0 A3 viejo ep21 | seen, solo 39 | 53 / 74 / 114 / 178 | **2,8 %** | más conservador (pinball), menos preciso |
| 2026-11-11 | E1 A3 v2 K=64 (corte ep 9) | seen, solo 39 | 39 / 75 / 112 / 180 | 8,5 % | val ruidosa con lr fija, cortó temprano |
| 2026-11-11 | E1 A3 v2 K=32 (corte ep 21) | seen, solo 39 | 46 / 69 / 109 / 179 | 3,5 % | lr bajó a 5e-4 y 2,5e-4 |
| 2026-11-11 | **E1c** A3 K=32 + `--city-grid` (corte ep 26, mejor ep 21) | seen, solo 39 | **38** / **61** / **93** / **153** | 4,7 % | global 90,7 s (A1 96,7); gana a A1 salvo en 0–5 min (38 vs 36); +645 k parámetros |

**Lectura E1:** K=32 rinde igual que K=64 → K=32 alcanza. El pipeline v2 (geometría, sin trip_id) no empeora: iguala o mejora apenas al A3 viejo. Pero **ningún A3 le gana a A1 en la 39** salvo en subestimaciones. Hipótesis: A3 no sabe *dónde* está el coche en la ciudad (solo distancia normalizada), y A1 sí (velocidad típica por tramo, hora y día).

**Lectura E1c:** darle la ubicación física de P y T (grilla aprendida de ~500 m, sin ramal ni sentido) es lo que faltaba: el A3 pasa de 105,6 a 90,7 s de MAE global y **le gana a A1 (96,7 s) en los buckets de 5–10, 10–20 y 20+ min**, y por distancia en los cuatro tramos (<500 m: 48 vs 54; 5+ km: 147 vs 151). La anticorrelación ida/vuelta del error de nivel baja de −0,60 a −0,14 (muestra de train; diag en `data/ml/v2/diag/e1c_tables.md`) y el MAE a >2 km de 141 a 124 s en train (A1 133). Una sola corrida: falta repetir con otra semilla y probar en `eval_heldout`/otras líneas antes de darlo por cerrado.
| — | — | — | — | — |

## 8. Decisiones previas que siguen vigentes (no re-discutir sin dato nuevo)

Del plan histórico: modelo único para todas las líneas (§7); pinball asimétrica por distancia, q 0,5→0,8 bajo 1 km (§7b); distancia mínima 100 m (§7); `schedule_dev_norm` aporta poco pero positivo (Exp. 2); `time_since_last_bus_s` ambiguo (Exp. 2); umbral "llegando" `pred < 150 s OR dist < 300 m` (Exp. 1, reevaluar con el modelo nuevo); stop-to-stop y Transformer seq2seq postergados (§7, Fase 5); la flota de entrada es la de la agencia (§7).

## 9. Inconsistencias conocidas en docs viejos

- Modelo "en producción": `CLAUDE.md` decía ep24 (72,7 s), el plan dice ep21 (72,5 s). No hay modelo en producción real (`proyectoconsola/lib/eta_predict.js` está roto desde el rediseño).
- `research_a3w_proyeccion_geometrica.md` habla de 9.165 filas; el parquet real tiene 71,5 M.
- Split de validación: el código usa último 20 % de días (`build_dataset.py:423`); `ml_timeline.md` dice últimos 7 días. **Ahora manda §5.**
- `INFERENCE_GUIDE.md` no incluye `schedule_dev_norm` ni `time_since_last_bus_s`, y asume `shape_id` vía ramal_lookup.
- `has_active_bus` es siempre 1 en training (nunca se entrenó el caso sin coche visible).

## 10. Cómo correr (pipeline v2, vara de medir y escalera E0–E2)

Todo desde la raíz del repo (`prediccion colectivos/`), en PowerShell, con el **Python del sistema** (torch 2.7.1+cu118, ve la RTX 3080; tiene también orjson, isal, psutil, scipy y onnxscript):
```powershell
$PY = "C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe"
& $PY -c "import torch; print(torch.cuda.is_available())"    # tiene que dar True
```
El venv de `Dondeestaelbondi\.venv` tiene torch CPU: no usarlo para entrenar. Si falla `python -m ...`, usar `$env:PYTHONPATH="."`. `scipy` hace falta para la proyección rápida (`ShapeIndex(fast=True)`).

Código: `prediccion/v2/` (shapes, pairs, rows, segmenter, day = `process_day`, assemble, build, select_lines, lines_final, make_eval, compare_old, compare_segmenters), `prediccion/eval.py`, `best_shape_for_trip` en `prediccion/pipeline/projector.py`. Todo lo nuevo escribe en `data/ml/v2*/` (el pipeline viejo y `data/ml/training|models` no se tocan).

### Estructura de `data/ml/v2/`
`lines.json` (train/control + motivos + métricas, versionado) · `line_metrics*.json` · `daily/YYYY-MM-DD.{parquet,trips.parquet,meta.json,carry.json}` · `manifest.json` · `training/eta_train|eta_val.parquet` · `shape_lengths.json` · `schedule_dev_medians.json` · `eval/eval_seen|eval_heldout.parquet` + resultados · `models/`.

### Paso 0 — construir el dataset completo (una vez; reanudable)
```powershell
& $PY -m prediccion.v2.build --lines-file data/ml/v2/lines.json --days 2026-03-28:2026-10-14 --pairs-per-trip 32 --workers 8
```
Medido con las 60 líneas y K=32: ~155 s de CPU por día hábil (92 s sábado), 2,3 GB de RAM por worker. Total: ~7,5 h de CPU → **~1 h de pared con 8 workers** (~19 GB de RAM), más la lectura por SMB (~40 GB de gz). Disco (104 B/fila): ~221 M filas = **~23 GB en `daily/`** + ~18 GB en `training/` = **~41 GB**. Con K=64 saldría el doble (~80 GB): no usarlo en el build principal. Mismo comando para reanudar tras un corte o para agregar una línea a `lines.json` (solo reprocesa los días que no la tienen). Re-ensamblar sin releer NDJSON: `& $PY -m prediccion.v2.assemble`.

### E0 — baselines (minutos)
```powershell
& $PY -m prediccion.v2.make_eval                                         # congela eval_seen / eval_heldout (no regenera si existen; --force)
& $PY -m prediccion.train --phase 1 --ml-dir data/ml/v2 --skip-build     # A1 reentrenado -> data/ml/v2/models/a1_v<ts>.pkl
foreach ($s in "seen","heldout") {
  & $PY -m prediccion.eval --model a0 --set $s
  & $PY -m prediccion.eval --model a0c:7 --set $s
  & $PY -m prediccion.eval --model a1:data/ml/v2/models/a1_v<ts>.pkl --set $s
}
# A3 actual ep21 (solo 39, referencia histórica; usa solo las medianas schedule_dev del pipeline viejo)
& $PY -m prediccion.eval --model a3:data/ml/models/eta_a3_nofleet_gfull_ep21_mae72s_20260606_183507.pt --set seen --lines 39
```
Resultados en `data/ml/v2/eval/<modelo>_<set>_<fecha>.{json,md}`; anotar lo que importa en §7.

### E1 — A3 sin flota, solo línea 39: ¿muestrear pares (K=32 vs K=64) empeora el error?
Dos builds chicos de solo la 39 (~15 s de CPU por día; minutos con 8 workers), cada uno en su dir:
```powershell
& $PY -m prediccion.v2.build --lines-file data/ml/v2/lines.json --lines 39 --out-dir data/ml/v2_39_k64 --days 2026-03-28:2026-10-14 --pairs-per-trip 64 --workers 8
& $PY -m prediccion.v2.build --lines-file data/ml/v2/lines.json --lines 39 --out-dir data/ml/v2_39_k32 --days 2026-03-28:2026-10-14 --pairs-per-trip 32 --workers 8
foreach ($k in "k64","k32") {
  & $PY -m prediccion.train --phase 3 --ml-dir data/ml/v2_39_$k --no-fleet --device cuda --batch-size 1024 --epochs 30 --patience 5
  & $PY -m prediccion.eval --model a3:data/ml/v2_39_$k/models/eta_a3_best.pt --set seen --lines 39    # eval único del v2 principal (hace falta el Paso 0 y make_eval)
}
& $PY -m prediccion.eval --model a1:data/ml/v2/models/a1_v<ts>.pkl --set seen --lines 39              # referencia en el mismo subconjunto
```
Tamaño: 39 con K=32 ≈ 4,7 M filas de train (~1 min por época con batch 1024), K=64 ≈ 9 M (~2 min). Las medianas de `schedule_dev` de cada modelo salen de su propio dir.

### E2 — A3 sin flota, las 48 líneas de train
```powershell
& $PY -m prediccion.train --phase 3 --ml-dir data/ml/v2 --no-fleet --device cuda --batch-size 1024 --epochs 30 --patience 5
foreach ($s in "seen","heldout") { & $PY -m prediccion.eval --model a3:data/ml/v2/models/eta_a3_best.pt --set $s }
& $PY -m prediccion.eval --model a3:data/ml/v2/models/eta_a3_best.pt --set seen --lines 39     # ¿mejora la 39 vs E1?
```
~27 min por época con `--batch-size 1024` (~147 M filas); ~5–6 h si corta por paciencia hacia la época 12. Con `--batch-size 256` sería ~100 min por época (no entra en una noche). Ojo: batch 1024 da 4× menos actualizaciones por época; si converge peor, probar `--scheduler onecycle` o subir `--lr`. El `.pt` queda también archivado con nombre (`eta_a3_nofleet_gfull_ep<N>_mae<M>s_<ts>.pt`).

## 11. Ideas a testear para el modelo final (anotadas 2026-11-11, no implementadas)

Importantes para el modelo óptimo; cada una entra a la escalera como **un solo cambio** contra el último modelo bueno, medido con la vara de §5.

1. **Tráfico actual sobre la grilla de ciudad (alternativa a la "flota").** E1c mostró que una grilla aprendida (`CityGridEncoder`, celdas ~500 m) le da al modelo la ubicación y le gana a A1. La misma grilla puede llevar una **capa dinámica**: la velocidad actual (y conteo) de **todos los coches en cada celda** en el snapshot (y/o los últimos 5–10 min), de **todas las líneas**, no solo los de la agencia. Es un "mapa de tráfico actual" en vez de una lista de vehículos, y una variante del estado de flota agregada por lugar en vez de por vehículo. Costo fijo por fila, no O(N²) como el FleetEncoder que se descartó (§9 del plan histórico).
   - **Primero (lo que se testea):** las celdas **del camino que le queda al coche**, las que atraviesa el recorrido entre P y T. Es lo lógico: importa el tránsito por donde va a pasar el coche, no lo que hay alrededor.
   - **Después, solo si el primero deja dudas:** variante por zona, todas las celdas en un radio alrededor de P o de T, que capta congestión de calles vecinas que el recorrido no toca.
2. **La restricción que motivó "flota de la agencia" ya no aplica.** Se eligió la agencia porque bajar la flota total en producción tardaba 3–4 s en JSON. Desde 2026-11-10 proyectoconsola baja la flota global en **protobuf** (medido en producción: ~2 s de descarga, 170 ms de decodificación, ~9k coches) y el recorte por zona es barato. El grabador ya guarda la flota total, así que entrenar con ella no cuesta datos nuevos. Se puede volver a evaluar usar la flota **del área** (todas las líneas) en vez de la de la empresa.
3. **Historia corta en producción.** Guardar en el servidor un caché de los últimos 5–10 min de la flota y darle al modelo lo que convenga (trayectoria del coche, velocidades recientes por celda). Qué conviene no se sabe todavía: lo deciden los experimentos 1 y 2.
4. **Evaluación sobre paradas (postergado a propósito).** Lo que importa al usuario es la llegada a la parada, no a un punto cualquiera. La vara se mantiene en puntos cualquiera para no romper la comparación entre experimentos. Cuando el modelo esté estable, sumar una vara sobre paradas *además* (no en reemplazo). Ojo: el pasaje por parada se interpola entre pings de ~60 s (error P50 ~24 s, P90 ~52 s, §7 del plan histórico).
5. **Ramal desconocido en tiempo real.** En el tramo compartido el coche puede ir a varios ramales. Si T está después de la divergencia hay varios futuros posibles (D3 midió +12 s de error ahí contra +8 s en el resto). Una salida posible es predecir por ramal candidato o con una probabilidad de que el coche pase por T. No se ataca hasta que sea el error dominante.
