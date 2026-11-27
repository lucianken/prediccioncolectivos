> Copia del estudio original (`proyectoconsola/OBA_IDENTIFICACION.md`, 2026-10-19). Las secciones de "diseño propuesto / NO implementado" están implementadas en este repo (bondiradar). Los paths relativos se refieren al monorepo local Dondeestaelbondi.

# Identificación de vehículos vía CuandoSubo (OneBusAway) tras la caída de la API CABA

> Estudio del 2026-10-19. Contexto, mediciones, invariantes, diseño propuesto y código para reproducir.
> **Estado: estudio terminado, NADA implementado en la consola todavía** (`server.js` sigue apuntando a la API CABA).

---

## 0. TL;DR

1. La API CABA (`apitransporte.buenosaires.gob.ar`) **cayó y no vuelve**. Era la única fuente con `VP_label` en todos los vehículos.
2. CuandoSubo (OBA) **usa el mismo vehicle id**: `708_93193` en OBA = `93193` en CABA. El prefijo es el agencyId (los agencyId de OBA = los de CABA / LABEL_LINE_MAP).
3. OBA **sí trae el label**, en `tripStatus.vehicleLabel`, pero **solo cuando el vehículo tiene trip asignado** (~30% de la flota). Coincide 100% con el label CABA (6.078/6.078).
4. Los vehículos **sin trip** (la app de CuandoSubo no los muestra, ej. todo el 151) siguen apareciendo en `vehicles-for-agency` con posición. Se identifican con un **registro `id → label`** construido de las grabaciones NDJSON (186 días).
5. **Invariante clave**: un `id` **nunca** cambió de label (36.432 ids, 185 días). El `id` representa *vehículo × registro en una línea*: si el mismo bondi físico hace otra línea, reporta con **otro id y otro label**. Por eso `id → línea` no deriva.
6. Corte de frescura: **`currentTime − lastUpdateTime ≤ 5 min`** = vivo. Más que eso = parado / stale.
7. Cadena final: `OBA vehicleId → id → label (vivo de tripStatus, o registro) → sufijo → LABEL_LINE_MAP → línea`. **Nunca usar el trip/route de OBA para decidir la línea** (está mal en cientos de casos). El ramal sigue siendo tarea del RamalEngine (el label da línea, no ramal).

---

## 1. Fuentes de datos

### 1.1 API CABA (muerta)
- Proxy en `server.js` → `/api/vehiclePositions` (formato GTFS-RT JSON: `_entity[]._vehicle{_vehicle{_id,_label,_license_plate}, _position, _trip{_route_id,_trip_id,...}, _timestamp}`).
- `VP_label` = `{interno}-{sufijo}`; el sufijo identifica la línea/flota (ver `CLAUDE.md` y `LABEL_LINE_MAP.json`).
- `VP_route_id` era el mismo numerito que usa OBA (`93` ↔ `708_93`). **Ya tenía el mismo problema que OBA**: los route_id de 65 y 151 (91–94) se mezclaban; el label los separaba (igual que 19/133/140/184).

### 1.2 Grabaciones NDJSON (verdad histórica)
- Ubicación: **`Z:\grabaciones\YYYY-MM-DD.ndjson.gz`** (unidad mapeada al NUC; también en el NUC `/mnt/buffer/grabaciones`). 186 días: **2026-03-28 → 2026-10-15** (último día antes de la caída). Copias sueltas del 14 y 15/10 en la raíz del repo.
- ~150–200 MB gz/día, ~4.400 vehículos por keyframe (todo el país).
- Formato (ver skill `grabador_nuc.md`):
  - Keyframe (cada ~10 min o tras reinicio): `{"t":..., "keyframe": true, "new":[{vehículo completo}], ...}`
  - Delta (cada 30 s): `{"t":..., "new":[...altas completas...], "del":[ids], "upd":[{id, ts, ...SOLO campos que cambiaron}]}`
  - **Trampa**: `upd` es parcial (ej. `{"id":"3820","ts":..., "lat":-34.49}` sin `lon`). Para reconstruir posiciones hay que mantener estado por id.
  - Vehículo completo: `id, label, license_plate, route_id, trip_id, direction_id, start_date, start_time, lat, lon, speed, odo, stop_id, seq, status, ts`. **No hay agency_id.**
- Leer solo label/patente: filtrar líneas con `'"new": [{' in line[:100]` (keyframes + altas). ~17 s/día en Python.

### 1.3 CuandoSubo / OneBusAway (fuente viva)
- Base: `https://cuandosubo.sube.gob.ar/onebusaway-api-webapp/api/where`
- Key: `key=<OBA_KEY>` (la de la app Android; también en `ejemplos/example apis.txt`).
- Endpoints usados:

| Endpoint | Uso |
|---|---|
| `agencies-with-coverage.json` | lista de agencias (todo el país) |
| `agency/{id}.json` | nombre de la agencia |
| `routes-for-agency/{id}.json` | rutas del GTFS estático de OBA (desactualizado, ver §3.3) |
| `vehicles-for-agency/{id}.json` | **el importante**: todos los vehículos de la agencia, con o sin trip |
| `vehicle/{agency}_{id}.json` | un vehículo |

- **WAF / rate limit**: 8 requests en paralelo → a partir de ~100 agencias todas devuelven `302 Security Redirect` (loop). Se recupera tras ~2 min de pausa. Secuencial con **3 s entre requests** bajó las 72 restantes sin un solo fallo. **Nunca paralelizar.** Un barrido completo (172 agencias AMBA) ≈ 9–10 min → no sirve para tiempo real del feed completo; sí para una agencia/línea a la vez.
- Respuesta trae `currentTime` (ms) a nivel raíz: usarlo como "ahora" para la frescura (no el reloj local).
- En el fuente local `onebusaway-application-modules/` (clon parcial, solo `transit-data-federation`, sin `vehicleLabel`) el `VehicleStatusBean` arma `tripStatus` solo si hay block/trip (`VehicleStatusBeanServiceImpl.java` ~L240). La versión que corre SUBE es más nueva (expone `vehicleLabel`).

---

## 2. Anatomía de `vehicles-for-agency`

```json
{
  "code": 200, "currentTime": 1792453277725,
  "data": {
    "list": [
      {
        "vehicleId": "708_97016",                 // {agencyId}_{id CABA}
        "lastUpdateTime": 1792453583000,          // ms; frescura = currentTime - esto
        "lastLocationUpdateTime": 0,              // siempre 0, no sirve
        "location": {"lat": -34.627, "lon": -58.378},   // null en algunos fantasmas
        "tripId": "708_10389-1",                  // "" si no tiene trip
        "phase": "", "status": "",                // siempre vacíos
        "tripStatus": {                           // null si no tiene trip
          "vehicleLabel": "455-4852",             // ★ EL LABEL (mismo que VP_label CABA)
          "vehicleId": "708_97016",
          "activeTripId": "708_10389-1",
          "position": {...}, "lastKnownLocation": {...}, "orientation": 182.5,
          "distanceAlongTrip": 623.4, "totalDistanceAlongTrip": 18976.8,
          "scheduleDeviation": -76, "predicted": true,
          "closestStop": "14_201526", "nextStop": "14_2087", "nextStopTimeOffset": 73,
          "serviceDate": 1792378800000, "blockTripSequence": 0, "status": "default"
        }
      }
    ],
    "references": {
      "trips":  [{"id":"708_10389-1","routeId":"708_93","directionId":"0","shapeId":"14_93",
                  "blockId":"708_0776HI0204","tripShortName":"10776HI0204","tripHeadsign":"a Bcas. de Belgrano","serviceId":"14_1"}],
      "routes": [{"id":"708_93","shortName":"65A","longName":"JCCABA065", ...}],
      "agencies": [...], "stops": [...], "situations": []
    }
  }
}
```

- `routeId` OBA `708_93` ↔ `VP_route_id` CABA `93`. `trip_id` CABA `10389-1` ↔ OBA `708_10389-1`.
- `references.routes` incluye rutas de otras agencias (vehículos que el feed cruza) — no asumir que todas son de la agencia pedida.

---

## 3. Mediciones (snapshot 2026-10-19 ~20:41–20:50, 172 agencias AMBA del map)

### 3.1 Cruce de ids
- 20.900 vehículos OBA. **Los 77 vehículos del 151 grabados el 14–15/10 están todos en `vehicles-for-agency/708` con el mismo id.**
- 362 ids aparecen en >1 agencia: todos fantasmas viejos (>2 días sin update) del operador anterior.

### 3.2 `vehicleLabel`
- 6.260 vehículos con `tripStatus` → **6.260 con `vehicleLabel`**.
- De esos, 6.078 tienen id en las grabaciones → **6.078 labels idénticos** (0 discrepancias). 182 ids nuevos (no grabados) traen label igual → OBA aprende flota nueva sola.
- Sufijos de label no presentes en `lines` del map (pendientes/interior): 4882, 4886, 4918, 4916, 4820, 4863, ... → trabajo de `pending_label_work.json`, no del id.

### 3.3 OBA asigna mal la línea (GTFS de OBA desactualizado)
- Agencia 708 (La Nueva Metropol, hoy 65 y 151) en OBA tiene **solo rutas del 65** (`708_91..94`). El 151 no existe. Agencia 9 (vieja del 151) solo tiene 194.
- Los 151 que logran trip reciben trips `708_92/93` → la app los muestra como **65**.
- Vehículos vivos donde el trip de OBA es de **otra línea** que la del label (312 casos). Peores (línea real → OBA dice):
  - 343 → 304 (30 de 79 vivos), 422 → 311/329/288, 215 → servicios OE62/OE85/..., 148 → 197 (15 de 16), 7 → 50 (7 de 8), 133 → 184/19/140, 151 → 65, 379 → 341/391, 429 → 410, 263 → 266.
- **Conclusión: el route/trip de OBA no sirve para decidir línea.** Sirve el label.

### 3.4 Cobertura del enfoque (vivos ≤10 min, 8.008 vehículos)

| Situación | n | Línea resuelta |
|---|---|---|
| Con trip, label → línea AMBA | 6.036 | ✔ (label vivo) |
| Con trip, sufijo no en map | 214 | pendiente de map |
| **Sin trip, id en registro** | **1.627** | ✔ (registro) — invisibles en la app |
| Sin trip, sufijo no en map | 122 | pendiente de map |
| Sin trip, id desconocido | 9 | ✘ (agencia sí, línea no) |

- Líneas con flota grabada pero **0 vehículos en OBA** en las 172 agencias: **25** (44 coches) y **124** (53). No investigado (¿otra agencia OBA?).

### 3.5 Frescura (`currentTime − lastUpdateTime`)

| Población | n | Distribución |
|---|---|---|
| Con trip | 6.250 | min 64 s, p10 83 s, **p50 120 s**, p90 127 s, **máx < 5 min** (nada arriba) |
| Sin trip | 13.696 | sin pico; p10 10 min, p50 3 h, p90 10 días; 260 con < 30 s |

- OBA tiene ~2 min de latencia en los asignados y les **quita el trip a los ~5 min sin update** (por eso no hay asignados > 5 min).
- Experimento 2 fotos de la agencia 708 separadas 416 s:
  - edad ≤ 5 min: 31/35 se movieron 170 m–2 km (los 4 quietos: detenidos con GPS al día).
  - edad 5–10 min: 1/4 se movió (y en ese momento tomó trip).
  - edad > 10 min: casi ninguno se movió; algunos actualizan `lastUpdateTime` **sin moverse** (heartbeat de guardados). Unos pocos "despiertan" (arrancan servicio) y en la foto siguiente ya son frescos.
- **Regla: vivo ⇔ edad ≤ 5 min** (6 con margen). 10 min mete parados (652 sin-trip en 5–10 min en el barrido total).
- ⚠ Medido con una agencia, de noche, 2 fotos. Validar en hora pico con 3–4 fotos espaciadas de 1–2 agencias grandes (pocas requests).

---

## 4. Invariantes de identidad (de 185 días de grabaciones)

### 4.1 `id → label` es inmutable
- 36.432 ids, 2026-03-28 → 2026-10-15: **0 ids con más de un label**. Tampoco dentro de un mismo día.
- La renumeración de flota mayo–junio 2026 (ej. 151: sufijo 4045 → 4852) **creó ids nuevos**, no cambió labels de ids existentes.

### 4.2 El id NO es el coche físico: es *coche × registro en línea*
Agrupando por patente válida (`^[A-Z]{2}\d{3}[A-Z]{2}$|^[A-Z]{3}\d{3}$`) y mismo interno:

| Caso | Patentes |
|---|---|
| 1 solo id | 8.632 |
| Mismo interno, misma línea (renumeración) | 5.229 |
| **Mismo interno, OTRA línea, mismo operador** | **2.837** |
| Mismo interno, otra línea, otra agencia del map | 785 (probablemente grupos con varios agencyId; no verificado) |
| Distinto interno (patente compartida / mal cargada) | 1.096 |

Ejemplo `AG335KA`, interno 407: id `1892` = `407-290` (línea 372), id `2726` = `407-288`, id `2790` = `407-291` (línea 300); alterna entre días.

Mismo día (15/10, 831 de 15.473 patentes con >1 id):
- 305 secuenciales (cambio de línea a mitad de jornada),
- 407 superpuestos con uno stale (registro viejo colgado),
- 15 duplicados reales (misma posición, dos ids a la vez),
- 104 a km de distancia → **patente mal cargada**: la patente NO es identidad confiable (incluye `000000`, con espacios al final, etc.).

### 4.3 Consecuencia
- Si un operador manda un coche del 151 a hacer el 65, lo esperable (y lo observado en 2.837 patentes) es que reporte con el **id/label de su registro en el 65** → `id → línea` sigue siendo correcto.
- El registro **no deriva**: solo le faltan ids nuevos (primera vez que un coche se registra en una línea). Esos se completan cuando OBA les asigna cualquier trip (`vehicleLabel`).
- Riesgo no medido: operador que manda el coche a otra línea **sin reconfigurar** el equipo → el label miente. Solo detectable por geometría (ver §7).

---

## 5. Diseño propuesto (NO implementado)

### 5.1 Registro `VEHICLE_REGISTRY.json`
```json
{ "version": 1, "generated": "...", "source": "grabaciones NDJSON (Z:\\grabaciones)",
  "days": {"from": "2026-03-28", "to": "2026-10-15", "count": 186},
  "vehicles": { "93193": {"label": "433-4852", "plate": "AH846RP", "first_seen": "...", "last_seen": "...", "src": "caba"} },
  "conflicts": {} }
```
- Construcción única desde grabaciones (la API CABA no vuelve → no hay más días). Código en §8.1.
- Aprendizaje en vivo: cada `tripStatus.vehicleLabel` visto → upsert con `src: "oba"`. Si llega un label distinto para un id existente → **registrar en `conflicts`** (rompería el invariante §4.1; alertar, no pisar en silencio).
- Guardar la patente solo como dato informativo, nunca como clave.

### 5.2 Resolución por vehículo OBA
```
vid      = vehicleId.split('_',1)[1]          // id CABA
agency   = vehicleId.split('_',1)[0]
age      = currentTime - lastUpdateTime
if !location or age > 5 min        → descartar (stale/guardado)   [parámetro max_age]
label    = tripStatus?.vehicleLabel ?? registry[vid]?.label ?? null
line     = LABEL_LINE_MAP(suffix(label), fecha)  (labelLineMapUtil.buildSuffixEntries)
if !label → línea desconocida; si la agencia opera UNA sola línea en el map → esa; si no → "agencia X, línea ?"
ramal    → RamalEngine (geometría), NO el trip de OBA
trip OBA → solo informativo (route_id/trip_id para compatibilidad), nunca para línea
```

### 5.3 Adaptador en `server.js` (para cuando se implemente)
- `/api/vehiclePositions?agency_id=X` con fuente OBA (env `VP_SOURCE=oba`), devolviendo **el mismo formato GTFS-RT JSON que la API CABA** para que `main.js`, `map.html`, RamalEngine y el enrichment LD_ sigan sin cambios:
  - `_vehicle._vehicle._id` = vid, `_label` = label resuelto, `_license_plate` = registro
  - `_vehicle._position` = `{_latitude, _longitude, _bearing: tripStatus.orientation||0, _speed: 0}`
  - `_vehicle._timestamp` = `lastUpdateTime/1000`
  - `_vehicle._trip` = si hay trip: `{_route_id: routeId sin prefijo, _trip_id: tripId sin prefijo, _direction_id: trips[].directionId, _start_date: serviceDate→YYYYMMDD}`; si no, `null`
  - `_header._timestamp` = `currentTime/1000`
- Cache por agencia ≥ 25 s (una request por agencia por ciclo). Sin `agency_id` → no barrer las 172 agencias en vivo (WAF); devolver error o snapshot cacheado de un barrido lento en background (secuencial, 3 s entre requests).
- `map.html?agency_id=708&line=151` ya pide por agencia → funciona con una sola request.
- El label vivo y el registro se mergean en memoria y se persisten debounced.

---

## 6. Enfoques evaluados y descartados

| Enfoque | Por qué no |
|---|---|
| Confiar en trip/route de OBA | GTFS de OBA desactualizado: 151 no existe, 312 vivos en línea equivocada, 75% de los vivos del 151 sin trip |
| Mapping route_id → línea (como `ROUTE_AGENCY_MAP`) | route_ids compartidos entre líneas (65/151, 19/133/140/184, 343/304...) — ya era ambiguo en CABA |
| Patente como clave | ruidosa: 1.096 patentes con internos distintos, 104 casos de la misma patente a km de distancia el mismo día |
| Huella espacial aprendida (celdas ~150 m por línea desde grabaciones, clasificador naive Bayes por trayectoria) | No necesaria para identificar línea (el label alcanza). Útil solo para verificar label vs recorrido real (§7). Scripts empezados y abortados |
| Barrido completo en vivo | WAF de SUBE, ~10 min por barrido |

---

## 7. Pendientes / riesgos

1. **Validar corte de 5 min** en hora pico (3–4 fotos, 1–2 agencias grandes).
2. **Label vs operación real**: medir con geometría (trayectoria vs shapes/huella de la línea del label) cuántas veces un coche corre una línea distinta a la de su label. Es el único escenario de drift no cubierto.
3. Líneas **25 y 124** ausentes en OBA: buscar en qué agencia OBA aparecen sus ids (están en el registro).
4. Sufijos sin línea AMBA (214 con trip + 122 sin trip vivos): resolver con `scripts/resolve_pending.js`.
5. 9 vivos sin trip y sin id en registro: quedan "agencia X, línea ?" hasta que tomen trip.
6. Ramal: el label no lo da. RamalEngine (zonas de divergencia sobre shapes) sigue siendo el método; los route_ids de OBA tienen el mismo comportamiento que tenían los de CABA (mismos números) — el conocimiento de `RAMAL_RESEARCH.md` / bug Darwin aplica igual.
7. Mapas HTML locales (`file://`): los tiles de OSM devuelven 403 (sin referer) y CARTO pide API key → usar Esri `https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}`.

---

## 8. Código para reproducir

Los scripts del estudio vivieron en el scratchpad de la sesión (se pierden). Lo esencial:

### 8.1 Registro `id → label` desde grabaciones (Python, ~1 min/6 workers por 20 días)
```python
# build_registry.py  —  python -I build_registry.py Z:/grabaciones VEHICLE_REGISTRY.json
import json, gzip, sys, os, collections
from concurrent.futures import ProcessPoolExecutor
SRC, OUT = sys.argv[1], sys.argv[2]

def day(path):
    V = collections.defaultdict(lambda: {'lab': collections.Counter(), 'plate': None})
    with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if '"new": [{' not in line[:100]:      # solo keyframes/altas (upd es parcial)
                continue
            try: d = json.loads(line)
            except Exception: continue
            for v in d.get('new', []):
                if v.get('label'):
                    V[v['id']]['lab'][v['label']] += 1
                    if v.get('license_plate'): V[v['id']]['plate'] = v['license_plate']
    return os.path.basename(path)[:10], {i: (x['lab'].most_common(1)[0][0], x['plate']) for i, x in V.items()}

if __name__ == '__main__':
    files = sorted(os.path.join(SRC, f) for f in os.listdir(SRC) if f.endswith('.ndjson.gz'))
    reg, conflicts = {}, {}
    with ProcessPoolExecutor(6) as ex:
        for date, vs in sorted(ex.map(day, files)):          # merge cronológico
            for i, (lab, plate) in vs.items():
                r = reg.get(i)
                if r and r['label'] != lab:
                    conflicts.setdefault(i, []).append({'old': r['label'], 'new': lab, 'date': date})
                    r['label'] = lab
                if not r:
                    reg[i] = r = {'label': lab, 'plate': plate, 'first_seen': date, 'src': 'caba'}
                r['last_seen'] = date
                if plate: r['plate'] = plate
    json.dump({'version': 1, 'vehicles': reg, 'conflicts': conflicts}, open(OUT, 'w'))
    print(len(reg), 'ids,', len(conflicts), 'con cambio de label')   # esperado: 0
```

### 8.2 Descarga de agencias sin disparar el WAF
```python
import json, time, urllib.request
K = 'key=<OBA_KEY>'
B = 'https://cuandosubo.sube.gob.ar/onebusaway-api-webapp/api/where'
m = json.load(open('LABEL_LINE_MAP.json', encoding='utf-8'))
agencies = sorted({a['agencyId'] for e in m['lines'].values() for a in e['agencies']})   # 172 AMBA
for a in agencies:
    for att in range(4):
        try:
            raw = urllib.request.urlopen(f'{B}/vehicles-for-agency/{a}.json?{K}', timeout=60).read()
            open(f'veh/{a}.json', 'wb').write(raw); break
        except Exception:
            time.sleep(60 * (att + 1))      # 302 Security Redirect = WAF → esperar
    time.sleep(3)                            # NUNCA en paralelo
```
⚠ Leer las respuestas con `encoding='utf-8'` (en Windows el default cp1252 rompe con nombres de agencia).

### 8.3 Resolución de línea por vehículo
```python
DATE = '2026-10-19'
idx = {s['suffix']: ln for ln, e in m['lines'].items() for s in e['suffixes']
       if s['from'] <= DATE and (s['to'] is None or s['to'] >= DATE)}
reg = json.load(open('VEHICLE_REGISTRY.json'))['vehicles']
j = json.load(open('veh/708.json', encoding='utf-8')); now = j['currentTime']
for v in j['data']['list']:
    if not v.get('location') or now - v['lastUpdateTime'] > 5 * 60_000:
        continue                                              # stale
    vid = v['vehicleId'].split('_', 1)[1]
    label = (v.get('tripStatus') or {}).get('vehicleLabel') or reg.get(vid, {}).get('label')
    line = idx.get(label.rsplit('-', 1)[1]) if label and '-' in label else None
    # line == '151' → dibujar
```

### 8.4 Validación del invariante (re-correr si hay datos nuevos)
- `id → label`: por día, label dominante por id; contar ids con >1 label distinto en todo el período → debe dar 0.
- Patentes: agrupar por patente válida + interno; contar líneas distintas por patente (§4.2).
- Mismo día: por keyframe, patente → ids presentes; clasificar secuencial / superpuesto-stale / duplicado (<100 m) / patente errónea (km de distancia).

---

## 9. Referencias en el repo
- `LABEL_LINE_MAP.json`, `pending_label_work.json`, `js/labelLineMapUtil.js` — sufijo → línea por fecha.
- `ROUTE_AGENCY_MAP.json` — route_id → info (estático, construido con CuandoSubo; no resuelve línea por las ambigüedades de §3.3).
- `ejemplos/example apis.txt` — URLs OBA de ejemplo.
- `test/fixtures/vp_live.json` — formato API CABA a replicar.
- `../prediccion colectivos/legacy/analisis_flota/` — `fleet_db.json` (flota por patente, abril–mayo) y `collect.py` (lee `Z:\grabaciones`).
- Skills: `.claude/skills/enrichment_ramal.md`, `grabador_nuc.md`, `prediccion colectivos/docs_old/skills/168_ramal_analysis.md` (historia).

---

## 10. Investigación 2026-10-20: fuente del servidor, GTFS-RT y por qué faltan 151/124/25

**Servidor.** Base compatible con OBA ~2017 (1.1.17, dic-2017): sin `config.json` ni `vehicle-position-for-vehicle` (404 "no Action mapped"), y la exportación GTFS-RT sin el filtro de 10 min que se agregó después. Dos cosas no están en ninguna versión pública (revisadas 2011 → 2026-10): `tripStatus.vehicleLabel`, y coches SIN trip listados (por GTFS-RT, el OBA de 2017 descarta toda posición sin `trip_id`; el actual también). O sea: OBA viejo + agregados/ingesta no estándar (según el usuario, el sistema de flota es de un proveedor italiano). No es un fork público consultable.

**Campos (código de OBA, `VehicleStatusBeanServiceImpl.getStatusAsBean`).** `location` y `lastUpdateTime` salen del mismo `VehicleLocationRecord` (`currentLocation`, `timeOfRecord`). `tripStatus.position` = posición extrapolada/interpolada sobre el viaje; `lastKnownLocation` = último GPS real (= `location`). `lastLocationUpdateTime` llega siempre 0. bondiradar dibuja `location` (GPS real).

**`lastUpdateTime` SÍ es la hora del último reporte real, con o sin trip.** 12 fotos de la agencia 708 cada 30 s:
- sin trip: 56 eventos posición+hora cambian, 200 hora cambia sin moverse (heartbeat de guardados), 694 nada; coches sin trip reportando tienen edad 1–35 s (más fresca que con trip: 75–200 s).
- 12 "saltos" de 2–7 km **sin cambio de hora**, todos en la misma foto: reacomodo en lote del servidor sobre registros viejos (edad 25–55 min), no movimiento real. Varios coches comparten exactamente el mismo `lastUpdateTime` (valor escrito en lote).
- Con trip, el GPS real (`location`) cambia cada ~2–2,5 min por coche (mediana edad 160 s); `position` (predicha) cambia en cada foto.
- (La conclusión del 2026-10-19 "sin trip, lastUpdateTime no es la hora del GPS" estaba mal: salía de esos saltos en lote.)

**GTFS-RT de OBA**: `api/gtfs_realtime/{vehicle-positions|trip-updates}-for-agency/{agencia}.pbtext?key=` existen, no filtran por antigüedad; `timestamp` = `lastUpdateTime`, sin `vehicle.label` ni patente (mismos datos que la API JSON). `trip-updates` de las agencias 6 y 11 (donde OBA tiene los viajes del 124 y 25): **0 entidades** → esos viajes no tienen ningún dato en tiempo real. 704: solo rutas 12A/12B; 707: solo 100 y 134.

**Barrido completo (189 agencias, 22.516 coches, 8.193 con reporte ≤ 180 s):**
- **151**: de 77 coches listados, **9 reportaron en 6 min** (65: 49 de 60). Con la API CABA la proporción era ~36:33. Los datos no están en CuandoSubo.
- **124 / 25**: 0 coches en todo el país con los 53 ids conocidos del 124 (ni los del 25). La agencia 705 ya no figura en `agencies-with-coverage`; agencias 6 (5 coches viejos), 7 y 11 vacías.
- Prueba espacial: todos los coches frescos sobre los recorridos OSM del 151/124/25 pertenecen a líneas ya mapeadas que comparten corredor; **ningún sufijo desconocido**. Ids fuera del registro: líneas del interior (Tucumán, etc.), ninguno sobre esos recorridos.
- Validación espacial del mapa (124 sufijos con ≥ 5 posiciones frescas): mediana 0 % fuera del recorrido de su línea. Revisar: 4914→159 (77 % fuera, encaja con 197/98), 4893→51 y 4895→79 (~50 %); 4820→26 bien (7 %).
- Sufijos vigentes sin mapear: líneas provinciales > 199 (271, 299, 236, 269, 219, 300, 403…), fuera del producto.

**`trip_id`/`route_id` de la API CABA (grabación 2026-10-14; los ids son los del bundle de Nación = OBA):**

| Línea | updates | con `trip_id` | rutas (OBA) |
|---|---|---|---|
| 124 | 31.335 | **0** | — |
| 25 | 23.006 | **0** | — |
| 84 | 25.402 | 3.805 | solo 82 = `706_82` **115A** |
| 151 | 52.984 | 22.066 | 91–94 = `708_9x` **65A/65B** (mismos `trip_id` que coches del 65) |
| 39 (control) | 55.433 | 49.483 | 1932–1942 |

Ya antes de la caída, Nación no asignaba viajes propios a esas líneas: 151 y 84 toman viajes de la línea hermana del mismo operador; 124 y 25 nunca (sus rutas siguen bajo agencias viejas 6 / 11). La API CABA publicaba igual todos los coches transmitiendo (con o sin viaje); CuandoSubo solo los muestra si puede colgarlos de una agencia que conoce: 151 (708) y 84 (706) aparecen sin trip, 124 (705, borrada) y 25 (7, vacía) no.

**Prefijos huérfanos**: `vehicles-for-agency/X` responde para cualquier X (filtra por prefijo, no por la lista de cobertura). Probados todos los ids 1–999 fuera de `agencies-with-coverage` (751 + 700–783): **ninguno con coches**. → CuandoSubo descarta en la ingesta los coches de 124/25 (no quedan guardados bajo ningún prefijo); la causa es el mapeo empresa → agencia roto por fusiones/cambios de operador, que Nación no corrigió.

Conclusión: no hay endpoint ni identidad alternativa donde estén; 124 y 25 transmiten (estaban en la API CABA hasta 2026-10-15) pero CuandoSubo los descarta; 151 y 84 aparecen sin viaje y con pocos coches reportando.
