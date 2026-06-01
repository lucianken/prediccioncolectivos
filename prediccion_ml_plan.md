# Plan ML/DL: Identificación de Ramal y Predicción de ETA

**Última actualización:** 2026-03-29
**Estado:** Research / Diseño — en espera de datos suficientes
**Prerequisito:** grabador-posiciones corriendo, mínimo 3 meses de grabación

---

## Revisiones importantes (leer antes que el resto)

Cuatro correcciones estructurales que cambian el diseño respecto a la versión inicial:

**1. Líneas comparten segmentos → el tráfico es geográfico, no por línea**

La línea 39, 64, 71, 99 y docenas más circulan por Av. Corrientes. Un embotellamiento en Corrientes afecta a todas. El estado de tráfico de un segmento se construye con los **vehículos de la agencia consultada (40-200 según la línea)**, no solo los del mismo ramal — y no con toda la flota (~5500), ya que el llamado filtrado por agencia es el único factible en producción. Esto enriquece el modelo de ETA y elimina el problema de "no hay vehículos de este ramal específico en ese segmento en este momento". Ver sección 7.

**2. La API actualiza cada 30 segundos — no cada segundo**

La resolución temporal es 30s. A 30 km/h, un vehículo se mueve ~250m por intervalo. Implicaciones:
- La velocidad reportada es un promedio sobre los últimos 30s, no instantánea
- No se puede detectar comportamiento fino (frenada en parada, arrancada)
- A 30 km/h un vehículo se mueve ~250m por ciclo — es el granulado mínimo observable en los datos
- Hay que modelar a nivel de segmento, no de parada individual

**3. El problema de ETA es 1D sobre el shape, no 2D en el mapa**

Con shapes precisos, todo el espacio GPS 2D colapsa a un escalar: distancia restante sobre la polilínea del ramal. El vehículo V proyectado sobre el shape tiene posición d_V metros desde el inicio. El target T (posición del usuario proyectada al shape, o parada conocida) tiene posición d_T. ETA = tiempo de recorrer (d_T − d_V) metros sobre ese shape. Las curvas, esquinas y cambios de dirección ya están incorporados en el shape. Si hay un desvío, la proyección falla silenciosamente (el sistema no colapsa, solo degrada la precisión). Ver sección 7.

**4. CABA tiene ~100 líneas**

- **Ramal ID (Modelo 1):** es inherentemente por línea. La estructura de ramales es específica de cada línea (la línea 39 tiene sus ramales, la 42 los suyos). Se resuelve con una lookup geométrica offline `route_id → shape` (módulo `ramal_lookup/`), no con ML. Aplicable solo a las líneas con shapes disponibles y múltiples ramales reales. El mapeo `VP_label → línea` ya está resuelto con LABEL_LINE_MAP.json y es robusto — es la base de este paso.

- **ETA (Modelo 2):** sí puede ser un modelo unificado para todas las líneas. El tráfico en un segmento geográfico es el mismo para todas las líneas que pasan por ahí. Ver sección 7.

---

## Índice

1. [Glosario de DL (leer primero)](#1-glosario-de-dl)
2. [Contexto: por qué OBA falla y qué ventaja tenemos](#2-contexto)
3. [Los datos que tenemos y cuándo son suficientes](#3-datos)
4. [Tres flujos independientes](#4-tres-flujos)
5. [Pipeline de datos: de NDJSON a entrenamiento](#5-pipeline)
6. [Modelo 1 — Identificación de ramal (lookup geométrica offline)](#6-modelo-ramal)
7. [Modelo 2 — Predicción de ETA](#7-modelo-eta)
   - [7b. Comparación de approaches A0–A3](#7b-comparacion)
8. [Reentrenamiento continuo y rotación de route_ids](#8-reentrenamiento)
9. [Hardware: qué podemos hacer con la RTX 3080](#9-hardware)
10. [Fases de implementación](#10-fases)
    - [10.1 Scope: 7 líneas es el punto de partida](#101-scope)
    - [10.2 Dependencia entre Modelo 1 y Modelo 2](#102-dependencia)
11. [Límites conocidos del sistema](#11-limites)

---

## 1. Glosario de DL

Estos términos aparecen en todo el documento. Referencia rápida para alguien sin background en DL.

**Red neuronal (neural network):** función matemática con muchos parámetros (pesos) que se ajustan durante el entrenamiento. Aprende a mapear inputs → outputs minimizando un error.

**Capa (layer):** bloque de operaciones matemáticas. Una red apila capas: cada una transforma el output de la anterior. Más capas = más capacidad de aprender patrones complejos = más datos necesarios.

**Transformer:** arquitectura de red neuronal basada en "atención" (attention). En vez de procesar una secuencia paso por paso (como un LSTM), procesa todos los pasos a la vez y cada elemento puede "mirar" a cualquier otro elemento directamente. En este plan se usa solo en Modelo 2 (ETA): como encoder de la trayectoria y del estado de flota, y como opción de Fase 5 (Seq2Seq).

**Self-attention:** mecanismo dentro del Transformer. Dado un conjunto de elementos (vehículos, puntos GPS), cada elemento aprende cuánto peso darle a cada otro elemento para producir su representación final. No está codificado cuáles son importantes — el modelo lo aprende.

**Embedding:** representación densa (vector de números) de algo discreto (un número de ruta, un día de la semana). El modelo aprende qué valores hacen sentido durante el entrenamiento. Por ejemplo, el embedding del "lunes" queda cerca del embedding del "martes" porque tienen patrones similares.

**Encoder:** parte de un modelo que convierte una secuencia de inputs en un vector compacto (embedding) que captura la información relevante.

**Epoch:** una pasada completa por todo el dataset de entrenamiento. Se entrena típicamente por 50-200 épocas.

**Batch:** subconjunto de ejemplos de entrenamiento procesados juntos. La GPU los procesa en paralelo. Batch size 64 = 64 ejemplos simultáneos.

**Loss / función de pérdida:** número que mide qué tan equivocado está el modelo. El entrenamiento consiste en reducir este número. Para clasificación (¿qué ramal?): cross-entropy. Para predicción de tiempo (ETA): MAE (error absoluto medio en segundos).

**Overfitting:** el modelo memoriza los datos de entrenamiento pero no generaliza a datos nuevos. Se detecta con un validation set (datos que el modelo no vio durante el entrenamiento). Se previene con dropout (apagar neuronas aleatoriamente) y early stopping (parar cuando el validation loss deja de mejorar).

**Fine-tuning:** en vez de entrenar desde cero, tomar un modelo ya entrenado y continuar el entrenamiento con datos nuevos. Mucho más rápido que reentrenar. Estándar para manejar distribución shift (por ejemplo, la rotación de route_ids cada 3 semanas).

**Inferencia:** usar el modelo entrenado para hacer predicciones sobre datos nuevos. Es rápida (<1ms) porque solo es una pasada forward por la red, no hay backpropagation.

**MAE (Mean Absolute Error):** error absoluto medio. Para ETA: si el modelo predice 8 min y el colectivo llegó en 10 min, el error es 2 min. El MAE es el promedio de estos errores sobre todo el dataset.

**VRAM:** memoria de la GPU (Video RAM). Limita el tamaño del modelo + batch size que caben simultáneamente. RTX 3080 tiene 10 GB.

**ONNX:** formato estándar para exportar modelos de ML/DL. Un modelo entrenado en PyTorch se exporta a ONNX y puede correrse en producción desde Node.js, Go, o cualquier runtime sin instalar PyTorch.

---

## 2. Contexto

### Por qué OBA falla

CuandoSubo/OneBusAway usa:
- Schedules teóricos (frecuencia, horario de salida) — incorrectos para CABA
- trip_headsign y stop_times del GTFS — datos no actualizados
- Posiciones GPS de algunos vehículos — sí tiene esto, pero sin contexto de tráfico

**El resultado:** predicciones que básicamente dicen "el próximo colectivo sale en N minutos según el schedule" sin importar que haya un embotellamiento en Corrientes o un paro parcial.

### Ventaja diferencial que tenemos

1. **GPS real de todos los vehículos simultáneamente**, cada 30 segundos, de forma indefinida. OBA tiene esto también pero no lo explota bien.

2. **Contexto de flota completa:** si 5 vehículos de la 39-1 están viajando a 8 km/h en un segmento específico en este momento, el próximo vehículo también va a viajar a ~8 km/h ahí. Nadie más modeliza esto.

3. **Sin dependencia de schedules:** el modelo aprende del comportamiento real, no del teórico.

4. **Identificación de ramal por geometría:** OBA asume que conoce el ramal (viene en el GTFS). Nosotros lo inferimos de los datos (lookup `route_id → shape`, módulo `ramal_lookup/`). Cuando los datos del GTFS son incorrectos, nosotros seguimos funcionando.

---

## 3. Datos

### Qué tenemos en cada ciclo de 30s

```
Por vehículo:
  id              str   — permanente mientras el vehículo exista en la API
  label           str   — "interno-sufijo", permanente por flota
  license_plate   str   — permanente
  route_id        str   — cambia cada ~3 semanas (rotación estacional)
  direction_id    int   — 0 o 1, ida o vuelta
  trip_id         str   — cambia al inicio de cada viaje (~26 veces por ciclo en toda la flota)
  lat, lon        float — posición GPS, 6 decimales (~10cm de precisión)
  speed           float — velocidad en m/s (de la API, no siempre confiable)
  stop_id         str   — DESCARTAR: datos obsoletos en la API
  seq             int   — DESCARTAR: ídem
  status          int   — 0=INCOMING_AT, 1=STOPPED_AT, 2=IN_TRANSIT
  ts              int   — unix timestamp de la posición
  start_date      str   — fecha de inicio del viaje
  start_time      str   — hora de inicio del viaje

Siempre 0, no guardar:
  bearing, occupancy, congestion, odometer
```

### Cuántos datos se acumulan

| Período | Vehículos/ciclo | Ciclos | Observaciones totales |
|---------|----------------|--------|----------------------|
| 1 mes | ~4.000 promedio | 86.400 | ~345 millones |
| 3 meses | ídem | 259.200 | ~1.000 millones |
| 6 meses | ídem | 518.400 | ~2.100 millones |

Para línea 39 específicamente (~40-60 vehículos activos en hora pico):
- 1 mes: ~50 veh × 86.400 ciclos = ~4.3 millones de observaciones de la línea 39

### Cuándo son suficientes para qué

| Tarea | Mínimo | Bueno | Óptimo |
|-------|--------|-------|--------|
| Ramal ID (Model 1) | 1-2 días por rotación | — | — |
| ETA con tráfico (Model 2) | 3 meses | 6 meses | 12 meses |

**Por qué 1-2 días para ramal ID:** la lookup `route_id → shape` no necesita meses de datos ni ver variación — solo acumular suficiente GPS por `route_id` dentro del período para que las métricas geométricas (containment/coverage/voto) converjan. Con 1-2 días post-rotación alcanza. No hay entrenamiento; se reconstruye en cada rotación.

**Por qué 3 meses para ETA con tráfico:** necesitás cubrir todos los patrones de hora (rush AM, midday, rush PM, noche) × días de semana × variación de congestion. 3 meses da cobertura razonable. 6 meses agrega fines de semana feriados, lluvia, etc.

---

## 4. Tres flujos independientes

Estos tres flujos tienen requerimientos completamente distintos. Mezclarlos es un error de diseño.

```
┌─────────────────────────────────────────────────────────────────────┐
│ FLUJO A — GRABACIÓN                                                  │
│   grabador.py corre en Ubuntu NUC                                    │
│   Protobuf → parse → delta → NDJSON.gz                             │
│   Output: /mnt/buffer/grabaciones/YYYY-MM-DD.ndjson.gz             │
│   Frecuencia: cada 30s, indefinidamente                             │
└─────────────────────────────────────────────────────────────────────┘
                    ↓ batch offline (mensual o bajo demanda)
┌─────────────────────────────────────────────────────────────────────┐
│ FLUJO B — ANÁLISIS Y ENTRENAMIENTO                                  │
│   Corre en Windows (RTX 3080) o Ubuntu                              │
│   NDJSON.gz → reconstruir snapshots → Parquet → DuckDB → features  │
│   → PyTorch → modelo.onnx                                           │
│   Frecuencia: cada ~3 semanas (rotación route_ids) o mensual        │
└─────────────────────────────────────────────────────────────────────┘
                    ↓ deploy modelo nuevo
┌─────────────────────────────────────────────────────────────────────┐
│ FLUJO C — INFERENCIA EN RUNTIME                                      │
│   server.js (proyectoconsola) carga modelo.onnx al arrancar         │
│   Cada refresh de vehículos: inferencia local <1ms/vehículo         │
│   Output: FP_ramal + ETA para cada vehículo, servido al frontend    │
│   Frecuencia: cada 30s                                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Pipeline de datos (Flujo B)

### Paso 1 — Reconstruir snapshots desde NDJSON

Los archivos `.ndjson.gz` contienen deltas. Para análisis necesitás snapshots completos (estado de todos los vehículos en cada timestamp).

```python
# reconstruct.py
# Input:  data/2026-03-01.ndjson.gz .. 2026-05-31.ndjson.gz
# Output: snapshots/2026-Q1.parquet (una fila por observación de vehículo)

import gzip, json, pandas as pd

def reconstruct_to_parquet(gz_files, output_parquet):
    state = {}
    rows = []

    for gz_file in gz_files:
        with gzip.open(gz_file, 'rt') as f:
            for line in f:
                frame = json.loads(line)
                if frame.get('gap'):
                    continue   # gap conocido, no contaminar

                for v in frame.get('new', []):
                    state[v['id']] = v.copy()

                for vid in frame.get('del', []):
                    state.pop(vid, None)

                for upd in frame.get('upd', []):
                    if upd['id'] in state:
                        state[upd['id']].update(upd)

                # Guardar snapshot completo en este timestamp
                t = frame['t']
                for vid, v in state.items():
                    rows.append({**v, 'snapshot_ts': t})

    pd.DataFrame(rows).to_parquet(output_parquet, compression='snappy')
```

Resultado: ~130M filas/mes en Parquet. Tamaño: ~800MB comprimido (Snappy es rápido).

### Paso 2 — Segmentación de viajes

Un "viaje" es una secuencia continua de observaciones de un vehículo con el mismo `trip_id`. Cuando cambia `trip_id`, el vehículo empezó un nuevo servicio.

```sql
-- DuckDB: segmentar viajes
SELECT
    id AS vehicle_id,
    trip_id,
    route_id,
    direction_id,
    label,
    lat, lon, speed, status,
    snapshot_ts,
    -- tiempo desde el punto anterior del mismo viaje
    snapshot_ts - LAG(snapshot_ts) OVER (PARTITION BY id, trip_id ORDER BY snapshot_ts) AS dt_seconds,
    -- distancia desde el punto anterior (proyectada en el shape del ramal)
    -- (calculada en Python después de proyectar, ver paso 3)
    ROW_NUMBER() OVER (PARTITION BY id, trip_id ORDER BY snapshot_ts) AS seq_in_trip
FROM snapshots
WHERE id IS NOT NULL AND trip_id IS NOT NULL
ORDER BY id, trip_id, snapshot_ts
```

Resultado: ~2 millones de viajes/mes en toda la flota. Para línea 39: ~5.000 viajes/mes.

### Paso 3 — Proyección sobre shape del ramal

Para ETA necesitás saber dónde está el vehículo **en la ruta** (no solo en el mapa). Se proyecta cada punto GPS sobre la polilínea del ramal y se calcula la distancia acumulada desde el origen.

```python
# project_on_shape.py
# Para cada punto GPS de un vehículo en el ramal R:
#   → encuentra el segmento más cercano de la polilínea R
#   → calcula distancia acumulada desde el inicio de la ruta
#   → calcula distancia perpendicular (qué tan lejos del shape)

import numpy as np

def project_point_on_polyline(lat, lon, shape_points):
    """
    shape_points: lista de (lat, lon) del shape del ramal
    Retorna: (distance_along_route_m, perpendicular_error_m, segment_idx)
    """
    # ... haversine + proyección línea segmento ...
    # Algoritmo ya implementado en ramal_engine.js, portar a Python
```

Este paso es computacionalmente intenso — ~500ms por viaje completo en Python puro. Paralelizable con multiprocessing. Total para 3 meses: ~30 horas en CPU (una sola vez).

### Paso 4 — Construir dataset de entrenamiento

#### Para Modelo 1 (ramal ID)

Modelo 1 **no entrena**, así que no necesita un dataset de entrenamiento. El módulo `ramal_lookup/` consume directamente los trips segmentados y proyectados: acumula los puntos GPS por `route_id` dentro del período y construye `ramal_map.json`. La única estructura intermedia es la evidencia por `route_id`:

```python
# ramal_lookup/route_lookup.py — RouteEvidence
{
    "route_id": "1973",
    "direction_id": 0,
    "n_trips": 14,
    "points": [(lat, lon), ...]   # GPS de todos los trips del route_id en el período
}
```

A partir de eso se calculan containment/coverage/voto y se asigna el shape (ver sección 6). No hay snapshots de flota, ni `route_id_rank`, ni labels — esos eran artefactos del transformer descartado.

#### Para Modelo 2 (ETA)

Schema del parquet `eta_train.parquet` / `eta_val.parquet`:

```
ramal_id             str
seg_idx              int32
dist_remaining_m     float32
dist_along_norm      float32
speed_mps            float32
hour_sin / hour_cos  float32    (encoding cíclico de la hora)
dow                  int8       (0=Lunes … 6=Domingo)
has_active_bus       bool
observed_eta_s       float32    (label)
time_since_start     float32
traj_flat            FixedSizeList<float32>[30]      (10 puntos × 3 features: dist_norm, speed, dt; paddeado con ceros)
traj_len             int8       (longitud real 1–10)
fleet_flat           FixedSizeList<float32>[N_FLEET*5]  (hasta N_FLEET buses × 5 features; paddeado con ceros)
n_fleet              int8       (vehículos reales activos)
```

Todas las columnas numéricas en float32. Las columnas FixedSizeList se leen con
`np.asarray()` sin pasar por Python (zero-copy del buffer Arrow contiguo).

---

## 6. Modelo 1 — Identificación de Ramal

> **No es un modelo de ML.** Es una lookup geométrica offline. Ver el módulo `ramal_lookup/` y `research_ramal_id_approaches.md` para el detalle completo.

### El problema, bien planteado

El planteo original ("dado un snapshot de la flota, ¿qué ramal es cada vehículo?") trataba esto como una clasificación en tiempo real. Es el planteo equivocado. La observación clave (validada sobre 62 días, ver `research_direction_routeid.md`) es:

- `route_id` mapea **1:1 a un shape físico dentro de un período** (~2-3 semanas), y a una única `direction_id`.
- El `route_id` se resetea en cada rotación (~cada 2-3 semanas): los mismos ramales físicos reciben números nuevos.

Por lo tanto el problema **no es clasificar GPS en tiempo real, sino construir y mantener offline una lookup `route_id → shape`**. En tiempo real, identificar el ramal de un vehículo es un `lookup[route_id]` O(1), sin GPS ni inferencia.

### Por qué se descartó el Fleet-level Transformer

El plan original proponía un transformer cross-flota entrenado con labels generados por el algoritmo geométrico. Se descartó por tres razones: (1) **dependencia circular** — si el algoritmo geométrico funciona como oráculo de labels, no hace falta el transformer; si no funciona, no hay labels; (2) **overkill** — resolver una lookup 1:1 por período no requiere una red neuronal; (3) **costo operacional** — entrenar, fine-tunear por rotación, exportar ONNX y monitorear drift, todo para un problema que se resuelve con geometría determinística. La inferencia por asociación de flota que motivaba el transformer es innecesaria: el `route_id` ya identifica el ramal desde el primer snapshot.

### El módulo `ramal_lookup/` (Enfoque C)

Construye `ramal_map.json` (la lookup `route_id → shape`) acumulando offline los GPS de todos los viajes de cada `route_id` y asignándole un shape. Es puramente geométrico, determinístico y sin entrenamiento. Para cada `route_id`:

1. **Filtrar candidatos por `direction_id`** — reduce los shapes de la línea a la mitad, gratis.
2. **Proyectar** todos los puntos GPS acumulados sobre cada shape candidato (`prediccion/pipeline/projector.py`), obteniendo error perpendicular y distancia sobre el shape.
3. **Calcular dos métricas ortogonales por shape:**
   - `containment` = fracción de puntos con perp < 30m → ¿el bus encaja sin salirse del shape?
   - `coverage` = rango p2/p98 de dist_along / largo del shape → ¿el bus llena el shape de punta a punta?
4. **Discriminar entre completos** (A/B/C, que comparten ~80% del recorrido) por **voto-por-punto** (cada GPS vota al shape de menor perp; el margen del ganador resuelve) y/o **cuantil p95 del perp** (ignora el troncal compartido, mira la cola discriminante).
5. **Discriminar completo vs fraccionado** (D⊆A, etc.) por `coverage`: un fraccionado llena su propio shape (~100%) pero solo cubre ~77% del padre. El `coverage_gap` contra el padre lo confirma. Las familias de fraccionados (qué shape es fracción de cuál) están en `families_{line}.json`.
   - **El MVP las define por conocimiento de dominio explícito** (escritas a mano por línea). Es lo implementado hoy.
   - **TBD:** podrían detectarse geométricamente offline desde las shapes solas (test de subset: shape S1 es fracción de S2 si todos sus puntos caen sobre S2 y `length(S1) < length(S2)`), eliminando el archivo manual. No implementado aún. Ver `research_ramal_id_approaches.md` §requisitos A/B.
6. **Gate de cold-start**: con menos de N viajes acumulados → `pending` en vez de resolver mal.

El detalle de por qué la media del perp no alcanza, y de las dos preguntas `containment`/`coverage`, está en `research_ramal_id_approaches.md`.

### Salida y mantenimiento

`ramal_map.json` guarda por entrada: `route_id`, `shape_key`, `assignment_type` (completo/fraccionado), `confidence`, `method`, y `first_seen`/`last_seen` para distinguir reusos del mismo número entre períodos. En cada rotación **se reconstruye la lookup** (no se reentrena nada): converge en 1-2 días de GPS acumulado. `build_ramal_map.py` es idempotente y lee GPS solo en los días con `route_ids` pendientes.

### Resultados (línea 39, 62 días, 3 períodos)

36/36 `route_ids` resueltos correctamente. Completos con confianza 0.89–0.98; fraccionados resueltos por su familia. Reemplaza al `RamalEngine` geométrico legacy (JS, en proyectoconsola), que no resolvía fraccionados ni la zona compartida de inicio de viaje.

---

## 7. Modelo 2 — Predicción de ETA

### El problema

Dado el vehículo V en la posición P del ramal R y el punto target T (parada del usuario proyectada sobre el shape), ¿cuántos segundos tarda en llegar a T?

### Por qué el modelo estadístico simple no alcanza

Un modelo que usa solo promedios históricos (velocidad media por segmento × hora del día) tiene MAE típico de 3-5 minutos en viajes de 30 min. Esto es comparable a OBA. El problema es que no ve el tráfico actual.

**La clave: usar velocidades observadas en tiempo real**

Si en los últimos 10 minutos, los 3 colectivos de la 39-1 que están delante de V pasaron por el segmento "Corrientes entre Pueyrredón y Medrano" a 4 km/h (embotellamiento), el modelo puede predecir que V también tardará más en ese segmento. Esto es información que ningún modelo basado en schedules tiene.

### Un modelo para todas las líneas (no uno por línea)

Con ~100 líneas en CABA, entrenar y mantener modelos separados es inviable. La clave es que **los factores que determinan el tiempo de viaje son transferibles entre líneas**:

- Si Av. Corrientes está congestionada, afecta al 39, al 64, al 99 y a todas las demás
- La relación "velocidad baja en segmento → tarde en ese segmento" es la misma sin importar la línea
- El patrón "viernes 18:00 → más lento que martes 14:00" aplica a todas las líneas

El modelo recibe como input la **posición normalizada sobre el shape del ramal** (distancia en metros desde el inicio), no el nombre de la línea. Esto lo hace agnóstico a la línea específica y transferible.

Lo único line-specific es el shape (la polilínea del recorrido). El shape se usa para proyectar la posición, pero el modelo no lo ve directamente.

Resultado: **un solo modelo entrenado con datos de todas las líneas simultáneamente**:
- 100 líneas × 30 trips/día × 90 días = ~270K viajes en 3 meses
- ~80 puntos/viaje = ~21M ejemplos de entrenamiento
- Mucho más rico que un modelo por línea

### El estado de la flota como contexto

**Constraint de inferencia:** llamar a la API completa (~5500 vehículos) en cada query tarda 3-4s — inaceptable en producción. La inferencia usa un llamado filtrado por agencia (~ms de latencia), que retorna entre 40 y 200 vehículos según la línea.

**El input de flota es la lista cruda de vehículos de la agencia** — sin agregación geográfica, sin grillas, sin celdas. El modelo recibe todos los vehículos activos de la agencia con sus posiciones y velocidades y aprende solo qué patrones son relevantes: si toda la flota va lenta es un día de alto tráfico general; si los vehículos del mismo ramal adelante van lento, el bus consultado también va a tardar más.

**Consecuencia para entrenamiento:** el entrenamiento usa el mismo input que producción — los vehículos de la agencia del snapshot correspondiente. Sin mismatch.

**Mejora futura (no implementar ahora):** llamar a múltiples agencias de líneas que comparten tramos. Requiere shapes completos de todas las líneas involucradas — no factible hasta tener mayor cobertura.

### Arquitectura unificada del Modelo 2

```
Input A — Historia del viaje actual del vehículo V (línea-agnóstico):
  Todos los puntos desde start_time hasta ahora (longitud variable):
    dist_along_route_m (normalizada 0-1 sobre la longitud total del ramal)
    speed_m_per_s
    dt_seconds (tiempo desde punto anterior)
  → Transformer encoder (longitud variable) → trajectory_embedding (dim=64)

Input B — Estado de la flota de la agencia:
  Todos los vehículos activos de la agencia en este momento (40-200 vehículos):
    lat_norm, lon_norm, speed, ramal_id (resuelto por la lookup, embedding), direction_id
  → Transformer encoder → fleet_embedding (dim=64)

Input C — Contexto temporal:
  hour_sin = sin(2π × hora / 24)   ← encoding cíclico (23:59 ≈ 00:01)
  hour_cos = cos(2π × hora / 24)
  day_of_week → embedding (dim=4)
  → time_embedding (dim=12)

Input D — Distancia al target (float continuo):
  distance_to_target_m normalizada sobre la longitud total del ramal  ← 1 float

Input E — Estado del viaje:
  time_since_start_s = now - start_time  ← segundos desde que arrancó el viaje
                                            negativo si el bus aún no partió (en terminal esperando)
                                            noisy pero útil: el modelo aprende el peso correcto
  ← 1 float

Concatenar: [trajectory_embedding(64), fleet_embedding(64), time_embedding(12), distance_to_target(1), time_since_start(1)]
  dim total = 142
  → MLP(142 → 64 → 32 → 1)
  → ETA en segundos hasta el punto target específico
```

**Parámetros totales: ~300K** — muy chico. Entrena en <30 min en RTX 3080 con los 21M ejemplos de 3 meses.

### La limitación de los 30 segundos

La resolución temporal de la API es 30 segundos. A velocidades urbanas:

| Velocidad | Distancia en 30s |
|-----------|-----------------|
| 15 km/h (zona congestionada) | 125 m |
| 30 km/h (flujo normal) | 250 m |
| 60 km/h (autopista) | 500 m |

**Implicaciones de diseño:**
- **Output continuo, no discretizado**: el modelo predice ETA a un punto específico (`distance_to_target_m` como float), no a waypoints fijos cada 500m. El target real (parada del usuario proyectada sobre el shape) nunca coincide exactamente con un waypoint fijo — el output continuo elimina el error de interpolación.
- **Resolución temporal de 30s define el granulado mínimo observable**: a 30 km/h un vehículo se mueve ~250m por ciclo. El modelo trabaja con posiciones y velocidades observadas a esa resolución — no hay agregación geográfica adicional.
- **No modelar paradas individuales**: a 30s de resolución no sabemos si el vehículo estuvo 10s o 25s en una parada — solo vemos que en ese ciclo se movió X metros. El modelo aprende el tiempo de parada implícitamente.
- **Speed reportada = promedio del período**: si el colectivo estuvo 20s parado y 10s moviéndose a 30 km/h, la API reporta speed = 10 km/h. El modelo aprende estos patrones estadísticamente.
- **Dataset x40 gratis**: cada viaje de 20 minutos genera ~40 ejemplos de entrenamiento, uno por ciclo de 30s. En cada ciclo, el tiempo real hasta que el bus llegó al target es un label válido y observable. No requiere cambio en la arquitectura — solo construir el dataset tomando todos los puntos del viaje como ejemplos independientes, no solo el punto inicial. Un viaje que antes aportaba 1 fila al dataset ahora aporta ~40.

### Datos necesarios

Con modelo unificado (todas las líneas):
- 3 meses: ~21M ejemplos de entrenamiento — más que suficiente
- Comparación: con modelo por línea necesitarías 3 meses por línea, ahora los 3 meses sirven para todo


---

## 7b. Comparación de approaches de ETA (dado shapes precisos)

### El problema real

Con shapes precisos, el target de predicción es siempre un **punto sobre la polilínea del ramal**: la posición del usuario proyectada al shape más cercano, o una parada con posición conocida en el shape. Esto reduce el problema a 1D: dado que el vehículo está a d_V metros del inicio y el target a d_T metros, ¿cuántos segundos tarda en recorrer (d_T − d_V) metros?

Las curvas, esquinas, y cambio de dirección ya están absorbidos en el shape. Un desvío del vehículo (colectivo que sale de su ruta) proyecta erróneamente al punto más cercano del shape: la predicción degrada silenciosamente sin romper el sistema. El usuario acordó que este caso no importa.

### Tabla comparativa

| | **A0 Naive** | **A1 Historial segmentos** | **A2 Regresión directa** | **A3 Traffic grid + MLP** |
|--|:--:|:--:|:--:|:--:|
| **MAE típico (viaje 30 min)** | ~8-12 min | ~3-5 min | ~2-3 min | ~1.5-2.5 min |
| **1 solo vehículo en barrio** | ✅ | ✅ | ✅ | ✅ (fallback a prior) |
| **Rush hour en avenida** | ❌ | ❌ no ve tráfico actual | ⚠️ parcial | ✅ |
| **Requiere shapes** | ❌ | ✅ | ✅ | ✅ |
| **Datos de entrenamiento** | 0 | 1 mes | 3 meses | 3 meses |
| **Implementación** | trivial | 1-2 días | 1 semana | 3-4 semanas |
| **Robusto a baja frecuencia (barrio)** | ✅ | ✅ | ✅ | ✅ (grid vacío → A1) |
| **Ve congestión actual** | ❌ | ❌ | ❌ | ✅ |

### A0 — Naive: distancia / velocidad actual

```
ETA = (d_T - d_V) / velocidad_actual
```

Falla en el momento que el vehículo frena, para en una parada o hay semáforo. Útil solo como sanity check y cota superior de error.

### A1 — Historial de velocidades por segmento

Dividir el trayecto restante en segmentos de 500m. Para cada segmento, usar la velocidad media histórica observada en ese segmento para la misma hora y día de semana (construido con DuckDB sobre los Parquet):

```
Para cada segmento S entre d_V y d_T:
    ETA_S = 500m / mean_speed(ramal, segmento, hora, día_semana)
ETA_total = sum(ETA_S)
```

**Importante — comparación honesta con OBA:** cuando OBA tiene un bus activo con GPS, ya proyecta posición sobre el shape y estima ETA con ~1-2 min de error en tráfico normal. A1 hace lo mismo con velocidades históricas reales en vez del schedule — la diferencia en ese escenario es pequeña. A1 no es una mejora sustancial sobre OBA para bus activo en tráfico normal.

**Dónde A1 sí gana:**
- "Próximo colectivo" sin bus visible: OBA usa frecuencias del schedule (incorrectas en CABA). A1 usa headways históricos reales — diferencia potencialmente grande.
- Como baseline de medición para cuantificar la mejora del modelo.
- Cuando OBA usa el shape equivocado (ramal incorrecto): con ramal correcto + A1 ya hay mejora.

**Debilidad:** no detecta congestión actual. Si hay un accidente en Rivadavia a las 18:00 de un martes, A1 usa el promedio histórico → subestima el delay.

**Rol real de A1:** baseline de medición y prior histórico, no producto final. Solo DuckDB + Python.

### A2 — Regresión directa punto a punto

Con shapes precisos, cada trip histórico provee ejemplos directos:

```
Input:  distancia_restante_m, velocidad_actual, hora_sin, hora_cos, día_semana
Output: segundos reales observados (tiempo que tardó el vehículo en recorrer esa distancia)
```

El modelo aprende la distribución completa de tiempos de viaje para distintas distancias, horas y días — sin segmentar. Captura efectos que A1 pierde: si el segmento 1 va lento, el vehículo llega al segmento 2 en un momento de mayor congestión también (correlación temporal entre segmentos). A1 suma independientemente; A2 aprende la correlación.

**Barrio / 1 solo vehículo:** el modelo fue entrenado con miles de trips históricos. Que ahora haya 1 solo vehículo activo no afecta la inferencia.

**No implementar A2 por separado:** A3 lo incluye como caso degenerado (cuando la flota de la agencia tiene pocos vehículos activos, A3 cae naturalmente al comportamiento de A2).

### A3 — Fleet state + MLP (el approach completo)

A2 más el estado actual de la flota de la agencia:

```
Input:  distancia_restante, velocidad_actual, hora, día_semana
        + fleet_state: todos los vehículos activos de la agencia (40-200 vehículos)
          con lat, lon, speed, ramal_id (resuelto por la lookup), direction_id
Output: segundos hasta el target
```

**La ventaja sobre A2:** el modelo ve el estado real de la flota en este momento. Si todos los vehículos van lento, es un día de tráfico pesado. Si los vehículos del mismo ramal adelante van lento, el bus consultado también tardará más. El modelo aprende estos patrones sin que se los codifiquemos.

**En madrugada / líneas chicas:** pocos vehículos activos — el fleet_state tiene menos señal y el modelo cae naturalmente al comportamiento de A2.

**En avenidas en rush hour:** la diferencia entre "martes 18:00 histórico" y "este martes 18:00 con embotellamiento real" puede ser 5-10 min. A3 lo ve, A2 no.

### El modelo correcto: predictor de "cuándo pasa el próximo bus"

El Modelo 2 no es un "predictor de ETA de un bus corriendo". Es un **predictor de cuándo pasa el próximo bus del ramal por el target del usuario**. Un bus visible es una feature de alta calidad, no un prerequisito.

El dataset contiene, para cada punto de cada shape, todos los timestamps en que pasó un bus. Eso es la distribución empírica de inter-arrivals. El modelo puede aprender "martes 8am, 39-1 en este punto → bus cada 8-12 min" puramente desde features temporales, sin necesitar un bus activo.

**¿Qué se codifica explícitamente vs qué aprende el modelo?**

Se codifica el **flag `has_active_bus`** (bool). Sin él, el modelo ve `distance_remaining=0` en dos situaciones opuestas: "no hay bus visible" y "el bus está exactamente en el target". Mismo valor, semántica completamente distinta. Lo mismo con `speed=0`: bus parado en parada vs sin bus activo. Esa ambigüedad no se puede resolver sola. El flag la elimina con 1 bit.

Lo que aprende el modelo: los **pesos relativos** entre features. Cuánto confiar en `distance_remaining` cuando `has_active_bus=True`, cuánto confiar en el contexto temporal y el fleet_state cuando es `False`. El entrenamiento lo resuelve solo — no hace falta decirle que la posición real es más confiable que el prior temporal.

Regla general: se codifica la **estructura de la información** (qué está presente, qué no, qué es cero genuino vs ausente). Se deja que el modelo aprenda los **pesos relativos**.

**Input unificado:**

```
Siempre disponible (incluso sin bus visible):
  hora_sin, hora_cos              ← encoding cíclico
  día_semana                      ← embedding
  fleet_state                     ← todos los vehículos activos de la agencia (lat, lon, speed, ramal_id, direction_id)
                                     (construido del llamado filtrado por agencia, 40-200 vehículos según la línea)

Adicional cuando hay bus activo del ramal:
  has_active_bus                  ← bool (elimina ambigüedad de distance_remaining=0 y speed=0)
  distance_remaining_m            ← posición proyectada sobre shape (float continuo)
  velocidad_actual                ← del bus específico
  historial GPS del viaje actual  ← todos los puntos desde start_time, longitud variable, para el encoder de trayectoria (Input A)
  time_since_start_s              ← segundos desde start_time (negativo si aún en terminal, noisy pero útil)

Output siempre:
  segundos hasta próximo bus en el target
  nivel de confianza: HIGH (bus visible) | LOW (solo prior temporal)
```

El bus visible convierte una predicción estadística en una predicción de posición real — no cambia la estructura del modelo, solo enriquece los features.

**Caso paro de transporte / fuera de servicio:**
El modelo predice igual (es out-of-distribution — no sabe del paro). La detección es externa: si el fleet_state retorna 0 vehículos activos → anomalía detectable → UI muestra "predicción basada en historial, sin flota activa detectada". No es un fallo del modelo, es incertidumbre etiquetada correctamente.

```python
def predict(ramal, target_point, active_vehicles):
    features = {
        "time": encode_time(now),
        "fleet_state": active_vehicles,  # lista cruda de vehículos de la agencia
        "has_active_bus": False,
    }

    ramal_buses = [v for v in active_vehicles if v.ramal == ramal]
    if ramal_buses:
        closest = min(ramal_buses, key=lambda v: eta_naive(v, target_point))
        features["has_active_bus"] = True
        features["distance_remaining"] = project_distance(closest, target_point)
        features["bus_speed"] = closest.speed
        features["bus_history"] = closest.last_20_points
        features["time_since_start"] = now - closest.start_time
        confidence = "high"
    else:
        confidence = "low"

    eta_seconds = model.predict(features)
    return eta_seconds, confidence

```

**A1 sigue siendo útil como:** baseline de medición para cuantificar cuánto mejora el modelo sobre el estadístico puro. No es un input ni un componente del sistema en producción.

A3 (este modelo unificado) se implementa en Fase 3 (3-4 semanas, 3 meses de datos).

### Loss function: Pinball asimétrica por distancia

El error de predicción no tiene el mismo costo en todos los puntos del recorrido.
A distancias cortas (< 1 km), la decisión del usuario es binaria: llego o no llego.
Subestimar ("faltan 2 min" cuando ya pasó) hace que el usuario pierda el colectivo.
Sobreestimar ("faltan 5 min" cuando son 3) solo hace que espere un poco más.

Por esto se usa una **Pinball Loss** (quantile loss) que varía con la distancia:

- **dist > 1 km:** q = 0.5 → L1 simétrica (MAE estándar)
- **dist < 1 km:** q = 0.8 → underestimar penaliza 4× más que overestimar

```
loss = q * error       si pred < real  (subestimé — usuario llega tarde)
loss = (1-q) * error   si pred > real  (sobrestimé — usuario espera un poco más)
```

Con q = 0.8 el modelo aprende a predecir "por las dudas un poco más" cuando el
bus está cerca — el error tolerable asimétrico refleja la realidad de uso.

La transición es suave: q = 0.5 + 0.3 × clamp(1 - dist_m/1000, 0, 1)

---

## 8. Reentrenamiento continuo

### Trigger de reentrenamiento

Hay dos triggers:

**A. Rotación de route_ids (~cada 3 semanas) — Modelo 1**
- Detectado automáticamente: aparecen `route_ids` nuevos para una línea (`build_ramal_map.py` los marca como pendientes)
- Acción: **reconstruir la lookup** `route_id → shape`, no reentrenar nada. No hay modelo ni pesos en Modelo 1.
- Costo: minutos de CPU; converge con 1-2 días de GPS acumulado del período nuevo

**B. Reentrenamiento mensual completo**
- Para Modelo 2 (ETA): fine-tuning con datos del último mes
- Costo: ~2-4h en RTX 3080
- Mejora incremental en MAE a medida que acumula más patrones de tráfico

### Estrategia de fine-tuning

Fine-tuning = tomar el modelo existente y continuar el entrenamiento con nuevos datos. Es mucho más rápido que entrenar desde cero porque los pesos ya capturan la mayoría de los patrones.

El fine-tuning aplica **solo a Modelo 2 (ETA)**. Modelo 1 no se fine-tunea: se reconstruye la lookup (ver trigger A arriba).

```
Modelo 2 — Fine-tuning mensual:
  Datos: último mes de viajes completos (todas las líneas juntas)
  Learning rate: 5x más bajo
  Épocas: 20-30
  Tiempo: ~1-2h (modelo unificado — un solo entrenamiento, no por línea)
```

### Qué hacer cuando el dataset crece mucho

**Problema:** después de 1 año, tenés 1.000M de observaciones. Entrenar en todo eso es innecesario y lento.

**Estrategia de ventana deslizante:**
- Entrenamiento inicial: 3 meses completos
- Después del primer año: usar solo los últimos 6 meses para entrenamiento
- Los datos más viejos quedan archivados en /mnt/buffer pero no se usan para training
- Excepción: si el modelo necesita ver patrones estacionales (verano 2026 vs verano 2027), usar muestras de datos viejos de las mismas estaciones

**Estrategia de muestreo estratificado:**
No usar todos los datos, sino una muestra balanceada:
- Mismo número de ejemplos por hora del día (no querés que las 8:00-9:00 dominen por ser la hora de más tráfico)
- Mismo número de ejemplos por día de semana
- Mismo número de ejemplos por ramal

```python
# sample_training_data.py
# Input: snapshots.parquet con 1 año de datos
# Output: training_sample.parquet con ~3M ejemplos balanceados

df.groupby(['ramal', 'hour_of_day', 'day_of_week']).sample(n=1000, random_state=42)
```

### Schema de archivos del flujo de entrenamiento

```
/mnt/buffer/grabaciones/
  2026-03-28.ndjson.gz
  2026-03-29.ndjson.gz
  ...

/mnt/buffer/ml/
  snapshots/
    2026-Q2.parquet         # reconstruido de NDJSON, ~800MB
    2026-Q3.parquet
  trips/
    2026-Q2-trips.parquet   # viajes segmentados, ~200MB
    2026-Q2-trips-projected.parquet   # con distancia en ruta calculada
  training/
    model2_eta/             # Modelo 1 no entrena → no tiene dataset de training
      train.parquet
      val.parquet
  models/
    eta_a3_v1.onnx          # modelo unificado, todas las líneas (solo Modelo 2 es .onnx)
  ramal_lookup/
    ramal_map.json          # lookup route_id → shape (Modelo 1), con first_seen/last_seen por período
    families_39.json        # familias de fraccionados, fijas por línea
```

---

## 9. Hardware: RTX 3080

### Specs relevantes

| Spec | Valor |
|------|-------|
| VRAM | 10 GB GDDR6X |
| CUDA Cores | 8.704 |
| FP32 (full precision) | 29.8 TFLOPS |
| FP16 (half precision, mixed precision) | 59.6 TFLOPS |
| Tensor Cores (generación 3) | sí — acelera entrenamiento |

**Mixed precision training:** PyTorch puede entrenar en FP16 con pérdida calculada en FP32. Esto duplica efectivamente la velocidad y permite batch sizes 2x más grandes. Estándar para RTX 30xx. Se activa con una línea de código.

### Estimaciones de tiempo de entrenamiento

#### Modelo 1 — Ramal ID

No usa GPU: es una lookup geométrica offline en CPU (`ramal_lookup/`). El costo es de I/O + proyección, del orden de minutos por línea por período. La RTX 3080 solo se usa para Modelo 2.

#### Modelo 2 — ETA (unificado, todas las líneas)

| Parámetros | ~300K |
|------------|-------|
| Dataset (3 meses, todas las líneas) | ~21M ejemplos |
| Batch size | 256 |
| Épocas | 50 |
| Iteraciones totales | ~4M |
| **Tiempo en 3080 (FP16)** | **~2-3 horas** |
| Fine-tuning mensual | ~1-2 horas |

#### Entrenamiento inicial completo (todas las líneas)

| Componente | Tiempo |
|------------|--------|
| Reconstruir snapshots (CPU, Python) | 6-8 horas una sola vez |
| Segmentar viajes (DuckDB, CPU) | 30 min |
| Proyectar sobre shapes (CPU, Python, multiprocess) | 4-6 horas |
| Construir lookup Modelo 1 (CPU, `ramal_lookup/`) | minutos por línea |
| Entrenar Modelo 2 (unificado, todas las líneas) | 2-3 horas |
| **Total setup inicial** | **~1-2 días** (incluyendo debugging) |

La 3080 aguanta perfectamente este workload. No necesitás cloud.

### Setup de entrenamiento en Windows

```
requirements para training:
  Python 3.11
  PyTorch 2.x con CUDA 12.x (instalador oficial pytorch.org)
  DuckDB (pip install duckdb)
  pandas, numpy, scikit-learn (pip install ...)

Los archivos de grabación están en Ubuntu. Para entrenar en Windows:
  opción A: compartir /mnt/buffer/ml vía SMB desde Ubuntu (//192.168.0.18/ml)
  opción B: rsync selectivo de los Parquet de entrenamiento a Windows cuando querés entrenar

El parquet de entrenamiento con el nuevo schema (FixedSizeList, float32, N_FLEET=60) ocupa
~3-6 GB en disco (compresión snappy/zstd sobre ceros de padding es muy efectiva). El schema
anterior era ~1.3 GB pero usaba List<double> variable-length, lo que hacía imposible leer
con numpy sin to_pylist(). El nuevo schema permite zero-copy con np.asarray().
```

### Tamaño de los modelos entrenados

| Artefacto | Parámetros | Tamaño en disco |
|--------|------------|------------------------|
| Ramal ID (`ramal_map.json`, lookup) | — | ~KB por línea (JSON) |
| ETA (unificado, todas las líneas, .onnx) | ~300K | ~1.5 MB |

El ETA se carga en RAM en milisegundos; la lookup de ramal es un JSON chico. Ninguno tiene costo de inferencia notable.

---

## 10. Fases de implementación

Esta es la hoja de ruta ordenada por balance de esfuerzo vs reducción de error.

### Fase 0 — Grabación (ya hecho)

**Estado:** ✅ Corriendo en NUC
**Esfuerzo:** 0 adicional
**Output:** NDJSON delta + gzip, creciendo 4.3 GB/mes

### Fase 1 — Pipeline de datos + baseline

**Cuándo:** al tener 1 mes de datos
**Esfuerzo:** ~3 días de trabajo
**Qué hace:**
- Reconstruir snapshots → Parquet
- DuckDB: calcular headways históricos reales por (ramal, hora, día) — cuánto tarda en pasar el próximo colectivo
- Calcular tiempos de viaje históricos por (ramal, segmento_500m, hora, día) — base para A1 y prior de A3

**Dónde A1 agrega valor real** (ver sección 7b para comparación completa con OBA):
1. **"Próximo colectivo" sin bus visible:** OBA usa frecuencias del schedule (incorrectas en CABA). A1 usa headways históricos reales. La diferencia puede ser grande.
2. **Baseline de medición:** cuantifica cuánto mejora A3.

**Por qué esta fase primero:** construir el pipeline de datos (reconstrucción, segmentación, proyección) es prerequisito para Fase 2 y 3. El valor inmediato es el pipeline, no A1 en sí.

### Fase 2 — Identificación de ramal (lookup offline)

**Cuándo:** al tener 1-2 días de datos por período (no requiere meses)
**Esfuerzo:** ✅ implementado (`ramal_lookup/`)
**Qué hace:**
- Construir `ramal_map.json` (lookup `route_id → shape`) con el módulo `ramal_lookup/` (ver sección 6)
- Integrar en server.js: cada ciclo, `lookup[route_id]` O(1) por vehículo
- Output: `FP_ramal` resuelto desde el primer snapshot, incluidos fraccionados

**Mejora:**
- RamalEngine legacy: ~65-70% de vehículos con ramal resuelto (solo los que pasaron divergencia)
- Lookup: ~100% dentro del período para líneas limpias; fraccionados (39D/E/F) resueltos por familia
- Validado en línea 39: 36/36 route_ids en 3 períodos

**Nota sobre rotaciones:** al aparecer route_ids nuevos se reconstruye la lookup (1-2 días), sin reentrenar. Ver sección 8, trigger A.

### Fase 3 — ETA con tráfico en tiempo real

**Cuándo:** al tener 3-4 meses de datos (y después de completar Fase 2)
**Esfuerzo:** ~2-3 semanas de trabajo
**Qué hace:**
- Implementar el llamado filtrado por agencia y construcción del fleet_state como input al modelo
- Entrenar Modelo 2 (ETA con MLP + tráfico actual)
- Integrar en server.js como feature adicional al endpoint de predicción

**Mejora sobre A1 (baseline estadístico):**
- A1 como prior histórico puro (sin tráfico actual): MAE ~3-5 min
- A3 (este modelo, con tráfico actual de toda la flota): MAE ~1.5-2.5 min
- En hora pico con tráfico variable: la diferencia puede ser mayor (~3x)

### Fase 4 — Fine-tuning automático

**Cuándo:** después de tener los modelos de Fases 2 y 3 corriendo
**Esfuerzo:** ~3-4 días
**Qué hace:**
- Cron semanal: detectar nuevos route_ids → reconstruir la lookup de ramal (Modelo 1, sin entrenamiento)
- Cron mensual: fine-tuning Modelo 2 con último mes de datos
- Log de métricas: guardar MAE del modelo en producción para monitorear degradación

### Fase 5 — Modelo de tráfico enriquecido (objetivo final)

**Cuándo:** 6+ meses de datos, si la calidad de Fase 3 no es suficiente
**Esfuerzo:** ~3-4 semanas
**Qué hace:**
- Reemplazar el MLP de ETA por un Transformer completo (Seq2Seq)
- El modelo aprende la correlación temporal: si los últimos 3 colectivos tardaron 12 min en un segmento, modela que el patrón persiste vs que es puntual
- Incorporar día especial (si el dataset ya acumuló feriados, lluvia via timestamps)
- MAE objetivo: ~1 min para viajes de 30 min

### Tabla resumen de fases

| Fase | Datos necesarios | Esfuerzo | MAE ETA | Ramal resuelto |
|------|-----------------|----------|---------|----------------|
| 0 (hoy) | — | ✅ Listo | — | ~65% (RamalEngine legacy, post-divergencia) |
| 1 — Pipeline + baseline | 1 mes | 3 días | A1 como prior² | ~65% (sin cambio) |
| 2 — Ramal lookup | 1-2 días/período | ✅ implementado | A1 como prior | **~100%** (líneas limpias) |
| 3 — ETA con tráfico | 3-4 meses | 3 semanas | **~2 min** | ~100% |
| 4 — Mantenimiento auto | post Fase 3 | 4 días | ~2 min (estable) | ~100% (estable) |
| 5 — Transformer ETA | 6+ meses | 4 semanas | **~1 min** | ~100% |

²Fase 1 no produce una mejora de MAE sobre OBA cuando hay bus activo (OBA ya da ~1-2 min en tráfico normal). Su valor es el pipeline de datos y los headways históricos reales que habilitan Fases 2 y 3.

---

## 10.1 Scope: 7 líneas es el punto de partida

### Modelo 1 — ramal ID: las 7 líneas son el punto de partida, no el scope completo

La gran mayoría de las líneas de CABA y AMBA tienen múltiples ramales. Contando fraccionados × 2 direcciones, son fácilmente 4-8 route_ids por línea. Con ~100 líneas en CABA más AMBA: **cientos de route_ids a identificar**. Modelo 1 es relevante para prácticamente todas las líneas, no solo las 7 actuales.

Las 7 líneas con shapes en `line_shapes.json` son el punto de partida por disponibilidad de shapes — no porque sean las únicas que lo necesitan.

**Escalado trivial:** agregar una línea nueva es crear su `families_{line}.json` (vacío `{}` si no tiene fraccionados) y volver a correr `build_ramal_map.py`. No hay entrenamiento, ni fine-tune, ni transfer learning — la misma lógica geométrica aplica a cualquier línea. El costo es minutos de CPU por línea.

El bottleneck sigue siendo el mismo en todos los casos: **shapes per-ramal precisos**. Sin shape, no hay ramal ID posible. BabusNova GTFS ya tiene `shapes.txt` con 700K líneas — el mismo origen que las 7 actuales. La pregunta abierta es cuántas líneas de BabusNova tienen shapes per-ramal suficientemente precisos para proyectar correctamente.

### Modelo 2 — ETA: entrena en 7, funciona en cualquier línea con shape

El modelo unificado de ETA aprende: *"dado X metros restantes, velocidad Y, tráfico actual Z, hora W → N segundos"*. Eso no es específico del 39 o el 42 — es comportamiento de tráfico urbano en CABA. Las 7 líneas cubren diversidad de recorridos: avenidas, barrios, zona norte, zona oeste. El modelo aprende el patrón general.

**Consecuencia:** si después se agrega el shape de la línea 60, la 64, o cualquier otra, Model 2 funciona sobre esa línea **sin reentrenar**. Solo necesitás el shape para proyectar la posición. El modelo ya está entrenado.

Con 7 líneas × 30 trips/día × 90 días: ~1.5M ejemplos de entrenamiento. Para un MLP de ~300K parámetros es más que suficiente.

### Inferencia remota: no aplica

El modelo pesa ~1MB y corre en <1ms en CPU. No hay ninguna razón para pagar por inferencia remota. El bottleneck es tener el shape, no la capacidad de cómputo.

| Situación | Approach | Costo |
|-----------|----------|-------|
| Línea con shape en `line_shapes.json` | Model 2 local | $0, <1ms |
| Línea sin shape, ≥1 mes de datos grabados | A1 estadístico (DuckDB) | $0 |
| Línea sin shape, sin datos históricos | Fallback OBA o no predecir | — |

Agregar una línea nueva al sistema = conseguir el shape → A1 funciona de inmediato con datos históricos, Model 2 funciona sin reentrenar.

---

## 10.2 Dependencia entre Modelo 1 y Modelo 2

Los modelos están **loosely coupled** a través del string `ramal_id`. No hay dependencia directa entre los pesos entrenados de ambos.

```
Model 1 output:  ramal_id = "39-A"   (lookup[route_id], o override manual)
                     ↓
Shape lookup:    polilínea del ramal "39-A"
                     ↓
Proyección GPS → distance_along_route
                     ↓
Model 2 input:   [distance_remaining, speed_history, fleet_state, time_of_day]
                 ← NO recibe el string "39-A", solo sus consecuencias geométricas
```

**Consecuencias:**

- Si Model 1 acierta → proyección correcta → Model 2 funciona bien
- Si Model 1 se equivoca → proyección sobre shape incorrecto → Model 2 produce basura (el error entra antes de Model 2, no dentro)
- Si corregís el ramal manualmente (override en el admin panel ya existente) → el pipeline usa el shape correcto → Model 2 funciona exactamente igual que si Model 1 hubiera acertado
- Model 2 es agnóstico al ramal: no tiene pesos que recuerden características de "39-1" vs "39-2". Aprende de distancia, velocidad, tráfico y hora — no de qué ramal es.

**El override del admin panel de ramal (ya implementado en map.html) propaga correctamente a ETA sin ningún cambio adicional.** Es la interfaz correcta.

---

## 11. Límites conocidos del sistema

### Límites inherentes a los datos

**Gaps en el dataset (cortes de luz, reinicio del NUC):** los registros `{"gap": true, "gap_seconds": N}` en el NDJSON marcan exactamente dónde hubo cortes. El impacto por capa:

- **Grabador:** ya manejado con `state.json` y gap records. No hay corrupción de datos.
- **Segmentación de viajes:** si `dt > 300s` entre dos observaciones consecutivas del mismo vehículo → cortar el segmento. No calcular tiempos de viaje que crucen un gap.
- **Feature de historia (últimos N puntos):** incluir `dt` como feature. Un `dt` grande (600s) le dice al modelo que hay un agujero. No descartar — el modelo aprende a ignorar historia pre-gap por el valor de `dt`.
- **A1 estadístico:** inmune. DuckDB agrega sobre todos los datos disponibles; los gaps solo reducen el n muestral de algunos segmentos/horas sin introducir sesgo (salvo que los cortes ocurran siempre en el mismo horario, lo cual es improbable).
- **Impacto cuantitativo con 5% downtime (2-3 cortes cortos/mes):** ~1.3 días perdidos/mes. Sin sesgo sistemático. El equivalente de 3 meses de datos se acumula en ~3.1 meses reales.

**Resolución temporal de 30 segundos:** ver Revisión 2 (inicio del documento) y sección 7. Granulado mínimo ~250m/ciclo a 30 km/h; `speed` es promedio del período; no se modela comportamiento sub-30s.

**LABEL_LINE_MAP.json y VP_label:** el mapeo sufijo del label → línea es robusto y ya está resuelto. El ramal ID usa esto como base: primero identificar la línea (resuelto), luego identificar el ramal dentro de esa línea (Modelo 1).

**stop_id / stop_sequence:** completamente inutilizables. Los datos de paradas en la API BA son desactualizados. Todo el sistema trabaja sobre segmentos geométricos proyectados en shapes OSM, no sobre paradas del GTFS.

**status (current_status):** medido en datos reales (15.077 vehículos): 0=INCOMING_AT nunca ocurre (0%), 1=STOPPED_AT ~1.2%, 2=IN_TRANSIT ~98.8%. El valor 1 sí tiene señal real: el vehículo está parado en una parada en este momento. Es una feature débil pero válida para el modelo de ETA (un vehículo con status=1 va a tardar al menos los próximos segundos de demora de parada antes de moverse).

**Odómetro:** siempre 0. Descartado.

**speed:** reportado por la API pero derivado de GPS consecutive deltas, no de sensor real. A 30s de intervalo y 30 km/h, la resolución es ~250m. Suficiente para el modelo pero no para inferir comportamiento fino (frenada en parada).

**bearing:** siempre 0 en la API BA. Sin uso. La dirección se infiere de la trayectoria.

### Límites del modelo

**Cold start de ramal (post-rotación):** cuando aparece un `route_id` nuevo y todavía no acumuló suficientes viajes, la lookup lo deja en `pending` (gate de cold-start) en vez de asignarlo mal. El cliente debe mostrar "identificando..." hasta que el `route_id` se resuelva (1-2 días). Nota: una vez resuelto, no hay cold start por viaje — el ramal se conoce desde el primer snapshot vía `lookup[route_id]`.

**Madrugada:** entre las 0:00 y las 5:00 hay 2-5 vehículos por línea. No afecta a Modelo 1 (la lookup ya está construida y no depende de la flota activa); sí reduce la señal de tráfico para Modelo 2, pero como hay pocos pasajeros el impacto es menor.

**Ventana de rotación:** cuando aparecen route_ids nuevos, los viejos dejan de servir y los nuevos están `pending` hasta acumular 1-2 días de GPS. Durante esa ventana esos vehículos no tienen ramal resuelto (degradación temporal aceptable). `direction_id` sí se conoce desde el primer snapshot.

**Eventos no recurrentes:** paro de transporte, accidente de tránsito, corte por obras. El modelo no los detecta de forma especial — simplemente observa velocidades bajas en ciertos segmentos y los incorpora al tráfico actual. No puede predecir cuándo termina el evento. Para esto haría falta integrar fuentes externas (Twitter/X, Waze) — fuera del scope actual.

**Líneas sin shapes OSM:** el sistema completo depende de tener polilíneas precisas por ramal. Las 7 líneas actuales en `line_shapes.json` están cubiertas. Agregar una nueva línea requiere: obtener el shape (OSM o BabusNova GTFS), crear su `families_{line}.json` y correr `build_ramal_map.py` (Modelo 1, sin entrenar); Modelo 2 funciona sin reentrenar.

**Líneas caóticas (151, 124):** la lookup asume `route_id ↔ shape` 1:1 estable en el período. La 151 (71 route_ids en 62 días, dual_direction, obs_count=1) y la 124 (gaps frecuentes) no cumplen eso del todo y requieren filtro previo por volumen. La lookup degrada a `pending` en esos casos en vez de resolver mal. Ver `research_direction_routeid.md`.

### Dependencias externas

- **API BA Transporte:** si deja de funcionar o cambia formato, el grabador deja de acumular datos. Los modelos ya entrenados siguen funcionando con datos históricos mientras la API esté parcialmente disponible.
- **Shapes OSM:** si cambia el recorrido de una línea físicamente, el shape queda desactualizado y la proyección falla. Requiere actualizar `line_shapes.json` manualmente.
- **Rotación de route_ids:** si el período cambia de 3 semanas a otra duración, la lookup se reconstruye automáticamente al aparecer route_ids nuevos (detecta cambios por observación, no por timer fijo).
