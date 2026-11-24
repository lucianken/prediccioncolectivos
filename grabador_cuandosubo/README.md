# Grabador de CuandoSubo: guía de implementación

Grabador **paralelo** al de la API CABA, que guarda lo que publica **CuandoSubo** (OneBusAway de Nación/SUBE): posiciones y predicciones.

**Para qué:** tener una **métrica alternativa** contra la cual comparar la API CABA y los modelos propios.
- **Cobertura:** qué coches ve cada fuente.
- **Latencia:** cuánto atrasa cada una.
- **Predicción:** las ETA de CuandoSubo contra la llegada real (medida con la API CABA) y contra el modelo propio.

Esta carpeta tiene la especificación (este README), la documentación de la API (`docs/`), **código, datos y fixtures de referencia** de una implementación anterior que funcionó tres semanas en el NUC (`referencia/`) y, desde 2026-11-13, **la implementación en Python** (ver §10 para correrla y deployarla).

---

## 0. Regla de oro: no mezclar datasets

**Este grabador escribe en su propia carpeta: `/mnt/buffer/grabaciones_cuandosubo/`, nunca en `/mnt/buffer/grabaciones/`.**

Ya pasó una vez: un grabador de CuandoSubo escribió con el mismo formato en la misma carpeta que el de la API CABA, y tres semanas de archivos se tuvieron que **borrar** porque ensuciaban el dataset del ML. Hacé lo mismo con:
- el archivo de estado (`state.json`) y el de salud (`health`): en su carpeta, con nombres propios;
- el nombre del contenedor, del proyecto de compose y de la carpeta en el NUC (`~/grabador-cuandosubo`);
- el **share SMB:** se lee desde Windows como `Z:\grabaciones_cuandosubo`, al lado de `Z:\grabaciones`.

Los dos grabadores corren **a la vez** y son independientes: si uno se cae, el otro sigue.

---

## 1. Contenido de esta carpeta

| Ruta | Qué es |
|---|---|
| `README.md` | Esta guía. |
| `docs/CUANDOSUBO_API.md` | **Leer primero.** Endpoints, campos y su confiabilidad, WAF (límites), identidad, qué líneas faltan y por qué, artefactos del servidor. |
| `docs/IDENTIFICACION.md` | Estudio completo con mediciones, invariantes id → label, cobertura, frescura, investigación del servidor y de las líneas faltantes (§10). Menciona rutas de un proyecto archivado; las reglas valen igual. |
| `referencia/codigo/grabador.js` | Grabador de referencia (Node): ciclo, tiers A y B, snapshot → keyframe/delta/gap, estado, salud. **Mismo formato NDJSON que el grabador CABA.** |
| `referencia/codigo/oba/limiter.js` | Cola con prioridad: un request por vez, separación mínima, `pause(ms)` para el WAF. |
| `referencia/codigo/oba/client.js` | Cliente OBA: caché por recurso, requests concurrentes iguales comparten la llamada, devuelve datos viejos ante error (stale-on-error), detección de WAF (`WafError`) y backoff de 2 min. |
| `referencia/codigo/identity.js` | id → label (vivo / registro / aprendido) → línea por sufijo y fecha. Aprende labels nuevos y registra conflictos. |
| `referencia/codigo/config.js` | Variables de entorno y defaults usados (intervalo de 3 s, backoff, TTL, líneas). |
| `referencia/codigo/build-registry.js` | Cómo se armó `registry.json` a partir de las grabaciones de la API CABA (por si hay que regenerarlo con datos nuevos). |
| `referencia/datos/registry.json` | **id → label y patente** de 36.433 coches (API CABA, abril–octubre 2026). Imprescindible: sin trip, CuandoSubo no manda label. |
| `referencia/datos/label_line_map_overrides.json` | Correcciones al `LABEL_LINE_MAP` (26 → Nuevos Rumbos desde 2026-09-18) y agencias OBA extra por línea (124 → 6, 704; 25 → 11, 707; 84 → 707). |
| `referencia/fixtures/vehicles-for-agency__708.json`, `__56.json` | Respuestas **reales** de CuandoSubo: 708 = 65 y 151 (casi todo el 151 sin trip); 56 = 39 (casi todo con trip). |
| `referencia/fixtures/seq_708_cada_60s/1..4.json` | Cuatro fotos reales consecutivas de la 708, una por minuto: movimiento, coches sin trip, cambios de hora. Sirven para tests de deltas. |
| `referencia/tests/*.js` | Tests de referencia: grabador (keyframe, delta, gap, legibilidad con gzip de Python), limitador, identidad, y `mock-oba.js` (OBA falso que sirve los fixtures y simula el WAF). |
| `referencia/fixtures/arrivals-and-departures-for-stop__14_20444.json`, `trip-details__56_128107-1.json` | Respuestas **reales** (2026-11-13) de arribos en una parada del 39 y del horario de un trip del 39. |
| `grabador.py` | **Implementación.** Scheduler, snapshot, posiciones/arribos/horarios, estado, stats, guardrails. |
| `limiter.py`, `oba_client.py`, `identity.py`, `config.py` | Reloj y limitador; cliente OBA (transporte HTTP inyectable, WAF); identidad y `LABEL_LINE_MAP` por fecha; configuración por env. |
| `arrival_stops.json` | Panel de paradas para arribos (§11). Lo genera `tools/elegir_paradas.py`. |
| `tests/` | pytest: OBA falso en Python (`fake_oba.py`) con los fixtures reales y reloj falso. |
| `Dockerfile`, `docker-compose.yml`, `stage.py`, `.env.example` | Deploy (§10). |

**Lenguaje:** el grabador CABA es Python (`../grabador/grabador.py` + `delta.py`). Implementar este en **Python** permite **reusar `delta.py` tal cual** (`compute_delta`, `make_keyframe`) y garantiza el mismo formato. El código de referencia es JS: sirve como especificación ejecutable, no hace falta portarlo línea por línea.

---

## 2. Qué graba

Cuatro flujos, cada uno en su propio archivo diario (fecha de Buenos Aires, UTC−3):

| Flujo | Archivo | Fuente | Para qué |
|---|---|---|---|
| **A. Posiciones** | `posiciones/YYYY-MM-DD.ndjson.gz` | `vehicles-for-agency/{agencia}` | Cobertura y latencia contra la API CABA, por coche, cruzando por id. |
| **B. Predicciones por parada** | `arribos/YYYY-MM-DD.ndjson.gz` | `arrivals-and-departures-for-stop/{parada}` | **ETA de CuandoSubo** contra la llegada real y contra el modelo propio. |
| **C. Estado del viaje** | dentro de A (campos extra) | `tripStatus` | ETA de OBA a la próxima parada (`nextStopTimeOffset`), desvío de horario y posición **predicha** por OBA, por coche. |
| **D. Horarios de los trips** | `horarios/YYYY-MM-DD.ndjson.gz` (+ `horarios_index.json`, `paradas.json`) | `trip-details/{trip}?includeSchedule=true` | Horario de cada trip **una vez por día de servicio** (detalle completo solo si el horario es nuevo, por hash). Con `sched_dev` de A permite reconstruir offline la predicción de la app para **cualquier coche y cualquier parada** (§2.3). |

### 2.1 Formato de posiciones (A + C): igual que el grabador CABA

Es NDJSON comprimido con gzip, con **varios bloques gzip concatenados**: cada frame se comprime como un bloque aparte y se agrega al final del archivo. Se lee con `gzip.open(p, 'rt')`, igual que los archivos de la API CABA.

```jsonc
// keyframe: al arrancar, cada K ciclos o después de un hueco de más de 10 min
{"t": 1792504800, "keyframe": true, "src": "cuandosubo", "new": [ {vehículo completo}, ... ], "del": [], "upd": []}
// delta: cada ciclo
{"t": 1792504830, "t_poll": {"56": 1792504829.412, "708": 1792504826.371}, "new": [...], "del": ["97938"], "upd": [{"id": "1839", "ts": 1792504825, "lat": -34.64, "lon": -58.55}]}
// gap: antes del keyframe de reinicio
{"t": 1792590000, "gap": true, "gap_seconds": 3600, "reason": "restart"}
```

Vehículo. Los primeros campos son los del formato CABA, para que el tooling existente funcione igual; los que OBA no tiene van `null` o `""`:

| Campo | Origen OBA | Nota |
|---|---|---|
| `id` | `vehicleId` sin prefijo | **= id de la API CABA** (clave de cruce) |
| `label` | `tripStatus.vehicleLabel` → registro → aprendido | `""` si no se conoce |
| `license_plate` | registro por id | CuandoSubo no manda patentes |
| `route_id`, `trip_id` | del trip, sin prefijo | **Solo informativo:** suele ser de otra línea (§5) |
| `direction_id`, `start_date` | trip / `serviceDate` | |
| `lat`, `lon` | `location` (**GPS real**), 6 decimales | **Nunca** `tripStatus.position` acá |
| `ts` | `lastUpdateTime / 1000` | **Hora del último reporte real**, con o sin trip |
| `speed`, `odo`, `stop_id`, `seq`, `status`, `start_time` | — | `null` / `0` / `""` |
| `agency` | prefijo del `vehicleId` | **extra** |
| `label_src` | `oba` / `registry` / `learned` / `null` | **extra** |
| `line` | sufijo del label → `LABEL_LINE_MAP` a la fecha del archivo | **extra.** Se graba resuelto para no depender del map al analizar, pero el label crudo también queda. |
| `pred_lat`, `pred_lon` | `tripStatus.position` | **extra.** Posición *predicha* por OBA. Sirve para medir el error de su extrapolación contra el GPS real. |
| `sched_dev` | `tripStatus.scheduleDeviation` (s) | **extra** |
| `dist_along` | `tripStatus.distanceAlongTrip` (m, entero) | **extra** |
| `next_stop`, `next_stop_eta_s` | `tripStatus.nextStop` (sin prefijo), `nextStopTimeOffset` | **extra.** ETA de OBA a la próxima parada. |
| `predicted` | `tripStatus.predicted` | **extra** |

**`t_poll` (desde 2026-11-13, extra de CuandoSubo; keyframe y delta):** objeto `{agencia: currentTime de la respuesta de vehicles-for-agency, en segundos, float con ms}`, una entrada por cada agencia cuya respuesta alimentó el frame (tier A fresca; tier C con la hora de su última vuelta, así que puede ser vieja hasta `SWEEP_MAX_AGE_S`). Es la hora **del servidor** en que se vio el dato. El coche tiene `agency` (prefijo de `vehicleId`), así que `t_poll[agency] - ts` es el retraso de publicación; `t` sigue siendo `max(ts)` (lo calcula `delta.py`). `grabador.py` lo agrega después de `compute_delta_ext`/`keyframe`; `delta.py` no se tocó.

`upd` lleva `id`, `ts` y **solo los campos que cambiaron** (los mismos campos dinámicos que `delta.py`, más los extra).

Implementación (2026-11-13): `delta.py` del grabador CABA se usa **sin modificar**; `grabador.compute_delta_ext` lo envuelve y agrega a `upd` los extra que cambiaron, más `label`, `license_plate` y `start_date` (acá sí cambian: label aprendido, cambio de día de servicio). Así el estado se reconstruye **exacto** desde los deltas con `reconstruct_at` de la skill `grabador_nuc.md` (está testeado). Además, si **solo** cambió `ts` (heartbeat de un coche quieto, §4 regla 5) va `{"id", "ts"}`: es un reporte real y sirve para medir cobertura. Ojo con el volumen: `pred_lat`/`pred_lon`/`next_stop_eta_s` cambian en casi cada foto de un coche con trip, así que esos coches aparecen en `upd` casi siempre.

### 2.2 Formato de predicciones (B)

Una línea por consulta a una parada. No es delta: el volumen es chico.

```jsonc
{"t": 1792504812,                // currentTime de la respuesta (s)
 "stop": "56_1234", "line": "39",
 "arrivals": [
   {"vehicle": "97938", "label": "452-1350", "route": "39A", "trip": "128863-1",
    "predicted": true,
    "pred_arr": 1792505100,      // predictedArrivalTime / 1000 (null si no hay tiempo real)
    "sched_arr": 1792505040,     // scheduledArrivalTime / 1000
    "stops_away": 4, "dist_m": 1830}
 ]}
```

Para comparar: la llegada real de ese `vehicle` a esa parada se mide con las posiciones de la API CABA (mismo id), proyectando el coche sobre el recorrido. Eso lo hace el análisis, no el grabador.

**Implementado (2026-11-13)**: cada arribo trae además lo necesario para separar predicciones por tiempo real / horario / frecuencia:

| Campo | Origen | Nota |
|---|---|---|
| `vehicle`, `label`, `veh_line` | `vehicleId` sin prefijo; `vehicleLabel` → registro → aprendido; línea por sufijo a la fecha | `null` si el trip no tiene coche (solo horario). `route` es la ruta de OBA (puede ser de otra línea); la línea del coche es `veh_line`. |
| `route`, `route_id`, `trip`, `service_date`, `stop_seq` | `routeShortName`, `routeId`, `tripId` (sin prefijo), `serviceDate`/1000, `stopSequence` | |
| `predicted` | `predicted` | `false` → `pred_arr = null`: es solo horario. |
| `pred_arr`, `sched_arr` | `predictedArrivalTime`/1000 (0 → `null`), `scheduledArrivalTime`/1000 | **Medido:** `pred_arr = sched_arr + sched_dev` en el 100 % de los arribos con `predicted` (12/12 en el fixture, 91/91 en el smoke). |
| `stops_away`, `dist_m` | `numberOfStopsAway`, `distanceFromStop` | **Negativos** = el coche ya pasó la parada según OBA. |
| `frequency`, `pred_interval`, `sched_interval` | `frequency`, `predictedArrivalInterval`, `scheduledArrivalInterval` | Los intervalos solo aparecen si no son `null` (trips por frecuencia). En las líneas objetivo, `frequency` vino siempre `null`. |
| `sched_dev`, `veh_ts` | `tripStatus.scheduleDeviation`, `lastUpdateTime`/1000 | `veh_ts` = hora del último GPS del coche. |
| `lat`, `lon`, `pred_lat`, `pred_lon` | `tripStatus.lastKnownLocation` (GPS real), `tripStatus.position` (extrapolada) | |

Se graban **todos** los arribos de la parada (también de otras líneas), no solo los de la línea del panel.

### 2.3 Horarios de los trips y cómo reconstruir la predicción de la app

**Cómo predice CuandoSubo (verificado 2026-11-13 contra la API real).** `trip-details/{trip}?includeSchedule=true&includeStatus=true` y `trip-for-vehicle/{agencia}_{id}?...` existen en este OBA 1.1.17 y devuelven lo mismo: `schedule.stopTimes[]` (`stopId`, `arrivalTime`/`departureTime` **en segundos desde `serviceDate`**, `distanceAlongTrip`) + `status` (el mismo `tripStatus` de siempre). **No hay ningún campo de predicción por parada.** La vista "detalle del viaje" de la app es, entonces:

```
ETA del coche en la parada s  =  serviceDate/1000 + stopTime[s].arrivalTime + scheduleDeviation
```

Lo confirma `arrivals-and-departures-for-stop`: `predictedArrivalTime = scheduledArrivalTime + scheduleDeviation·1000` en todos los arribos con `predicted: true`. **El desvío actual se propaga igual a todas las paradas que faltan.** Por eso, si los `stopTimes` del trip tienen tiempos entre paradas irreales (o el coche corre un trip que no es el suyo, ver abajo), la predicción hereda ese error: eso explica ver "4–5 paradas en 1–2 min".

Además se vio (2026-11-13, parada 14_20444 del 39) **dos coches distintos colgados del mismo trip** (`56_128923-1`) con desvíos de −1416 s y −870 s: OBA les asigna un trip programado que no es el que hacen, y el "desvío" de −23 min mide eso, no un adelanto real.

**Qué se graba.** Cada `(tripId, serviceDate)` se pide **una vez por día de servicio** en que aparece: en un coche de las líneas objetivo en posiciones (`RECORD_LINES`, línea por label) o en un coche de esas líneas en los arribos del panel. **No se asume** que un `tripId` conserve su horario entre días: el bundle GTFS de Nación se reemplaza y los ids rotan (en la API CABA el `route_id` rota cada ~3 semanas). Va con prioridad baja (`TRIPS_PER_CYCLE` por ciclo, en los huecos, antes de la rotación C); primero los trips de coches vistos en las paradas del panel y después el resto. El pedido es `trip-details/{trip}?includeSchedule=true&serviceDate=<ms>`.

Siempre se escribe **una línea por (tripId, serviceDate)** con el `hash` del horario. Es un SHA-1 truncado a 16 caracteres del JSON canónico de `route_id`, `headsign`, `direction_id`, `frequency` y `stop_times` (`stop`, `arr`, `dep`, `dist`). El **detalle completo** (esos campos) va **solo la primera vez que aparece ese hash** (`"full": true`). Si el horario no cambió, la línea lleva solo el hash (`"full": false`) y el archivo no crece por repetir lo mismo:

```jsonc
// primera vez que se ve este horario
{"t": 1794575515, "trip_id": "128107-1", "oba_trip_id": "56_128107-1", "service_date": 1794538800,
 "hash": "3f9c0a1b2c3d4e5f", "full": true, "route": "39A", "block_id": "56_9339HI0039", "shape_id": "14_1932",
 "time_zone": "America/Argentina/Buenos_Aires",
 "route_id": "1932", "headsign": "R1 a Chacarita x Pza. Italia", "direction_id": 0, "frequency": null,
 "stop_times": [{"stop": "14_2032608", "arr": 33360, "dep": 33360, "dist": 0.0}, ...]}
// mismo trip al día siguiente, mismo horario
{"t": 1794661915, "trip_id": "128107-1", "oba_trip_id": "56_128107-1", "service_date": 1794625200,
 "hash": "3f9c0a1b2c3d4e5f", "full": false, "route": "39A", "block_id": "56_9339HI0039", "shape_id": "14_1932",
 "time_zone": "America/Argentina/Buenos_Aires"}
```

- `horarios_index.json` (persistente):
  - `trips`: `"oba_trip_id|serviceDate(s)" → {hash, t}` o `{missing: true}` si OBA dio 404. Es lo ya pedido; se poda a los últimos ~3 días.
  - `last`: `oba_trip_id → {sd, hash}`, el último día de servicio pedido, para detectar cambios.
  - `hashes`: `hash → {file, t}`, el archivo `horarios/…` donde está el detalle completo de ese horario.
- `paradas.json`: `stopId → {name, code, lat, lon, direction}`, de las `references.stops` de horarios y arribos.
- `stats.json` → `trips_day` (se reinicia cada día BA) responde con datos si los trips son estables:
  - `fetched`: trips pedidos ese día;
  - `new_trip_ids`: tripId nunca visto;
  - `same_as_prev_service_day`: mismo hash que el día de servicio anterior de ese trip;
  - `horario_cambiado`: hash distinto;
  - `new_hashes` y `missing`.

  También están `horario_cambiado_total`, `trips_queue` (cola pendiente) y `trips_queue_priority` (los del panel).

**Presupuesto (medido 2026-11-12 en la grabación CABA, mismos trip_id que el bundle de Nación):** las 5 líneas del panel (39, 26, 42, 92, 168) usaron **~2.320 trips distintos en el día** (39: 653, 26: 554, 92: 458, 168: 357, 42: 299); ~2.670 sumando los del 151 (viajes del 65). El pico es de ~140 trips nuevos por hora (8–18 h), y unos 160/h con el 151. Con `TRIPS_PER_CYCLE=2` y ciclo de 45 s la capacidad es de **160/h** si siempre entran en el hueco. Alcanza justo: en el pico la cola crece algo y se vacía a la noche, y los del panel van primero. `TRIPS_PER_CYCLE=3` (240/h) da margen a costa de ~1 request menos por ciclo para la rotación C (la vuelta a AMBA pasa de ~40 a ~60 min). Un trip que no se llega a pedir su día queda sin horario ese día (mirar `trips_queue` a la noche).

**Reconstrucción offline** de la predicción de la app para el coche `v` en el instante `T` y la parada `s`:
1. Tomar el estado de `v` en `T` desde posiciones (`trip_id`, `start_date`, `sched_dev`, `next_stop`).
2. Buscar la línea de horarios con ese `trip_id` y `service_date` = 00:00 BA de `start_date` (en `horarios/` de ese día o del anterior). Esa línea da el `hash`.
3. Buscar el detalle: `horarios_index.json` → `hashes[hash].file`, y ahí la línea con ese `hash` y `"full": true`.
4. Calcular `ETA = service_date + arr(s) + sched_dev`, solo para las paradas desde `next_stop` en adelante.

Ojo con los ids: en posiciones `next_stop` y `trip_id` van **sin** prefijo; en horarios y `paradas.json` los `stop` van con prefijo (`14_…`). Se compara contra los `arribos` de la misma parada (deben coincidir) y contra la llegada real.


### 2.4 Estado y salud

En `/mnt/buffer/grabaciones_cuandosubo/`:
- `state.json`: último estado de vehículos y hora (para seguir con deltas y detectar huecos después de reiniciar);
- `horarios_index.json`, `paradas.json`: ver §2.3;
- `learned_labels.json`: labels aprendidos en vivo y conflictos;
- `health`: se toca en cada ciclo, para el HEALTHCHECK;
- `stats.json`: contadores (requests, WAF, errores, vehículos por línea, artefactos), útiles para monitorear sin abrir los NDJSON.

---

## 3. Arquitectura

```
                 ┌──────────── Scheduler (un solo hilo, ciclo de 30 s) ───────────┐
                 │  tier A: agencias de las líneas objetivo   (prioridad 1)       │
                 │  panel de paradas para arribos            (prioridad 2)        │
                 │  tier B: resto de AMBA en rotación        (prioridad 3)        │
                 └───────────────┬────────────────────────────────────────────────┘
                                 ▼
                 RateLimiter: cola por prioridad, 1 request a la vez, ≥ 3 s entre requests,
                              pause(120 s) ante WAF
                                 ▼
                 ObaClient: GET + key, timeout, detección de WAF, caché por recurso,
                            reintento, stale-on-error
                                 ▼
          Identity (registro + aprendidos + LABEL_LINE_MAP por fecha + overrides)
                                 ▼
          Snapshot (merge de todas las agencias, filtros §5) ──► delta/keyframe ──► posiciones/*.ndjson.gz
          Arribos (por parada) ─────────────────────────────────────────────────────► arribos/*.ndjson.gz
                                 ▼
                       state.json, learned_labels.json, health, stats.json
```

### 3.1 RateLimiter (ver `referencia/codigo/oba/limiter.js`)
- **Un request por vez** y **separación mínima de 3 s** entre el fin de uno y el inicio del siguiente (`OBA_MIN_INTERVAL_MS=3000`).
- **Cola con prioridad:** dentro de una misma prioridad, en orden de llegada.
- **`pause(ms)`:** frena la cola entera. Se usa con 120 s ante el WAF.
- No hay paralelismo **nunca**, ni "solo dos a la vez": el WAF de SUBE corta con 302 apenas detecta concurrencia.

### 3.2 ObaClient (ver `referencia/codigo/oba/client.js`)
- **WAF:** si la respuesta es HTTP 301/302/303/307/403/429, un redirect opaco o un cuerpo que no es JSON (HTML), se trata como `WafError`: `limiter.pause(120000)`, se registra en `stats` y se reintenta después de la pausa.
- **Key inválida:** cuerpo con `code: 401`. Es un error fatal de configuración: loguear CRITICAL y salir.
- **Otros errores:** HTTP 5xx, timeout (20 s) o red. Reintentar en el próximo ciclo; ese ciclo usa el último dato de esa agencia si tiene menos de 2 min.
- Guardar `currentTime` de cada respuesta: **todas las edades se calculan contra eso**.

### 3.3 Identity (ver `referencia/codigo/identity.js`)
1. `label = tripStatus.vehicleLabel ?? registry[id] ?? learned[id]`.
2. Si llega un `vehicleLabel` en vivo distinto del conocido para ese id, **registrarlo como conflicto** (rompería el invariante) en vez de pisarlo en silencio. Debería dar 0.
3. `line = LABEL_LINE_MAP[sufijo]` vigente en la **fecha de Buenos Aires del archivo**. Se carga de `proyectoconsola/LABEL_LINE_MAP.json` (o su espejo en `prediccion colectivos/`) **más** los overrides de `referencia/datos/`. Recargar el map una vez por día o si cambia el archivo.
4. Agencias de una línea = las del map vigentes a la fecha + `obaAgencies` de los overrides (agencias donde OBA tiene esa línea o adonde pasó).

### 3.4 Scheduler y presupuesto
Con 3 s de separación entran **~10 requests por ciclo de 30 s**. Repartirlos así:

| Tier | Qué | Frecuencia | Requests |
|---|---|---|---|
| A | `vehicles-for-agency` de las agencias de las **líneas objetivo** (`RECORD_LINES`, ej. `39 26 42 92 124 152 168` → agencias 56, 12, 15, 20, 80, 6, 704, …) | cada ciclo, 30 s | ≤ 6 |
| B-arribos | `arrivals-and-departures-for-stop` de un **panel fijo de paradas** (`ARRIVAL_STOPS`, ej. 2–3 paradas por línea objetivo, sobre el recorrido real) | cada 60 s, en rotación | ~2 por ciclo |
| C | `vehicles-for-agency` del **resto de AMBA**, en rotación | en los huecos libres | el resto |

Si tier A + arribos no entran en el ciclo, **avisar** (`stats.json`: `cycle_overrun`) en vez de acortar la separación. Con ~10 agencias en tier A hay que estirar el ciclo a 45–60 s, y está bien: el GPS de CuandoSubo se refresca cada ~2 min por coche.

- El **snapshot** de cada ciclo se arma con **la última respuesta de cada agencia** (tier A fresca y tier C de la rotación), así que el archivo de posiciones cubre todo AMBA, con resolución de 30 s en las líneas objetivo y de ~11 min en el resto.
- **Opcional:** filtrar el snapshot a solo líneas AMBA ≤ 199. (No implementado.)

**Implementado (2026-11-13), defaults:** ciclo `CYCLE_S=45`; tier A = agencias de `RECORD_LINES=39 26 42 92 152 168` (2026-11-13: sale el 151, que reporta ~9 de 77 coches; entra el 152, agencia OBA 20); `ARRIVALS_PER_CYCLE=3` paradas del panel en rotación (18 paradas → cada una cada ~7,5 min); después, en los huecos (`next_start + duración típica ≤ fin del ciclo`): `TRIPS_PER_CYCLE=2` horarios y la rotación C con lo que sobre. En el smoke en vivo (2026-11-13, 152 + 168) entraron 15 requests por ciclo de 45 s sin `cycle_overrun`.
- **124 fuera de `RECORD_LINES`** (desvío del ejemplo): CuandoSubo no lo publica y sus agencias (6, 704, 705) gastarían 3 requests por ciclo para dar 0. Siguen en la rotación C, así que si el 124 vuelve aparece igual (con menos resolución). Para medirlo en cada ciclo, agregarlo a `RECORD_LINES`.
- La rotación C cubre ~170 agencias AMBA de a ~4–8 por ciclo: una vuelta tarda del orden de 20–40 min, no los ~11 min del ejemplo (el presupuesto lo comen tier A, arribos y horarios). Por eso `SWEEP_MAX_AGE_S=7200`: el snapshot usa el último dato de cada agencia C hasta 2 h; tier A, hasta `STALE_MAX_S=120`.
- Prioridad: el limitador es de un solo hilo (no hay concurrencia posible); la prioridad la da el orden del ciclo (A → arribos → horarios → C).
- WAF: pausa de 120 s y **un reintento** del mismo recurso después de la pausa.

### 3.5 Delta, keyframe y gap
- **Reusar `../grabador/delta.py`.** Keyframe al arrancar, cada `KEYFRAME_EVERY` ciclos (igual que el grabador CABA) o si el hueco desde el último guardado supera 600 s. En ese último caso, antes del keyframe se escribe el registro `gap`.
- El archivo del día se decide por la fecha de Buenos Aires de `t`.
- `append` de un bloque gzip por frame, y después `state.json` escrito de forma atómica (tmp + rename).
- **Si un ciclo no tiene vehículos** (todo falló), no escribir delta vacío ni borrar el estado: el siguiente ciclo bueno sigue normal.

---

## 4. Reglas de datos (las que más importan)

1. **`ts = lastUpdateTime`, también sin trip.** Se verificó el 2026-10-20: es la hora real del último reporte. (Una conclusión anterior, que decía que sin trip no era la hora del GPS, estaba mal: salía de los artefactos de la regla 3.)
2. **Posición = `location`** (GPS real). `tripStatus.position` es la **extrapolación de OBA** y va aparte (`pred_lat`/`pred_lon`).
3. **Artefactos en lote:** si la posición cambió pero `lastUpdateTime` **no**, no es movimiento: el servidor reacomodó registros viejos (saltos de 2–7 km, muchos coches en la misma foto). **No grabar ese cambio de posición**: mantener la anterior y sumar `stats.artifacts`.
4. **Hora compartida:** varios coches con **exactamente** el mismo `lastUpdateTime` al ms vienen de una escritura en lote del servidor. Grabarlos igual, pero contarlos (`stats.shared_ts`) para poder filtrarlos en el análisis.
5. **No descartar coches por antigüedad.** Se graba todo lo que lista la API, como el grabador CABA; la edad está en `ts`. Los guardados en depósito aparecen con heartbeat (cambia `ts`, no la posición).
6. **Bounding box AMBA:** lat −35,1…−34,3, lon −59,1…−57,9. Fuera de eso se descarta (la API lista todo el país).
7. **Id fantasma:** si el mismo id aparece en dos agencias, quedarse con el de `ts` mayor.
8. **Línea por label, nunca por trip ni por ruta.** El trip suele ser de otra línea (el 151 con viajes del 65, el 84 con los del 115). Se graba igual como dato.
9. **Fecha del map:** resolver `line` con el map vigente **a la fecha del archivo**, no a la de hoy.

---

## 5. Limitaciones conocidas (no son bugs del grabador)

Ver `docs/CUANDOSUBO_API.md` §6. En resumen, a 2026-10-20:
- **124 y 25: CuandoSubo no los publica.** Los descarta al ingerirlos por el mapeo empresa → agencia roto. El grabador va a dar 0 y está bien: es justamente una métrica de cobertura.
- **151:** ~9 de 77 coches reportando. **84:** 1 de 49.
- Sin trip no hay label en vivo: depende del registro, que solo cubre ids de la era de la API CABA. **Mientras la API CABA esté activa**, conviene **actualizar el registro** periódicamente con `build-registry.js` (o su port) sobre `Z:\grabaciones`, para que los ids nuevos tengan label y patente.

---

## 6. Despliegue en el NUC

```
~/grabador-cuandosubo/        (código + docker-compose.yml + .env)
/mnt/buffer/grabaciones_cuandosubo/
    posiciones/YYYY-MM-DD.ndjson.gz
    arribos/YYYY-MM-DD.ndjson.gz
    state.json  learned_labels.json  health  stats.json
```

`docker-compose.yml` (esquema):
```yaml
services:
  grabador-cuandosubo:
    build: .
    restart: always
    env_file: .env              # OBA_KEY=...  (nunca en git)
    environment:
      - DATA_DIR=/data
      - RECORD_LINES=39 26 42 92 124 152 168
      - ARRIVAL_STOPS=...       # ids OBA de paradas, separados por espacio
      - OBA_MIN_INTERVAL_MS=3000
    volumes:
      - /mnt/buffer/grabaciones_cuandosubo:/data
      - /ruta/al/LABEL_LINE_MAP.json:/app/LABEL_LINE_MAP.json:ro   # o copiarlo en el build
    dns: [1.1.1.1, 8.8.8.8]     # el DNS de la VM falló con Docker (SRV/"server misbehaving")
    healthcheck:
      test: ["CMD", "python", "-c", "import os,time,sys; sys.exit(0 if time.time()-os.path.getmtime('/data/health')<180 else 1)"]
      interval: 60s
```

Guardrails, iguales a los del grabador CABA:
- error de fetch: saltear y reintentar en el ciclo siguiente;
- **N fallos consecutivos** (todas las agencias fallando unos 10 min, que no sea WAF): `exit(1)`, así `restart: always` recrea el contenedor y se regenera el DNS;
- **disco** con menos de 2 GB libres: dejar de escribir y loguear CRITICAL;
- **WAF:** no cuenta como fallo de red, es una pausa.

Volumen esperado: unos 30–45 MB/día en posiciones (medido con tier A de 7 líneas + rotación de todo AMBA) y unos pocos MB/día en arribos.

**Acceso desde Windows:** el share SMB `[buffer]` ya exporta `/mnt/buffer` en solo lectura, así que la carpeta aparece como `Z:\grabaciones_cuandosubo` sin tocar Samba.

Logs, una línea por ciclo como el grabador CABA:
`ciclo=N veh=… new=… del=… upd=… artefactos=… waf=… reqs=… [KF] errs=…`

---

## 7. Tests (antes de desplegar)

Testear comportamiento observable: archivos escritos, contenido y contadores. No testear detalles internos.

- **OBA falso** (`referencia/tests/mock-oba.js`): sirve los fixtures reales por recurso, modos `ok` / `waf` (302) / `down` (500), secuencias de fotos (`seq_708_cada_60s`) y registro de requests.
- **Casos mínimos:**
  1. Primer ciclo = keyframe completo con los campos del §2.1, ids sin prefijo, `ts` = `lastUpdateTime`, todo dentro del bbox.
  2. Segundo ciclo con la misma foto = delta vacío (`upd: []`).
  3. Con la secuencia real de 4 fotos: los coches que se mueven aparecen en `upd` con `ts` nuevo; los quietos no.
  4. **Artefacto:** posición distinta con la misma `lastUpdateTime` → no aparece en `upd` y `stats.artifacts` sube.
  5. Gap: reloj +1 h → registro `gap` + keyframe. **No se toca nada fuera de su carpeta** (que no exista `/mnt/buffer/grabaciones` en el test, o que quede intacta).
  6. WAF: el mock devuelve 302 → no hay requests durante 120 s (reloj inyectable), se reanuda y no se pierden frames.
  7. **Los requests nunca se superponen** y respetan la separación mínima (registro de tiempos del mock).
  8. Identidad: label del registro sin trip, label en vivo con trip, conflicto registrado, línea por sufijo a la fecha (26 antes y después del 2026-09-18).
  9. El archivo se lee con `gzip.open(..., 'rt')` de Python y el estado se reconstruye con la función de la skill `grabador_nuc.md`.
  10. Arribos: una consulta escribe una línea con el esquema del §2.2.
- **Smoke en vivo** (manual, una vez): 3 ciclos contra CuandoSubo real con 1–2 líneas, verificando 0 WAF y los contadores de `stats.json`.

---

## 8. Cómo usarlo para comparar (lo que habilita)

Cruce **por `id` de vehículo y tiempo** con las grabaciones CABA (`Z:\grabaciones`), que tienen el mismo id:

| Métrica | Cómo |
|---|---|
| Cobertura por línea | Coches con reporte de los últimos 3 min en CuandoSubo contra la API CABA, por línea y hora. |
| Latencia | Para un mismo id, `ts` de CuandoSubo contra `ts` de la API CABA para la misma posición. |
| Error de posición | Distancia entre `lat`/`lon` de las dos fuentes al mismo instante (interpolando). |
| Error de la extrapolación de OBA | `pred_lat`/`pred_lon` contra la posición CABA real a esa hora. |
| **ETA de CuandoSubo** | `arribos.pred_arr` contra la llegada real del coche a la parada (posiciones CABA proyectadas sobre el recorrido), por horizonte (0–5, 5–10, 10–20 min). Es la vara para el modelo propio: **mismo set de paradas y horarios**, mismo cálculo de error. |
| Desvío de horario | `sched_dev` contra la llegada real. |
| **Predicción de la app a todas las paradas** | `horarios` + `sched_dev`/`next_stop` de posiciones: `ETA(s) = serviceDate + arr(s) + sched_dev`, con el horario **vigente ese día de servicio**: la línea de `(trip, serviceDate)` da el `hash` y `horarios_index.json → hashes[hash]` dice dónde está el detalle (§2.3). Vale para cualquier coche y parada, no solo las del panel. Validar contra `arribos` en las paradas del panel. |
| Tipo de predicción | Filtrar arribos por `predicted` (tiempo real vs solo horario) y `frequency`/`sched_interval` (trips por frecuencia). Marcar sospechosos: `abs(sched_dev)` grande o dos `vehicle` con el mismo `trip` a la vez (trip mal asignado). |

---

## 9. Checklist de implementación

- [x] Leer `docs/CUANDOSUBO_API.md`, y `docs/IDENTIFICACION.md` §4 y §10.
- [x] Config por variables de entorno (key, intervalo, líneas, paradas, carpeta, TTL); nada hardcodeado; la key nunca en git.
- [x] Limitador secuencial con prioridad y pausa; cliente con detección de WAF.
- [x] Identidad: registro + aprendidos + map por fecha + overrides; conflictos registrados.
- [x] Scheduler: tier A, arribos y rotación C, con aviso de `cycle_overrun`. (+ horarios de trips, §2.3)
- [x] Snapshot con las reglas del §4 (artefactos, fantasmas, bbox).
- [x] `delta.py` reusado; keyframe, gap y archivo por fecha BA; estado atómico.
- [x] Flujo de arribos.
- [x] `stats.json` + `health` + log por ciclo.
- [x] Tests del §7 en verde (21 tests, `python -m pytest tests`).
- [x] Compose con **carpeta propia**, `dns`, healthcheck y `restart: always` (en esta carpeta; falta copiarlo al NUC).
- [x] Líneas objetivo `39 26 42 92 152 168` (2026-11-13: sin 151, con 152) en compose y default de `config.py`.
- [x] Panel con 18 paradas (3 por línea, incluye el 152; §11).
- [x] `t_poll` en cada frame de posiciones (§2.1) + test.
- [x] Smoke en vivo hecho desde Windows (2026-11-13, 3 ciclos, 152 + 168, 594 → 1842 coches vistos, 0 WAF, 45 requests); `python stage.py` → `dist/grabador-cuandosubo/` con `.env`.
- [~] Deploy: `.env` y `dist/` listos. **Falta** el deploy en el NUC y ver que en `Z:\grabaciones_cuandosubo` aparezcan los archivos y que `Z:\grabaciones` no haya cambiado.

---

## 10. Cómo correr y deployar

### Local (Windows, sin Docker)
```powershell
cd "prediccion colectivos\grabador_cuandosubo"
pip install -r requirements.txt pytest
python -m pytest tests                       # OBA falso + reloj falso; no toca la red ni nada fuera de un tmp
# Smoke en vivo (3 ciclos). DATA_DIR en un temporal: NUNCA Z:\ ni una carpeta de grabaciones.
$env:OBA_KEY = "<CUANDOSUBO_API_KEY de proyectoconsola\.env.local>"
$env:DATA_DIR = "$env:TEMP\cuandosubo_smoke"; $env:RECORD_LINES = "152 168"
python grabador.py --test 3
```
En el repo, `grabador.py` importa `../grabador/delta.py` (el del grabador CABA, sin copiarlo) y lee `../LABEL_LINE_MAP.json`.

### NUC (Docker)
El contenedor no ve el repo: `stage.py` arma el contexto de build con el código, `delta.py` (copia del grabador CABA), `LABEL_LINE_MAP.json` (de `prediccion colectivos/`), `arrival_stops.json`, `registry.json` y los overrides.
```bash
# en Windows (Git Bash o PowerShell), desde prediccion colectivos/grabador_cuandosubo
python stage.py                                       # → dist/grabador-cuandosubo/ (ignorado por git)
scp -r dist/grabador-cuandosubo laek@192.168.0.18:~/

# en el NUC
ssh laek@192.168.0.18
sudo mkdir -p /mnt/buffer/grabaciones_cuandosubo && sudo chown laek: /mnt/buffer/grabaciones_cuandosubo
cd ~/grabador-cuandosubo
test -f .env || (umask 077; echo "OBA_KEY=<key>" > .env)     # la key nunca en git
docker compose up -d --build
```
Si `grabador_cuandosubo/.env` existe localmente (está en `.gitignore`), `stage.py` lo copia y no hace falta crearlo en el NUC.

**Actualizar** el map, el registro, el panel o el código: volver a correr `stage.py`, `scp` y `docker compose up -d --build` (el `.env` del NUC no se pisa si no hay uno local).

### Monitoreo
```bash
docker compose -f ~/grabador-cuandosubo/docker-compose.yml logs -f --tail 50   # una línea por ciclo
docker ps --filter name=grabador-cuandosubo                                     # (healthy)
cat /mnt/buffer/grabaciones_cuandosubo/stats.json | python3 -m json.tool        # waf, cycle_overrun, vehicles_by_target_line…
ls -la /mnt/buffer/grabaciones_cuandosubo/{posiciones,arribos,horarios}
```
Qué mirar en `stats.json`: `waf` (debería quedar en 0), `cycle_overrun` (si sube seguido, subir `CYCLE_S` o bajar `ARRIVALS_PER_CYCLE`), `fetch_errors`, `reporting_3min_by_target_line`, `identity.conflicts` (debería ser 0), `trips_queue` (debería vaciarse a la noche) y `trips_day.horario_cambiado`. Los contadores se reinician con el contenedor. `shared_ts` cuenta reportes nuevos con la misma `lastUpdateTime` al ms que otro coche de la foto: muchos `lastUpdateTime` vienen redondeados al segundo, así que tiene falsos positivos; es orientativo.

Guardrails implementados: tier A sin respuestas (que no sean WAF) por `FATAL_FAIL_S=600` → `exit(1)` y `restart: always` recrea el contenedor; disco < `DISK_MIN_GB=2` → deja de escribir y loguea CRITICAL; key inválida (`code 401`) → CRITICAL, espera 10 min y `exit(2)`; ciclo sin vehículos → no escribe ni borra el estado; hueco > 600 s en marcha → registro `gap` con `reason: "outage"` + keyframe (al arrancar, `reason: "restart"`).

---

## 11. Panel de paradas (`arrival_stops.json`)

Generado el 2026-11-13 con `tools/elegir_paradas.py` (requests secuenciales a ≥ 3,5 s con el mismo limitador; respuestas cacheadas para no repetir):

1. `routes-for-agency` de las agencias de cada línea en el map → rutas OBA de la línea (cada ruta OBA = un sentido de un ramal). El **26** tiene sus rutas bajo la agencia **13** (`13_1994/1995`, 26A), aunque los coches 4820 reportan bajo la 12.
2. `stops-for-route` de cada ruta; las rutas se agrupan por sentido.
3. **Tronco**: paradas que están en **todos** los ramales de ese sentido, para que la parada sirva a toda la flota de la línea.
4. Por distancia acumulada: sentido 0 al ~20 % (**inicio**) y ~80 % (**final**), sentido 1 al ~50 % (**medio**). Si el tronco no llega a esa altura se toma la parada del tronco más cercana (por eso el 39 "final" quedó al 93 %, y el 92 "inicio" y el 168 "inicio" al ~40 %: los ramales recién se juntan ahí).
5. Validación contra `prediccion/data/line_shapes.json`: todas a ≤ 10 m del recorrido real.

| Línea | Inicio (sentido 0) | Medio (sentido 1) | Final (sentido 0) |
|---|---|---|---|
| 39 | 14_206600 1165 Ciudadela | 14_203270 1754 Santa Fe Av. | 14_201063 6481 Córdoba |
| 26 | 14_2093 1185 Córdoba Av. | 14_202133 459 Gascón | 14_201708 Barco Centenera 789 |
| 42 | 14_204691 Juramento 1293 | 14_20796 375 Guzmán | 14_206135 1685 Cachimayo |
| 92 | 14_205731 C. Transbordo Flores | 14_201704 8350 Rivadavia Av. | 14_203994 Av. Eva Perón 7463 |
| 168 | 14_S00094695 Metrobús Norte – Gral. Paz | 14_S00094827 Av. Elcano 3006 | 14_S00094902 Adolfo Alsina 2410 |
| 152 | 14_S00081644 Metrobús Norte – Álvarez | 14_S00081575 Av. Santa Fe 933 | 14_S00081526 Metrobus Del Bajo – Av. Corrientes |

Total: 18 paradas, 3 por línea. El 152 se agregó el 2026-11-13 con `--lines 152 --merge` (las otras líneas quedaron intactas; 7 requests). El 152 no está en `line_shapes.json`, así que sus paradas **no** se validaron contra el recorrido real, y sus fracciones (13 %, 29 %, 80 %) quedaron lejos de las nominales porque los 3 ramales recién se juntan en el tronco ahí.

**Fuera del panel:** el **151** (casi no reporta; CuandoSubo le asigna viajes del 65 y casi ningún coche tiene trip, así que no tendría arribos propios; desde 2026-11-13 tampoco está en `RECORD_LINES`) y el **124** (no está en CuandoSubo). Para regenerar: `OBA_KEY=… python tools/elegir_paradas.py --cache <dir temporal> --out arrival_stops.json`. Con `--lines <línea…> --merge` regenera solo esas líneas y conserva las demás del archivo existente.
