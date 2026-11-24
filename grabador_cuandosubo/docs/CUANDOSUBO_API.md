# CuandoSubo (OneBusAway de Nación/SUBE): llamadas, campos y limitaciones

Todo lo de este documento se midió contra la API en vivo entre el 2026-10-19 y el 2026-10-20, salvo donde se aclara. El estudio completo, con las mediciones y por qué de cada regla, está en `IDENTIFICACION.md`, sobre todo en la §10.

## 1. Acceso

| | |
|---|---|
| Base JSON | `https://cuandosubo.sube.gob.ar/onebusaway-api-webapp/api/where/{recurso}.json?key=KEY` |
| Base GTFS-RT | `https://cuandosubo.sube.gob.ar/onebusaway-api-webapp/api/gtfs_realtime/{recurso}/{agencia}.pbtext?key=KEY` (`.pb` = binario) |
| Key | La de la app Android (`CuandoSUBO-Android-…`). Está en `proyectoconsola/.env.local` como `CUANDOSUBO_API_KEY`. **Nunca en el repo**: siempre por variable de entorno. Si la key es inválida, la API devuelve HTTP 200 con el cuerpo `{"code":401}`. |
| Formato | Envelope OBA v2: `{code, currentTime, text, version: 2, data: {list \| entry, references: {agencies, routes, trips, stops, situations}}}` |
| Hora | Todas las edades se calculan contra **`currentTime` de la respuesta** (hora del servidor, en ms), nunca contra el reloj local. |

## 2. El servidor

- Es un **OneBusAway viejo, compatible con 1.1.17 (diciembre 2017)**, con agregados que no respetan el estándar:
  - no tiene `config.json` ni `vehicle-position-for-vehicle` (404 "There is no Action mapped");
  - la exportación GTFS-RT no filtra por antigüedad.
- **Lo no estándar** (no está en ninguna versión pública de OBA entre 2011 y 2026):
  - `tripStatus.vehicleLabel`;
  - lista **coches sin trip**. El OBA estándar descarta toda posición sin `trip_id`.
- **De dónde salen los datos:** validadores SUBE + "monitoreo satelital", según Nación. Es la misma fuente de fondo que usaba la API CABA, pero filtrada por el mapeo de Nación empresa → agencia → viajes, que está roto para varias líneas (§6).

## 3. Endpoints útiles

### 3.1 `agencies-with-coverage`
Unas 189 agencias, entre AMBA e interior. Ids numéricos; las entidades nuevas del cambio de operadores de junio de 2026 son 7xx.
**Ojo:** esta lista no es todo lo que existe (ver §3.2).

### 3.2 `vehicles-for-agency/{agencia}`: **el recurso del grabador**
Devuelve todos los coches cuyo `vehicleId` empieza con `{agencia}_`.
- **Responde para cualquier id de agencia**, aunque no esté en `agencies-with-coverage`, porque filtra por el prefijo del id. Se probaron todos los ids del 1 al 999 que no están en la lista y no había coches en ninguno (2026-10-20).
- **Tamaño:** de 30 a 70 KB por agencia AMBA grande.

Campos de cada vehículo (`data.list[]`):

| Campo | Qué es | Confiabilidad |
|---|---|---|
| `vehicleId` | `"{agencia}_{id}"`. **El `{id}` es el mismo id de vehículo que la API CABA** (`708_97938` ↔ CABA `97938`). | Clave de cruce con las grabaciones CABA. |
| `location` | **GPS real** (última posición reportada; igual a `tripStatus.lastKnownLocation`). | Es lo que hay que grabar. |
| `lastUpdateTime` | ms. **Hora del último reporte real del coche, con o sin trip.** | Confiable. Coches con trip: el GPS se refresca cada ~2–2,5 min por coche, con edad mediana de ~160 s. Sin trip y reportando: 1–35 s. |
| `lastLocationUpdateTime` | — | **Siempre 0. No usar.** |
| `phase`, `status` | — | Vacíos sin trip. |
| `tripId` | `"{agencia}_{trip}"` o `""`. | **No sirve para decidir la línea** (§6). |
| `tripStatus` | Solo si tiene trip; si no, `null`. | Ver abajo. |

`tripStatus` (solo coches con trip):

| Campo | Qué es |
|---|---|
| `vehicleLabel` | `"{interno}-{sufijo}"`: **el label, la única forma de saber la línea**. Sin trip no viene y hay que sacarlo del registro (§5). |
| `position` | **Posición predicha** por OBA (extrapolada sobre SU recorrido según horario y desvío). Cambia en cada request. **No es GPS.** |
| `lastKnownLocation`, `lastKnownOrientation`, `orientation` | Último GPS y rumbo. |
| `scheduleDeviation` | Segundos de atraso (+) o adelanto (−) contra el horario. |
| `distanceAlongTrip`, `scheduledDistanceAlongTrip`, `totalDistanceAlongTrip` | Metros sobre el recorrido de OBA. |
| `nextStop`, `nextStopTimeOffset`, `closestStop`, `closestStopTimeOffset` | Próxima parada y ETA a ella **según OBA**: la "predicción" de CuandoSubo. |
| `predicted` | `true` si hay tiempo real aplicado. |
| `serviceDate`, `activeTripId`, `blockTripSequence`, `frequency`, `situationIds` | Metadatos del viaje. |

En `references.trips[]` y `references.routes[]` vienen `routeId`, `tripHeadsign`, `directionId` y `shortName` de la ruta (ej. "65A").

### 3.3 Otros
| Recurso | Uso |
|---|---|
| `vehicle/{agencia}_{id}` | Un coche suelto, con los mismos campos. |
| `routes-for-agency/{agencia}` | Rutas de la agencia (`shortName`, `id`). |
| `routes-for-location?lat=&lon=&query=124` | Encontrar bajo qué agencia tiene OBA una línea (ej. el 124 está en `6_1649`). |
| `trips-for-route/{ruta}?includeStatus=true` | Viajes activos de una ruta y si tienen vehículo. Para el 124 y el 25 hay viajes **sin vehículo**. |
| `stops-for-route/{ruta}` | Paradas de una ruta (con agrupaciones por sentido). Estables: alcanza con un snapshot mensual. |
| `arrivals-and-departures-for-stop/{parada}` | **Predicciones por parada:** `predictedArrivalTime` / `scheduledArrivalTime`, `vehicleId`, `tripStatus.vehicleLabel`, `routeShortName`, `numberOfStopsAway`. Es la fuente para comparar ETA de CuandoSubo contra el modelo propio. |
| `trip/{id}`, `current-time` | Auxiliares. |
| `gtfs_realtime/vehicle-positions-for-agency/{agencia}` | Los mismos datos que `vehicles-for-agency` en GTFS-RT; `timestamp` = `lastUpdateTime`. **Sin label ni patente.** No aporta nada nuevo. |
| `gtfs_realtime/trip-updates-for-agency/{agencia}` | Predicciones en formato GTFS-RT. Para las agencias 6 y 11 (viajes del 124 y el 25) devuelve **0 entidades**. |

## 4. Límites: el WAF de SUBE

- **Los requests en paralelo disparan el WAF:** devuelve HTTP **302 "Security Redirect"**, también vistos como 301/303/307/403/429, redirect opaco o HTML en vez de JSON.
- **Regla que funcionó sin un solo bloqueo en miles de requests:** todo **secuencial**, **≥ 3 s entre requests** (3,5 s en barridos largos), y ante cualquiera de esas respuestas **pausa de 2 min** antes de seguir.
- **Presupuesto que sale de eso:** unos 17–20 requests por minuto. Un barrido de las 189 agencias tarda **~11 min**. **No se puede** muestrear todo AMBA cada 30 s: hay que priorizar (ver README §4).
- **Overpass/OSM no tiene nada que ver con esto.**
- Errores de red propios (DNS de Docker): fijar `dns: [1.1.1.1, 8.8.8.8]` en el compose si los registros SRV o la resolución fallan dentro del contenedor.

## 5. Identidad: de vehículo a línea

1. `id` = `vehicleId` sin el prefijo de agencia.
2. **Label:**
   - si viene `tripStatus.vehicleLabel`, se usa ese;
   - si no, sale de **`referencia/datos/registry.json`** (id → label, 36.433 ids armados con 186 días de API CABA, de abril a octubre de 2026);
   - si tampoco está ahí, se usa lo aprendido en vivo (labels vistos con trip, que se persisten).
3. **Línea** = sufijo del label → `LABEL_LINE_MAP.json` a la fecha (`proyectoconsola/`, con vigencias), más `referencia/datos/label_line_map_overrides.json` (corrección del 26: Nuevos Rumbos desde 2026-09-18; agencias OBA extra para 124, 25 y 84).
4. **Invariantes verificados:**
   - un id **nunca** cambió de label: 0 conflictos en 36.433 ids;
   - el id representa "coche × línea": el mismo bus en otra línea tiene otro id. Por eso las patentes se mueven entre ids (casos reales: PEJ023 del 64 al 124, PNN487…).
5. **Patentes:** CuandoSubo **no las manda**. Salen del registro por id, así que solo existen para ids de la era de la API CABA. Hoy, con la API CABA activa, se pueden cruzar en vivo con el id.
6. **Nunca** usar `tripId` ni la ruta de OBA para decidir la línea (§6).

## 6. Calidad de los datos: qué falta y por qué

Medido el 2026-10-20:

| Línea | Qué pasa en CuandoSubo | Causa |
|---|---|---|
| **124, 25** | **No aparecen.** 0 coches en todo el país, bajo ningún prefijo. | El mapeo de Nación empresa → agencia quedó roto con las fusiones y cambios de operador de junio de 2026 (la agencia 705 fue borrada; la 7 está vacía). CuandoSubo **descarta esos coches al ingerirlos**. Sus viajes siguen colgados de agencias viejas (6 y 11) y no tienen tiempo real. En la API CABA del 14/10 sí transmitían (31.335 y 23.006 updates), pero sin ningún `trip_id`. |
| **151** | Aparece en la agencia 708, pero **solo 9 de 77 coches reportan**, y sin trip propio. | No tiene rutas propias en el bundle: Nación le asigna **viajes del 65** (rutas 91–94 = 65A/65B, mismos `trip_id`). Con la API CABA eran ~36 contra 33 del 65. |
| **84** | En la agencia 706: 49 coches listados, **1 reportando**. | Le asigna viajes del **115** (ruta 82 = 115A). |
| 39, 12, 26, 65 | Bien. | — |
| En general | 312 coches vivos con el trip de **otra línea** (ej. 148 → 197, 7 → 50). | Mismo problema de mapeo. |

**Artefactos del servidor que hay que filtrar:**
- **Saltos en lote:** el servidor reacomoda registros viejos todos a la vez. Se ven coches que "saltan" 2–7 km **sin cambiar `lastUpdateTime`**, todos en la misma foto. **Regla:** posición nueva con la misma `lastUpdateTime` que antes = artefacto, no movimiento.
- **Hora compartida en lote:** varios coches con exactamente el mismo `lastUpdateTime` (incluso de líneas distintas). No es un reporte propio de cada coche.
- **Heartbeat de guardados:** coches quietos que actualizan `lastUpdateTime` sin moverse. Son coches en el depósito o la cabecera, reportando.
- **Ids fantasma** en dos agencias de la misma línea: quedarse con el registro más reciente.
- Basura vieja en el GTFS-RT: coches de hace semanas, algunos sin posición.

## 7. Endpoints de la API CABA, para el cruce

`apitransporte.buenosaires.gob.ar/colectivos/vehiclePositions` (GTFS-RT, `client_id` / `client_secret`) trae **el mismo id de vehículo**, `label`, `license_plate`, `route_id` / `trip_id` (los mismos números que el bundle de Nación/OBA), posición y `timestamp`. Refresca cada ~60 s. Estuvo suspendida del 2026-10-15 al 2026-11-10.
