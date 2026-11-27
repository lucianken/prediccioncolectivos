# Inferencia del modelo por tramos en el navegador (contrato 2.3)

Spec para implementar en JS (`onnxruntime-web`) la predicción de ETA del modelo por tramos (`models/path_eta.py`, ARQUITECTURA §6.2).
Especificación ejecutable: `prediccion/inference/path_reference.py` (`predict_from_raw`), probada contra el pipeline de eval en `prediccion/tests/test_path_export.py`. Ante duda, manda el código de referencia.

**La asignación de un ping a recorrido y sentido (§4) no se define en la app ni en la referencia: es la de `prediccion/v2/geo_assign.py`, la misma que usa el pipeline de entrenamiento** (ARQUITECTURA.md §4.5). La referencia importa ese módulo; el cliente reproduce sus reglas con los valores de `manifest.assignment`. La app no tiene reglas de asignación propias.

Reemplaza a `INFERENCE_GUIDE.md` (A3 viejo, ramal conocido; en `docs_old/`).

## 1. Archivos exportados

`python -m prediccion.scripts.export_path_onnx --ckpt <best.pt> --out <dir>` (repetible con cualquier checkpoint; verifica ONNX vs PyTorch y que la geometría de `line_shapes` coincida con las celdas del checkpoint). Versión activa: `data/ml/export/path_v3_l1_s1/` (pérdida L1, paradas por tramo, 48 líneas; checkpoint `data/ml/v3_sub/runs/path_lr2e-3_s1/path_eta_best.pt`); anteriores: `path_v2c_l1_s1/`, `path_v2b_s0/`, `path_v2b_pinv_s0/`. El manifest declara `contract_version` 2.3 (1.x usaba tolerancia de 150 m y constantes propias del cliente).

`--reshape` exporta un checkpoint con los `line_shapes` actuales aunque difieran de los del entrenamiento (ARQUITECTURA §10.5): reconstruye `seg_lat`, `seg_lon`, `shape_off` y `stop_key` (el shape solo indexa esas tablas; el modelo no tiene parámetros por shape), `path_eta.onnx` queda idéntico y el contrato no cambia. El manifest agrega el campo opcional `reshaped_from` (`checkpoint`, `shapes_dir`, `date`, `shapes_repo_commit`, `weights` = «sin reentrenar», `shapes_not_in_shapes_dir`, `shapes_added`, `lines_without_shapes`). Es informativo: el cliente lo ignora y no es motivo de cambio de versión del contrato.

Versiones: el mayor cambia si cambia el significado de una salida o de un campo existente; el menor, con agregados compatibles. 2.1 agrega el sentido por geometría (`assignment.heading_tol_deg`, §4), el campo de salida `sense` y el ajuste del punto del usuario al recorrido (§4); los grupos (`seguro`, `puede_venir`, `provisional`) y sus códigos no cambian de significado. Un cliente 2.0 sobre un manifest 2.1 sigue siendo correcto pero conservador (deja provisionales coches cuyo sentido ya da la geometría). El cliente 2.1 exige `heading_tol_deg`.

2.3 cambia la regla de sentido por historial (`direction_from_history`, §4): decide sobre la racha final de pings consecutivos a ≤ `tol_m` del shape (`assignment.direction_rule = "trailing_run"`) y elimina `assignment.min_near_frac`. El ONNX y `lines/` no cambian. Un cliente que implemente la regla anterior (≥ `min_near_frac` de la ventana a ≤ `tol_m`) sobre un manifest 2.3 no la reproduce: el cliente rechaza un manifest sin `direction_rule = "trailing_run"`. Las referencias congeladas de `prediccion/replay/pinned/` están a 2.3 desde 2026-11-16.

2.2 agrega las **paradas por tramo** (§3.3): `manifest.stops_feature`, `manifest.stops` (`decimals`, `next_cap_m`, `n_stops`, `rule`), `stops_m` en cada shape de `lines/<línea>.json` y las entradas `seg_stop_n` y `seg_stop_next` del ONNX. Un manifest con `stops_feature = true` declara 2.2 o mayor; un manifest sin `stops_feature` (modelos v2) sigue siendo válido y no usa paradas. Un cliente 2.1 sobre un modelo 2.2 falla (el ONNX pide entradas que no arma).

| archivo | contenido | tamaño (v3_l1_s1) |
|---|---|---|
| `path_eta.onnx` | red, opset 17, `B` (candidatos) y `N` (tramos) dinámicos | 2,64 MB (2,44 MB gzip) |
| `manifest.json` | `contract_version`, `model_version`, tabla línea→índice, constantes y normalizaciones, `assignment` (parámetros de la asignación, §4), E/S del ONNX, tamaño y sha256 de cada archivo | 9 KB |
| `lines/<línea>.json` | por línea: shapes `{id, name, short_name, length_m, n_cells, points [lat,lon,...], cells [lat,lon,...], stops_m [m,...]}` (vectores planos, 6 decimales; `stops_m` solo con `stops_feature`) | 48 archivos (v3), 10–255 KB |

Total v3 7,6 MB (ONNX 2,64 MB y `lines/` ~4,9 MB). El cliente carga `manifest.json` y el ONNX al inicio y `lines/<línea>.json` bajo demanda. El modelo se reemplaza cambiando el directorio; el cliente rechaza un `contract_version` que no sea 2.x y cachea por `model_version`.

`cells` son los puntos medios (lat, lon) de las celdas de 250 m de cada shape, exactamente los del entrenamiento (la celda `j` cubre `[250j, 250(j+1)]` m; la última es parcial y su punto medio se satura al largo del shape). `stops_m` son las paradas del recorrido (ramal) proyectadas sobre el shape, en metros desde su inicio, ordenadas y redondeadas a `stops.decimals` (la fuente es `ramales[].stops` de `proyectoconsola/data/line_shapes/{N}.json`, la misma entrada de ramal que da los puntos; `prediccion/models/stops.py`). Son las del entrenamiento (el export verifica que coincidan con las del checkpoint). El cliente no recalcula nada de esto. El mapa de la ciudad (grilla de 500 m con embeddings) está dentro del ONNX.

### Opción elegida: ONNX con tramos de entrada
El grafo recibe los tramos ya armados y devuelve el ETA; el cliente solo arma geometría y 9 números de estado. Se descartó tabular por (tramo, línea, hora, día): el tiempo de un tramo depende de la hora continua (sin/cos) y del largo parcial del primer y último tramo, así que la tabla sería aproximada, pesaría ~4 MB (4.043 celdas × 168 franjas × 4 B) y el ajuste global (MLP con el estado del coche) habría que reimplementarlo en JS. El ONNX completo es exacto, pesa ~2,6 MB comprimido y no requiere reimplementar ninguna red.

## 2. Inventario de entradas

| entrada | entrenamiento | tiempo real (cliente) |
|---|---|---|
| línea → `line_idx` | sufijo del label vía `LABEL_LINE_MAP` | disponible (nunca route_id/trip_id) |
| `shape_id` / recorrido | etiqueta elegida ex post sobre el viaje completo (`best_shape_for_trip`), solo entre shapes compatibles (ARQUITECTURA §4.5); cada fila es "ETA si va por este recorrido" | **NO existe**: se calcula el ETA por cada shape compatible (§4) |
| posición del coche P (`dist_along_m`) | proyección del ping sobre el shape; solo pings compatibles (`geo_assign`) generan filas | lat/lon del ping, se proyecta sobre cada candidato |
| punto del usuario T (`dist_remaining_m = d_T − d_P`) | par futuro F del mismo viaje | lat/lon del usuario/parada, se proyecta sobre cada candidato |
| tramos de 250 m, lugar (celda → embedding de grilla) | derivados de (shape, `d_P`, `d_T`) | derivables con `lines/*.json` |
| paradas por tramo (`seg_stop_n`, `seg_stop_next`) | de `stops_m` del shape y del tramo recortado a P→T | derivables con `stops_m` (§3.3) |
| hora y día | hora local BA del **ping** P (`ts_p`), sin/cos continuo, `dow` 0 = lunes | disponible (timestamp del ping, UTC−3 fijo) |
| `speed_mps` del ping | campo `speed` del API (m/s, promedio del último ciclo de 30 s) | disponible |
| `ts_age_s` | `min(frame_ts − ts_p, 600)` | disponible (hora del snapshot − timestamp del ping) |
| `time_since_start` | `ts_p − inicio del viaje`; NaN si el inicio es desconocido | **NO disponible**: se envía 0 (§5) |
| `start_unknown` | 1 si el viaje no arranca en cabecera | siempre 1 (§5) |
| `dist_along` normalizada, `stopped`, `dist_remaining` normalizada | derivadas | derivadas por candidato |
| `time_since_last_bus`, `last_bus_found` ("coche de adelante") | tiempo desde que el viaje anterior de otro coche pasó por T (tope 3600 s), sobre el shape elegido ex post | **parcial**: solo con historial de otros coches guardado por el cliente (§6); si no, `3600 s` y `found = 0` |
| escala de la suma de tramos (10.ª componente del estado) | `log1p(suma)/8` | la calcula el ONNX |
| historial del propio coche (`traj_flat`) | lo usa el A3 viejo; este modelo no lo usa | necesario para el sentido solo donde la geometría no lo da (§4) |
| flota / tránsito / `schedule_dev` | no entran en este modelo | — |

Medido sobre 20.000 filas de eval (v2b, MAE de la red): real 102,4 s; forzando `start_unknown = 1` y `time_since_start = 0` 103,1 s (+0,65); además sin coche de adelante 103,5 s. Las condiciones de producción cuestan < 1 % del error. El 16 % de las filas de eval ya tiene `start_unknown = 1`.

## 3. Cálculo por candidato

Dado un shape candidato con `d_P` (m desde su inicio), `rem = d_T − d_P ≥ 100 m`, línea, hora del ping y estado:

1. **Constantes** (`manifest.constants`): `seg_base_m = 250`, `max_seg = 160`.
2. **Tramos** (`build_segments`, float64): `step = 250 · max(1, ceil(rem / (250 · 158)))` (250 m salvo caminos de más de 39,5 km); `d1 = d_P + rem`; `k0 = floor(d_P / step)`; `k1 = max(k0, ceil(d1 / step) − 1)`; para `k = k0..k1`: `len_k = min((k+1)·step, d1) − max(k·step, d_P)`, `mid_m = (k + 0,5)·step`, celda `c = clamp(floor(mid_m / 250), 0, n_cells − 1)`, `(seg_lat, seg_lon) = cells[c]`. La suma de `len_k` es `rem`.
3. **Estado** (9 floats, orden de `manifest.onnx.state_columns`): `clip(speed/30, 0, 2)`; `1 si speed < 0,5 sino 0`; `clip(ts_age/600, 0, 1,5)`; `clip(tss/3600, 0, 4)` (0 con inicio desconocido); `clip(d_P/50000, 0, 2)`; `log1p(clip(tlb, 0, 3600))/log1p(3600)`; `last_bus_found` (0/1); `log1p(clip(rem, 0, 80000))/log1p(80000)`; `start_unknown` (0/1). `speed` nulo = 0.
4. **Tiempo**: `hour = ((ts_ping − 10800) mod 86400) / 3600`; `h_sin = sin(2π·hour/24)`, `h_cos = cos(2π·hour/24)`; `dow = (floor((ts_ping − 10800)/86400) + 3) mod 7`. Se usa el `ts` del **ping** del coche, no la hora actual.
5. **ONNX** (float32 salvo `line_idx`, `dow` int32): `seg_lat, seg_lon, seg_mid_m, seg_len, seg_mask` `(B, N)` (relleno 0, máscara 0; `N` = máximo de tramos entre candidatos, ≤ 160); con `stops_feature`, también `seg_stop_n, seg_stop_next` `(B, N)` (relleno 0, §3.3); `line_idx (B)` de `manifest.lines` (índice 1..n de la tabla); `dow, h_sin, h_cos (B)`; `state (B, 9)`. Salidas `eta`, `seg_sum`, `adj` `(B)` en segundos. Un solo `run` con todos los candidatos del coche.
6. **ETA del modelo** `= max(eta, 0)`, medido desde el instante del ping. **ETA a anunciar** `= max(0, eta_modelo − (ahora − ts_ping) − CABA_TS_OFFSET_S)`, con `CABA_TS_OFFSET_S = 60` s: corrimiento estimado del sello `timestamp` de la API CABA respecto de la hora real del GPS (la hora real del ping es `ts_ping − 60`). Base al 2026-11-14: `ts_CABA − ts_CuandoSubo` del mismo punto GPS, p50 28 s / p90 30 s, llevado a 60 s por una observación en campo del 2026-11-14 10:56 (línea 39, interno 93, parada Plaza de los Colegiales; una sola muestra); falta validarlo con más observaciones en parada (`analisis_latencia_fuentes/INFORME.md`). Sólo afecta el ETA anunciado: `ts_age` (§2) y la hora del día (paso 4) usan horas de CABA, igual que en entrenamiento. `predict_from_raw` (`path_reference.py`) no aplica el corrimiento; en `proyectoconsola` es `CABA_TS_OFFSET_S` de `public/prediccion/core.js`.

### 3.3 Paradas por tramo (`manifest.stops_feature`)

Por cada tramo del paso 2, con `lo = max(k·step, d_P)` y `hi = min((k+1)·step, d1)` (los mismos que dan `len_k = hi − lo`) y `stops_m` del shape (ordenado):

- `seg_stop_n` = cantidad de paradas con `lo ≤ parada < hi` (búsqueda `lower_bound` izquierda: la parada exactamente en `hi` pertenece al tramo siguiente; la que está en `lo`, a este).
- `seg_stop_next` = `min(p − lo, stops.next_cap_m)` con `p` = primera parada `≥ lo`; sin parada `≥ lo`: `next_cap_m` (1000 m). Va en metros: el ONNX la divide por `next_cap_m`.

Un shape sin paradas (`stops_m = []`) da `seg_stop_n = 0` y `seg_stop_next = next_cap_m` en todos los tramos (así se entrenó). Referencia: `stop_features_np` (`prediccion/models/stops.py`), usada por `build_segments`. El relleno de tramos inexistentes es 0 en ambas entradas. Un cliente toma `next_cap_m` del manifest.

## 4. Proyección y elección de candidatos de ramal

Proyección de un punto sobre un shape (`Shape.project`): distancia acumulada con ángulo pequeño (`dy = Δlat·111320`, `dx = Δlon·111320·cos(lat media del segmento)`); segmento de menor distancia perpendicular con `t` recortado a [0, 1]; devuelve `(metros desde el inicio, perp)`; con empate (perp a ≤ 1e-6 m de la mínima, típico de un recorrido que repite la misma calle) gana el primer segmento: el ruido de coma flotante no puede decidir el tramo (`PROJECT_TIE_M` de `path_reference.py`). Recorrer todos los segmentos (≤ ~720 puntos por shape) alcanza.

### Asignación de ping a recorrido y sentido (`geo_assign.py`)

Parámetros en `manifest.assignment` (el cliente las lee del manifest, sin valores propios, y rechaza un manifest sin alguno de ellos o con contract_version distinta de 2.x; la referencia verifica que coincidan con el módulo): `tol_m` (T), `margin_m` (M), `history_window_s`, `direction_rule` (cadena, `trailing_run`), `min_near_pings`, `min_forward_frac`, `min_net_forward_m`, `step_moving_m`, `step_jump_m`, `stop_max_perp_m`, `stop_fallback_perp_m`, `heading_tol_deg`.

- **Shapes compatibles con una posición** (`compatible_shapes(lat, lon, shapes)`): perp ≤ `tol_m` y perp ≤ (mínima perp entre TODOS los shapes de la línea) + `margin_m`. La tolerancia admite el ruido de GPS; el margen descarta la calle paralela cuando otro shape explica mucho mejor la posición. Ida y vuelta por la misma calle son ambas compatibles. Se aplica igual al ping del coche y al punto del usuario (GPS o toque en el mapa).
- **Rumbo local de un shape** (`shape_heading(shape, lat, lon, lim)`): rumbo (grados, 0 = norte, horario; `atan2(dx, dy)` con la misma métrica de ángulo pequeño) del segmento no degenerado de menor distancia perpendicular al punto (el primero si empatan). El shape es **de doble sentido en ese punto** si otro de sus segmentos a ≤ `lim` difiere en más de 180° − `heading_tol_deg` (bucle o ida y vuelta dentro del mismo recorrido).
- **Sentido por geometría** (`direction_from_geometry(lat, lon, shapes)`): con `lim` = límite de compatibilidad de la posición (`min(tol_m, mínima perp + margin_m)`), el sentido es conocido sin historial si hay ≥ 1 shape compatible, ninguno es de doble sentido en ese punto y los rumbos de todos los compatibles difieren de a pares en ≤ `heading_tol_deg` (45°). Entonces todos los compatibles van hacia adelante. Si hay rumbos opuestos o cruzados entre compatibles (ida y vuelta por la misma calle, doble mano compartida, esquinas donde los recorridos doblan distinto), el sentido sale del historial.
- **Sentido por historial** (`direction_from_history(pings, shape)`, regla `trailing_run`): pings propios de los últimos `history_window_s` anteriores al ping actual, más el ping actual, proyectados sobre el shape. Se toma la **racha final**: los pings consecutivos, terminando en el actual, a ≤ `tol_m`; se usan todos. Racha con < `min_near_pings` pings: `sin_sentido`. Sobre la racha: `forward_fraction ≥ min_forward_frac` (pasos de entre `step_moving_m` y `step_jump_m`, metros avanzados / totales; si no, `sentido_incoherente`) y avance neto (último menos primero de la racha): ≤ −`min_net_forward_m` → `sentido_incoherente`; entre −`min_net_forward_m` y +`min_net_forward_m` → `sin_sentido`; ≥ +`min_net_forward_m` → adelante. Los pings anteriores a la racha (a más de `tol_m`) no cuentan. La ventana se mide respecto del ping actual (no de la hora de la consulta).
- **Combinación por shape compatible:** historial hacia adelante → adelante. `sin_sentido` (historial insuficiente o coche quieto) con sentido por geometría → adelante. `sin_sentido` sin sentido por geometría → sentido desconocido (ETA provisional, abajo). `sentido_incoherente` → descartado aunque la geometría dé el sentido (el historial contradice ese shape: otro ramal, desvío o marcha atrás).
- **Ajuste del punto del usuario al recorrido** (`snap_to_route(bundle, línea, lat, lon)`, GPS o toque en el mapa): el punto más cercano entre los shapes de la línea (proyección y `latlon_at`); `on_route` = perp ≤ `tol_m`. Con `on_route` el punto ajustado es el punto del usuario; sin `on_route` no se usa (el toque no se acepta; con GPS se avisa que la ubicación no está sobre el recorrido y se sugiere elegir una parada). Las paradas no se ajustan.
- **Paradas** (posición exacta, no es un ping): se asocian por nombre de recorrido a ≤ `stop_max_perp_m`; sin coincidencia por nombre, al shape a ≤ `stop_fallback_perp_m`.

### Reglas de candidatos

**Shapes que sirven el punto del usuario** (`user_shapes`):

- Parada elegida (`user_kind = "parada"`): los shapes cuyo nombre figura en `stop_recorridos` (con perp ≤ `stop_max_perp_m`). Sin coincidencia por nombre (o sin `stop_recorridos`): los shapes a ≤ `stop_fallback_perp_m`. El resto: `no_sirve_parada`.
- Ubicación GPS o toque en el mapa (`user_kind = "punto"`): los shapes compatibles con la posición (regla de arriba); el resto: `paralela` o, si perp > `tol_m`, `usuario_fuera_del_recorrido`.

**Shapes compatibles de un coche**: shapes compatibles con la posición del ping (`compatible_shapes`) con sentido conocido y hacia adelante (por geometría o por historial, combinación de arriba). Los shapes no compatibles con la posición: `coche_fuera_del_recorrido`.

**Orden en cada shape compatible**: si no sirve el punto del usuario, no pasa (motivo de `user_shapes`). Si sirve: `rem = d_T − d_P`; `rem < 0` no pasa (`ya_paso`); `0 ≤ rem < 100` pasa como "llegando"; `rem ≥ 100` pasa como candidato con ETA.

**Estado y grupo del coche**:

- Sin shapes compatibles y sin shapes de sentido desconocido: `sin_sentido` si algún shape es compatible con la posición (todos `sentido_incoherente`); si no, `sin_candidatos`. Sin ETA.
- **ETA provisional** (sin ningún shape compatible: el sentido no sale ni de la geometría ni del historial): los shapes compatibles con la posición del coche cuyo motivo es `sin_sentido` (ambos sentidos de la calle) se evalúan igual que los compatibles (servicio del punto, `rem`, ETA) y se informan en `provisional` (`{shape_id, name, short_name, passes, reason}`). Si el usuario queda adelante (`rem ≥ 0`) en alguno: `status = provisional`, `group = provisional`, `depends_on = []`, ETA = **mínimo** entre los que pasan (`0` y "llegando" si alguno tiene `rem < 100`), `en_cabecera` con la misma regla. Si en ninguno queda adelante: `pasado` (alguno con `rem < 0`) o `sin_candidatos`, sin ETA. Los `sentido_incoherente` no participan. Con ≥ 1 shape compatible el coche sigue la clasificación normal y `provisional` queda vacío.
- Ningún compatible pasa: `pasado` si alguno tenía `rem < 0`; si no, `sin_candidatos`. Sin ETA.
- Grupos (dos incertidumbres separadas: el **sentido**, casi siempre conocido por geometría, y el **ramal/destino**, desconocido en tronco compartido):
  - `seguro` ("viene"): sentido conocido y **todos** los shapes compatibles en ese sentido pasan por el punto. El ramal puede ser desconocido: si todos pasan, el coche viene igual.
  - `puede_venir`: sentido conocido y solo **algunos** shapes compatibles pasan; `depends_on` = shapes compatibles que pasan (el ramal del que depende el arribo).
  - `provisional` ("sentido sin confirmar"): solo cuando el sentido no sale ni de la geometría ni del historial (regla de arriba).
- `sense`: `geometria` si `direction_from_geometry` es verdadero en la posición del coche, `historial` si no (con grupo `seguro` o `puede_venir`), `null` en el resto.
- Con grupo, el ETA anunciado es el **mínimo** de los ETA de los shapes que pasan (el error grave es que el colectivo llegue antes de lo anunciado); `llegando` (ETA 0) si algún shape que pasa tiene `0 ≤ rem < 100`. Los shapes con bucles pueden proyectar al pasaje equivocado; el historial lo acota pero es una limitación conocida.

Salida de `predict_from_raw`: `status` (`ok | llegando | provisional | pasado | sin_sentido | sin_candidatos | linea_fuera_del_modelo`), `eta_s`, `shape_id`, `candidates`, `en_cabecera`, `group` (`seguro | puede_venir | provisional | null`), `depends_on`, `sense` (`geometria | historial | null`), `compatible` y `provisional` (`{shape_id, passes, reason}`) y `discarded` (`{shape_id, reason}`). Motivos: `coche_fuera_del_recorrido`, `sin_sentido`, `sentido_incoherente`, `no_sirve_parada`, `paralela`, `usuario_fuera_del_recorrido`, `ya_paso`.

## 5. `start_unknown` en producción

El cliente rara vez sabe dónde arrancó el viaje. Se envía siempre `start_unknown = 1` y `time_since_start = 0`: es la rama que el modelo entrenó con el 16 % de las filas, cuesta +0,65 s de MAE (§2) y evita inventar un `time_since_start` falso. Aunque el cliente haya visto salir al coche, no se usa: un solo camino de código.

## 6. Coche de adelante (opcional)

Si el cliente guarda pings recientes de otros coches de la línea `[(ts, lat, lon)]`, para cada candidato (`last_bus`): proyectarlos sobre el shape; descartar los que no cumplen perp ≤ `tol_m` y `forward_fraction ≥ min_forward_frac`; el instante de paso por T es la interpolación lineal entre dos pings consecutivos que encierran `d_T` (si no, el ping a ≤ 250 m de T), solo si es anterior a `ts_ping`; tomar el paso más reciente. `tlb = min(ts_ping − paso, 3600)`, `found = 1`. Sin ese historial: `tlb = 3600`, `found = 0` (cuesta ~0,35 s de MAE; no es imprescindible).

## 7. Casos límite

- **Línea fuera del modelo** (`manifest.lines`): no predecir (el índice 0 "desconocida" no se usa en producción). El modelo v3 trae 48 líneas; producción habilita 46 (ARQUITECTURA §6: 61 y 88 quedan fuera). La lista habilitada es config de la app, no del contrato.
- **Coche ya pasó** (`rem < 0` en todos los compatibles que sirven el punto): "ya pasó", sin ETA.
- **`rem < 100 m`**: "llegando"; el modelo no se entrenó por debajo de 100 m.
- **Coche quieto en cabecera** (`speed < 0,5` y `d_P < 300 m`, con sentido conocido por geometría o historial; `en_cabecera = true`): el modelo no predice cuándo sale el coche (ARQUITECTURA §6.2.5.B). Mostrar "en cabecera" y el ETA como cota inferior. Sin sentido confirmado: ETA provisional con la marca "en cabecera".
- **Ping viejo**: se descuenta la antigüedad (§3.6). Con ping de más de ~10 min, no predecir.
- **Camino > 39,5 km**: tramos de múltiplo de 250 m (§3.2); sigue válido.
- **Coche fuera del recorrido** (ningún shape compatible con su posición: depósito, desvío, calle paralela): no predecir.
- **Hora**: siempre la del ping en UTC−3 (Buenos Aires, sin DST).

## 8. Paridad (versión inicial)

ONNX vs PyTorch sobre 1.000 filas seen + 1.000 heldout de `data/ml/v2b/eval`: diferencia máxima 0,002 s (tolerancia 0,5 s). Referencia numpy desde lat/lon crudos (P y T reconstruidos sobre el shape, hora desde `ts_p`) vs eval: < 0,5 s en las filas reconstruibles. Para validar el JS: reproducir los casos de `test_path_export.py` y comparar contra `predict_from_raw`. El fixture de paridad (`gen_path_parity_fixture.py`) incluye el sentido por geometría sin historial (calle de un solo shape → `seguro`; tronco de un solo sentido con parada de todos los ramales → `seguro`; parada después de la bifurcación → `puede_venir`; ida y vuelta por la misma calle → `provisional`; línea 168 en Gascón y Corrientes → `seguro`) y casos de `snap_to_route` (`snaps`).
