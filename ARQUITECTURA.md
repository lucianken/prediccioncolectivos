# Arquitectura de predicción — plan vigente (desde 2026-11-10)

**Este es el documento rector.** Si contradice a otro doc, manda este.
`docs_old/prediccion_ml_plan.md` queda como **referencia histórica de diseño**: ahí está el porqué de muchas decisiones (§7, §7b, §9, §11), pero su estado y su plan de fases están desactualizados.
Resultados, registros de error y pendientes cerrados: `RESULTADOS.md`. Historia (replanteo 2026-11-12, escalera E0–E2, inconsistencias de docs viejos): `docs_old/ARQUITECTURA_historia.md`. Docs superados (plan A3, research, plan de parquet): `docs_old/`; restos de las copias del 2026-11-10 en `docs_old/2026-11-10/`. **Siguen vigentes sin cambios:** `.claude/skills/grabador_nuc.md` (grabador, formato NDJSON, monitoreo) y `analisis_grabacion_mensual.md`. Tag git `pre-arquitectura-2026-11` = estado del código antes del cambio.

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
- Pings reales cada **~60 s** por coche; el grabador emite cada 30 s.
- El tamaño de la flota varía por día y hora (~14k hábil al mediodía, mucho menos de noche/fin de semana).
- Cambio de flota AMBA mayo–junio 2026: lo resuelve el map con vigencias; no es un problema para el pipeline.
- Recorridos: **`../proyectoconsola/data/line_shapes/{N}.json`** (129 líneas, OSM; las 7 históricas con datos de junio 2026, el resto OSM 2026-10-20). Formato `{color, ramales:[{name, shortName, shapeId, points:[[lat,lon]...], stops:[{id,lat,lng,name}]}]}`. Es la **fuente única** para el pipeline nuevo (solo lectura). `prediccion/data/line_shapes.json` (7 líneas) queda como legacy.
- `trip_id` y `start_time` **no se usan** (cobertura 0–92 % según línea, inconsistentes). El v2 segmenta los viajes por geometría (`prediccion/v2/segmenter.py`): corta al llegar al final del recorrido, ante una inversión sostenida de sentido (>300 m por detrás del máximo durante 3 pings), tras >10 min detenido en una cabecera, al salirse del recorrido o con un hueco de datos >5 min; descarta los pings de depósito/garage (coches quietos y lejos de todo recorrido de su línea). En el segmentador v2, el inicio del viaje es el primer ping válido (a ≤ 150 m del recorrido) y `time_since_start` se mide desde ahí; el segmentador v2b (`--segmentation geo2`, RESULTADOS.md «Paso 6.2.5») lo ancla a la salida de la cabecera y marca `start_unknown` cuando el viaje arranca a mitad de recorrido. Las líneas sin `trip_id` (4, 25, 84, 102, 124) se incluyen.
- Disco libre en C: ~106 GB (2026-11-10). El parquet actual de la 39 pesa 3,5 GB. Vigilar tamaño (§4.3).

## 4. Pipeline v2 (dataset)

Cambios respecto del actual (`prediccion/pipeline/build_dataset.py`), en orden de importancia:

### 4.1 Recorrido por geometría, sin route_id
Implementar la **opción A** de `docs_old/research_a3w_proyeccion_geometrica.md`: `best_shape_for_trip(lats, lons, shapes_de_la_línea) → (shape_id, median_perp)` usando `ShapeIndex.project_many`. Se elige el recorrido con menor error perpendicular mediano sobre el viaje completo (en training se conoce el viaje entero). Con `--assign legacy` (default, v2/v2b) se mantiene el filtro de puntos con `perp > 150 m` (`project_trip`); con `--assign geo3` la validez de cada ping la define §4.5. Esto reemplaza a `route_shape_map`/`load_ramal_map()` y elimina el `skip if not sh_id`.
Consecuencias aceptadas (documentadas en ese research): en tramos compartidos la elección puede ser arbitraria → ruido de normalización, no sesgo; los labels siguen siendo válidos.

### 4.2 Máximo de pares por viaje
El pipeline anterior aportaba **todos** los pares (P, F) por viaje → O(n²) (~6.000 pares en un viaje de ~110 puntos; 71,5 M filas para la 39 en 10 semanas). El pipeline v2 aporta **K pares por viaje** (parámetro; default del build **32**, 64 solo para la comparación de E1), con semilla determinística por viaje. El muestreo es **estratificado por distancia restante** (buckets logarítmicos: 100–500 m, 0,5–1, 1–2, 2–5, 5+ km), porque el muestreo sin estratificar se sesga hacia distancias largas. Justificación: `docs_old/research_training_performance.md` #3 (diversidad está en los viajes, no en los pares).

### 4.3 Unidad de trabajo = un día, idempotente
Unidad de trabajo: `process_day(date) → data/ml/v2/daily/YYYY-MM-DD.parquet` (skip si existe), carry al día siguiente, `manifest.json` con líneas por día, `assemble_dataset()` barato. Agregar una línea reprocesa solo los días que no la tienen. El NDJSON se lee **una vez por día para todas las líneas** (filter-first por label).
Columnas de flota (`fleet_flat`): **opcionales y apagadas por defecto** (las primeras corridas son sin flota y pesan ~1,2 KB/fila). Agregar columnas `line` y `shape_id` (para evaluar por línea).

### 4.4 Líneas
**60 líneas: 48 de train y 12 de control** (decisión del usuario, 2ª tanda). Criterios: las **27 líneas de CABA** (`experiments/velocidades/lineas_caba.py`; `caba_lines` en `lines.json`) están todas en el dataset: 22 en train y 5 en control (`caba_missing_from_dataset` vacío); el resto salió de calidad de recorrido (perp bajo sobre pings en movimiento y viajes segmentados), volumen y variedad geográfica y de empresa. Sin criterio de `trip_id` (no se usa). Las 7 actuales (26, 39, 42, 92, 124, 151, 168) siguen en train; 124 y 151 se mantienen por decisión aunque sus datos sean peores.

Líneas 7, 44, 65, 76, 115 y 151: 10–20 % de los pings están a > 150 m de su recorrido; son pings de depósito/garage y traslados entre depósitos compartidos (las líneas comparten depósito y se pasan unidades; el coche reporta estando guardado). Con pings en movimiento y viajes segmentados, la fracción de pings a ≤ 150 m es 0,91–0,98 (tabla en `lines.json`, `depot_study`). Por debajo: 7 (0,91 de pings en movimiento a ≤ 150 m), 84 (0,93) y 115 (0,87 de viajes con perp mediano ≤ 50 m): candidatas a ramal o desvío faltante en OSM.

La lista final, el motivo de cada línea, el reparto de 9 líneas de CABA entre train y control (`nine_caba_split`: control 12, 64, 68, 109; train 34, 61, 108, 118, 132) y las métricas de las 60 líneas van en `data/ml/v2/lines.json` (generado por `python -m prediccion.v2.lines_final`).

### 4.5 Asignación de recorrido y sentido: qué es causal y qué es ex post

**Regla.** La asignación de un ping a recorrido y sentido se define UNA vez, en el pipeline (`prediccion/v2/geo_assign.py`), y la app la porta tal cual. La app no tiene reglas de asignación propias: cualquier cambio se hace en el pipeline y se porta (`path_reference.py` importa el módulo; el cliente usa los mismos valores vía `manifest.json["assignment"]`, contrato 2.1 de `prediccion/INFERENCIA_PATH.md`). El motivo es evitar diferencias entre entrenamiento y servicio (training/serving skew).

**Causal y compartido pipeline/app** (solo usa el ping y pasados del mismo coche):
- *Posición sobre un shape:* un shape es compatible con un ping si su error perpendicular es ≤ **T = 45 m** y además ≤ (mínimo error perpendicular entre todos los shapes de la línea) + **M = 20 m**. Ida y vuelta por la misma calle son ambas compatibles; la calle paralela (~100–130 m) no.
- *Proyección* del ping sobre cada shape compatible.
- *Sentido por geometría* (`direction_from_geometry`, sin historial): si todos los shapes compatibles con la posición tienen ahí el mismo rumbo local (diferencias ≤ 45°, `HEADING_TOL_DEG`, `manifest.assignment.heading_tol_deg`) y ninguno pasa por ese punto también en sentido opuesto (bucle), el coche va en ese sentido. Cubre calles de mano única y troncos compartidos en un solo sentido: el ramal queda desconocido y el sentido queda determinado. Puntos cada 100 m de los shapes del modelo activo con sentido por geometría: 60 % en total; por línea, 26 ≈ 88 %, 124 ≈ 83 %, 106 ≈ 83 %, 168 54–74 %, 42 ≈ 48 %, 39 28–45 % (la 39 comparte calle en los dos sentidos en buena parte del recorrido).
- *Sentido por historial* (regla `trailing_run`, `manifest.assignment.direction_rule`, vigente desde 2026-11-16; donde la geometría no alcanza: ida y vuelta por la misma calle, doble mano compartida, cruces): dentro de los últimos 15 min (`history_window_s` = 900 s), se toma la **racha final** de pings consecutivos, terminando en el actual, a ≤ T del shape, y se usan todos los pings de la racha. Racha < 2 pings (`min_near_pings`): `sin_sentido` (el coche no se descarta: queda el sentido por geometría o «sentido sin confirmar»). Sobre la racha: fracción de avance hacia adelante (`forward_fraction`) ≥ 0,6 (si no, `sentido_incoherente`); avance neto (último menos primero) ≤ −40 m: `sentido_incoherente`; < +40 m: `sin_sentido`; si no, hacia adelante. Los pings anteriores a la racha (fuera del shape: coche aún en cabecera o en otra calle) no cuentan. No hay fracción mínima de pings cercanos en la ventana. El sentido lo define el avance sostenido sobre el shape; la distancia al shape no distingue ida de vuelta en 5,9 % de los viajes. Un historial que contradice un shape (`sentido_incoherente`) lo descarta aunque la geometría dé el sentido. Medición de la regla contra la anterior (≥ 80 % de la ventana a ≤ T): `data/ml/replay/BARRIDO_SENTIDO.md`.
- *Pipeline:* el sentido por geometría no cambia la máscara `valid` de geo3: el recorrido elegido ex post es siempre uno de los compatibles con el ping, y cuando la geometría da el sentido coincide con el de ese recorrido. El dataset v2c no se reconstruye. Lo usa la referencia de inferencia (`path_reference.py`) y, a través de ella, el replay (`prediccion/replay/`).

**Ex post, solo pipeline:** qué recorrido tomó finalmente el viaje y cuándo llegó a cada punto. Se usa solo como etiqueta y condición: cada fila de entrenamiento es "ETA si el coche va por el recorrido X", la misma pregunta que la app responde por cada candidato. Nunca decide qué pings son válidos ni cómo se proyectan. `best_shape_for_trip` elige el recorrido del viaje (menor error mediano con avance hacia adelante) solo entre los shapes compatibles (≥ 50 % de los pings del viaje compatibles); los pings no compatibles con el elegido no generan filas. También es ex post y solo del pipeline el corte de viajes (§4.1, segmentador): define etiquetas y estructura del viaje, y en producción `start_unknown = 1` y `time_since_start = 0` siempre. Por eso el segmentador usa **FIT_M = 150 m**: con 45 m fragmenta más (cortes por salida del recorrido ×3,1, huecos no unidos ×2, `start_unknown` +0,9 pp, −42 % de cortes por inversión), sin mejorar los datos.

**Elección de T y M** (`data/ml/v2b/diag/asignacion/ASIGNACION_RECORRIDO.md`, 93,6 M de pings de 15 líneas, 183 días): sobre los pings válidos (≤ 150 m al recorrido asignado ex post) el error perpendicular tiene p50 3,5 m, p90 10,5 m, p95 14,5 m, p99 73 m; 98,4 % está a ≤ 45 m (≈ 3 × p95; 30 m retiene 97,8 %). Entre 45 y 150 m no hay ruido de GPS sino otra calle o un desvío. M = 20 m es algo más que el p95 del ruido: dos shapes distan del ping casi lo mismo salvo que el coche vaya claramente por uno (ramales que comparten tronco empatan por ruido y siguen siendo ambos compatibles); con M = 10 m, el 0,55 % de los pings a ≤ 45 m tiene otro shape más cerca (diagnóstico) y sería descartado sin motivo.

**Registro de cambio (2026-11-16): regla de sentido por historial.** Movido a `RESULTADOS.md`, «Registros de error», con el motivo y el efecto (contrato 2.3; el pipeline y el entrenamiento no cambian).

**Estado de la asignación (2026-11-13):** vigente en el dataset `data/ml/v2c` (`--assign geo3`); sentido por geometría vigente en la inferencia (contratos 2.1 a 2.3, exports `path_v3_l1_s1` y `path_v4_l1_s1`). `data/ml/v2` y `v2b` usan la tolerancia de 150 m (registro de error en §5). Pendiente: retrocesos de la distancia a lo largo > 150 m entre pings válidos consecutivos en 26–34 % de los viajes de las líneas 15, 42, 124 y 92 (8,7 % del total), probablemente bucles del recorrido; afectan la proyección tanto en el pipeline como en la app.

## 5. Vara de medir (antes de entrenar nada nuevo)

Los números de las corridas previas a la vara no son comparables entre sí: A3 72 s (16,5 M filas val, solo 39), A1 158 s (muestra de 500k), naive 672 s; el MAE global lo domina el tramo de >5 km (7,1 M de 16,5 M filas, 204 s). Por bucket, **A1 da 59 s en 0–500 m y 91 s en 0,5–2 km**, comparable o mejor que A3 (68 / 77 s): una tabla de 7 s de entrenamiento compite con el modelo de horas en distancia corta. Toda decisión se toma con la vara única descrita abajo.

- **Período de validación fijo:** 2026-09-15 → 2026-10-14. Train: todo lo anterior (menos excluidos). El 2026-10-15 y lo posterior a 2026-11-10 no se usan para esta vara (posterior = test futuro).
- **Dos conjuntos de evaluación congelados** (parquet con semilla, se generan una vez y no se regeneran):
  - `eval_seen`: líneas del train, período de validación.
  - `eval_heldout`: las líneas de control (12 en `lines.json`, §4.4; los eval de v2 usan 12, 15 y 128), período de validación.
- **Consulta de evaluación:** (coche en P a tiempo t, punto objetivo T adelante en el mismo viaje), con ETA real observada. Muestreo estratificado por ETA real para que cada bucket tenga suficientes casos.
- **Métricas, siempre por bucket** de ETA real (0–5, 5–10, 10–20, 20+ min) y de distancia (<500 m, 0,5–2, 2–5, 5+ km): MAE, P50, P90, sesgo, y la métrica clave: **% que llega antes de lo anunciado > 60 s** (pred − real > 60 s; el usuario pierde el colectivo), sobre todo en 0–5 min y <1 km. Se acompaña de **% que llega después de lo anunciado > 60 s** (real − pred > 60 s; espera de más, tolerable) y de la **espera extra media** cuando llega después (media de real − pred sobre las filas con real > pred), para no premiar anunciar todo "en 1 min". El MAE global se informa pero no decide.

**Vara principal (desde 2026-11-13): banda de ETA real 3–7 min**, con dos números: MAE y % que llega antes de lo anunciado > 60 s. Es el rango en que el usuario decide cuándo salir. Por debajo de 2 min la predicción es inviable y no se usa para decidir. La tabla por bandas de ETA real (0–2, 2–4, 4–6, 6–8, 8–10, 10–15, 15–20 min: MAE, P90 del error absoluto, % llega antes >60 s, % llega después >60 s, espera extra media) la produce `prediccion.eval` (clave `by_eta_band` del JSON, última sección del markdown). Las tablas por bucket de arriba se mantienen como informativas.

**Vara de producto (desde 2026-11-14).** Complementa la vara del modelo (MAE por bandas de ETA real sobre `eval_seen` / `eval_heldout`, arriba). Es el replay en condiciones de producción: `prediccion/replay/`, con la lógica de `path_reference` fijada por hash (copias en `prediccion/replay/pinned/`) y el modelo exportado, usando solo los pings disponibles hasta cada instante t y la presentación de la app (viene / puede venir / sentido sin confirmar, orden por ETA, tope de 5). Se evalúa contra el paso real del coche por la parada (verdad: cruce interpolado entre dos pings a lo sumo 10 min separados; horizonte 40 min). Métricas:
- **MAE del próximo coche que pasa por la parada**, en la banda de ETA real 3–7 min.
- **Bondis fantasma:** coches anunciados que no pasan por la parada.
- **Bondis no anunciados:** coches que pasan en ≤10 min y no estaban anunciados.
- **Sin aviso firme:** instantes sin ningún "viene" aunque pasa un coche en ≤10 min.
- Desglose por **tramo exclusivo** contra **tronco compartido** de la línea, y por línea.

Referencia, MAE del próximo coche anunciado, banda de ETA real 3–7 min (la vara del modelo da ~55 s para el ETA de cada coche; la diferencia viene de qué coche se anuncia como próximo, no del error de ETA por coche):

| Configuración | MAE | Días |
|---|---|---|
| Regla de sentido anterior (2026-11-14) | 107 s | 10 |
| Regla de sentido `trailing_run` (contrato 2.3) | 97 s | 10 |
| `trailing_run`, sin parche de ramal | 107 s | 6 con `route_id` resoluble |
| `trailing_run` + parche de ramal de CuandoSubo (producción) | 94 s | los mismos 6 |
| Oráculo de ramal (techo del ramal) | 87 s | los mismos 6 |

Cifras con la vara vigente (§5, verdad por recorrido ex post); la fila de 2026-11-14 es con la vara anterior. Los 6 días del parche son más difíciles que los 10 (107 contra 97 s sin parche); la comparación válida es dentro de los mismos días. El error de ETA por coche es ~54 s (RESULTADOS.md «Error de ETA por coche»): la diferencia hasta el MAE del próximo coche viene de qué coche se anuncia primero (coche que ya pasó, bondi fantasma, otro coche que llega antes). Informes: `ORACULO_RAMAL.md`, `BARRIDO_SENTIDO.md`, `FILTRO_RAMAL_CS.md` en `data/ml/replay/`; resultados en RESULTADOS.md.

**Métricas de la vara de producto** (usuario en una parada en un instante t):
- *Bondi fantasma:* la app muestra un coche con su ETA y ese coche no pasa por la parada en los 40 min siguientes. % sobre los coches listados.
- *Bondi no anunciado:* un coche pasa por la parada en los próximos 10 min y no estaba en la lista de la app. % sobre los coches que pasan.
- *Sin aviso firme (problema de la app, no del modelo):* pasa al menos un coche en los próximos 10 min y el grupo «Viene» estaba vacío (solo había coches en «Puede venir» o «Sentido sin confirmar»). Mide cómo la app agrupa y presenta coches que ya encontró; no es una métrica del modelo ni un objetivo de optimización del modelo. % sobre los instantes con algún coche que pasa.
- *Error del anuncio:* MAE del próximo coche anunciado (banda de ETA real 3–7 min) y % que llega antes / después de lo anunciado en más de 60 s.
Las métricas para decidir cambios de modelo o de asignación son el error del anuncio, el bondi fantasma y el bondi no anunciado.

**Vara de producto corregida (desde 2026-11-16).** Detalle y resultados: `data/ml/replay/VARA_CORREGIDA.md`. La verdad es el próximo cruce firme de la parada en (t, t + 40 min]:
- *Bondi fantasma:* coche listado con ETA anunciado (hora común) ≤ 40 min que no cruza; los listados con ETA > 40 min salen del denominador. Un coche que cruzó entre su último ping (≤ t) y t no es bondi fantasma (llega antes de lo anunciado).
- *Cruce firme:* par consecutivo entre los pings compatibles con el shape (se saltean los no compatibles), separados ≤ 10 min, con velocidad media ≤ 25 m/s (+ 50 m); parada en el último tramo del shape = se cruza al llegar a 50 m del final; recorridos que sirven la parada = solo los que la tienen en su lista (`ramales[].stops`); un recorrido que no la tiene no para ahí, aunque pase por la calle.
- *No verificable:* par de pings adyacentes (sin ping entre ellos) separados 10–40 min que encierra la parada: no entra en bondis fantasma y excluye el instante del MAE / llega antes / sin aviso firme si el paso pudo ser anterior al próximo paso firme. Se informa cuántos.
- *Recorrido real:* un cruce cuenta como paso solo si el viaje ex post del coche (segmentador geo2 + asignación geo3) en el tramo del cruce tiene la parada en su lista; si no, el coche no para ahí (si estaba listado, es bondi fantasma). Sin viaje ex post: no verificable (0,36 % de los cruces). Información ex post usada solo como verdad de la medición, no en la app.
- Bondi no anunciado y paso real usan la misma verdad.
Resultado de referencia (10 días, 12 líneas, `path_v3_l1_s1`, regla `trailing_run`; vara anterior → vigente): bondis fantasma 24,5 → 17,1 % (3–7 min: 14,6 → 12,7 %), bondi no anunciado 9,3 → 9,5 %, sin aviso firme 10,0 → 9,8 %, MAE 3–7 min 98 → 97 s, llega antes 14,4 → 14,4 %, llega después 26,4 → 26,3 %. Por grupo, bondis fantasma: «Viene» 5,7 %, «Puede venir» 56,7 %, «Sentido sin confirmar» 48,8 %.

**Registros de error (2026-11-16): definición de bondi fantasma de la vara de producto; asociación parada↔recorrido por geometría en la vara corregida.** Movidos a `RESULTADOS.md`, «Registros de error».

**Pérdida de entrenamiento (vigente desde 2026-11-13).** El modelo por tramos se entrena con L1 (`--loss l1`, simétrica: q = 0,5 a toda distancia, mediana). La asimetría ante el error grave (colectivo que llega antes de lo anunciado) no se resuelve con la pérdida: una pérdida asimétrica solo corre el anuncio, igual que un factor de anuncio en la app (ETA mostrada = ETA predicha × (1 − a)), que tampoco se usa (a = 0; sin valor según el usuario, RESULTADOS.md «Factor de anuncio»). El error grave se ataca mejorando la predicción y la asignación. `--loss pinball` (q 0,5 → 0,8 bajo 1 km; default del trainer para reproducir corridas anteriores y reanudar sus checkpoints), `--loss pinball_inv` (q 0,5 → 0,2 bajo 1 km) y `--loss pinball_band` (q 0,3 según la distancia restante, §6.2) son opciones del trainer y no se usan. Comparación en RESULTADOS.md ("Pérdida asimétrica vs ajuste en producto").

**Registros de error (hasta 2026-11-13: pérdida pinball y rótulo «subest. >60 s»; 2026-11-13: tolerancia de 150 m y calle paralela).** Movidos a `RESULTADOS.md`, «Registros de error»: listan las corridas, datasets y evaluaciones afectados. Resumen: la definición correcta es pérdida L1 simétrica y error grave = «llega antes de lo anunciado»; los datasets `v2`, `v2b` y afines usan la tolerancia de 150 m, `v2c` usa `geo3`.
- **Baselines en el mismo conjunto:** A0 naive (distancia / velocidad, con piso de velocidad razonable), A1 (reentrenado con el train v2; es barato), A3 actual ep21 (solo sobre la 39, como referencia histórica). Cuándo Subo se suma cuando exista su grabación.
- Script único `python -m prediccion.eval ...` que toma un modelo y escribe `data/ml/v2/eval/<modelo>_<fecha>.json` + tabla markdown. Resultados que importan se anotan en RESULTADOS.md.

## 6. Estado y plan de modelado

### 6.1 Estado de producción (2026-11-27)
- **Modelo en producción: `path_v4_l1_s1_r20261126`, desde 2026-11-27 (commit d6d507e de proyectoconsola, decisión del usuario).** Es el mismo checkpoint que `path_v4_l1_s1` (pesos y `path_eta.onnx` idénticos, sin reentrenar) con las tablas de shapes reconstruidas desde los `line_shapes` del 2026-11-26 (recorridos de CABA rehechos desde OSM, proyectoconsola c2bb8ec): 129 líneas, 646 shapes, 33 051 paradas (v4: 652 y 33 362). Los 6 shapeIds que ya no existen en la calle salen del export: 3075311, 4119935, 19912253 y 19912254 (línea 47), 10768848 y 10768850 (línea 132). Ninguna línea quedó sin shapes ni sin paradas. Exportado con `export_path_onnx --reshape` (§10.5); el manifest declara `reshaped_from` (checkpoint, fecha, commit de proyectoconsola de los shapes). Motivo y prueba: `data/ml/replay/RECORRIDOS_NUEVOS_42.md`; medición en las líneas que más cambiaron: RESULTADOS.md «Recorridos nuevos en las líneas que más cambiaron». Export `data/ml/export/path_v4_l1_s1_r20261126/`. **Volver atrás:** `activeModel` = `path_v4_l1_s1` en `proyectoconsola/public/config/prediccion.json` (la carpeta sigue en `public/models/`; fixture de paridad a regenerar con ese export).
- **Modelo base `path_v4_l1_s1`, en producción 2026-11-22 → 2026-11-27 (commit 576aeb5 de proyectoconsola).** Modelo por tramos con `--loss l1 --stops-feature` sobre `data/ml/v4_sub` (129 líneas AMBA < 200, LR 2e-3, 12 épocas, val MAE 80,5 s), semilla 1. Export `data/ml/export/path_v4_l1_s1/` (ONNX 2,65 MB; con `lines/`, 17 MB); checkpoint `data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt`; script `prediccion/scripts/export_path_onnx.py`. Resultados en RESULTADOS.md «v4».
- **Contrato 2.3** (`prediccion/INFERENCIA_PATH.md`):
  - 2.1: modelo por tramos + asignación geo3 (§4.5).
  - 2.2: + paradas por tramo. `manifest.stops_feature`, `manifest.stops.next_cap_m` = 1000 m, `stops_m` por shape en `lines/<línea>.json` (paradas del ramal proyectadas sobre el shape, metros desde el inicio), entradas ONNX `seg_stop_n` y `seg_stop_next`, armadas por tramo con `lo`/`hi` recortados a P→T (`stop_features_np`, INFERENCIA_PATH §3.3).
  - 2.3 (2026-11-16): + regla de sentido `trailing_run` (§4.5). ONNX sin cambios.
- **Líneas habilitadas en la app: 126:** 1, 2, 4, 7, 8, 9, 10, 12, 15, 17, 19, 20, 21, 22, 24, 25, 26, 28, 29, 31, 32, 33, 34, 37, 39, 41, 42, 44, 45, 46, 47, 49, 50, 51, 53, 55, 56, 57, 59, 60, 62, 63, 64, 65, 67, 68, 70, 71, 74, 76, 78, 79, 80, 84, 85, 86, 87, 91, 92, 93, 95, 96, 97, 98, 100, 101, 102, 103, 105, 106, 107, 108, 109, 110, 111, 113, 114, 115, 117, 118, 119, 123, 124, 126, 127, 128, 129, 130, 132, 133, 134, 135, 136, 140, 143, 145, 146, 150, 151, 152, 153, 154, 158, 159, 160, 161, 163, 166, 168, 169, 172, 174, 176, 177, 178, 179, 180, 181, 182, 184, 185, 188, 193, 194, 195, 197.
  - Las 46 habilitadas con v3: 4, 7, 9, 20, 25, 26, 28, 29, 33, 34, 39, 41, 42, 44, 46, 47, 50, 62, 74, 76, 84, 85, 92, 98, 102, 106, 107, 108, 110, 113, 114, 115, 118, 123, 124, 127, 132, 143, 151, 168, 169, 180, 184, 188, 194, 197.
  - 72 habilitadas con v4 el 2026-11-22 (criterio de RESULTADOS.md «v4»): 1, 2, 8, 10, 12, 15, 17, 19, 21, 22, 24, 31, 32, 37, 45, 51, 53, 55, 56, 57, 59, 60, 63, 64, 65, 67, 68, 70, 71, 78, 79, 80, 86, 87, 91, 93, 95, 96, 100, 101, 103, 105, 109, 111, 117, 126, 128, 129, 130, 133, 134, 135, 136, 140, 145, 146, 150, 152, 158, 159, 160, 161, 166, 172, 174, 176, 177, 178, 179, 181, 182, 195.
  - 8 habilitadas el 2026-11-22 tras el eval ampliado y el replay (RESULTADOS.md «v4»; commit 0f688b1 de proyectoconsola, decisión del usuario): 49, 97, 119, 153, 154, 163, 185, 193.
  - El modelo trae 129. No habilitadas: 61 y 88 (decisión del usuario); 164 (MAE 404 s en el replay, start_unknown 74 %).
  - Con aviso de calidad baja (`quality: "baja"` + `qualityNote` en `proyectoconsola/public/config/prediccion.json`; decisión del usuario 2026-11-22 con la vara de producto de v4, RESULTADOS.md «v4»; commit 96fd195): 8, 21, 28, 29, 45, 55, 80, 95, 96, 98, 100, 118, 136, 145, 159, 160, 166, 180, 182, 188, 194, 197.
    - Criterio aplicado: líneas nuevas con MAE del próximo coche ≥ 159 s; de las de v3, las 7 con aviso previo salvo la 7, más la 118 (190 s). Sin aviso: 7 (solo supera sin aviso firme), 34 y 102 (superan solo llega después y bondi no anunciado), 57, 178, 15 y 195 (139–159 s; corte del usuario).
    - `qualityNote` según el caso dominante de la descomposición del próximo coche (RESULTADOS.md «Descomposición del error del próximo coche»): «muchos coches anunciados no pasan por esta parada» (bondi fantasma: 8, 21, 29, 55, 80, 96, 136, 145, 159, 160, 166, 180, 182, 188, 194, 197); «el primer coche anunciado suele no ser el que llega» (otro coche llega primero: 28, 45, 95, 98, 100, 118).
  - La 29 tiene un shape sin paradas en `line_shapes` (`stops_m` vacío, igual que en entrenamiento).
- **Asignación en la app:** porta `prediccion/v2/geo_assign.py` tal cual (`compatible_shapes`, `direction_from_geometry`, `direction_from_history`, `forward_fraction`, proyección) con las constantes de `manifest.assignment` (T = 45 m, M = 20 m, rumbo 45°, ventana de historial, regla de sentido). No tiene reglas de asignación propias, salvo el parche de ramal de abajo.
  - Punto del usuario: parada → shapes que la tienen en su lista de paradas; GPS o mapa → `snap_to_route` a ≤ T y luego `compatible_shapes`.
  - Proyección: entre segmentos a ≤ 1e-6 m de la distancia mínima gana el primero (recorridos que repiten la misma calle).
- **Parche de producción: ramal informado por CuandoSubo (desde 2026-11-16).** Solo en la app; no es parte del pipeline ni del entrenamiento (decisión del usuario).
  - Tabla `proyectoconsola/public/config/ramal_cuandosubo.json`, generada desde `mapping_cuandosubo_osm/TABLA_MAPEO.csv` (filas `estado_par = PAR`: 34 pares, 12 líneas de producción). Clave: terna `longName|shortName|description` de la ruta de CuandoSubo (estable), no `route_id` (rota cada pocas semanas).
  - Si el ramal informado está en la tabla y coincide con algún shape compatible del coche, los candidatos se restringen a esos shapes y el sentido queda confirmado (salvo que el historial lo contradiga). Sin dato, sin coincidencia o con intersección vacía: sin restricción.
  - Medición con la vara de producto: `data/ml/replay/FILTRO_RAMAL_CS.md`.
- **Texto de destino en la app (`csDestino`):** `<shortName de CuandoSubo>: <destino>`; la ruta 99A se muestra "106 rojo (ex 99)".
- **Factor de anuncio** (ETA mostrada = ETA predicha × (1 − a), solo corre el anuncio, no mejora la predicción): a = 0. Sin valor según el usuario (2026-11-16): ajuste fino irrelevante, no se usa (RESULTADOS.md).
- **Corrección de hora:** `CABA_TS_OFFSET_S` = 60 s en la app; provisorio, sin verdad de campo.
- **Paridad pipeline/app:** la referencia numpy del export verifica contra el modelo entrenado; fixture JS contra Python regenerado con `path_v4_l1_s1_r20261126` (`proyectoconsola/test/fixtures/path_parity.json`, 35 MB), dentro de `npm test`.
- **Volver atrás (modelos anteriores):** `path_v4_l1_s1` (shapes del entrenamiento), `path_v3_l1_s1` (48 líneas, contrato 2.3) y `path_v2c_l1_s1` (12 líneas, contrato 2.1) quedan en `data/ml/export/` y en `proyectoconsola/public/models/`; volver a `path_v3_l1_s1` exige también reducir `enabledLines` a las 46.

### 6.2 Estado de los experimentos
Resultados y números en RESULTADOS.md; comandos en §10.
Lista de experimentos priorizada: §11.
- **v2c, asignación geo3, 12 líneas (2026-11-13):** dataset `data/ml/v2c`, subconjunto `data/ml/v2c_sub`, eval `data/ml/v2c/eval`, lanzador `prediccion/scripts/run_v2c.py`, tabla `data/ml/v2c_sub/runs/comparacion.md`. Base de `path_v2c_l1_s1`.
- **Paradas por tramo (2026-11-13):** adoptada desde v3; no cuesta en líneas vistas y mejora en no vistas.
- **v3, 48 líneas (2026-11-15):** en producción del 2026-11-15 al 2026-11-22; reemplazado por v4. Train 48 (las 12 de producción + 36 nuevas), control 12 (1, 12, 15, 21, 64, 65, 68, 87, 100, 109, 128, 181), lista de 60 líneas de `data/ml/v2/lines.json`. Datos `data/ml/v3`, `data/ml/v3_sub`, eval `data/ml/v3/eval`, lanzador `prediccion/scripts/run_v3.py`.
- **v4, 129 líneas AMBA < 200 (2026-11-21):** en producción desde 2026-11-22. Datos `data/ml/v4`, `data/ml/v4_sub` (todas), `data/ml/v4_ctrl` (sin las 12 de control de v3), eval `data/ml/v4/eval`, lanzador `prediccion/scripts/run_v4.py`, informe `data/ml/v4_sub/runs/INFORME.md`, no regresión `data/ml/v4_sub/runs/no_regresion.md` y `decision.json`.
- **v3full, train desde 2026-03-28 (2026-11-15):** descartado. Mejora ~1 s en líneas vistas, empeora en no vistas y cuesta 3,2× más entrenar.
- **Pérdidas `pinball`, `pinball_inv` y `pinball_band` (2026-11-13):** descartadas; se usa L1 y la asimetría va al producto (§5). Configuración de `pinball_band`: q depende de la distancia restante (entrada del modelo, nunca de la ETA real); banda [d_lo, d_hi] = p10 y p90 de la distancia restante de las filas de train de `data/ml/v2b_sub` con ETA real 3–10 min (532 m y 2074 m); q = 0,30 dentro de la banda, rampa lineal a 0,5 en los 300 m afuera de cada borde, 0,5 en el resto; parámetros en `loss_cfg` del checkpoint y de `path_eta_metrics.json`. Corrida: lanzador `prediccion/scripts/run_v2b_band.py`, salida `data/ml/v2b_sub/runs_band/`.
- **Tránsito actual por tramo (2026-11-16):** mejora ~1–2 s; no se porta a la app.
- **Factor de anuncio (2026-11-16):** descartado; solo corre el anuncio, no es una mejora (§6.1).
- **Regla de coche detenido (2026-11-16):** descartada.
- **Objetivos de entrenamiento en paradas reales (2026-11-17):** descartado; sin mejora en líneas vistas y peor en no vistas.

### 6.3 Replanteo del 2026-11-12 y 6.4 Escalera anterior (E0–E2)
Movidos a `docs_old/ARQUITECTURA_historia.md` (historia; los pasos «Paso 6.2.N» que cita `RESULTADOS.md` están en §6.3 de ese archivo).

## 7. Resultados
Movida completa a `RESULTADOS.md` (resultados en orden de subsección, con índice; también los registros de error y los pendientes cerrados).

## 8. Decisiones previas que siguen vigentes (no re-discutir sin dato nuevo)

Del plan histórico: modelo único para todas las líneas (§7); pérdida L1 con el ajuste de anuncio en el producto (§5, §7); distancia mínima 100 m (§7); `schedule_dev_norm` aporta poco pero positivo (Exp. 2); `time_since_last_bus_s` ambiguo (Exp. 2); umbral "llegando" `pred < 150 s OR dist < 300 m` (dato del modelo A3, Exp. 1; sin efecto en el modelo por tramos: la app usa `LLEGANDO_UMBRAL_S` = 60 s solo como texto de presentación, `proyectoconsola/public/prediccion/core.js`); stop-to-stop y Transformer seq2seq postergados (§7, Fase 5); la flota de entrada es la de la agencia (§7).

## 9. Inconsistencias conocidas en docs viejos
Movida a `docs_old/ARQUITECTURA_historia.md`.

## 10. Cómo correr

Todo desde `prediccion colectivos/`, en PowerShell.

### 10.1 Entorno y corridas largas
- **Python:** el del sistema, `C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe` (torch 2.7.1+cu118, ve la RTX 3080; tiene orjson, isal, psutil, scipy y onnxscript). El `python` de PowerShell resuelve a `Dondeestaelbondi\.venv`, que tiene torch CPU: no usarlo. Si falla `python -m ...`, usar `$env:PYTHONPATH="."`. `scipy` hace falta para la proyección rápida (`ShapeIndex(fast=True)`).
  ```powershell
  $PY = "C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe"
  & $PY -c "import torch; print(torch.cuda.is_available())"    # tiene que dar True
  ```
- **Corridas largas (obligatorio desde 2026-11-15):** lanzar desacopladas con `Start-Process` (una tarea en segundo plano de la sesión se corta a las 2 h) y mantener la PC despierta con `prediccion/scripts/keep_awake.py <pid>` apuntando al PID del proceso lanzado; verificar que imprima `keep_awake activo` y que el log de entrenamiento diga `device=cuda`. Sin PID, `keep_awake.py` corre hasta que se lo mata.
  ```powershell
  $p = Start-Process $PY -ArgumentList "-u","-m","prediccion.scripts.run_v3" -WindowStyle Hidden -PassThru -RedirectStandardOutput data\ml\v3_sub\runs\launcher.out -RedirectStandardError data\ml\v3_sub\runs\launcher.err
  Start-Process $PY -ArgumentList "prediccion/scripts/keep_awake.py",$p.Id -WindowStyle Hidden
  ```
- Registro de error (2026-11-14): suspensión de la PC durante el entrenamiento v3 (bloqueo de suspensión desde PowerShell inefectivo). Movido a `RESULTADOS.md`, «Registros de error».

### 10.2 Dataset
Código: `prediccion/v2/` (shapes, pairs, rows, segmenter, geo_assign, day = `process_day`, assemble, build, make_eval). Todo escribe en `data/ml/v2*/` y `data/ml/v3*/`. Receta vigente: segmentación `geo2`, asignación `geo3`, K = 32 pares por viaje, train desde 2026-07-20, val = muestra del 40 %.

Lanzador reanudable de v4 para todas las líneas AMBA < 200: `prediccion/scripts/run_v4.py` (build, selección por volumen, ensamblado de `v4_sub` y `v4_ctrl`, eval congelado, 2 runs, no regresión contra producción y decisión de publicar; no exporta ni instala). Lanzador único y reanudable de v3 (build por bloques de 14 días, validación, ensamblado, eval congelado, entrenamiento de 2 semillas, evaluación y `comparacion.md`); probar antes con `--smoke` (2 días, CPU, `data/ml/v3_smoke`):
```powershell
& $PY -m prediccion.scripts.run_v3 --smoke
```
Equivale a (el lanzador agrega la lista de líneas de `data/ml/v3/lines.json`, 48 de train y 12 de control, y reparte los días en bloques):
```powershell
& $PY -m prediccion.v2.build --lines-file data/ml/v3/lines.json --lines <60 líneas> --days 2026-03-28:2026-10-14 --pairs-per-trip 32 --workers 3 --segmentation geo2 --assign geo3 --low-priority --out-dir data/ml/v3 --no-assemble
& $PY -m prediccion.v2.assemble --v2-dir data/ml/v3 --lines-file data/ml/v3/lines.json --only-lines <48 de train> --dest data/ml/v3_sub --train-start 2026-07-20 --val-sample-frac 0.4
& $PY -m prediccion.v2.make_eval --v2-dir data/ml/v3 --lines-file data/ml/v3/lines.json --n-per-bucket 15000
```
- Costo medido (60 líneas, K = 32): ~155 s de CPU por día hábil (92 s sábado), 2,3 GB de RAM por worker; ~1 h de pared con 8 workers más la lectura por SMB (~40 GB de gz). Disco ~104 B/fila.
- El build es idempotente por día: el mismo comando reanuda un corte o agrega una línea (solo reprocesa los días que no la tienen). Un día construido con otra asignación (`meta.assign`) se reprocesa. `meta.json` de cada día guarda los parámetros.
- El eval de v3 usa 15.000 filas por bucket de ETA (60.000 por conjunto) para que el desglose por línea tenga muestra.
- Estructura de cada `data/ml/<dataset>/`: `lines.json` (train/control) · `daily/YYYY-MM-DD.{parquet,trips.parquet,waiting.parquet,meta.json,carry.json}` · `manifest.json` · `training/eta_train|eta_val.parquet` · `shape_lengths.json` · `schedule_dev_medians.json` · `eval/eval_seen|eval_heldout.parquet` + resultados.

### 10.3 Entrenar y reanudar
```powershell
& $PY -m prediccion.train_path --ml-dir data/ml/v3_sub --out-dir data/ml/v3_sub/runs/path_lr2e-3_s0 --lines-file data/ml/v3/lines.json --epochs 12 --batch-size 1024 --lr 2e-3 --seed 0 --loss l1 --stops-feature --resume
```
Receta vigente: modelo por tramos, L1, `--stops-feature`, LR 2e-3, 12 épocas, OneCycle, batch 1024; el mejor checkpoint se elige por MAE de val. Tiempo medido en v3 (31 M filas de train): ~5,4 min por época, ~65 min por semilla.

**Reanudar.** Al final de cada época el trainer escribe `path_eta_last.pt` de forma atómica (a `.tmp` y `os.replace`). Contiene modelo, optimizador, scheduler, época, mejor métrica, historial, RNG y la config del run; `path_eta_best.pt` va aparte. Para retomar, relanzar el mismo comando con `--resume`: sigue en la época siguiente con el LR que le tocaba; si el corte fue a mitad de época se pierde solo esa época. Si la config guardada no coincide con la actual (épocas, lr, batch, datos, etc.) falla y lista las diferencias. En CPU la reanudación es exacta (`test_resume.py`); en GPU con varios workers de DataLoader el orden de filas de la época reanudada no es idéntico.

### 10.4 Evaluar
- **Vara del modelo** (filas de eval congeladas, §5):
  ```powershell
  & $PY -m prediccion.eval --model path:data/ml/v3_sub/runs/path_lr2e-3_s1/path_eta_best.pt --set seen --out-dir data/ml/v3_sub/runs/eval
  ```
  `--set seen|heldout`, `--lines` para filtrar, `--save-preds` para guardar predicciones. Reporta bandas de ETA (principal 3–7 min), llega antes / después > 60 s y desglose por línea.
- **Vara de producto** (replay en condiciones de la app, §5; lógica de la app fijada en `prediccion/replay/pinned/`, hoy contrato 2.3):
  ```powershell
  & $PY -m prediccion.replay.run --model data/ml/export/path_v4_l1_s1 --variants base --out data/ml/replay/<corrida> --workers 3
  & $PY -m prediccion.replay.report_vara vara --runs data/ml/replay/<corrida> --days <días> --out <informe>.md
  ```
  Por defecto: 12 líneas de producción, 10 días de evaluación, 40 paradas por línea, instantes cada 10 min. Variantes: `base` (producción), `sentido`, `ramal` (oráculo del ramal ex post), `cs` (parche de ramal de CuandoSubo; solo en los días de `--cs-days`, donde `--cs-map` resuelve los `route_id`). Salidas por (día, línea): `<out>/<día>_<línea>.veh.parquet` e `.inst.parquet`; se salta lo ya hecho. Otros reportes: `prediccion/replay/report_v3.py`, `report_consistencia.py`.

### 10.5 Llevar un modelo a producción
1. Exportar: `& $PY -m prediccion.scripts.export_path_onnx --ckpt <path_eta_best.pt> --out data/ml/export/<versión>` (verifica la referencia numpy contra el modelo entrenado salvo `--no-verify`; shapes de `proyectoconsola/data/line_shapes`).
2. Fixture de paridad: `& $PY -m prediccion.scripts.gen_path_parity_fixture --export data/ml/export/<versión> --out ../proyectoconsola/test/fixtures/path_parity.json`.
3. Instalar en la app: `node scripts/instalar_modelo.js <versión> --activar` (desde `proyectoconsola/`; origen por defecto `../prediccion colectivos/data/ml/export/<versión>/`; `--activar` cambia `activeModel` sin tocar las líneas habilitadas).
4. Tests de la app: `npm test` (incluye la paridad JS contra Python) y `npm run test:e2e`.
5. Deploy: push a `main` de proyectoconsola (Vercel); verificar que `https://consola-transporte.vercel.app/models/<versión>/manifest.json` sirva el contrato nuevo.
6. **Reexportar sin reentrenar con los `line_shapes` actuales** (cuando cambian los recorridos o paradas de proyectoconsola): en el paso 1 agregar `--reshape` y un nombre con la fecha de los shapes, p. ej. `--ckpt data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt --out data/ml/export/path_v4_l1_s1_r20261126 --reshape`. Sin `--reshape` el script aborta si la geometría o las paradas de `line_shapes` difieren de las del checkpoint (salvaguarda contra desfase entre entrenamiento y servicio). Con la opción reconstruye `seg_lat`, `seg_lon`, `shape_off` y `stop_key` desde `line_shapes` (los shapeIds que ya no están se conservan en la tabla y no se exportan; los nuevos se agregan), mantiene la verificación ONNX contra PyTorch, avisa de las líneas sin `line_shapes` y anota `reshaped_from` en el manifest (checkpoint, fecha, commit de proyectoconsola). El modelo no tiene parámetros por shape: pesos y ONNX no cambian, el contrato tampoco (INFERENCIA_PATH.md). Test: `prediccion/tests/test_export_reshape.py`. Un modelo reexportado no es retrocompatible con coches que todavía van por el recorrido viejo: activarlo cuando el nuevo es el vigente en la calle.

### Corridas históricas
E0–E2 (A0, A1, A3 con y sin grilla, línea 39 y 48 líneas), el subconjunto `v2_sub`, v2b, v2c, pérdidas y tránsito: comandos en sus lanzadores (`prediccion/scripts/run_confirmacion.py`, `run_v2b.py`, `run_v2b_l1.py`, `run_v2b_pinv.py`, `run_v2b_band.py`, `run_v2c.py`, `run_stops.py`, `run_traffic.py`, `run_v3full.py`) y en el tag git `pre-arquitectura-2026-11` (`git show pre-arquitectura-2026-11:<ruta>`); resultados en RESULTADOS.md. El trainer A3 (`prediccion.train --phase 3`) y A1 (`--phase 1`) siguen en el código.

## 11. Pendientes

Lista ordenada por prioridad (actualizada 2026-11-27). Cada experimento de modelo entra como un solo cambio contra el modelo de producción, medido con las varas de §5. Lo ya evaluado está en RESULTADOS.md y su estado en §6.2.

Motivo del orden: el modelo está estancado en ~54–56 s de MAE. Pasar de 48 a 129 líneas no cambió las líneas vistas; 3× más días de entrenamiento dieron −1 s; el tránsito, −1/−2 s; las paradas, 0 en las vistas. Antes de seguir cambiando el modelo hay que medir el piso alcanzable (ítem 1) y atacar lo que sí pesa: qué coche viene y por qué ramal (ítems 2–4).

| # | Pendiente | Tipo | Estado |
|---|---|---|---|
| 0 | **Arreglar las líneas débiles (prioridad máxima, decisión del usuario 2026-11-27)** | producto | sin empezar |
| 0b | **Reentrenamiento con recorridos que cambiaron** | datos | problema para ver, sin resolver |
| 1 | Piso del ETA por coche (experimento «gemelos») | medición | cerrado 2026-11-27: el modelo está en el piso |
| 2 | Prior de ramal por cabecera | medición | en curso desde 2026-11-27 |
| 3 | Asignación probabilística unificada: P(el coche pasa por la parada en el horizonte) | asignación | diseño después de 1 y 2 |
| 4 | Coche que ya pasó y sigue listado | asignación | medido 2026-11-23, sin portar; decisión del usuario pendiente |
| 5 | Ritmo propio del coche | modelo | prioridad baja (margen ≤ ~2–7 s de MAE, resultado de 1) |
| 6 | Corrección de hora con registros «Pasó» | producto | WIP del usuario; se revisa con ~100 pasos |
| 7 | Drift fuera del período de validación | medición | bloqueada hasta ~mediados de diciembre 2026 |
| 8 | Errores en las colas y lluvia | medición | para después |
| 9 | Prueba de generalización más fiel que las líneas de control | medición | para después |
| 10 | Primer minuto con un solo ping | producto | sin empezar |
| 11 | Atributos de calle de OSM por tramo | modelo | sin empezar |
| 12 | Ramal desconocido en tiempo real | modelo | sin empezar; el camino son los ítems 2 y 3 |
| 13 | Tránsito por zona y grilla más fina | modelo | baja prioridad |

Los pendientes cerrados están al final de la sección.

### Lo de producción se muda a `bondi/red` (decisión del usuario, 2026-11-27)

Roadmap del producto: `../bondi/docs/ROADMAP.md` (repo `lucianken/bondi`), secciones «Qué vive dónde», «Transición» y «Fase 1 — La red». Lo que corre en producción o define una regla que producción usa sale de este proyecto y pasa a `lucianken/bondi`, carpeta `red/`. **Este proyecto queda como investigación**: grabadores, datasets, entrenamiento, evaluación, replay y experimentos. No corre nada de producción y su desorden (`legacy/`, `docs_old/`, código del A3, `data/ml` versionado) no bloquea nada.

Qué se muda (tareas F1.2–F1.8 del roadmap):
- **Datos fuente** a `red/datos/`: `LABEL_LINE_MAP.json` con `pending_label_work.json` y su ciclo de resolución (fuente única: se borra el espejo de este proyecto), `prediccion/label_map/`, y los recorridos y paradas de `proyectoconsola/data/line_shapes/` con OSM, `official_ref` y paradas compartidas.
- **Reglas y referencia** al paquete Python `red` (`red/python/red/`): `prediccion/v2/geo_assign.py`, la regla de sentido `trailing_run` y `prediccion/inference/path_reference.py`, la carga de recorridos y del map (`shapes_io.py`, lo que haga falta de `prediccion/v2/shapes.py`), el armado de entradas del modelo (`encode_time_np`, `stop_features_np`). El contrato `prediccion/INFERENCIA_PATH.md` pasa a `bondi/docs/contratos/`.
- **Export y paquete** a `red/paquete/`: `prediccion/scripts/export_path_onnx.py`, `gen_path_parity_fixture.py` y la definición del modelo que usa el export. De un checkpoint sale un **paquete de datos** versionado con todo en un solo corte (modelo, recorridos, paradas, `LABEL_LINE_MAP`, calidad por línea). Los recorridos que dibuja la app, los del servicio de estado y los del modelo son los mismos archivos (motivo: la 42 con el Trambus, 2026-11-25/27, dibujaba el recorrido nuevo y el modelo de v4 seguía con el viejo; se arregló reexportando a mano). Cuando cambian los recorridos, un solo paso arma un paquete nuevo con los mismos pesos, sin reentrenar; cuándo además hace falta reentrenar sigue siendo de este proyecto (ítem 0b).
- **Servicio de estado** a `red/estado/`: un contenedor junto al caché del producto que lee cada lote (con el historial de 20 min de cada coche) y devuelve por coche `candidatos: [{shape_id, p, sentido, d_m}]` y `version` (asignación y ramal juntos). La app deja de tener la asignación portada al JS. v0 = la asignación vigente tal cual, `p` = 1/n entre los compatibles con sentido conocido. El ítem 3 (asignación probabilística unificada) es una versión siguiente de este servicio. El producto no consume CuandoSubo: el parche de ramal de CuandoSubo y `csDestino` salen del producto.

Cómo trabaja este proyecto después de la mudanza:
- Importa el paquete `red` de `bondi` por versión (tag de git) y registra la versión en el `meta` de cada dataset y de cada corrida. La regla de §4.5 («la asignación se define una vez en el pipeline y la app la porta») pasa a ser: **la asignación se define una vez en `bondi/red` y la importan el pipeline y el servicio de estado**. Un cambio de regla se hace en `red/` con test; después este proyecto sube la versión que importa.
- Su salida es un checkpoint entrenado; `red/paquete/` lo convierte en paquete y lo publica. El servidor del producto decide qué versión está activa.
- Antes de borrar el código movido de acá, el pipeline y el replay tienen que dar los mismos resultados con el paquete importado que con el código anterior, sobre un día fijo.
- Hasta que termine la mudanza siguen vigentes las fuentes actuales (`proyectoconsola/data/line_shapes/`, el espejo de `LABEL_LINE_MAP.json`, `data/ml/export/`). Cuando termine, actualizar §3, §4.5, §6.1 y §10.5 de este documento.

### Pendientes abiertos

0. **Arreglar las líneas débiles.** Producto, prioridad máxima (decisión del usuario, 2026-11-27); los ítems 1–13 quedan por debajo y valen en la medida en que sirvan a este.
   - Alcance: las 22 líneas con aviso de calidad baja (§6.1: 8, 21, 28, 29, 45, 55, 80, 95, 96, 98, 100, 118, 136, 145, 159, 160, 166, 180, 182, 188, 194, 197) y las no habilitadas 164, 61 y 88.
   - Su error es de asignación, no de ETA por coche: el error por coche es igual a la vara del modelo y la diferencia está en qué coche se anuncia primero (RESULTADOS.md «Descomposición del error del próximo coche, v4»). Caso dominante: bondi fantasma en 8, 21, 29, 55, 80, 96, 136, 145, 159, 160, 166, 180, 182, 188, 194 y 197; otro coche llega primero en 28, 45, 95, 98, 100 y 118. La 164 tiene 74 % de `start_unknown`, la 88 79 %.
   - Primer paso: diagnóstico por línea de la causa del bondi fantasma y del «otro coche llega primero» (otro ramal, sentido, viaje que termina antes, recorrido faltante en OSM, parada fuera de la lista), con la clasificación de `FALSAS_ALARMAS.md` extendida a estas líneas. La 8 tiene 6 ramales en `line_shapes` y el usuario indica 10–12 reales.
   - Los recorridos de CABA se rehicieron desde OSM el 2026-11-26 (proyectoconsola c2bb8ec); el modelo en producción usa los del export de v4. Medir estas líneas también con los recorridos nuevos (prueba de la 42: `data/ml/replay/RECORRIDOS_NUEVOS_42.md`).
   - Criterio de salida: una línea pierde el aviso cuando queda bajo los umbrales de la vara de producto de v4 (RESULTADOS.md «v4», umbral de avisos).

0b. **Reentrenamiento con recorridos que cambiaron.** Problema para ver (2026-11-27); sin resolver.
   - Los días del dataset (`data/ml/v4/daily/`) se armaron con los shapes viejos. El build reprocesa un día solo si cambian sus parámetros (`meta.json`, p. ej. `assign`), no si cambian los shapes.
   - Un reentreno mezclaría días con shapes viejos y días con shapes nuevos; y en las líneas que cambiaron, los pings anteriores al cambio en la calle (p. ej. la 42 antes del 2026-11-25) no encajan con el recorrido nuevo.
   - Opciones a evaluar: huella de shapes en `meta.json` (el build reprocesa el día si cambia), shapes con vigencia por fecha (cada día usa los recorridos vigentes ese día), excluir de cada línea los días previos a su cambio.
   - Hoy el modelo en producción no depende de esto: usa el checkpoint de v4 con las tablas nuevas (§6.1).

1. **Piso del ETA por coche (experimento «gemelos»).** Medición, **cerrada 2026-11-27** (`experiments/piso_gemelos/INFORME.md`, commit 376f35a; RESULTADOS.md «Piso del ETA por coche (gemelos)»).
   - Resultado: el modelo está en el piso con oráculo de tránsito. Tramo de 1000 m, banda 3–7 min: el gemelo da 49,9 s de MAE y el modelo 49,6 s en los mismos casos; a 1500 m, 55,4 contra 59,4 s. El piso neto de ruido de interpolación es de 43–50 s. La prioridad pasa a la asignación (ítems 2–4).
   - Dos coches que recorren el mismo tramo (mismo sentido, entrada al tramo con ≤ 60 s de diferencia) equivalen a un predictor con oráculo de tránsito: el tiempo de uno predice el del otro. Su error es una cota del error alcanzable en 3–7 min.
   - Líneas: 39, 42, 92, 107, 132, 168.
   - Salida: `experiments/piso_gemelos/INFORME.md`.
   - Planteo original: si el modelo (~54–56 s) ya está cerca del piso, el resto de las mejoras de ETA por coche rinde poco y la prioridad pasa a la asignación (ítems 2–4).
2. **Prior de ramal por cabecera.** Medición, en curso desde 2026-11-27.
   - Mezcla de ramales por línea × hora × día de la semana, y secuencia de despachos por cabecera (cualquier coche, no el mismo).
   - Distinto de la persistencia por coche, que ya se midió y no sirve (ítem 12).
   - Salida: `experiments/prior_ramal_cabecera/INFORME.md`.
3. **Asignación probabilística unificada: P(el coche pasa por la parada en el horizonte).** Asignación; diseño después de los ítems 1 y 2.
   - Un solo clasificador calibrado por candidato que combine: compatibilidad geométrica, estado del sentido, prior de ramal, ramal informado por CuandoSubo, ETA, edad del ping, distancia a la divergencia y «ya pasó». El coche detenido entra como variable de este clasificador (la regla ad hoc está descartada, RESULTADOS.md).
   - Reemplaza las reglas sueltas de asignación.
   - Etiqueta ex post (cruce firme). Se define en el pipeline y la app la porta.
   - CuandoSubo entra como evidencia con su confiabilidad medida por línea (91,3 % de contención; en la 42 no coincide en el 57 %), no como override.
   - Ataca los casos (b), (c) y (d) de la descomposición del próximo coche: 15 + 29 + 18 s de los 117 s (RESULTADOS.md «Descomposición del error del próximo coche, v4»).
4. **Coche que ya pasó y sigue listado (ex 11.10).** Asignación.
   - El 7 % de los instantes anuncia como próximo a un coche que ya cruzó la parada entre su último ping y la consulta; aporta 19 de los 97 s del MAE del próximo coche (RESULTADOS.md «Error de ETA por coche»).
   - Medido 2026-11-23 (RESULTADOS.md «Coche que ya pasó»): la variante P > 0,5 «baja» da −3,3 s en el MAE del próximo coche 3–7 min, mejora 117 de 126 líneas y no cambia los bondis no anunciados. Sin portar.
   - Queda absorbido por el ítem 3 si este avanza; si no, portarlo solo (pipeline → app). Decisión del usuario pendiente.
5. **Ritmo propio del coche.** Modelo; **prioridad baja** (resultado del ítem 1, 2026-11-27): margen ≤ ~2–7 s de MAE (hasta ~4–5 s más si la señal valiera tanto como promediar varios gemelos). Margen relativo solo en «llega antes > 60 s» (modelo 19,5 % contra gemelo 13,0 % a 1000 m), en parte por sesgo del modelo y en parte por la selección por ETA real.
   - Entrada causal nueva: tiempo real de los últimos 1–2 km del coche contra el tiempo típico del modelo en esos tramos.
   - Va como entrada del modelo, por tramo; hoy el estado del coche entra únicamente en el ajuste global `adj` (`prediccion/models/path_eta.py`, forward).
   - La define el pipeline y la app la calcula con su historial de 20 min (como `--stops-feature`); máscara si hay menos de 2 pings.
   - Requiere reentrenar y un contrato nuevo.
6. **Corrección de hora con registros «Pasó» (ex 11.3).** Producto; WIP del usuario, se revisa con ~100 pasos.
   - `CABA_TS_OFFSET_S` = 60 s es provisorio, sin verdad de campo; funciona bien de forma provisoria.
   - Cada «Pasó» da la hora real de paso; el replay reconstruye lo que la app anunció en cada minuto previo.
   - Tamaño: ~100 registros para un desfase global (σ ~90 s → ±10 s); unos cientos para un desfase por banda de ETA.
7. **Drift fuera del período de validación.** Medición, bloqueada hasta tener ≥ 30 días posteriores a la caída de la API (datos desde 2026-11-10/14; revisar ~mediados de diciembre 2026).
   - Evaluar v4 sobre esos días contra la val 09-15 → 10-14, que está sobreusada: todas las decisiones se tomaron ahí.
   - Decidir un reentreno periódico automatizado.
8. **Errores en las colas y lluvia.** Medición, para después.
   - El tránsito se evaluó en la media; falta evaluarlo en días anómalos y en el P90.
   - Residuos por día de lluvia sin entrenar, como se hizo con el feriado (sesgo −28 s, RESULTADOS.md).
9. **Prueba de generalización más fiel que las líneas de control (ex 11.8).** Medición, para después.
   - Las líneas de control no representan producción (no hay líneas nuevas; sí recorridos modificados, ramales nuevos y tramos poco recorridos).
   - Opciones: dejar afuera un ramal o un tramo de una línea vista, o recorridos sintéticos (`docs_old/ARQUITECTURA_historia.md` §6.3).
10. **Primer minuto con un solo ping (ex 11.4).**
    - Con 1 ping del coche: bondis fantasma 35 %, MAE 3–7 min 230 s. Con 2 pings (~1 min de app abierta): MAE 99 s (RESULTADOS.md «Regla de sentido por racha final»).
    - Opciones: presentación del primer minuto en la app, o un servidor con los últimos 10–20 min de la flota. Vercel no guarda estado entre llamadas: el escritor tendría que ser externo (p. ej. el NUC).
11. **Atributos de calle de OSM por tramo (ex 11.6).**
    - Tipo de vía, carril exclusivo / Metrobús, semáforos, intersecciones, giros.
    - Valor esperado: generalización a recorridos nuevos o modificados y tramos con pocos datos; poco en líneas ya entrenadas. Depende de la calidad de OSM (`arreglar OSM/`).
12. **Ramal desconocido en tiempo real (ex 11.7).** El camino son los ítems 2 y 3; este ítem guarda la evidencia medida.
    - En tramo compartido el coche puede ir a varios ramales; si T está después de la divergencia hay varios futuros (D3: +12 s de error contra +8 s en el resto).
    - Salida: predecir por ramal candidato o con probabilidad de pasar por T (ítem 3). El parche de ramal de CuandoSubo (§6.1) cubre parte en producción.
    - Persistencia del ramal por coche (medido en junio 2026, línea 168, tramo compartido La Boca → Darwin, 66 días, 9.341 viajes; `docs_old/skills/168_ramal_analysis.md`, scripts en `experiments/explore_168/`): el ramal del viaje previo del mismo coche ese día acierta el 62 % (base 50 %, cobertura 70 %); patente, patente × día, hora, `trip_id`, odómetro y posición en la terminal: 48–62 %. El 65 % de los coche-día cambia de ramal en el día (rotación vuelta a vuelta). Sin utilidad operacional.
    - Persistencia del ramal por coche, línea 39 (2026-11-23; `experiments/ramal_persistencia_39/INFORME.md`, `r39.py`, `verif39.py`). Verdad: recorrido ex post del pipeline (geo3) y, en 2026-09-24/25/26, `route_id` de CuandoSubo traducido con `ramal_cuandosubo.json`. 7 días de septiembre, 5.635 viajes, 577 coche-día: ramal igual al del viaje previo del mismo coche 35,7 % contra 36,3 % del ramal más frecuente; 0,7 % de los coche-día hacen un solo ramal; transición casi uniforme. Con CuandoSubo como verdad: 36,8 % contra 38,0 %. Con viajes confirmados por pings en el tramo exclusivo de su ramal (solo B y C; A no tiene tramo exclusivo a ≥ 100 m): 53,0 % contra 54,8 %. Sin utilidad: los coches rotan de ramal casi al azar dentro del día.
    - Acuerdo del ramal ex post del pipeline con CuandoSubo en la 39 (mismos 3 días, 1.750 viajes con ramal de CuandoSubo): 90,7 %; B 99 %, C 98 %, A 74 % (cuando el pipeline dice A, CuandoSubo dice B en 87 casos y C en 55). La etiqueta ex post de A es la menos confiable.
13. **Tránsito por zona y grilla más fina (ex 11.11).** Baja prioridad.
    - La feature de tránsito por el camino dio ~1–2 s (RESULTADOS.md).
    - Variantes no probadas: celdas en un radio alrededor de P o T; celdas menores a 500 m o ventanas menores a 2 min (techo con la grilla actual ≤ 2 %).

### Pendientes cerrados

Movidos a `RESULTADOS.md`, «Pendientes cerrados» (consistencia temporal, objetivos en paradas reales, cabecera y coche detenido, paso de coches sin la parada, vara de producto de v4, feriado, historial de 20 min).
