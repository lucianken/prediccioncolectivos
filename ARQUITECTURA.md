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
Implementar la **opción A** de `research_a3w_proyeccion_geometrica.md`: `best_shape_for_trip(lats, lons, shapes_de_la_línea) → (shape_id, median_perp)` usando `ShapeIndex.project_many`. Se elige el recorrido con menor error perpendicular mediano sobre el viaje completo (en training se conoce el viaje entero). Con `--assign legacy` (default, v2/v2b) se mantiene el filtro de puntos con `perp > 150 m` (`project_trip`); con `--assign geo3` la validez de cada ping la define §4.5. Esto reemplaza a `route_shape_map`/`load_ramal_map()` y elimina el `skip if not sh_id`.
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

### 4.5 Asignación de recorrido y sentido: qué es causal y qué es ex post

**Regla.** La asignación de un ping a recorrido y sentido se define UNA vez, en el pipeline (`prediccion/v2/geo_assign.py`), y la app la porta tal cual. La app no tiene reglas de asignación propias: cualquier cambio se hace en el pipeline y se porta (`path_reference.py` importa el módulo; el cliente usa los mismos valores vía `manifest.json["assignment"]`, contrato 2.1 de `prediccion/INFERENCIA_PATH.md`). El motivo es evitar diferencias entre entrenamiento y servicio (training/serving skew).

**Causal y compartido pipeline/app** (solo usa el ping y pasados del mismo coche):
- *Posición sobre un shape:* un shape es compatible con un ping si su error perpendicular es ≤ **T = 45 m** y además ≤ (mínimo error perpendicular entre todos los shapes de la línea) + **M = 20 m**. Ida y vuelta por la misma calle son ambas compatibles; la calle paralela (~100–130 m) no.
- *Proyección* del ping sobre cada shape compatible.
- *Sentido por geometría* (`direction_from_geometry`, sin historial): si todos los shapes compatibles con la posición tienen ahí el mismo rumbo local (diferencias ≤ 45°, `HEADING_TOL_DEG`, `manifest.assignment.heading_tol_deg`) y ninguno pasa por ese punto también en sentido opuesto (bucle), el coche va en ese sentido. Cubre calles de mano única y troncos compartidos en un solo sentido: el ramal sigue desconocido, el sentido no. Puntos cada 100 m de los shapes del modelo activo con sentido por geometría: 60 % en total; por línea, 26 ≈ 88 %, 124 ≈ 83 %, 106 ≈ 83 %, 168 54–74 %, 42 ≈ 48 %, 39 28–45 % (la 39 comparte calle en los dos sentidos en buena parte del recorrido).
- *Sentido por historial* (donde la geometría no alcanza: ida y vuelta por la misma calle, doble mano compartida, cruces): a partir de los pings propios de los últimos 15 min más el actual, por avance sostenido sobre el shape (≥ 80 % de los pings a ≤ T, fracción de avance hacia adelante ≥ 0,6, avance neto ≥ 40 m), no por distancia al shape: en 5,9 % de los viajes la distancia no distingue ida de vuelta. Un historial que contradice un shape (`sentido_incoherente`) lo descarta aunque la geometría dé el sentido.
- *Pipeline:* el sentido por geometría no cambia la máscara `valid` de geo3: el recorrido elegido ex post es siempre uno de los compatibles con el ping, y cuando la geometría da el sentido coincide con el de ese recorrido. El dataset v2c no se reconstruye. Lo usa la referencia de inferencia (`path_reference.py`) y, a través de ella, el replay (`prediccion/replay/`).

**Ex post, solo pipeline:** qué recorrido tomó finalmente el viaje y cuándo llegó a cada punto. Se usa solo como etiqueta y condición: cada fila de entrenamiento es "ETA si el coche va por el recorrido X", la misma pregunta que la app responde por cada candidato. Nunca decide qué pings son válidos ni cómo se proyectan. `best_shape_for_trip` elige el recorrido del viaje (menor error mediano con avance hacia adelante) solo entre los shapes compatibles (≥ 50 % de los pings del viaje compatibles); los pings no compatibles con el elegido no generan filas. También es ex post y solo del pipeline el corte de viajes (§4.1, segmentador): define etiquetas y estructura del viaje, y en producción `start_unknown = 1` y `time_since_start = 0` siempre. Por eso el segmentador **sigue con FIT_M = 150 m**: con 45 m fragmenta más (cortes por salida del recorrido ×3,1, huecos no unidos ×2, `start_unknown` +0,9 pp, −42 % de cortes por inversión), sin mejorar los datos.

**Elección de T y M** (`data/ml/v2b/diag/asignacion/ASIGNACION_RECORRIDO.md`, 93,6 M de pings de 15 líneas, 183 días): sobre los pings válidos (≤ 150 m al recorrido asignado ex post) el error perpendicular tiene p50 3,5 m, p90 10,5 m, p95 14,5 m, p99 73 m; 98,4 % está a ≤ 45 m (≈ 3 × p95; 30 m retiene 97,8 %). Entre 45 y 150 m no hay ruido de GPS sino otra calle o un desvío. M = 20 m es algo más que el p95 del ruido: dos shapes distan del ping casi lo mismo salvo que el coche vaya claramente por uno (ramales que comparten tronco empatan por ruido y siguen siendo ambos compatibles); el diagnóstico midió con 10 m que el 0,55 % de los pings a ≤ 45 m tiene otro shape más cerca, que con un margen de 10 m serían descartados sin motivo.

**Estado de la asignación (2026-11-13):** vigente en el dataset `data/ml/v2c` (`--assign geo3`); sentido por geometría vigente en la inferencia (contrato 2.1, export `path_v2c_l1_s1`). `data/ml/v2` y `v2b` usan la tolerancia de 150 m (registro de error en §5). Pendiente, no resuelto: retrocesos de la distancia a lo largo > 150 m entre pings válidos consecutivos en 26–34 % de los viajes de las líneas 15, 42, 124 y 92 (8,7 % del total), probablemente bucles del recorrido; afectan la proyección tanto en el pipeline como en la app.

## 5. Vara de medir (antes de entrenar nada nuevo)

Hoy los números no son comparables: A3 72 s (16,5 M filas val, solo 39), A1 158 s (muestra de 500k), naive 672 s; y el MAE global lo domina el tramo de >5 km (7,1 M de 16,5 M filas, 204 s). Ojo: por bucket, **A1 da 59 s en 0–500 m y 91 s en 0,5–2 km**, comparable o mejor que A3 (68 / 77 s) — una tabla de 7 s de entrenamiento compite con el modelo de horas en distancia corta. Sin una vara única no se puede decidir nada.

- **Período de validación fijo:** 2026-09-15 → 2026-10-14. Train: todo lo anterior (menos excluidos). El 2026-10-15 y lo posterior a 2026-11-10 no se usan para esta vara (posterior = test futuro).
- **Dos conjuntos de evaluación congelados** (parquet con semilla, se generan una vez y no se regeneran):
  - `eval_seen`: líneas del train, período de validación.
  - `eval_heldout`: las ~8 líneas de control, período de validación.
- **Consulta de evaluación:** (coche en P a tiempo t, punto objetivo T adelante en el mismo viaje), con ETA real observada. Muestreo estratificado por ETA real para que cada bucket tenga suficientes casos.
- **Métricas, siempre por bucket** de ETA real (0–5, 5–10, 10–20, 20+ min) y de distancia (<500 m, 0,5–2, 2–5, 5+ km): MAE, P50, P90, sesgo, y la métrica clave: **% que llega antes de lo anunciado > 60 s** (pred − real > 60 s; el usuario pierde el colectivo), sobre todo en 0–5 min y <1 km. Se acompaña de **% que llega después de lo anunciado > 60 s** (real − pred > 60 s; espera de más, tolerable) y de la **espera extra media** cuando llega después (media de real − pred sobre las filas con real > pred), para no premiar anunciar todo "en 1 min". El MAE global se informa pero no decide.

**Vara principal (desde 2026-11-13): banda de ETA real 3–7 min**, con dos números: MAE y % que llega antes de lo anunciado > 60 s. Es el rango en que el usuario decide cuándo salir. Por debajo de 2 min la predicción es inviable y no se usa para decidir. La tabla por bandas de ETA real (0–2, 2–4, 4–6, 6–8, 8–10, 10–15, 15–20 min: MAE, P90 del error absoluto, % llega antes >60 s, % llega después >60 s, espera extra media) la produce `prediccion.eval` (clave `by_eta_band` del JSON, última sección del markdown). Las tablas por bucket de arriba se mantienen como informativas.

**Vara de producto (desde 2026-11-14).** Complementa la vara del modelo (MAE por bandas de ETA real sobre `eval_seen` / `eval_heldout`, arriba). Es el replay en condiciones de producción: `prediccion/replay/`, con la lógica de `path_reference` fijada por hash (copias en `prediccion/replay/pinned/`) y el modelo exportado, usando solo los pings disponibles hasta cada instante t y la presentación de la app (viene / puede venir / sentido sin confirmar, orden por ETA, tope de 5). Se evalúa contra el paso real del coche por la parada (verdad: cruce interpolado entre dos pings a lo sumo 10 min separados; horizonte 40 min). Métricas:
- **MAE del próximo coche que pasa por la parada**, en la banda de ETA real 3–7 min.
- **Falsas alarmas:** coches anunciados que no pasan por la parada.
- **Omisiones:** coches que pasan en ≤10 min y no estaban anunciados.
- **"Viene" vacío:** instantes sin ningún "viene" aunque pasa un coche en ≤10 min.
- Desglose por **tramo exclusivo** contra **tronco compartido** de la línea, y por línea.

Referencia (2026-11-14): producción actual 107 s en la banda 3–7 min contra ~55 s de la vara del modelo. La diferencia no es error de ETA por coche sino la elección de qué coche es el próximo. Informe: `data/ml/replay/ORACULO_RAMAL.md`; resultados en §7.

**Pérdida de entrenamiento (vigente desde 2026-11-13).** El modelo por tramos se entrena con L1 (`--loss l1`, simétrica: q = 0,5 a toda distancia, mediana). La asimetría ante el error grave (colectivo que llega antes de lo anunciado) se resuelve en el producto, no en el entrenamiento: un factor de anuncio `a` en la app, con ETA mostrada = ETA predicha × (1 − a); hoy a = 0 (sin ajuste). `--loss pinball` (q 0,5 → 0,8 bajo 1 km; default del trainer para reproducir corridas anteriores y reanudar sus checkpoints), `--loss pinball_inv` (q 0,5 → 0,2 bajo 1 km) y `--loss pinball_band` (q 0,3 según la distancia restante, §6.2) son opciones del trainer y no se usan. Comparación en §7 ("Pérdida asimétrica vs ajuste en producto").

**Registro de error (corregido el 2026-11-13).** Hasta esa fecha la pinball usaba q 0,5 → 0,8 bajo 1 km, lo que castigaba que el colectivo llegue después de lo anunciado, y la vara rotulaba "subest. >60 s (el usuario pierde el colectivo)" a las filas donde el colectivo llega después. Afecta a:
- Modelos entrenados con esa pinball: todos los A3 y por tramos de `data/ml/models/`, `data/ml/v2/models_e2_geo/`, `data/ml/v2_39_k32/`, `data/ml/v2_39_k32_geo/`, `data/ml/v2_39_k64/`, `data/ml/v2_sub/conf/{a3_*,path_*}` y `data/ml/v2b_sub/runs/{a3_*,path_*}` (las corridas E0/E1/E2 de §6.4 y las de §7).
- Tablas de evaluación de todos los modelos (también A0 y A1) en `data/ml/*/eval*` y las tablas de §7: la columna "subest. >60 s" mide "llega después de lo anunciado > 60 s" y la columna "sobreest. >60 s" mide "llega antes de lo anunciado > 60 s".
- Las evaluaciones generadas desde 2026-11-13 traen las columnas "llega antes >60 s", "llega después >60 s" y "espera extra media" (claves JSON `pct_llega_antes_60s`, `pct_llega_despues_60s`, `espera_extra_media_s`; `pct_over_60s` y `pct_under_60s` son sus alias históricos).
**Registro de error (2026-11-13): tolerancia de 150 m y calle paralela.** La máscara de pings válidos (`valid` de `geometry_for_trip`), el filtro de `project_trip` y el criterio de ajuste del segmentador admitían como válido un ping a hasta 150 m del recorrido, que incluye el recorrido de la calle paralela (~100–130 m) y el sentido opuesto del mismo ramal. Medido (`data/ml/v2b/diag/asignacion/ASIGNACION_RECORRIDO.md`): 3,76 % de las filas de `v2b` son sucias (P o F a 45–150 m del recorrido, o con otro recorrido ≥ 10 m más cerca), con ~2 × el MAE de las limpias (banda 3–7 min, seen: 85 contra 53 s; heldout 158 contra 79 s); limpiarlas bajaría el MAE global 3,9–4,5 % y en la banda 3–7 min 2,2–3,4 %. Afecta a los datasets `data/ml/v2/`, `v2b/`, `v2_sub/`, `v2b_sub/`, `v2_39_k32/`, `v2_39_k32_geo/`, `v2_39_k64/` y a todos los modelos y evaluaciones entrenados o construidos sobre ellos: `data/ml/v2/models_e2_geo/`, `data/ml/v2_sub/` (`models*`, `conf/`), `data/ml/v2b_sub/` (`runs/`, `runs_l1/`, `runs_band/`), los eval `data/ml/v2/eval`, `data/ml/v2_sub/eval` y `data/ml/v2b/eval`, y los exportes `data/ml/export/path_v2b_s0` y `path_v2b_pinv_s0`. Corrección: §4.5 (`--assign geo3`, dataset `data/ml/v2c`). Los números de §7 anteriores a esta fecha siguen siendo válidos como comparación entre sí.
- **Baselines en el mismo conjunto:** A0 naive (distancia / velocidad, con piso de velocidad razonable), A1 (reentrenado con el train v2; es barato), A3 actual ep21 (solo sobre la 39, como referencia histórica). Cuándo Subo se suma cuando exista su grabación.
- Script único `python -m prediccion.eval ...` que toma un modelo y escribe `data/ml/v2/eval/<modelo>_<fecha>.json` + tabla markdown. Resultados que importan se anotan en §7.

## 6. Plan de modelado (replanteado 2026-11-12)

### 6.1 Por qué se replantea
E0–E2 fueron parches sucesivos sobre la arquitectura A3 de junio (ubicación → grilla, después metros, después tránsito), cada uno reaccionando a un diagnóstico. Es un máximo local. Los síntomas ("no sabe dónde está", "no sabe los metros", "no generaliza a líneas no vistas", "no ve el tránsito del camino") tienen **una sola causa**: A3 es una regresión global sobre escalares normalizados, y el problema tiene otra estructura.

**Estructura del problema:** el tiempo de llegada es la **suma del tiempo de cada tramo** del camino entre el coche (P) y el objetivo (T). Cada tramo tiene un comportamiento típico (hora, día) más el estado actual del tránsito. Por eso la tabla A1 (suma por tramos) le gana a A3: tiene la estructura correcta, no más información.

### 6.2 Pasos, en orden
1. **Techo y cobertura (sin entrenar).** Antes de construir, medir cuánto se puede ganar:
   - *Ruido de etiqueta:* el pasaje se interpola entre pings de ~60 s (error P50 ~24 s). Nadie baja de eso.
   - *Tránsito, con la tabla de tránsito por celda (§11.1):* para cada fila de eval, recorrer los tramos/celdas del camino P→T y usar la velocidad observada de **otros** coches en esa celda donde la haya; donde no, la velocidad típica de A1. Dos versiones: **oráculo** (coches que pasan en los minutos siguientes: techo, usa futuro) y **realista** (últimos ~10 min: lo que tiene producción).
   - *Cobertura:* fracción del camino con información real, por línea y hora. En tramos de una sola línea la información es, con suerte, el coche de adelante; esto mide en cuántos casos el tránsito puede aportar algo.
   - **Decide:** si oráculo ≈ A1, el tránsito no es prioridad; si el oráculo baja mucho y la cobertura es alta, sí. Duda abierta del usuario sobre el oráculo: se intenta igual y se interpreta con la cobertura.
2. **Infraestructura de iteración (una vez, no es experimento).**
   - Subconjunto chico fijo para comparar ideas en ~30–45 min: **train 12 líneas: 26, 39, 42, 92, 124, 151, 168, 50, 106, 107, 108, 132** · **control 3: 12 (corta), 15 (larga, 54 km), 128 (corta)**. Todas ya están en el dataset v2 armado. Ventana de train acotada (p. ej. 6–8 semanas) dentro del período de train; la vara (§5) no cambia.
   - Entrenamiento estándar fijo: presupuesto fijo de épocas, lr con schedule programado (coseno/onecycle), sin early stopping sobre una val ruidosa. Corrige el defecto que dejó a E2 subentrenado.
   - Las 48 líneas solo para confirmar al ganador.
3. **Modelo por tramos del camino.** El camino P→T partido en tramos fijos (250–500 m). El tiempo de cada tramo se aprende **solo con colectivos** (incluye paradas, semáforos, regulación, cabecera); no es un modelo de tránsito general como Maps, y no depende de que haya muchos otros vehículos.
   - Valor de cada tramo = **componente del lugar** (compartido entre las líneas que lo recorren) **+ componente propio de la línea** (paradas, demanda, puntos de regulación, frecuencia distintos en la misma calle). Más hora/día.
   - **Señal dinámica principal: el coche de adelante de la misma línea**, que acaba de hacer ese camino (existe también en tramos de una sola línea). El tránsito de otras líneas en tramos compartidos es secundario y entra solo si el paso 1 muestra que aporta.
   - Más el estado del coche (velocidad, antigüedad GPS, detenido). Salida: tiempo por tramo sumado + un ajuste no-por-tramo (cabecera, demoras). Puede reproducir A1, así que no debería quedar por debajo.
   - Forma inspirada en los sistemas de ETA de la industria (DiDi WDR, Uber DeepETA), adaptada a colectivos.
   - **Nota sobre las líneas de control (abierto):** en producción no hay líneas nuevas: se entrena siempre con todas. Lo que sí aparece son **modificaciones de recorrido o ramales nuevos** de líneas existentes, y tramos poco recorridos. Las líneas de control son un proxy imperfecto de eso. Pendiente definir una prueba más fiel (p. ej. dejar afuera un ramal o un tramo de una línea vista, o recorridos sintéticos).
4. **Comparar en el subconjunto chico** A1 / A3+grilla (E1c) / modelo por tramos, con la vara de siempre. Escalar a 48 líneas solo el ganador.

5. **Arreglo del corte de viajes (problema de datos, no de modelo).** Medido en el paso 2: el inicio de viaje tiene 1,3–1,4× el error del resto en los tres modelos, por dos defectos del segmentador v2:
   - **A. Viajes que arrancan a mitad de recorrido (~13 % de las filas):** un hueco de datos > 5 min corta el viaje y el siguiente arranca con `time_since_start` ≈ 0 aunque el coche lleve media hora. Arreglo: **unir el hueco** si después el coche sigue avanzando sobre el mismo recorrido con un avance físicamente posible para el tiempo transcurrido (mismo viaje, el tiempo sigue desde la salida real). Si no se puede unir, el viaje queda marcado **"inicio desconocido"** (flag explícito) en vez de un `time_since_start` falso.
   - **B. La espera en cabecera queda dentro del viaje:** hoy se corta solo con > 10 min detenido, así que esperas de 3–9 min cuentan como viaje. Arreglo: el viaje arranca cuando el coche **sale de la zona de cabecera** (~300 m sobre el recorrido) y avanza. Las posiciones previas son el estado **"esperando en cabecera"**: es otro problema (cuándo sale), que se trata aparte y no contamina la predicción del recorrido.
   - **Validación antes de entrenar:** % de viajes que empiezan lejos de la cabecera (debería bajar mucho desde ~13 %), coherencia de `time_since_start` con la distancia recorrida, y duración de viajes por línea consistente con el recorrido.
   - Cambia los datos: el antes y el después no se comparan directamente. Se rearma el subconjunto con el segmentador nuevo y se re-miden A1 / A3+grilla / por tramos con la misma receta, **después** de cerrar la comparación con semillas del paso 4.

**Opción de pérdida `--loss pinball_band`.** q depende de la distancia restante (entrada del modelo; nunca de la ETA real) y actúa en el rango donde cae la ETA 3–10 min. Banda [d_lo, d_hi] = p10 y p90 de la distancia restante de las filas de `data/ml/v2b_sub` (train) con ETA real 3–10 min (532 m y 2074 m); q = 0,30 dentro de la banda, rampa lineal a 0,5 en los 300 m afuera de cada borde, 0,5 en el resto. d_lo / d_hi / q / rampa quedan en `loss_cfg` del checkpoint y de `path_eta_metrics.json`. Corrida de comparación: modelo por tramos, LR 2e-3, 12 épocas, OneCycle, batch 1024, semillas 0 y 1; lanzador `prediccion/scripts/run_v2b_band.py`, salida en `data/ml/v2b_sub/runs_band/`, tabla en `runs_band/comparacion.md`; resultados en §7.

**Estado de producción (2026-11-13):** `path_v2c_l1_s1` (`data/ml/export/path_v2c_l1_s1/`; script `prediccion/scripts/export_path_onnx.py`; contrato 2.1, `prediccion/INFERENCIA_PATH.md`). Modelo por tramos entrenado sobre `data/ml/v2c_sub` con pérdida L1 (LR 2e-3, 12 épocas, semilla 1, val MAE 82,8 s). Asignación geo3 (§4.5): la app porta `prediccion/v2/geo_assign.py` tal cual (`compatible_shapes`, `direction_from_geometry`, `direction_from_history`, `forward_fraction`, proyección) con las constantes de `manifest.assignment` (T = 45 m, M = 20 m, rumbo 45°, ventana de historial y parámetros de sentido); no tiene reglas de asignación propias y el punto del usuario usa las mismas primitivas (parada: shapes que la sirven; GPS o mapa: punto ajustado al recorrido con `snap_to_route` a ≤ T y luego `compatible_shapes`). Reemplaza a `path_v2b_s0` (pinball, tolerancia de 150 m), que queda exportado en `data/ml/export/path_v2b_s0/` y en el historial git de proyectoconsola para volver atrás.

**Estado de la asignación (2026-11-13):** dataset `data/ml/v2c` armado con `--assign geo3` (§4.5: pings válidos con T = 45 m y shape más cercano + M = 20 m; recorrido del viaje elegido solo entre los compatibles; segmentación geo2 sin cambios). Subconjunto `data/ml/v2c_sub` y eval `data/ml/v2c/eval` con la misma receta que v2b. Modelo por tramos con L1 (LR 2e-3, 12 épocas, OneCycle, batch 1024, semillas 0 y 1) en `data/ml/v2c_sub/runs/`, evaluado en `data/ml/v2c/eval` junto con los L1 de v2b (`data/ml/v2b_sub/runs_l1`) en el mismo eval; tabla por bandas de ETA real (principal 3–7 min) en `data/ml/v2c_sub/runs/comparacion.md`. Lanzador: `prediccion/scripts/run_v2c.py`. El modelo exportado a producción es el de v2c (`path_v2c_l1_s1`, ver «Estado de producción»).

**Decisión: paradas por tramo (2026-11-13).** La feature `--stops-feature` queda activada en los entrenamientos siguientes: no cuesta nada en líneas vistas y ayuda en generalización (resultado en §7). Producción no cambia ahora: las 12 líneas habilitadas son todas vistas y sumar la feature exige portar a la app el cálculo de paradas por tramo. Se porta junto con el próximo modelo (escalado a 30–40 líneas).

**Pendiente (sin fecha):** integrar el ramal de CuandoSubo como restricción de shapes candidatos. No está en curso ni planificada; spec en §11, ítem 8.

**Próximo paso propuesto:** evaluación en condiciones de producción por replay de días posteriores al entrenamiento grabados por el NUC, con la regla de candidatos de producción (`INFERENCIA_PATH.md`: sentido, shapes del usuario, pasa seguro / puede venir) contra el paso real del coche por el punto. Es la vara fija para lo que siga.

### 6.3 Qué se descarta y qué se reusa
- **Se descarta:** seguir agregando inputs a A3 (metros, E3a/E3b como parche).
- **Se reusa:** pipeline v2 (corte geométrico, recorridos), vara de medir, tabla de tránsito, la grilla (como embedding del tramo), y E0–E2 como referencia.

### 6.4 Escalera anterior (histórica, E0–E2 corridos)

Cada escalón es una corrida nocturna y responde una pregunta. Se corta donde deja de haber mejora.

| # | Corrida | Pregunta | Decide |
|---|---|---|---|
| E0 | Baselines A0/A1/A3-actual en la vara | ¿Dónde estamos de verdad? | piso a superar |
| E1 | A3 no-fleet, solo 39, pipeline v2, K=64 | ¿El muestreo de pares y la geometría empeoran algo vs A3 actual? | si K=64 alcanza |
| E1c | E1 K=32 + grilla de ciudad (ubicación de P y T), solo 39 | ¿Falta saber *dónde* está el coche? | hecho: sí, le gana a A1 (§7) |
| E2 | A3 no-fleet **+ grilla**, 48 líneas, K=32 | ¿Más líneas mejoran la 39? ¿Generaliza a las líneas de control? | si vale escalar |
| E3a | E1c + tránsito actual en las celdas del camino P→T (todas las líneas de la flota), **solo 39** | ¿El tránsito actual aporta sobre la ubicación? | si vale escalarlo |
| E3b | E2 + lo mismo, **48 líneas** (solo si E3a mejora) | ¿Se sostiene en todas las líneas y en las de control? | modelo candidato |

E3 sigue el mismo escalonado que E1→E2: primero solo la 39 (barato, ~30 min) y después todas. Aun entrenando con la 39, el tránsito de cada celda sale de **todos** los coches de la flota grabada (todas las líneas), porque es la información de la ciudad, no de la línea. Requiere una tabla nueva por snapshot × celda (velocidad media y conteo de coches en movimiento), construida una vez desde el NDJSON. La variante por zona y la flota como lista de vehículos (FleetEncoder) quedan después (§11).

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

| 2026-11-12 | E2 A3 + grilla, 48 líneas (corte ep 11, mejor ep 6) | seen (100k) | 46 / 78 / 122 / 211 | 4,5 % | vs A1 42 / 89 / 134 / 213: gana en 5–20 min, pierde en 0–5 |
| 2026-11-12 | E2 A3 + grilla | heldout (100k) | 93 / 169 / 268 / 488 | 5,9 % | vs A0 68 / 186 / 377 / 890; sesgo +75 s (sobreestima en líneas no vistas) |
| 2026-11-12 | E2 A3 + grilla | seen, solo 39 | 45 / 70 / 99 / 171 | 3,3 % | **peor que E1c** (38 / 61 / 93 / 153) |

**Lectura E2:** con 48 líneas la 39 empeora respecto de E1c, y en líneas no vistas generaliza a medias (le gana al naive salvo en 0–5 min, con sesgo +75 s). **No es concluyente sobre "más líneas":** E2 cortó por paciencia en la época 11 con la lr fija en 1e-3 (nunca bajó; E1c sí bajó y entrenó 26 épocas), y el error de train seguía bajando → probablemente subentrenado. Sospecha para heldout: celdas de la grilla que ninguna línea de train recorre quedan con embeddings sin entrenar.

**Lectura E1c:** darle la ubicación física de P y T (grilla aprendida de ~500 m, sin ramal ni sentido) es lo que faltaba: el A3 pasa de 105,6 a 90,7 s de MAE global y **le gana a A1 (96,7 s) en los buckets de 5–10, 10–20 y 20+ min**, y por distancia en los cuatro tramos (<500 m: 48 vs 54; 5+ km: 147 vs 151). La anticorrelación ida/vuelta del error de nivel baja de −0,60 a −0,14 (muestra de train; diag en `data/ml/v2/diag/e1c_tables.md`) y el MAE a >2 km de 141 a 124 s en train (A1 133). Una sola corrida: falta repetir con otra semilla y probar en `eval_heldout`/otras líneas antes de darlo por cerrado.
| — | — | — | — | — |

**Paso 6.2.1, techo y cobertura (2026-11-12, `data/ml/v2/diag/TECHO_TRANSITO.md`, subconjunto 12+3 líneas):**
- Ruido de etiqueta chico: estimado ~6–19 s de MAE (cota superior 18,6 s con hueco de 120 s).
- Cobertura de tránsito 97–99 % del camino; los tramos de una sola línea son ~3 % de los pasos (casi todo es compartido).
- Sustituir la velocidad típica por la observada por celda (500 m × 2 min) **no le gana a A1**: la mejor mezcla gana 2,2 % con oráculo (usa futuro) y 1,2 % realista. Ni en tramos de una línea, ni con la misma línea, ni con otras.
- Límite: es una sustitución directa en un sumador por tramos, no un modelo aprendido, con celdas gruesas y velocidad solo en movimiento. No descarta que un modelo aprendido saque algo del tránsito, pero no hay señal fuerte a la vista.
- El error que queda está en otro lado: **cabecera** (MAE 143 s a <5 min de la salida vs 105 s el resto), **coche detenido** (120 vs 109 s) y variabilidad entre coches.
- Decisión: tránsito **no es prioridad**. El foco pasa a lo que explica el error: cabecera, paradas, estado del coche.

**Pasos 6.2.2–6.2.4, subconjunto 12+3 líneas (2026-11-12; archivos en `data/ml/v2_sub/`, evals en `data/ml/v2_sub/eval/`).**
Receta fija: train 2026-07-20 → 2026-09-14 (10,25 M filas, 46 días; todos < 2026-09-15, sin superposición con la validación), val = muestra reproducible del 40 % de la val de siempre en las 12 líneas (2,28 M filas, 25 días), 12 épocas, batch 1024, OneCycle (coseno), sin early stopping. Se toma el **mejor checkpoint sobre esa val** (muestra grande y estable; en los dos modelos coincidió con la última época). Eval = la vara de siempre filtrada: train = `eval_seen` en las 12 líneas (29.779 filas), control = `eval_heldout` en 12, 15, 128 (26.537 filas). MAE (s) por bucket de ETA 0–5 / 5–10 / 10–20 / 20+ min; "Subest. 0–5" = % de subestimaciones >60 s en 0–5 min; entre paréntesis, % de subestimaciones >60 s global.

| Fecha | Experimento | Conjunto | MAE por bucket | Subest. 0–5 | Notas |
|---|---|---|---|---|---|
| 2026-11-12 | A1 reentrenado (ventana del subconjunto) | train 12 líneas | 41 / 82 / 125 / 198 | 12,4 % (33,7 %) | global 116,0; sesgo −29; por distancia 62 / 83 / 112 / 192 |
| 2026-11-12 | A3 + grilla (E1c), 12 líneas, 12 ép. (44,5 min) | train 12 líneas | 42 / 71 / 117 / 195 | 5,1 % (34,8 %) | global 110,5; sesgo −41; por distancia 57 / 76 / 108 / 186 |
| 2026-11-12 | **Por tramos** (sin tránsito, 21,4 min) | train 12 líneas | **41 / 69 / 111 / 170** | **4,5 %** (28,5 %) | global **101,6**; sesgo −15; por distancia 55 / 72 / 102 / 164 |
| 2026-11-12 | A1 | control 12, 15, 128 | 73 / 216 / 428 / 1034 | 50,4 % (85,4 %) | global 467; sin tabla para esas líneas: es el naive de 7 m/s |
| 2026-11-12 | A3 + grilla | control | 76 / 163 / 291 / 541 | 10,3 % (32,3 %) | global 282; sesgo −21 |
| 2026-11-12 | **Por tramos** | control | 57 / 116 / 185 / 440 | 9,6 % (46,5 %) | global **211**; sesgo −33; por distancia 65 / 107 / 178 / 490 |

Desglose por fase del viaje (MAE s; inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s; solo reporte):

| Conjunto / modelo | inicio | resto | detenido | en movimiento | global sin inicio |
|---|---|---|---|---|---|
| train, A1 | 147,5 | 105,7 | 122,6 | 111,6 | 105,7 (global 116,0) |
| train, A3 + grilla | 136,5 | 102,1 | 115,1 | 107,5 | 102,1 (110,5) |
| train, por tramos | 125,9 | 93,6 | 105,5 | 99,0 | 93,6 (101,6) |
| control, A1 | 570,9 | 431,0 | 491,5 | 449,3 | 431,0 (467,4) |
| control, A3 + grilla | 330,6 | 265,3 | 278,2 | 285,4 | 265,3 (282,3) |
| control, por tramos | 254,6 | 195,8 | 195,8 | 222,6 | 195,8 (211,1) |

**Lectura.** (1) En líneas vistas el modelo por tramos le gana a A1 y a A3+grilla en casi todo (global −12 % vs A1, −8 % vs A3; −14 % en 20+ min vs A1) y tiene el menor % de subestimaciones >60 s global; en 0–5 min empata con A1 en MAE (41) y con A3 en subestimaciones. Es una sola corrida por modelo (sin repetir semillas) y la val del modelo por tramos saltó entre épocas finales (86 → 98 → 82 s con lr casi nula), señal de que no está bien condicionado: el ruido entre corridas no está medido. (2) En control gana por mucho a A3 (211 vs 282) y a A1, aunque el control es solo de 3 líneas y con sesgo y subestimaciones mayores que A3 (46 % vs 32 % global): generaliza mejor en nivel pero subestima más. Línea desconocida = índice de "línea no vista" (se entrena con 10 % de dropout de la línea); la geometría de las líneas de control está en la tabla de tramos y la grilla da el lugar. (3) Inicio de viaje: el error es 1,3–1,4× el del resto en los tres modelos; excluirlo baja el MAE medio de A1 de 116,0 a 105,7 s (−9 %), de A3 de 110,5 a 102,1 y del modelo por tramos de 101,6 a 93,6. El ajuste global del modelo por tramos no cierra esa brecha: inicio 125,9 vs resto 93,6. (4) Por qué es el inicio (A1, `eval_seen` de 12 líneas): 26 % de las filas de eval cumplen "inicio", pero solo 9 % son inicio verdadero (<5 min Y <1 km del shape; MAE 172 s); 13 % tienen tss <5 min pero ya están a >1 km del shape (viajes que el segmentador empieza a mitad de recorrido tras un corte; MAE 122 s) y 2 % llevan >5 min dentro del primer km (MAE 161 s). Las filas a <200 m del inicio del shape (1.555) tienen MAE 200–210 s y sesgo −62 / −110 s (detenidas): el coche espera en la cabecera dentro del viaje, hasta 5–10 min, porque el segmentador solo corta tras >10 min detenido; A1 ignora esa espera. El segundo término es que `time_since_start` mide desde el primer punto válido (a ≤150 m del shape), no desde la salida de cabecera, y en el 52 % de las filas con time_since_start ≈ 0 (primer punto válido del viaje) ese punto está a >1 km del inicio del shape.
- Receta: A3 usó el trainer actual (pérdida pinball de val como criterio de "mejor"), el modelo por tramos su propio loop (`prediccion/train_path.py`, MAE de val como criterio) con lr 2e-3 contra 1e-3 del A3; no son idénticos en lr ni en métrica de selección.
- **Confirmación con 2 semillas (2026-11-12; `data/ml/v2_sub/conf/resumen.md`, generado por `prediccion/scripts/resumen_confirmacion.py`).** Misma receta, 6 corridas: A3 + grilla LR 1e-3 (semillas 0, 1) y por tramos LR 2e-3 (semillas 0, 1; el mejor checkpoint se elige por MAE de val). LR elegido: A3 1e-3, por tramos 2e-3.

| Conjunto | Modelo | Global (semillas) | Media | Dif. entre semillas | Ventaja del por tramos | Notas |
|---|---|---|---|---|---|---|
| train (12 líneas) | A3 + grilla | 106,5 / 109,3 | 107,9 | 2,9 | | 20+ min: 187 |
| train (12 líneas) | por tramos | 101,6 / 102,2 | 101,9 | 0,6 | 6,0 s (5,6 %), 2,1× la dif. entre semillas | 20+ min: 171 |
| control (12, 15, 128) | A3 + grilla | 298,6 / 287,6 | 293,1 | 11,0 | | subest. >60 s ~30 % |
| control (12, 15, 128) | por tramos | 211,1 / 229,8 | 220,4 | 18,7 | 72,7 s (24,8 %), 3,9× la dif. entre semillas | subest. >60 s ~46–50 %, sesgo −20 a −33 s |

  **Conclusión:** la ventaja del modelo por tramos es real (supera la varianza entre semillas) en ambos conjuntos; sigue siendo el candidato. La ganancia en train se concentra en 20+ min (187 → 171). Pendiente: el por tramos subestima más que A3 en líneas no vistas.
- **Paso 6.2.5, segmentador v2b (2026-11-12; código `segmenter_version=2` / `--segmentation geo2`, el v2 de siempre sigue de default y no cambió).** Validación antes de construir (4 días hábiles 2026-07-14, 08-12, 09-16, 10-07 + sábado 09-12; las 15 líneas; `data/ml/v2b/validation/summary.md`, `cars.md`; `python -m prediccion.v2.validate_segmenter_v2`): viajes 46.484 → 38.600; filas de viajes que arrancan a >1 km del inicio del recorrido **31,2 % → 17,7 %** (ahora marcadas `start_unknown`, `time_since_start` = NaN); filas con `time_since_start` < 5 min pero a >1 km (el defecto medido en el paso 2) 11,0 % → 1,2 %; huecos >5 min dentro de un viaje 12.953: **9.962 unidos (77 %)**, 2.991 no (parado en el hueco o retroceso; ninguno >1 h se une; 93 % de los de 5–7 min se unen), más 6.008 excursiones fuera del recorrido, 4.780 unidas; velocidad implícita `dist_along / time_since_start` p10/p50/p90 2,7 / 4,3 / 14,3 → 2,6 / 3,7 / 5,3 m/s (filas a >60 km/h 8,5 % → 0,01 %); duración de viajes completos por línea p50 de 67–151 min, 11,7–20,7 km/h, consistente con el largo del recorrido; 16.809 esperas en cabecera (93.304 pings, 3,9 % de los pings de viaje; mediana 6 min, p90 18 min, máx 108) pasan a `daily/*.waiting.parquet`. Lo que queda `start_unknown` (~15–18 %) son inversiones de sentido a mitad de recorrido, cambios de ramal y el primer viaje del día de cada coche. Cotas de unión sacadas de los datos (hueco con coche en movimiento: 1,4–16,7 m/s, retroceso ≤150 m, ≤1 h; coche quieto a mitad de recorrido: ≤15 min). Build: `python -m prediccion.v2.build --lines-file data/ml/v2/lines.json --lines 26,39,42,92,124,151,168,50,106,107,108,132,12,15,128 --days 2026-03-28:2026-10-14 --pairs-per-trip 32 --workers 3 --segmentation geo2 --low-priority --out-dir data/ml/v2b --no-assemble` (35 min con 3 workers; 44,1 M filas; 14,6 % `start_unknown`); subconjunto en `data/ml/v2b_sub` (`assemble --v2-dir data/ml/v2b --lines-file data/ml/v2b/lines.json --only-lines <las 12> --dest data/ml/v2b_sub --train-start 2026-07-20 --val-sample-frac 0.4`: 9,41 M filas de train, 1,92 M de val) y eval en `data/ml/v2b/eval` (`make_eval --v2-dir data/ml/v2b --lines-file data/ml/v2b/lines.json --n-per-bucket 7500`, 30.000 filas por conjunto). **Los viajes cambian, así que los conjuntos y los números de v2_sub y v2b no se comparan directamente.** Los trainers todavía no leen `start_unknown`: A3 pasaría NaN al modelo (hay que enmascarar o imputar antes de entrenar; el modelo por tramos ya hace `nan_to_num`).
- **Reentrenamiento sobre v2b (segmentador nuevo) (2026-11-13; evaluación en `data/ml/v2b/eval`, 30.000 filas por conjunto; resultados en `data/ml/v2b_sub/runs/eval/`, lanzador `prediccion/scripts/run_v2b.py`; modelos viejos de `v2_sub`/`conf` evaluados sobre el eval nuevo en `data/ml/v2b_sub/runs/eval_old/`).**

| Modelo | seen (12 líneas de train), MAE global s | heldout (12, 15, 128), MAE global s | Notas |
|---|---|---|---|
| A1 v2b | 116,3 | 455,4 | heldout: sesgo −436 s, subest. >60 s 84 % |
| A3 + grilla v2b, LR 1e-3 (semillas 0 / 1) | 108,9 / 107,1 (media 108,0) | 276,8 / 268,3 (media 272,6) | sesgo ~0, subest. 27–28 % |
| Por tramos v2b, LR 2e-3 (semillas 0 / 1) | 102,7 / 103,5 (media 103,1) | 205,7 / 224,7 (media 215,2) | sesgo −24 / −34 s, subest. 45–46 % |
| A3 viejo (entrenado en `v2_sub`) | 113,0 / 115,6 (media 114,3) | 283,4 / 276,9 (media 280,2) | evaluado en el eval v2b |
| Por tramos viejo (entrenado en `v2_sub`) | 103,0 / 103,5 (media 103,3) | 198,7 / 214,6 (media 206,7) | evaluado en el eval v2b |

MAE en seen por inicio de viaje (desconocido / conocido): A3 v2b 128 / 104; A3 viejo 161 / 105; por tramos v2b 123 / 99; por tramos viejo 123 / 99. El 17 % de las filas seen y el 21 % de las heldout son de inicio desconocido. MAE en seen por bucket de ETA 0–5 / 5–10 / 10–20 / 20+ min: A3 v2b 45 / 70 / 114 / 204; por tramos v2b 40 / 69 / 110 / 192.

  **Conclusiones:**
  1. El orden se mantiene: por tramos < A3 < A1 en ambos conjuntos. La ventaja del por tramos sobre A3 es de ~5 s en seen y ~57 s en heldout, por encima de la diferencia entre semillas (seen ≤1,8 s; heldout hasta 19 s en el por tramos).
  2. El segmentador nuevo mejora a A3 (seen 114 → 108; heldout 280 → 273), casi todo en filas de inicio desconocido (161 → 128): A3 dependía de `time_since_start` y el 0 falso lo engañaba.
  3. Al modelo por tramos no lo mejora (103,3 → 103,1 en seen; 206,7 → 215,2 en heldout, dentro de la varianza entre semillas): ya no usaba fuerte `time_since_start`. Los datos limpios quedan como base igual (etiquetas y eval más honestos), pero el error que queda no es ruido de corte de viajes.
  4. Pendientes abiertos: subestimación del por tramos en líneas no vistas (45 % subest. >60 s, sesgo −24 a −34 s); filas de inicio desconocido ~25 % peores que las de inicio conocido; error en 20+ min.

- **Pérdida asimétrica vs ajuste en producto (2026-11-13).** Banda de ETA real 3–7 min, eval v2b (`data/ml/v2b/eval`), media de 2 semillas; resultados en `data/ml/v2b_sub/runs_band/comparacion.md`. Cada celda: MAE (s) / % llega antes >60 s / % llega después >60 s.

| Pérdida de entrenamiento | seen | heldout |
|---|---|---|
| `pinball` (q 0,5 → 0,8 bajo 1 km) | 53,3 / 17,2 / 16,6 | 82,8 / 18,1 / 30,7 |
| `l1` | 55,3 / 15,1 / 20,4 | 85,5 / 16,4 / 35,7 |
| `pinball_inv` (q 0,5 → 0,2 bajo 1 km) | 58,4 / 14,0 / 24,2 | 90,9 / 16,1 / 38,8 |
| `pinball_band` (q 0,3 con distancia 532–2074 m, rampa 300 m) | 61,4 / 7,0 / 34,7 | 94,1 / 11,6 / 47,5 |

  Ajuste multiplicativo posterior de la ETA predicha, misma banda, sin reentrenar:

| Modelo base | Factor | seen | heldout |
|---|---|---|---|
| `pinball` (s0) | ×1,00 | 53,1 / 17,1 / 16,6 | |
| `pinball` (s0) | ×0,95 | 52,6 / 11,9 / 21,8 | |
| `pinball` (s0) | ×0,92 | 53,8 / 9,0 / 26,0 | |
| `pinball` (s0) | ×0,89 | 55,9 / 6,8 / 30,7 | 83,8 / 10,3 / 43,0 |
| `l1` (s0) | ×0,95 | 55,8 / 9,9 / 26,5 | |
| `l1` (s0) | ×0,92 | 57,4 / 7,7 / 30,9 | |

  **Conclusión:** la pérdida asimétrica no mejora la información del modelo, solo desplaza el anuncio; un factor posterior logra el mismo desplazamiento con menor MAE y sin reentrenar. Por eso la pérdida es L1 y el ajuste es un parámetro de producto (§5). El factor se calibró sobre el eval; si se usa, se calibra sobre val.

- **Validación de la asignación geo3 (2026-11-13; 5 días 2026-08-11 a 2026-08-15, 15 líneas, segmentación geo2, K=32; `data/ml/v2c/validation`).** Mismos días de `data/ml/v2b`:

| | v2b (150 m) | v2c (geo3: T = 45 m, M = 20 m) |
|---|---|---|
| Viajes | 46.881 | 46.929 |
| Filas | 1.487.183 | 1.484.231 |
| Filas con `start_unknown` | 15,12 % | 15,35 % |
| Viajes con `start_unknown` | 15,44 % | 15,83 % |
| Pings de viajes con recorrido descartados (no compatibles) | 1,42 % | 3,08 % |

De 46.785 viajes emparejados (mismo coche e inicio), 768 (1,6 %) cambian de recorrido elegido; sobre ellos y el resto se pierden 50.116 de 2.982.732 pings válidos (1,7 %). Lo descartado de más son sobre todo coches parados a ~75–115 m de la cabecera o del final del recorrido (estacionados; en v2b generaban filas con la etiqueta de un coche que no está en el recorrido), pings sobre otro ramal o sentido más cercano y pings de la calle paralela. Ejemplos revisados (2026-08-12, hora local UTC−3; recorrido y distancias en m): línea 151, coche 96230, 14:48:48, (-34,62880, -58,37909): v2b lo asignaba al recorrido 19481773 a 129 m y otro recorrido de la línea (4020850) pasa a 1 m; línea 151, coche 97380, 15:54:44, (-34,61010, -58,40878): 95 m al recorrido elegido y 24 m al más cercano; línea 15, coche 33659, 08:12:36, (-34,45473, -58,69512): 55 m al elegido y 3 m al más cercano; línea 15, coche 35941, 19:59:52: viaje de 175 pings con el coche parado a ~100 m del recorrido (mediana de perp 105 m): 32 filas en v2b, 0 en v2c.

- **Paradas por tramo (2026-11-13).** Entrada nueva por tramo de 250 m: cantidad de paradas del recorrido dentro del tramo (opción `--stops-feature`). Recetas idénticas a v2c L1 (datos `v2c_sub`, LR 2e-3, 12 épocas, semillas 0 y 1). Eval `data/ml/v2c/eval`, banda de ETA real 3–7 min, media de 2 semillas; comparación en `data/ml/v2c_sub/runs_stops/comparacion.md`. Cada celda: MAE (s) (% llega antes >60 s).

| Modelo | seen (12 líneas de train) | heldout (líneas no vistas 12, 15, 128) |
|---|---|---|
| v2c L1 | 55,8 (15,3 %) | 87,9 (18,9 %) |
| v2c L1 con paradas por tramo | 55,7 (14,9 %) | 82,3 (15,3 %) |
| Diferencia entre semillas | 0,7 | 4,0 |

  **Lectura:** en seen el efecto es nulo (0,1 s contra 0,7 s entre semillas). En heldout mejora 5,6 s (6 %), por encima de los 4,0 s entre semillas: supera el criterio por poco. En líneas entrenadas la memoria por tramo ya captura el efecto de las paradas; la feature es transferible y ayuda en recorridos no vistos o con pocos datos.

- **Oráculo de ramal (2026-11-14).** Replay de la vara de producto (§5): 12 líneas habilitadas (26, 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168), 40 paradas por línea (mitad tronco compartido, mitad tramo exclusivo), instantes cada 10 min de 6 a 23 h, 10 días del período de evaluación (15, 16, 17, 18, 19, 20 de sep. y 3, 4, 6, 8 de oct.; la línea 26 solo tiene datos 15–17 de sep.). Lógica de `geo_assign.py` y `path_reference.py` fijada en el commit e7479f7 (contrato 2.1); modelo `path_v2c_l1_s1`. Variantes: `base` (producción: ramal y sentido por historial + geometría), `solo sentido` (shapes restringidos al sentido del recorrido ex post) y `oráculo ramal` (shapes restringidos al recorrido ex post del viaje en curso; sin restricción si el coche no tiene viaje ex post). Informe y tablas completas: `data/ml/replay/ORACULO_RAMAL.md`.

  Global (465.560 pares parada-instante). MAE del próximo coche en la banda 3–7 min (s); falsas alarmas; omisión con coche en ≤10 min; "viene" vacío con coche en ≤10 min:

| Variante | MAE 3–7 min | Falsas alarmas | Omisión ≤10 min | "Viene" vacío |
|---|---|---|---|---|
| base | 107 | 24,0 % | 17,0 % | 13,7 % |
| solo sentido | 104 | 23,5 % | 17,2 % | 13,6 % |
| oráculo ramal | 94 | 17,4 % | 17,0 % | 7,9 % |

  Tramo exclusivo contra tronco compartido (base → oráculo ramal):

| Tipo de parada | MAE 3–7 min | Falsas alarmas | "Viene" vacío |
|---|---|---|---|
| Tramo exclusivo | 113 → 82 s | 45,6 → 24,4 % | 30,5 → 7,5 % |
| Tronco compartido | 124 → 112 s | 16,0 → 15,1 % | 11,0 → 9,6 % |

  Línea 39 (base → oráculo ramal): MAE 86 → 82 s; falsas alarmas 30,4 → 11,3 %; "viene" vacío 24,6 → 5,0 % (en su tramo exclusivo, 42,1 → 5,3 %). La ganancia es de confiabilidad más que de precisión.

  - **Mejoran claramente:** 42 (MAE 164 → 103 s), 106 (115 → 80 s), 132 (117 → 75 s; falsas alarmas 25,4 → 7,1 %) y 168 (117 → 97 s).
  - **No mejoran:** 26, 92, 108 y 124 (un solo recorrido por sentido; no hay ramal que restringir) y, en el MAE, 107, 151 y 50.

  **Lectura:** conocer solo el sentido no aporta (con contrato 2.1 el sentido ya sale bien). Conocer el ramal aporta por sacar de la lista coches de otro ramal, sobre todo en tramo exclusivo; no por afinar la ETA.

  **Salvedades:**
  - Es un techo: supone el ramal siempre correcto; cualquier error del ramal de CuandoSubo lo reduce.
  - Los huecos de GPS impiden interpolar algunos cruces, por lo que falsas alarmas y omisiones están algo sobrestimadas, por igual en las tres variantes. La omisión no cuenta los coches sin ping vigente en t.
  - Con el oráculo, casi todo lo que queda en "puede venir" son coches sin viaje ex post; su tasa de falsas alarmas (~96 %) no es comparable con la de base.
  - La omisión de 17 % no cambia con el oráculo: queda por investigar (§6).
  - En la línea 151, tramo exclusivo, el MAE de la banda (225 → 862 s) sale de muy pocos instantes y no se interpreta.

## 8. Decisiones previas que siguen vigentes (no re-discutir sin dato nuevo)

Del plan histórico: modelo único para todas las líneas (§7); pérdida L1 con el ajuste de anuncio en el producto (§5, §7); distancia mínima 100 m (§7); `schedule_dev_norm` aporta poco pero positivo (Exp. 2); `time_since_last_bus_s` ambiguo (Exp. 2); umbral "llegando" `pred < 150 s OR dist < 300 m` (Exp. 1, reevaluar con el modelo nuevo); stop-to-stop y Transformer seq2seq postergados (§7, Fase 5); la flota de entrada es la de la agencia (§7).

## 9. Inconsistencias conocidas en docs viejos

- Modelo "en producción": `CLAUDE.md` decía ep24 (72,7 s), el plan dice ep21 (72,5 s). No hay modelo en producción real (`proyectoconsola/lib/eta_predict.js` está roto desde el rediseño).
- `research_a3w_proyeccion_geometrica.md` habla de 9.165 filas; el parquet real tiene 71,5 M.
- Split de validación: el código usa último 20 % de días (`build_dataset.py:423`); `ml_timeline.md` dice últimos 7 días. **Ahora manda §5.**
- `docs_old/INFERENCE_GUIDE.md` (sin efecto; reemplazada por `prediccion/INFERENCIA_PATH.md`) no incluye `schedule_dev_norm` ni `time_since_last_bus_s`, y asume `shape_id` vía ramal_lookup.
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

### Entrenar el subconjunto y reanudar un corte (A3 y modelo por tramos)
```powershell
& $PY -m prediccion.v2.assemble --only-lines 26,39,42,92,124,151,168,50,106,107,108,132 --dest data/ml/v2_sub --train-start 2026-07-20 --val-sample-frac 0.4
& $PY -m prediccion.train --phase 1 --ml-dir data/ml/v2_sub --skip-build                  # A1
& $PY -m prediccion.train --phase 3 --ml-dir data/ml/v2_sub --no-fleet --city-grid --device cuda --batch-size 1024 --epochs 12 --lr 1e-3 --scheduler onecycle --patience 99
& $PY -m prediccion.train_path --ml-dir data/ml/v2_sub --epochs 12 --batch-size 1024 --lr 2e-3
& $PY -m prediccion.eval --model path:data/ml/v2_sub/models_path/path_eta_best.pt --set seen --lines 26,39,42,92,124,151,168,50,106,107,108,132 --tag sub --out-dir data/ml/v2_sub/eval
```
(Lanzar los entrenamientos desacoplados con `Start-Process` y log; una tarea en segundo plano se corta a las 2 h.)

**Reanudar.** Al final de cada época los dos trainers escriben `last.pt` de forma atómica (a `.tmp` y `os.replace`: un corte durante el guardado deja intacto el anterior): `eta_a3_last.pt` en `<ml-dir>/models/` y `path_eta_last.pt` en `<ml-dir>/models_path/`. Contiene modelo, optimizador, estado del scheduler (OneCycle o plateau), época, mejor métrica y mejor época, historial, estado del RNG (torch, numpy, python) y la config del run. El `best.pt` se sigue guardando aparte. Para retomar, relanzar **el mismo comando agregando `--resume`**: sigue en la época siguiente con el LR que le tocaba (el scheduler restaura su paso). Si el run se cortó a mitad de una época se pierde solo esa época. Si la config guardada no coincide con la actual (épocas, scheduler, lr, batch, datos —tamaño y fecha de los parquet—, d_model, grilla, etc.) falla con un mensaje que lista las diferencias. En CPU la reanudación es exacta (los tests `test_resume.py` comparan pesos y LR por paso contra un run sin corte); en GPU con varios workers de DataLoader el orden de filas de la época reanudada no es idéntico (RNG propio de cada worker), pero modelo, optimizador, LR y RNG del proceso principal sí. `last.pt` del modelo por tramos también se puede evaluar (`--model path:<last.pt>`). Ganchos de test: `stop_after_epoch` y `lr_trace`.

### Dataset con asignación geométrica (v2c)
Mismo comando que v2b más `--assign geo3` y otro `--out-dir` (el lanzador `prediccion/scripts/run_v2c.py` lo corre completo y reanuda):
```powershell
& $PY -m prediccion.v2.build --lines-file data/ml/v2/lines.json --lines 26,39,42,92,124,151,168,50,106,107,108,132,12,15,128 --days 2026-03-28:2026-10-14 --pairs-per-trip 32 --workers 3 --segmentation geo2 --assign geo3 --low-priority --out-dir data/ml/v2c --no-assemble
& $PY -m prediccion.v2.assemble --v2-dir data/ml/v2c --lines-file data/ml/v2c/lines.json --only-lines 26,39,42,92,124,151,168,50,106,107,108,132 --dest data/ml/v2c_sub --train-start 2026-07-20 --val-sample-frac 0.4
& $PY -m prediccion.v2.make_eval --v2-dir data/ml/v2c --lines-file data/ml/v2c/lines.json --n-per-bucket 7500
```
Un día construido con otra asignación (`meta.assign`) se reprocesa. Las constantes T y M están solo en `prediccion/v2/geo_assign.py` y `meta.json` de cada día guarda los parámetros usados.

## 11. Ideas a testear para el modelo final (anotadas 2026-11-11, no implementadas)

Importantes para el modelo óptimo; cada una entra a la escalera como **un solo cambio** contra el último modelo bueno, medido con la vara de §5.

1. **Tráfico actual sobre la grilla de ciudad (alternativa a la "flota").** E1c mostró que una grilla aprendida (`CityGridEncoder`, celdas ~500 m) le da al modelo la ubicación y le gana a A1. La misma grilla puede llevar una **capa dinámica**: la velocidad actual (y conteo) de **todos los coches en cada celda** en el snapshot (y/o los últimos 5–10 min), de **todas las líneas**, no solo los de la agencia. Es un "mapa de tráfico actual" en vez de una lista de vehículos, y una variante del estado de flota agregada por lugar en vez de por vehículo. Costo fijo por fila, no O(N²) como el FleetEncoder que se descartó (§9 del plan histórico).
   - **Primero (lo que se testea):** las celdas **del camino que le queda al coche**, las que atraviesa el recorrido entre P y T. Es lo lógico: importa el tránsito por donde va a pasar el coche, no lo que hay alrededor.
   - **Tabla construida (2026-11-11):** `data/ml/v2/traffic/daily/YYYY-MM-DD.parquet` (sparse: `window`, `cell`, `speed_mps`, `n`, `n_stopped`; celdas de `CityGridEncoder`, solo las 2465 por donde pasan recorridos de las 60 líneas de `lines.json`, ventana de 2 min en hora de BA, sin coches de depósito, velocidad por desplazamiento entre pings, toda la flota). Medido: ~1 M filas y ~3,3 MB por día, **531 MB los 183 días** (con ventana de 1 min serían ~1 GB); ~1.700 celdas ocupadas por ventana (mediana); ~15-25 s de CPU por día, 24 min con 3 workers. Comando: `python -m prediccion.v2.traffic.build --days 2026-03-28:2026-10-14 --window-min 2 --workers 3` (parámetros en `data/ml/v2/traffic/meta.json`). Aún sin integrar al dataset ni al modelo.
   - **Después, solo si el primero deja dudas:** variante por zona, todas las celdas en un radio alrededor de P o de T, que capta congestión de calles vecinas que el recorrido no toca.
2. **La restricción que motivó "flota de la agencia" ya no aplica.** Se eligió la agencia porque bajar la flota total en producción tardaba 3–4 s en JSON. Desde 2026-11-10 proyectoconsola baja la flota global en **protobuf** (medido en producción: ~2 s de descarga, 170 ms de decodificación, ~9k coches) y el recorte por zona es barato. El grabador ya guarda la flota total, así que entrenar con ella no cuesta datos nuevos. Se puede volver a evaluar usar la flota **del área** (todas las líneas) en vez de la de la empresa.
3. **Historia corta en producción.** Guardar en el servidor un caché de los últimos 5–10 min de la flota y darle al modelo lo que convenga (trayectoria del coche, velocidades recientes por celda). Qué conviene no se sabe todavía: lo deciden los experimentos 1 y 2.
4. **Evaluación sobre paradas (postergado a propósito).** Lo que importa al usuario es la llegada a la parada, no a un punto cualquiera. La vara se mantiene en puntos cualquiera para no romper la comparación entre experimentos. Cuando el modelo esté estable, sumar una vara sobre paradas *además* (no en reemplazo). Ojo: el pasaje por parada se interpola entre pings de ~60 s (error P50 ~24 s, P90 ~52 s, §7 del plan histórico).
5. **Ramal desconocido en tiempo real.** En el tramo compartido el coche puede ir a varios ramales. Si T está después de la divergencia hay varios futuros posibles (D3 midió +12 s de error ahí contra +8 s en el resto). Una salida posible es predecir por ramal candidato o con una probabilidad de que el coche pase por T. No se ataca hasta que sea el error dominante.
6. **Tránsito con grilla más fina.** El oráculo de tránsito con celdas de 500 m y ventanas de 2 min no mejora más de ~2 % con la calidad de datos actual; experimento futuro: celdas más chicas / grilla más densa.
7. **Atributos de calle de OpenStreetMap por tramo.** Entradas por tramo del camino derivadas de OSM: tipo de vía, carril exclusivo / Metrobús, semáforos e intersecciones por tramo, giros.
   - *Valor esperado:* generalización a recorridos nuevos o modificados y a tramos con pocos datos (brecha entre líneas vistas, ~103 s, y no vistas, ~215 s, en v2b). Poco valor esperado en líneas ya entrenadas, donde la memoria por tramo ya captura cada calle.
   - *Prioridad:* menor que escalar a 30–40 líneas.
   - *Nota:* la dirección / mano de las calles ya está implícita en los shapes.
   - *Relación con `arreglar OSM/`:* ese proyecto corrige la nomenclatura y las referencias de OSM; estos atributos dependerían de la calidad de esos datos, y no se necesita ninguno de los dos para el otro.
8. **Pendiente (sin fecha): integración del ramal de CuandoSubo como restricción de shapes candidatos.** No está en curso ni planificada para ahora; es solo especificación para cuando se retome. Se basa en el oráculo de ramal (§7, "Oráculo de ramal (2026-11-14)"): conocer el ramal en tiempo real reduce falsas alarmas y "viene" vacío, sobre todo en tramo exclusivo; no afina la ETA.
   - *Cómo sería:* la restricción usa la misma lógica que la variante oráculo del replay: los shapes candidatos del coche se restringen a los del ramal informado. Se definiría en el pipeline (`prediccion/`) y se portaría a la app. Si el coche no tiene ramal informado, queda sin restricción (comportamiento actual).
   - *El modelo no cambia* (`path_v2c_l1_s1`); solo cambia el conjunto de shapes candidatos.
   - *Alcance:* línea por línea, con candidatas 39, 42, 106, 132 y 168. En líneas sin ramales no hay nada que ganar.
   - *Requisito previo:* medir antes el acierto del ramal de CuandoSubo por línea. El techo del oráculo supone un ramal siempre correcto y cualquier error de CuandoSubo lo reduce; solo se habilitaría en las líneas donde ese acierto sea suficiente.
   - *Validación:* con la vara de producto (§5) en cada línea habilitada.
   - *Pendiente relacionado:* investigar la omisión de 17 %, que el oráculo no cambia.
