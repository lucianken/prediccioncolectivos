# Inferencia del modelo por tramos en el navegador (contrato 1.2)

Spec para implementar en JS (`onnxruntime-web`) la predicción de ETA del modelo por tramos (`models/path_eta.py`, ARQUITECTURA §6.2).
Especificación ejecutable: `prediccion/inference/path_reference.py` (`predict_from_raw`), probada contra el pipeline de eval en `prediccion/tests/test_path_export.py`. Ante duda, manda el código de referencia.

Reemplaza a `INFERENCE_GUIDE.md` (A3 viejo, ramal conocido; en `docs_old/`).

## 1. Archivos exportados

`python -m prediccion.scripts.export_path_onnx --ckpt <best.pt> --out <dir>` (repetible con cualquier checkpoint; verifica ONNX vs PyTorch y que la geometría de `line_shapes` coincida con las celdas del checkpoint). Versión activa: `data/ml/export/path_v2b_s0/`; exportada sin activar: `path_v2b_pinv_s0/` (pérdida pinball q 0,5→0,2 bajo 1 km). El manifest nuevo declara `contract_version` 1.2.

| archivo | contenido | tamaño (v2b_s0) |
|---|---|---|
| `path_eta.onnx` | red, opset 17, `B` (candidatos) y `N` (tramos) dinámicos | 2,64 MB (2,44 MB gzip) |
| `manifest.json` | `contract_version`, `model_version`, tabla línea→índice, constantes y normalizaciones, E/S del ONNX, tamaño y sha256 de cada archivo | 3 KB |
| `lines/<línea>.json` | por línea: shapes `{id, name, short_name, length_m, n_cells, points [lat,lon,...], cells [lat,lon,...]}` (vectores planos, 6 decimales) | 12 archivos, 23–104 KB; 0,78 MB (0,18 MB gzip) |

Total 3,4 MB (~2,6 MB gzip). El cliente carga `manifest.json` y el ONNX al inicio y `lines/<línea>.json` bajo demanda. El modelo se reemplaza cambiando el directorio; el cliente rechaza un `contract_version` mayor que el que implementa y cachea por `model_version`.

`cells` son los puntos medios (lat, lon) de las celdas de 250 m de cada shape, exactamente los del entrenamiento (la celda `j` cubre `[250j, 250(j+1)]` m; la última es parcial y su punto medio se satura al largo del shape). El cliente no recalcula nada de esto. El mapa de la ciudad (grilla de 500 m con embeddings) está dentro del ONNX.

### Opción elegida: ONNX con tramos de entrada
El grafo recibe los tramos ya armados y devuelve el ETA; el cliente solo arma geometría y 9 números de estado. Se descartó tabular por (tramo, línea, hora, día): el tiempo de un tramo depende de la hora continua (sin/cos) y del largo parcial del primer y último tramo, así que la tabla sería aproximada, pesaría ~4 MB (4.043 celdas × 168 franjas × 4 B) y el ajuste global (MLP con el estado del coche) habría que reimplementarlo en JS. El ONNX completo es exacto, pesa ~2,6 MB comprimido y no requiere reimplementar ninguna red.

## 2. Inventario de entradas

| entrada | entrenamiento | tiempo real (cliente) |
|---|---|---|
| línea → `line_idx` | sufijo del label vía `LABEL_LINE_MAP` | disponible (nunca route_id/trip_id) |
| `shape_id` / recorrido | elegido ex post sobre el viaje completo (`best_shape_for_trip`) | **NO existe**: se prueban todos los shapes de la línea (§4) |
| posición del coche P (`dist_along_m`) | proyección del ping sobre el shape | lat/lon del ping, se proyecta sobre cada candidato |
| punto del usuario T (`dist_remaining_m = d_T − d_P`) | par futuro F del mismo viaje | lat/lon del usuario/parada, se proyecta sobre cada candidato |
| tramos de 250 m, lugar (celda → embedding de grilla) | derivados de (shape, `d_P`, `d_T`) | derivables con `lines/*.json` |
| hora y día | hora local BA del **ping** P (`ts_p`), sin/cos continuo, `dow` 0 = lunes | disponible (timestamp del ping, UTC−3 fijo) |
| `speed_mps` del ping | campo `speed` del API (m/s, promedio del último ciclo de 30 s) | disponible |
| `ts_age_s` | `min(frame_ts − ts_p, 600)` | disponible (hora del snapshot − timestamp del ping) |
| `time_since_start` | `ts_p − inicio del viaje`; NaN si el inicio es desconocido | **NO disponible**: se envía 0 (§5) |
| `start_unknown` | 1 si el viaje no arranca en cabecera | siempre 1 (§5) |
| `dist_along` normalizada, `stopped`, `dist_remaining` normalizada | derivadas | derivadas por candidato |
| `time_since_last_bus`, `last_bus_found` ("coche de adelante") | tiempo desde que el viaje anterior de otro coche pasó por T (tope 3600 s), sobre el shape elegido ex post | **parcial**: solo con historial de otros coches guardado por el cliente (§6); si no, `3600 s` y `found = 0` |
| escala de la suma de tramos (10.ª componente del estado) | `log1p(suma)/8` | la calcula el ONNX |
| historial del propio coche (`traj_flat`) | lo usa el A3 viejo; este modelo no lo usa | obligatorio para conocer el sentido (§4) |
| flota / tránsito / `schedule_dev` | no entran en este modelo | — |

Medido sobre 20.000 filas de eval (v2b, MAE de la red): real 102,4 s; forzando `start_unknown = 1` y `time_since_start = 0` 103,1 s (+0,65); además sin coche de adelante 103,5 s. Las condiciones de producción cuestan < 1 % del error. El 16 % de las filas de eval ya tiene `start_unknown = 1`.

## 3. Cálculo por candidato

Dado un shape candidato con `d_P` (m desde su inicio), `rem = d_T − d_P ≥ 100 m`, línea, hora del ping y estado:

1. **Constantes** (`manifest.constants`): `seg_base_m = 250`, `max_seg = 160`.
2. **Tramos** (`build_segments`, float64): `step = 250 · max(1, ceil(rem / (250 · 158)))` (250 m salvo caminos de más de 39,5 km); `d1 = d_P + rem`; `k0 = floor(d_P / step)`; `k1 = max(k0, ceil(d1 / step) − 1)`; para `k = k0..k1`: `len_k = min((k+1)·step, d1) − max(k·step, d_P)`, `mid_m = (k + 0,5)·step`, celda `c = clamp(floor(mid_m / 250), 0, n_cells − 1)`, `(seg_lat, seg_lon) = cells[c]`. La suma de `len_k` es `rem`.
3. **Estado** (9 floats, orden de `manifest.onnx.state_columns`): `clip(speed/30, 0, 2)`; `1 si speed < 0,5 sino 0`; `clip(ts_age/600, 0, 1,5)`; `clip(tss/3600, 0, 4)` (0 con inicio desconocido); `clip(d_P/50000, 0, 2)`; `log1p(clip(tlb, 0, 3600))/log1p(3600)`; `last_bus_found` (0/1); `log1p(clip(rem, 0, 80000))/log1p(80000)`; `start_unknown` (0/1). `speed` nulo = 0.
4. **Tiempo**: `hour = ((ts_ping − 10800) mod 86400) / 3600`; `h_sin = sin(2π·hour/24)`, `h_cos = cos(2π·hour/24)`; `dow = (floor((ts_ping − 10800)/86400) + 3) mod 7`. Se usa el `ts` del **ping** del coche, no la hora actual.
5. **ONNX** (float32 salvo `line_idx`, `dow` int32): `seg_lat, seg_lon, seg_mid_m, seg_len, seg_mask` `(B, N)` (relleno 0, máscara 0; `N` = máximo de tramos entre candidatos, ≤ 160); `line_idx (B)` de `manifest.lines` (1..12); `dow, h_sin, h_cos (B)`; `state (B, 9)`. Salidas `eta`, `seg_sum`, `adj` `(B)` en segundos. Un solo `run` con todos los candidatos del coche.
6. **ETA del modelo** `= max(eta, 0)`, medido desde el instante del ping. **ETA a anunciar** `= max(0, eta_modelo − (ahora − ts_ping))`.

## 4. Proyección y elección de candidatos de ramal

Proyección de un punto sobre un shape (`Shape.project`): distancia acumulada con ángulo pequeño (`dy = Δlat·111320`, `dx = Δlon·111320·cos(lat media del segmento)`); segmento de menor distancia perpendicular con `t` recortado a [0, 1]; devuelve `(metros desde el inicio, perp)`. Recorrer todos los segmentos (≤ ~720 puntos por shape) alcanza.

### Reglas de candidatos (contrato 1.2)

Constantes del cliente (no están en el manifest; mismos valores en `path_reference.py` y `core.js`): `MIN_NET_FORWARD_M = 40`, `POINT_MAX_PERP_M = 40`, `POINT_PARALLEL_MARGIN_M = 15`, `STOP_FALLBACK_PERP_M = 25`. `user_max_perp_m` (100) solo acota las paradas asociadas por nombre.

**Shapes que sirven el punto del usuario** (`user_shapes`):

- Parada elegida (`user_kind = "parada"`): los shapes cuyo nombre figura en `stop_recorridos` (recorridos que la lista como parada, con perp ≤ `user_max_perp_m`). Sin coincidencia por nombre (o sin `stop_recorridos`): los shapes a ≤ `STOP_FALLBACK_PERP_M`. El resto: `no_sirve_parada`.
- Ubicación GPS o toque en el mapa (`user_kind = "punto"`): los shapes a ≤ `POINT_MAX_PERP_M`; entre ellos solo los de perp ≤ (perp mínima + `POINT_PARALLEL_MARGIN_M`); el resto: `paralela`. Más lejos: `usuario_fuera_del_recorrido`.

**Shapes compatibles de un coche**: shape de la línea con `perp_P ≤ 150 m` (`max_perp_m`) y sentido conocido y hacia adelante. Sentido (`_sense`): pings propios de los últimos 15 min (`history_window_s`) anteriores al ping actual, más el ping actual, proyectados sobre el shape. Se exige: ≥ 2 pings a ≤ 150 m (si no, `sin_sentido`); ≥ 80 % de los pings a ≤ 150 m y `forward_fraction ≥ 0,6` (pasos de entre 30 m y 5 km, metros avanzados / totales); avance neto (último menos primero de los pings a ≤ 150 m) ≥ `MIN_NET_FORWARD_M`. Con avance neto ≤ −`MIN_NET_FORWARD_M`, `forward_fraction` bajo o pings lejos del shape: `sentido_incoherente`; con avance neto entre −40 m y 40 m: `sin_sentido`. Sin historial o coche quieto no hay sentido confirmado: se aplica el ETA provisional (abajo).

**Orden en cada shape compatible**: si no sirve el punto del usuario, no pasa (motivo de `user_shapes`). Si sirve: `rem = d_T − d_P`; `rem < 0` no pasa (`ya_paso`); `0 ≤ rem < 100` pasa como "llegando"; `rem ≥ 100` pasa como candidato con ETA.

**Estado y grupo del coche**:

- Sin shapes compatibles y sin shapes de sentido desconocido: `sin_sentido` si algún shape queda a ≤ 150 m (todos `sentido_incoherente`); si no, `sin_candidatos`. Sin ETA.
- **ETA provisional** (sin ningún shape compatible): los shapes a ≤ 150 m del coche cuyo motivo es `sin_sentido` (ambos sentidos de la calle) se evalúan igual que los compatibles (servicio del punto, `rem`, ETA) y se informan en `provisional` (`{shape_id, name, short_name, passes, reason}`). Si el usuario queda adelante (`rem ≥ 0`) en alguno: `status = provisional`, `group = provisional`, `depends_on = []`, ETA = **mínimo** entre los que pasan (`0` y "llegando" si alguno tiene `rem < 100`), `en_cabecera` con la misma regla. Si en ninguno queda adelante: `pasado` (alguno con `rem < 0`) o `sin_candidatos`, sin ETA. Los `sentido_incoherente` no participan. Con ≥ 1 shape compatible el coche sigue la clasificación normal y `provisional` queda vacío.
- Ningún compatible pasa: `pasado` si alguno tenía `rem < 0`; si no, `sin_candidatos`. Sin ETA.
- Todos los compatibles pasan: grupo `seguro`. Solo algunos: grupo `puede_venir`, con `depends_on` = shapes compatibles que pasan (el ramal del que depende el arribo).
- Con grupo, el ETA anunciado es el **mínimo** de los ETA de los shapes que pasan (el error grave es que el colectivo llegue antes de lo anunciado); `llegando` (ETA 0) si algún shape que pasa tiene `0 ≤ rem < 100`. Los shapes con bucles pueden proyectar al pasaje equivocado; el historial lo acota pero es una limitación conocida.

Salida de `predict_from_raw`: `status` (`ok | llegando | provisional | pasado | sin_sentido | sin_candidatos | linea_fuera_del_modelo`), `eta_s`, `shape_id`, `candidates`, `en_cabecera`, `group` (`seguro | puede_venir | provisional | null`), `depends_on`, `compatible` y `provisional` (`{shape_id, passes, reason}`) y `discarded` (`{shape_id, reason}`). Motivos: `coche_fuera_del_recorrido`, `sin_sentido`, `sentido_incoherente`, `no_sirve_parada`, `paralela`, `usuario_fuera_del_recorrido`, `ya_paso`.

## 5. `start_unknown` en producción

El cliente rara vez sabe dónde arrancó el viaje. Se envía siempre `start_unknown = 1` y `time_since_start = 0`: es la rama que el modelo entrenó con el 16 % de las filas, cuesta +0,65 s de MAE (§2) y evita inventar un `time_since_start` falso. Aunque el cliente haya visto salir al coche, no se usa: un solo camino de código.

## 6. Coche de adelante (opcional)

Si el cliente guarda pings recientes de otros coches de la línea `[(ts, lat, lon)]`, para cada candidato (`last_bus`): proyectarlos sobre el shape; descartar los que no cumplen perp ≤ 150 m y avance ≥ 0,6; el instante de paso por T es la interpolación lineal entre dos pings consecutivos que encierran `d_T` (si no, el ping a ≤ 250 m de T), solo si es anterior a `ts_ping`; tomar el paso más reciente. `tlb = min(ts_ping − paso, 3600)`, `found = 1`. Sin ese historial: `tlb = 3600`, `found = 0` (cuesta ~0,35 s de MAE; no es imprescindible).

## 7. Casos límite

- **Línea fuera del modelo** (`manifest.lines`): no predecir (el índice 0 "desconocida" no se usa en producción). Hoy: 26, 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168.
- **Coche ya pasó** (`rem < 0` en todos los compatibles que sirven el punto): "ya pasó", sin ETA.
- **`rem < 100 m`**: "llegando"; el modelo no se entrenó por debajo de 100 m.
- **Coche quieto en cabecera** (`speed < 0,5` y `d_P < 300 m`, con sentido conocido: avanzó ≥ 40 m en la ventana; `en_cabecera = true`): el modelo no predice cuándo sale el coche (ARQUITECTURA §6.2.5.B). Mostrar "en cabecera" y el ETA como cota inferior. Sin sentido confirmado: ETA provisional con la marca "en cabecera".
- **Ping viejo**: se descuenta la antigüedad (§3.6). Con ping de más de ~10 min, no predecir.
- **Camino > 39,5 km**: tramos de múltiplo de 250 m (§3.2); sigue válido.
- **Coche fuera del recorrido** (`perp > 150 m` en todos los shapes: depósito, desvío): no predecir.
- **Hora**: siempre la del ping en UTC−3 (Buenos Aires, sin DST).

## 8. Paridad (versión inicial)

ONNX vs PyTorch sobre 1.000 filas seen + 1.000 heldout de `data/ml/v2b/eval`: diferencia máxima 0,002 s (tolerancia 0,5 s). Referencia numpy desde lat/lon crudos (P y T reconstruidos sobre el shape, hora desde `ts_p`) vs eval: < 0,5 s en las filas reconstruibles. Para validar el JS: reproducir los casos de `test_path_export.py` y comparar contra `predict_from_raw`.
