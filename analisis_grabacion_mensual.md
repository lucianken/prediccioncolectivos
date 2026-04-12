# Análisis: Costo de Grabar Posiciones CABA por un Mes

**Fecha de medición:** 2026-03-15
**Todos los números son de llamadas reales en vivo.**

---

## 1. Datos base medidos

### Un ciclo completo (104 agencias sub-200, serie)
| Métrica | Valor |
|---------|-------|
| Agencias con líneas < 200 | 104 |
| Vehículos CABA activos (mañana domingo) | ~2.700–3.900* |
| JSON raw por ciclo | 2,29 MB |
| Tiempo del ciclo serial | 3,9 s |
| Factible en 30s | ✅ usa 13% del intervalo |

*Varía según horario: mañana domingo 2.700, pico laboral estimado 4.500-5.500.

### Formatos de descarga (llamada sin filtro, todos los vehículos)
| Formato | Tamaño respuesta | Tiempo |
|---------|-----------------|--------|
| JSON (`&json=1`) | 3.741 KB | 1.010 ms |
| **Protobuf** (default) | **617 KB** | **250 ms** |
| Ratio | **16,5% del JSON** | **4x más rápido** |

**Protobuf es 6x más chico y 4x más rápido que JSON.**

---

## 2. Estrategia de llamadas

### Opción A — 104 calls/ciclo por agencia (medido)
- Descarga solo los ~2.700–3.900 vehículos CABA
- 104 × 86.400 = **8,9 millones calls/mes** → riesgo de throttle/bloqueo

### Opción B — 1 call/ciclo sin filtro + filtrar local ✅
- JSON: 3,7 MB descargados, ~2,3 MB útiles (CABA)
- Protobuf: **617 KB** descargados, filtramos a CABA (~260 KB útiles)
- 86.400 calls/mes
- Protobuf + filtro local = **mínimo ancho de banda + mínimas llamadas**

**Recomendación: 1 call/ciclo en protobuf, filtrar localmente.**

---

## 3. Análisis delta (medición real: dos snapshots a 31s de diferencia)

### Qué cambia entre intervalos

| Campo | Vehículos que cambian | % |
|-------|----------------------|---|
| timestamp | 2.536 | 95,2% |
| lat | 2.418 | 90,8% |
| lon | 2.408 | 90,4% |
| odometer | 2.295 | 86,2% |
| speed | 2.163 | 81,2% |
| stop_id | 1.691 | 63,5% |
| current_stop_sequence | 1.690 | 63,5% |
| trip_id | 26 | 1,0% |
| current_status | 25 | 0,9% |
| route_id | 24 | 0,9% |
| start_time | 22 | 0,8% |
| direction_id | 11 | 0,4% |
| label | 0 | 0% |
| license_plate | 0 | 0% |
| bearing | 0 | 0% |
| occupancy_status | 0 | 0% |
| congestion_level | 0 | 0% |

**Hallazgos clave:**
- El 97,9% de los vehículos cambia algo por intervalo → los deltas no son tan dramáticos
- 7 campos son dinámicos (cambian > 1% de vehículos): lat, lon, timestamp, odometer, speed, stop_id, stop_sequence
- 13 campos son casi estáticos: label, license_plate, bearing, occupancy, congestion **nunca cambiaron** en la muestra
- bearing = 0 en todos los casos (la API BA parece no actualizar este campo)

### Vehículos apareados/desaparecidos por ciclo
- Nuevos: 31 vehículos (1,1%)
- Borrados: 42 vehículos (1,6%)
- Sin cambio alguno: 57 vehículos (2,1%) — en delta: skip completo

---

## 4. Tamaños de almacenamiento y por qué el binario custom es frágil

### Cómo funciona un struct binario fijo

En un struct fijo no hay separadores entre campos: la posición en el buffer *es* el identificador.

```
byte 0-3   → vehicle_id   (siempre 4 bytes)
byte 4-5   → route_id     (siempre 2 bytes)
byte 6-9   → lat          (siempre 4 bytes)
...
```

Para leer el vehicle_id del vehículo #37: `buffer.readUInt32LE(37 * 61 + 0)`. Sin ambigüedad.

Los campos numéricos no tienen problema: route_id "2145" se guarda como el entero 2145 en 2 bytes. No importa si es 1 o 9999, siempre ocupa 2 bytes exactos.

### El problema de los strings

Los campos de texto son variables por naturaleza:

| Campo | Ejemplos reales | Problema |
|-------|----------------|---------|
| label | "3124-923", "55-1331" | longitud variable |
| license_plate | "OUL336", "AB123CD" | longitud variable |
| trip_id | "317228-1", "89043-2" | string, no número puro |
| stop_id | "6427100277" | 10 dígitos → no entra en uint32 (max 4.294.967.295) |

Para strings en un struct fijo hay tres opciones, todas con tradeoffs:
1. **Padding fijo**: reservar N bytes, rellenar con ceros. Funciona hasta que un valor supera N.
2. **Convertir a número**: trip_id "317228-1" → guardar solo 317228 como uint32. Implica decisiones de diseño y pérdida del sufijo.
3. **Hash**: `hash("6427100277") % 2^32` → siempre 4 bytes, pero riesgo teórico de colisión.

### El fallo es silencioso

Este es el problema crítico para un sistema desatendido: **el binario custom no falla ruidosamente, falla silenciosamente**.

Si un día el API devuelve un stop_id con 11 dígitos en vez de 10, un uint32 lo trunca sin tirar error. El grabador sigue corriendo. Al final del mes tenés datos corruptos sin saber en qué frame ocurrió.

Lo mismo aplica al delta: los valores de los campos que cambian siguen necesitando ser encodeados con tamaño fijo, el problema no desaparece.

### Registro binario completo (20 campos, estructura fija) — referencia teórica
```
vehicle_id        4 bytes  uint32
route_id          2 bytes  uint16
trip_id           4 bytes  uint32  ← asume que solo importa la parte numérica
direction_id      1 byte
start_date        3 bytes
start_time        3 bytes
schedule_rel.     1 byte
lat               4 bytes  int32 microgrados
lon               4 bytes  int32 microgrados
speed             1 byte   uint8 (m/s × 10)
bearing           2 bytes  uint16
odometer          4 bytes  uint32
stop_id           4 bytes  uint32  ← puede truncar si supera 4.294.967.295
timestamp         4 bytes  uint32
current_status    1 byte
stop_sequence     2 bytes  uint16
occupancy_status  1 byte
congestion_level  1 byte
label             8 bytes  ASCII fijo
license_plate     7 bytes  ASCII fijo
─────────────────────────
TOTAL             61 bytes/vehículo
```

Frame completo: 2.694 veh × 61 bytes = **160 KB**

### Frame delta binario (referencia teórica)
- ID (4) + bitmask (3) + campos cambiados (lat/lon delta int16 = 2 bytes c/u)
- Vehículo típico en movimiento: **~21 bytes**
- Vehículo sin cambios: 0 bytes (skip)
- Frame delta medido: **55,9 KB** (34,9% del frame completo)
- Reducción por delta: **65,1%**

---

## 5. Proyección mensual — todos los escenarios

**Ciclos/mes:** 86.400 (cada 30s, 30 días)
**Keyframe cada 10 min** (20 intervalos) = 4.320 keyframes + 82.080 deltas

| Estrategia | KB/frame | GB/mes | Robustez |
|-----------|---------|--------|----------|
| JSON raw (descarga) | 3.741 | 324 | — (solo descarga) |
| Protobuf (descarga) | 617 | 53,3 | — (solo descarga) |
| Protobuf CABA guardado directo | ~260 | ~22,5 | ✅ estándar GTFS-RT |
| Binario custom completo | 160 | 13,2 | ⚠️ falla silencioso |
| Binario custom delta | 55,9 | 5,0 | ⚠️ falla silencioso |
| Binario mínimo (18b/veh, 6 campos) | 47 | 3,9 | ⚠️ falla silencioso |
| **NDJSON delta + gzip** | **~50** | **~4,3** | **✅ robusto** |
| TimescaleDB comprimido | ~13 | ~1,1 | ✅ robusto |

### ¿Por qué NDJSON delta + gzip es similar al binario?

El JSON es repetitivo (mismas keys, valores parecidos entre frames), y gzip explota esa repetición. Una línea de delta para un vehículo en movimiento en JSON puro:

```json
{"id":"1839","lat":-34.6402,"lon":-58.5525,"spd":8.3,"odo":30350,"sid":"6427100277","seq":12}
```

~90 bytes en texto → ~25-30 bytes después de gzip sobre el archivo completo. Comparable al binario custom.

### ¿Cuánto ocupa 1 año?
| Estrategia | Año 1 | Robustez |
|-----------|-------|----------|
| Protobuf CABA directo | 270 GB | ✅ |
| Binario completo | 158 GB | ⚠️ |
| Binario delta | 60 GB | ⚠️ |
| **NDJSON delta + gzip** | **~52 GB** | **✅** |
| TimescaleDB | ~13 GB | ✅ |

---

## 6. Formato de almacenamiento recomendado: NDJSON delta + gzip

Un archivo por día. Cada línea es un frame JSON con timestamp + vehículos nuevos, borrados y actualizados:

```
{"t":1773583200,"new":[{...vehículo completo...}],"del":["5521","8832"],"upd":[{"id":"1839","lat":-34.6402,"lon":-58.5525,"spd":8.3}]}
{"t":1773583230,"new":[],"del":[],"upd":[{"id":"1839","lat":-34.6404,"lon":-58.5522},...]}
```

**Por qué es robusto:**
- Si el API devuelve un campo nuevo o un stop_id inesperado, el JSON lo guarda tal cual. No hay overflow, no hay truncamiento.
- Si un frame falla (timeout, parse error), se loggea y se salta. El resto del mes sigue intacto.
- Inspeccionable con `zcat archivo.ndjson.gz | head` sin ninguna herramienta especial.
- Para reconstruir el estado en un momento T: último keyframe antes de T + replay de deltas hasta T.

**Cuándo usar protobuf directo en vez:** si querés que los datos sean consumibles por herramientas GTFS-RT estándar sin trabajo extra, a cambio de 5x más espacio.

**Cuándo usar TimescaleDB:** si necesitás queries SQL sobre los datos (ej: "dame todos los vehículos de la línea 60 entre las 8 y las 9hs del 10 de marzo"). Requiere más setup pero es la opción más potente para análisis.

---

## 7. Protobuf como formato de descarga (no de almacenamiento)

Protobuf es claramente superior a JSON para la **descarga** del API:
- 617 KB vs 3.741 KB (6x más chico)
- 250ms vs 1.010ms (4x más rápido)

Pero como formato de **almacenamiento** tiene desventajas:
- ~96 bytes/vehículo vs 61 bytes binario custom (por los tags de campos y mensajes anidados GTFS-RT)
- Incluye campos que siempre son 0 (bearing, occupancy, congestion)
- Para analytics hay que decodificar cada frame con la librería protobuf

**Conclusión:** bajar en protobuf siempre, guardar en NDJSON+gzip o TimescaleDB.

---

## 8. Stack de análisis y ML para predicción de horarios

### Los tres flujos son distintos

```
[1] GRABACIÓN          [2] ANÁLISIS / FEATURES      [3] INFERENCIA
    (cada 30s,              (batch, semanal               (runtime,
    append-only)             o mensual)                   por vehículo)
```

Cada flujo tiene requerimientos opuestos. Confundirlos lleva a sobreingeniería.

---

### Flujo 1 — Grabación (ver secciones anteriores)
NDJSON delta + gzip. Sin base de datos, sin servidor de DB, sin schema.

---

### Flujo 2 — Análisis y extracción de features: DuckDB + Parquet

Para entrenar un modelo de predicción necesitás queries analíticas sobre millones de registros: tiempos de viaje entre paradas, adherencia al horario, velocidades por segmento, etc.

**TimescaleDB** (Postgres + extensión de time-series) es excelente, pero está pensado para OLTP + time-series en producción: múltiples escrituras concurrentes, queries en tiempo real, continuous aggregates automáticos. Para análisis batch offline es overkill y requiere mantener un servidor Postgres corriendo.

**DuckDB** es una base columnar analítica (OLAP) diseñada exactamente para este caso:

```python
import duckdb

# Lee los Parquet directamente, sin importar nada
conn = duckdb.connect()
conn.execute("""
    SELECT
        vehicle_id,
        route_id,
        epoch(timestamp) AS t,
        lat, lon, speed
    FROM 'recordings/2026-03/*.parquet'
    WHERE route_id = 2145
    ORDER BY vehicle_id, timestamp
""").df()  # → DataFrame pandas listo para sklearn
```

- 130M registros/mes → query analítica en **2-4 segundos** (ejecución vectorizada)
- Lee Parquet/NDJSON/CSV directamente sin importar
- Cero servidor, binario embebido, Python/Node nativo
- `COPY TO 'features.parquet'` para exportar features al entrenamiento

**Pipeline completo de features:**
```
recordings/2026-03.ndjson.gz
    ↓  reconstruct_snapshots.py (replay keyframes + deltas)
snapshots.parquet
    ↓  extract_features.sql (DuckDB)
stop_arrivals.parquet     ← cuándo llegó cada vehículo a cada parada
travel_times.parquet      ← tiempo entre paradas por ramal/hora
schedule_adherence.parquet ← desvío respecto al horario teórico
    ↓  train.py (sklearn / lightgbm)
modelo.pkl
```

**¿Cuándo sí usar TimescaleDB?**
Si el sistema crece y necesitás:
- Continuous aggregates pre-computados (promedios de 5min automáticos)
- Múltiples procesos escribiendo simultáneamente
- La grabación y el análisis conviviendo en la misma DB
- API de consulta sobre datos recientes en tiempo real

Para la primera etapa (grabación + análisis offline + entrenamiento), DuckDB + Parquet es suficiente y más simple.

---

### Flujo 3 — Inferencia en runtime: modelo cargado en memoria

La predicción en producción es el caso más simple de los tres. Un nuevo vehículo llega con su posición actualizada y hay que predecir cuándo llega a la próxima parada.

**No necesita una DB compleja.** El modelo entrenado (sklearn, lightgbm, etc.) se carga una vez en memoria al arrancar el servidor y corre la inferencia localmente:

```javascript
// server.js — al arrancar
const model = await loadModel('modelo_linea39.pkl');  // ~MB, en RAM

// al recibir nueva posición de un vehículo
app.get('/api/prediccion/:vehicleId', (req, res) => {
    const vehicle = getLatestPosition(req.params.vehicleId);
    const features = extractFeatures(vehicle);  // velocidad, hora, segmento
    const eta = model.predict(features);         // inferencia local, <1ms
    res.json({ eta_segundos: eta });
});
```

- Inferencia < 1ms por vehículo (el modelo está en RAM)
- Sin llamadas a DB en el path crítico
- El modelo se re-entrena offline (flujo 2) y se despliega como archivo

**Qué necesita el servidor en runtime:**
- Posiciones actuales: ya las tiene (las descarga cada 30s del API BA)
- Modelo: archivo `.pkl` o `.onnx` cargado en memoria
- Datos estáticos de paradas/segmentos: JSON o SQLite en disco (solo lectura, pocas MB)

**Conclusión:** la complejidad está en la fase de entrenamiento (flujo 2), no en la inferencia. Un VPS de $6/mes aguanta perfectamente correr el modelo en producción.

---

## 9. Costo total mensual estimado

### Escenario recomendado: protobuf descarga + NDJSON delta + gzip + Backblaze B2

| Ítem | Costo/mes |
|------|-----------|
| VPS DigitalOcean São Paulo (1 vCPU / 1 GB RAM) | $6,00 |
| Almacenamiento B2 (~4,3 GB/mes, acumulado año 1: ~52 GB) | $0,31 |
| Descarga API BA Transporte (incluida en red del VPS) | $0 |
| Llamadas API (86.400/mes, sin límite documentado) | $0 |
| **Total** | **~$6,31/mes** |

---

## 10. Notas importantes

- **bearing siempre = 0** en los datos del API → la API BA no actualiza este campo, no guardar
- **occupancy_status y congestion_level siempre = 0** → ídem
- Los vehículos activos varían según horario: mínimo ~1.500 (madrugada), pico ~5.000 (hora pico laboral)
- La medición se hizo un domingo a la mañana — los números de pico serían mayores en días hábiles
- Para re-construir posición exacta de un vehículo en cualquier momento del mes: necesitás el último keyframe anterior + todos los deltas hasta ese punto (keyframe recomendado: cada 10 minutos)
- trip_id cambia ~26 vehículos/ciclo = cambios de turno/ramal → importante guardar cuando cambia
- Antes de implementar binario custom: medir `max(parseInt(stop_id))` sobre datos reales para confirmar si cabe en uint32

---

*Mediciones en vivo — 2026-03-15 — benchmark_results.json + benchmark_delta_results.json*
