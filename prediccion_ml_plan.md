# Plan ML/DL: Identificación de Ramal y Predicción de ETA

**Última actualización:** 2026-06-03
**Estado:** Fase 3 activa — A3ETAModel entrenado y funcionando, línea 39
**Líneas en parquet:** 39

---

## Estado actual (2026-06-03)

### Pipeline implementado
- `segmenter → projector → build_dataset → eta_train.parquet` funcionando end-to-end
- Parquet línea 39: **71.5M filas train / 16.5M val**, 313 + 73 row groups
- Naive baseline: **672s** (valor de referencia para medir mejoras)

### Features del modelo (A3ETAModel)
| Feature | Descripción |
|---------|-------------|
| `dist_remaining_m / shape_length` | Distancia normalizada al target |
| `hour_sin / hour_cos` | Hora del día (encoding cíclico, Buenos Aires UTC-3) |
| `dow` | Día de semana (embedding 0-6) |
| `time_since_start` | Segundos en el viaje actual / 3600 |
| `ts_age_s` | Staleness GPS del vehículo, `min(frame_t - vehicle_ts, 600) / 600` |
| `has_active_bus` | Bool: hay bus visible o es predicción por headway |
| `schedule_dev_norm` | Desvío del viaje respecto a la mediana histórica del ramal: `clip((time_since_start - mediana_bucket) / 600, -3, 3)`. Valores en unidades de 10 min; positivo = más lento que lo típico. Computado on-the-fly en training desde `schedule_dev_medians.json` — no se almacena en el parquet. |
| `traj_flat (10×3)` | Historia de posición: (dist_norm, speed/30, dt/30) × 10 pts |
| `fleet_flat (60×5)` | Flota: (lat_norm, lon_norm, speed, direction_id, is_same_dir) × 60 |

### Modelos entrenados

| Archivo | Config | Val MAE | Epochs | Notas |
|---------|--------|---------|--------|-------|
| `eta_a3_nofleet_gfull_ep10_mae79s_20260602_212440_metrics.json` | no-fleet, d64, 10ep | **79.2s** | 10/10 | parquet con umbral 50m |
| `eta_a3_nofleet_gfull_ep14_mae75s_20260603_004827_metrics.json` | no-fleet, d64, 15ep | **75.9s** | 14/15 | parquet con umbral 100m + ts_age_s |

**Modelo en producción:** `eta_a3_best.pt` + `eta_a3_final.onnx` = epoch 14 del segundo run (75.9s val MAE).

### Mejoras implementadas desde el diseño inicial
1. **Umbral dist_remaining ≥ 100m** (era 50m): elimina pares de corto alcance con ruido GPS desproporcionado
2. **Feature `ts_age_s`**: staleness del GPS del vehículo respecto al frame global. Mediana ~10s, cap en 600s. Ver commit `d49e7c2`.
3. **Pinball loss asimétrica**: penaliza subestimación 4x en distancias <500m (perder el colectivo es peor que esperar de más). Under<500m ratio ~22% = modelo sobreestima 78% del tiempo en distancia corta. ✓
4. **LR scheduler**: baja automáticamente lr cuando no mejora (6e-4 → 3e-4 observado en epoch 6).
5. **Feature `schedule_dev_norm`**: desvío del viaje actual respecto a la mediana histórica del ramal en el mismo punto del recorrido. Captura si el bus va adelantado o retrasado respecto a su patrón típico — señal complementaria a `time_since_start` que el modelo puede usar para ajustar el ETA. Generado por `build_schedule_dev_table.py` (DuckDB sobre el parquet completo con deduplicación) → `schedule_dev_medians.json`. Aplicado on-the-fly en `ETADataset._iter_group` por row group (no se almacena en el parquet). Ver detalles de implementación en sección §schedule_dev_norm.

### Experimento fleet — bloqueado por costo computacional

Fleet con `--fleet-same-dir-cap 20` tomó **6235s por epoch** (vs 505s sin fleet) = ~12× más lento. Causa: FleetEncoder backward a través de 3 capas de transformer con batch=8192 domina el cómputo GPU. I/O no es el cuello de botella (fetch_ms=1.4ms).

**Opciones para desbloquear fleet:**
- **Reducir FleetEncoder a 1 capa** (cambio mínimo en `a3_eta.py`, sin regenerar parquet) — ~3× más rápido
- **Reemplazar transformer por mean pooling** — mucho más rápido, pérdida mínima de capacidad
- **Reducir N_FLEET en parquet de 60 a 20** (regenerar parquet) — reduce activaciones en backward

### Requerimiento de inferencia — ventana de 5 minutos

Para obtener calidad real en la predicción, el sistema de inferencia debe mantener un **buffer rolling de los últimos 5 minutos de posiciones por vehículo** (no solo el estado puntual actual). Con ciclo real de ~60s por vehículo, 5 min = ~5 pings reales → `traj_len=5`, mucho mejor que el `traj_len=1` del stub actual.

**Diseño:** `fleet_cache.py` pasa de `{vehicle_id: LiveVehicle}` a `{vehicle_id: deque(maxlen=10, LiveVehicle)}`. Cada entry tiene `ts, lat, lon, speed, dist_along_shape_m` (pre-proyectado). En inferencia: el último elemento es estado actual, los anteriores son la trayectoria.

El buffer de 5 min también resuelve el "last bus departed": vehículos que ya pasaron la posición del usuario siguen en el buffer y permiten calcular cuándo fue el último bus del ramal.

### Feature `time_since_last_bus_s` — análisis de viabilidad

**Contexto:** El caso "no hay bus visible" se resuelve sin nuevo training pasando `dist_remaining = distancia_usuario_desde_terminal`, velocidad=0, traj=zeros. El modelo ya aprendió ETAs con distancias grandes desde el training existente (buses al inicio del viaje). El único dato genuinamente nuevo que A3 puede explotar y A1 no tiene es cuánto tiempo pasó desde que el último bus del ramal pasó por la posición del usuario.

**Por qué vale la pena:** A1 dice "los martes a las 8am el headway es 9 minutos". Con `time_since_last_bus_s` el modelo puede decir "el headway histórico es 9 min, el último bus pasó hace 2 minutos, el próximo llega en ~7 min". Eso es información en tiempo real que mejora la predicción de modo concreto y medible — especialmente en horas pico donde el headway varía por congestión.

**Costo de implementación:** bajo, condicionado a tener el buffer rolling de 5 min (necesario de todas formas para trajectory). El buffer ya contiene los vehículos que recientemente pasaron la posición del usuario — `time_since_last_bus` es una resta de timestamps.

**En training:** para generar ejemplos con esta feature, para cada par `(t_i, t_{i+1})` de buses consecutivos pasando por la posición P, `time_since_last_bus = query_time - t_i`. La data ya existe en los viajes proyectados — es gratis extraerla.

**Recomendación:** implementar junto con el buffer rolling de 5 min. No requiere nuevo pipeline de training separado — se agrega como feature adicional en las filas existentes (cuando `has_active_bus=True`, `time_since_last_bus` refleja cuánto antes llegó el bus anterior al mismo ramal por esa posición, también útil).

### Pendiente / próximos pasos (ordenados por prioridad)

1. **Resolver bottleneck fleet** — elegir entre las 3 opciones arriba y correr fleet
2. **Agregar línea 42 al parquet** — más datos, mejora representaciones generales
3. **Implementar has_active_bus=0.0** — training con ejemplos de "no hay bus visible" (ver sección de diseño más abajo)
4. **Integrar A3 ONNX en producción** con buffer rolling de 5 min (`predictor.py` tiene el stub)
5. **Fine-tuning mensual automático** (Fase 4)

---

## Experimentos offline

### Experimento 1 — Umbral "llegando" y distribución de error (2026-06-05, definitivo)

**Objetivo:** determinar qué umbral usar en la UI para mostrar "llegando".

**Modelo:** `eta_a3_nofleet_gfull_ep24_mae72s_20260605` — no-fleet, d_model=64, PyTorch CUDA directo.
**Script:** `experiments/arriving_threshold_analysis.py`
**Resultados raw:** `data/ml/experiments/arriving_threshold_20260605_092742.json`
**Tiempo de inferencia:** 110s en GPU (RTX 3080) sobre 16.5M filas (73 grupos, filtro obs_eta ≤ 7200s, dist_rem ≥ 100m).

**Error por bucket de distancia:**

| Bucket | N | MAE | P50 | P90 | Bias | Under% |
|--------|---|-----|-----|-----|------|--------|
| 100–250m | 291K | 67.7s | 48s | 103s | +24.9s | 15% |
| 250–500m | 597K | 64.9s | 47s | 108s | +21.8s | 23% |
| 500m–1km | 1.15M | 66.9s | 46s | 123s | +7.9s | 35% |
| 1km–2km | 2.15M | 82.1s | 57s | 165s | −3.7s | 45% |
| 2km–5km | 5.22M | 121.8s | 87s | 258s | −4.2s | 48% |
| 5km+ | 7.1M | 204.2s | 148s | 446s | −11.6s | 51% |

Patrón de bias: el modelo **sobreestima** a distancias cortas (<1km) y **subestima levemente** a distancias largas (>1km). Consistente con el pinball loss asimétrico (q>0.5 cuando dist<1km).

**Error por bucket de ETA predicho:**

| ETA predicho | N | MAE | P50 |
|---|---|---|---|
| <60s | 698 | 39s | 27s |
| 60–120s | 266K | 43.6s | 37s |
| 120–180s | 633K | 53s | 44s |
| 3–5 min | 1.17M | 62.5s | 46s |
| 5–10 min | 2.47M | 82.3s | 59s |
| 10min+ | 11.98M | 173s | 121s |

**Grid search umbral "llegando"** (definición real: `obs_eta < 90s`, flag: `pred_eta < T OR dist_rem < D`):

Nota: F1 trata precision y recall como iguales, pero **F2 es más apropiado** — perder el colectivo (falso negativo) es peor que una falsa alarma (falso positivo). Con F2 (beta=2, recall pesa doble):

| time_t | dist_t | Precision | Recall | F1 | F2 |
|--------|--------|-----------|--------|----|----|
| 150s | 300m | 51.0% | 89.0% | 0.649 | **0.775** ← mejor F2 |
| 150s | 250m | 52.6% | 86.4% | 0.654 | 0.766 |
| 150s | 200m | 53.5% | 84.0% | 0.654 | 0.754 |
| 120s | 300m | 60.5% | 74.9% | **0.669** ← mejor F1 | 0.714 |

**Recomendación UI:** mostrar "llegando" cuando `pred_eta < 150s OR dist_remaining < 300m`.
- Precision 51% (1 de 2 alarmas es falsa — el bus tarda un poco más de 90s)
- Recall 89% (casi nunca se pierde un bus que realmente estaba llegando)

### Experimento 2 — Impacto de features acumuladas (2026-06-06)

**Objetivo:** medir si `schedule_dev_norm` y `time_since_last_bus_s` mejoran el val MAE.

| Run | Features | Best Ep | Val MAE | 0–500m | 500m–2km | 2km+ | Under<500m |
|-----|----------|---------|---------|--------|----------|------|-----------|
| ep24 (2026-06-05 03h) | baseline sin schedule_dev | 24 | 72.7s | 68.1 | 77.3 | 170.0 | 20.0% |
| ep24 (2026-06-05 18h) | + schedule_dev_norm | 24 | **70.4s** | 68.3 | 77.5 | 164.2 | 17.0% |
| ep21 (2026-06-06) | + schedule_dev + time_since_last_bus_s | 21 | 72.5s | **62.1** | 78.7 | 169.4 | 22.2% |

**`schedule_dev_norm`:** mejora de −2.3s sobre el baseline.

**`time_since_last_bus_s`:** resultado ambiguo — MAE global retrocedió 2s (70.4 → 72.5s), pero el bucket 0–500m mejoró sustantivamente (68.3 → 62.1s, −6s). El parquet fue regenerado obligatoriamente al agregar las columnas, lo que confunde la comparación: la regresión en buckets largos puede ser variación de training, no daño de la feature.

**Sobre la magnitud de la variación:** el rango 70.4–72.7s (2.3s) es pequeño y probablemente mezcla señal real con ruido. El val set es fijo (últimos 20% de días temporalmente) — días atípicos pueden mover el MAE 2-3s sin cambio real en el modelo.

**Nota sobre Under<500m vs MAE:** pueden moverse en direcciones opuestas. MAE es simétrico. Under<500m mide subestimaciones (pred < real) — con pinball loss el objetivo es mantenerlo bajo. El modelo con time_since_last_bus es más exacto en esa zona (MAE −6s) pero menos conservador (más subestimaciones): conoce cuándo pasó el bus anterior y predice más ajustado, reduciendo el colchón de seguridad.

**Decisión:** no se reentrena. La mejora en 0–500m es sustantiva y el resto puede ser variación del training. Modelo en producción: `eta_a3_nofleet_gfull_ep21_mae72s_20260606`.

**Límite actual:** la variación entre los 3 runs sugiere que se está cerca del techo con los datos actuales (1 línea, ~10 semanas). Los movimientos más grandes pendientes son fleet (bloqueado por costo 12×) y agregar más líneas al parquet.

---

## Revisiones importantes (leer antes que el resto)

Cuatro correcciones estructurales que cambian el diseño respecto a la versión inicial:

**1. Líneas comparten segmentos → el tráfico es geográfico, no por línea**

La línea 39, 64, 71, 99 y docenas más circulan por Av. Corrientes. Un embotellamiento en Corrientes afecta a todas. El estado de tráfico de un segmento se construye con los **vehículos de la agencia consultada (40-200 según la línea)**, no solo los del mismo ramal — y no con toda la flota (~5500), ya que el llamado filtrado por agencia es el único factible en producción. Esto enriquece el modelo de ETA y elimina el problema de "no hay vehículos de este ramal específico en ese segmento en este momento". Ver sección 7.

**2. La API actualiza cada 30 segundos**

La resolución temporal es 30s. A 30 km/h, un vehículo se mueve ~250m por intervalo. Implicaciones:
- La velocidad reportada es un promedio sobre los últimos 30s, no instantánea
- No se puede detectar comportamiento fino (frenada en parada, arrancada)
- A 30 km/h un vehículo se mueve ~250m por ciclo — es el granulado mínimo observable en los datos
- Hay que modelar a nivel de segmento, no de parada individual

**3. El problema de ETA es 1D sobre el shape, no 2D en el mapa**

Con shapes precisos, todo el espacio GPS 2D colapsa a un escalar: distancia restante sobre la polilínea del ramal. El vehículo V proyectado sobre el shape tiene posición d_V metros desde el inicio. El target T (posición del usuario proyectada al shape, o parada conocida) tiene posición d_T. ETA = tiempo de recorrer (d_T − d_V) metros sobre ese shape. Las curvas, esquinas y cambios de dirección ya están incorporados en el shape. Si hay un desvío, la proyección falla silenciosamente (el sistema no colapsa, solo degrada la precisión). Ver sección 7.

**4. CABA tiene ~100 líneas**

- **Ramal ID:** es inherentemente por línea. La estructura de ramales es específica de cada línea (la línea 39 tiene sus ramales, la 42 los suyos). Se resuelve con una lookup geométrica offline `route_id → shape` (módulo `ramal_lookup/`), no con ML. Aplicable solo a las líneas con shapes disponibles y múltiples ramales reales. El mapeo `VP_label → línea` ya está resuelto con LABEL_LINE_MAP.json y es robusto — es la base de este paso.

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

Estos tres flujos tienen requerimientos completamente distintos.
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

`schedule_dev_norm` **no se almacena en el parquet** — se computa on-the-fly en `ETADataset` por row group usando `schedule_dev_medians.json`. Ver §schedule_dev_norm.

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

**Línea de investigación — flota completa como señal de entrenamiento:**
La API completa (~6000-9000 vehículos) es inviable en producción (3-4s latencia) pero el NUC la graba en cada ciclo. Hipótesis: entrenar con toda la flota como input enriquece las representaciones de tráfico aprendidas aunque en inferencia solo se use la agencia (40-200 vehículos). El FleetEncoder actual (self-attention O(N²)) no escala a N=6000. Requeriría pre-agregar la flota en un resumen geográfico (grid de velocidades por celda, o histograma por corredor) antes de pasarlo al modelo — lo que esencialmente convierte el problema en un "mapa de tráfico actual" como feature. Referencia: arquitectura de tráfico de Google Maps. No implementar hasta validar el modelo con flota por agencia.

**Línea de investigación — filtrar fleet al mismo shape/corredor:**
Los vehículos de la agencia en rutas completamente distintas (ej: línea 168 norte vs línea 168 sur) aportan señal débil o ruido. Filtrar el fleet_flat a solo los vehículos en el mismo corredor geográfico reduciría ruido y costo computacional. Requiere conocer el ramal resuelto de cada vehículo del fleet en el snapshot (disponible vía ramal_map.json en producción, y reconstruible en el pipeline de features offline). No requiere cambio en la arquitectura — solo en cómo se construye fleet_flat en build_dataset.py.

### Arquitectura real del Modelo 2 (A3ETAModel)

```
TrajectoryEncoder  (3 → d_model, 4 heads, 3 capas transformer, mean pooling)
  input:  (batch, 10, 3)  — dist_along_norm, speed/30, dt/30; paddeado a 10 pts
  output: (batch, d_model)

FleetEncoder  (5 → d_model, 4 heads, 3 capas transformer, CLS token)
  input:  (batch, N_FLEET, 5)  — lat_norm, lon_norm, speed, direction_id, is_same_dir
  output: (batch, d_model)
  si n_fleet=0: zeros (modelo degrada a no-fleet)

  direction_id (0/1): permite al modelo diferenciar tráfico en sentido contrario — un bus
    yendo en la dirección opuesta viaja por el mismo corredor pero no predice el delay del
    vehículo consultado. is_same_dir (0/1): flag precomputado que marca si el vehículo de
    la flota va en el mismo sentido que el vehículo consultado — evita que el modelo tenga
    que aprender esa comparación desde los datos. Ambos se pasan porque direction_id aporta
    información absoluta (norte vs sur puede tener patrones de congestión distintos) mientras
    que is_same_dir aporta información relativa al vehículo consultado.

TimeEncoder
  input:  hour_sin(1) + hour_cos(1) + dow → Embedding(7, 8)
  → Linear(10 → 16)
  output: (batch, 16)

Scalars (5 features):
  dist_remaining_norm   — dist_remaining_m / shape_length_m
  time_since_start      — segundos desde start_time / 3600
  ts_age_s              — staleness GPS: min(frame_t - vehicle_ts, 600) / 600
  has_active_bus        — 0.0 o 1.0
  schedule_dev_norm     — clip((time_since_start_s - mediana_bucket) / 600, -3, 3)
                          las medianas son por ramal_id × bucket: este scalar inyecta
                          identidad de ramal implícitamente sin un embedding explícito.
                          El modelo no ve el ramal_id pero recibe "qué tan atípico es
                          este viaje para este ramal en este punto". Limitación: colapsa
                          la identidad del ramal en un escalar — no distingue entre ramales
                          con tiempos absolutos distintos, solo la desviación relativa.

Concatenar: [traj(d_model) + fleet(d_model) + time(16) + scalars(5)]
  concat_dim = 2 * d_model + 21   → con d_model=64: 149

MLP: Linear(149→256) → GELU → Dropout(0.1) →
     Linear(256→128) → GELU → Dropout(0.1) →
     Linear(128→64)  → GELU → Dropout(0.1) →
     Linear(64→1) → Softplus   ← garantiza output positivo

Output: ETA en segundos (siempre > 0)
```

**Parámetros totales con d_model=64: ~300K.** Epoch ~8.5 min en RTX 3080 (no-fleet).

**Feature pendiente: `time_since_last_bus_s`**
Segundos desde que el último bus del ramal pasó por la posición del usuario. Permite al modelo razonar sobre el headway actual en tiempo real, especialmente útil cuando `has_active_bus=False`. Requiere cambios en el pipeline de training para generar el feature por cada fila — la inferencia es problema del producto. **Señal ruidosa por diseño:** análisis sobre 2 días L39 mostró dt real=60s (no 30s), error de interpolación P90=52s, cobertura con fallback 87.2%. Ver §time_since_last_bus_s para el análisis completo.

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
- **No modelar paradas individuales**: a 30s de resolución no sabemos si el vehículo estuvo 10s o 25s en una parada — solo vemos que en ese ciclo se movió X metros. El modelo aprende el tiempo de parada implícitamente. Ver nota sobre arquitectura alternativa stop-to-stop más abajo.
- **Speed reportada = promedio del período**: si el colectivo estuvo 20s parado y 10s moviéndose a 30 km/h, la API reporta speed = 10 km/h. El modelo aprende estos patrones estadísticamente.
- **Dataset x40 gratis**: cada viaje de 20 minutos genera ~40 ejemplos de entrenamiento, uno por ciclo de 30s. En cada ciclo, el tiempo real hasta que el bus llegó al target es un label válido y observable. No requiere cambio en la arquitectura — solo construir el dataset tomando todos los puntos del viaje como ejemplos independientes, no solo el punto inicial. Un viaje que antes aportaba 1 fila al dataset ahora aporta ~40.

### Datos necesarios

Con modelo unificado (todas las líneas):
- 3 meses: ~21M ejemplos de entrenamiento — más que suficiente
- Comparación: con modelo por línea necesitarías 3 meses por línea, ahora los 3 meses sirven para todo

### Arquitectura alternativa — modelo stop-to-stop

**Idea:** en vez de predecir ETA a cualquier punto del shape, predecir de parada a parada. El target es discreto: "el bus está en parada A, ¿cuánto tarda en llegar a parada B?"

**Ventajas:**
- Problema discreto y repetible: el mismo segmento A→B se repite exactamente igual miles de veces, el modelo aprende distribuciones específicas por segmento
- Menos pares de entrenamiento pero más limpios — sin la varianza de targets arbitrarios
- El "menos pares" es ventaja, no desventaja: con datos acumulándose indefinidamente, no hay escasez de observaciones por segmento
- Captura tiempo de parada por segmento (implícito en el tiempo observado A→B)
- Los segmentos compartidos entre líneas (ej: 39 y 42 por Corrientes) podrían entrenar con datos combinados → ventaja sobre el modelo 1D actual que los trata como shapes separados
- Predicción inversa natural: "estoy arriba, ¿cuándo llego a Y?" es el mismo problema con roles invertidos

**Desventajas:**
- Requiere inferir cuándo el bus pasó cada parada desde GPS con resolución 60s — error de ~30s en el timestamp de pasaje
- No se puede evitar ese error sin interpolación; con interpolación se introduce ruido adicional. Sin interpolación, se acepta el error como ruido del sistema (el modelo lo aprende estadísticamente)
- Solo sirve cuando el usuario está en una parada conocida — no generaliza a posición arbitraria
- Requiere stops confiables en OSM (tenemos datos pero calidad variable)

**Cuándo explorar:** cuando la calidad de stops OSM esté validada y haya 6+ meses de datos. No antes.

---

### Feature `schedule_dev_norm` — desvío del viaje respecto a la mediana histórica

**Qué mide:** para cada ramal y cada posición normalizada `dist_along_norm` (buckets de 5% del recorrido: 0%, 5%, ..., 100%), se computa la mediana histórica del `time_since_start` en ese punto. El feature es cuántos "10 minutos" se desvía el viaje actual de esa mediana:

```
schedule_dev_norm = clip((time_since_start - mediana_bucket) / 600, -3, 3)
```

- Positivo → viaje más lento que lo típico (demorado)
- Negativo → viaje más rápido que lo típico (adelantado)
- Rango: [-3, 3] = ±30 minutos respecto a la mediana
- Las medianas son globales (todos los días y horas mezclados) — captura desvío respecto al promedio histórico total, no respecto a la hora del día

**Por qué complement a `time_since_start`:** `time_since_start` le dice al modelo "este viaje lleva N segundos". `schedule_dev_norm` le dice "ese tiempo es rápido o lento para este ramal en este punto". Son señales distintas — `time_since_start` es absoluto, `schedule_dev_norm` es relativo al historial.

**Pipeline:**
1. `build_schedule_dev_table.py` — lee `eta_train.parquet` con DuckDB, deduplica en `(ramal_id, dist_along_norm, time_since_start)` para evitar bias por vehículos parados, agrupa en 21 buckets por ramal y computa medianas. Output: `data/ml/schedule_dev_medians.json` con keys enteras `"0"`..`"20"` (bucket = `round(dist_along_norm * 20)`).
2. `ETADataset.__init__` — carga el JSON y pre-convierte a `dict[ramal_id → np.ndarray[21]]` para lookup O(1).
3. `ETADataset._iter_group` — por cada row group (250K filas), computa el feature vectorizado sobre todas las filas y lo incluye en cada mini-batch. No se escribe al disco.

**Flujo de regeneración:**
```
# 1. Regenerar el parquet (si hay datos nuevos)
python -m prediccion.pipeline.build_dataset --data-dir Z:\grabaciones --ml-dir data\ml --lines 39

# 2. Regenerar medianas (borrar el JSON primero si hay datos nuevos)
del data\ml\schedule_dev_medians.json
python -m prediccion.pipeline.build_schedule_dev_table

# 3. El trainer las carga automáticamente en el próximo entrenamiento
```

No hace falta `--merge-only` ni reescribir el parquet.

---

### Feature `time_since_last_bus_s` — análisis de señal y diseño de implementación

**Qué mide:** segundos desde que el último bus del mismo ramal pasó por la posición target del usuario. Captura el headway en tiempo real, complementando `schedule_dev_norm` (que mide si el viaje *activo* va adelantado) con información sobre el bus *anterior*.

#### Análisis de señal (L39, 2026-06-03 y 2026-06-04, `experiments/headway_analysis/`)

El análisis sobre 2 días, 2572 trips proyectados, respondió 4 preguntas de diseño:

**1. Gaps entre pings consecutivos del mismo vehículo**

| Percentil | dt (s) |
|-----------|--------|
| P25 | 60s |
| P50 | 60s |
| P75 | 64s |
| P90 | 120s |
| P99 | 1292s |

El grabador emite deltas cada 30s pero el vehículo pingea efectivamente cada **60s** (dos ciclos). Gaps > 300s son el 2.5% — raros pero no ignorables. A 10 m/s esto significa ~600m de incertidumbre posicional entre pings consecutivos.

**2. Cobertura de targets bracketados**

Para 5000 targets hipotéticos aleatorios sobre trips reales de L39:
- **Bracketados exactos** (dos pings consecutivos engloban el target): **49.3%**
- **Fallback ≤250m** (ping más cercano dentro de 250m): **38.0%**
- **Miss** (ningún ping en 250m): **12.8%**
- **Cobertura total** (bracket + fallback): **87.2%**

El 12.8% restante corresponde a gaps de datos o zonas donde el bus aceleró mucho. Se maneja con cap=3600s y flag `last_bus_found=False`.

**3. Headways reales de L39**

| Métrica | Pico (7-9h, 17-19h) | Todo el día |
|---------|--------------------|----|
| P25 | 0.8 min | 0.9 min |
| P50 | **1.8 min** | **2.2 min** |
| P75 | 3.5 min | 4.5 min |
| P90 | 5.4 min | 7.0 min |
| > 1 hora | 0.0% | 0.1% |

El cap de 3600s (1h) está bien justificado: prácticamente nunca se alcanza. La feature es más informativa en el rango 60-540s (P25-P90). L39 tiene headway muy corto en hora pico — la varianza del headway real es lo que hace útil la feature (no el promedio histórico, que ya lo captura `schedule_dev_norm`).

**4. Error de interpolación lineal (supuesto de velocidad constante)**

| Percentil | Error (s) |
|-----------|-----------|
| P50 | 24.3s |
| P75 | 38.9s |
| P90 | 51.8s |
| P99 | 87.9s |

El 96.4% de casos tiene error < 60s. El P90 de ~52s sobre headways medianos de 132s implica un **error relativo de ~39% en el peor caso típico**.

**Conclusión de señal:** la interpolación lineal es suficiente (no hay evidencia de aceleración/frenada no lineal sistemática que justifique un modelo más complejo). La señal es ruidosa por diseño — el dt=60s es el límite físico del sistema. El modelo debe aprender a ponderar esta señal según su incertidumbre intrínseca.

#### Diseño de implementación

**Interpolación lineal para estimar timestamp de pasaje:**
```
Para (ping_i, ping_{i+1}) que bracketean F_dist:
  t_passage = ping_i.ts + (F_dist - ping_i.dist) / (ping_{i+1}.dist - ping_i.dist) * (ping_{i+1}.ts - ping_i.ts)
```

**Fallback cuando no hay bracket:**
- Ping más cercano dentro de ±250m → usar su timestamp directamente (error máximo ~30s a 10 m/s)
- Ningún ping en 250m → `time_since_last_bus_s = 3600` (cap) + `last_bus_found = False`

**Columnas nuevas en el parquet:**
- `time_since_last_bus_s`: float32, cap 3600s. NaN → 3600 (no almacenar NaN para simplificar el schema).
- `last_bus_found`: bool. False cuando se usó el cap por falta de datos.

**Estructura en memoria durante `build_dataset.py`:**
```python
ramal_passage_cache: dict[ramal_id, list[tuple[vehicle_id, list[tuple[dist_m, ts]]]]]
```
Por cada training row (ramal_id=R, F_dist=D, vehicle_id=V, P_ts=T): iterar trips en cache[R] en orden cronológico inverso, excluir vehicle_id=V, interpolar timestamp de pasaje por D, retornar T − t_passage del primer candidato con t_passage < T.

**Bordes de día:** cargar los últimos 10 trips de cada ramal del día anterior al iniciar el procesamiento del día N (análogo al `_carry_window_s` existente).

**En el modelo:**
- Añadir `time_since_last_bus_s / 3600` como scalar adicional al bloque Scalars (dim 5 → 7, concat_dim 149 → 151).
- Añadir `last_bus_found` como segundo scalar adicional (0.0/1.0).
- Considerar `log1p(time_since_last_bus_s) / log1p(3600)` como normalización alternativa (comprime la cola larga de la distribución de headways).

**Archivos a modificar:**
| Archivo | Cambio |
|---------|--------|
| `prediccion/pipeline/build_dataset.py` | `ramal_passage_cache`; poblar con trips proyectados; query por training row |
| `prediccion/pipeline/features.py` | Outputs `time_since_last_bus_s` y `last_bus_found` en `make_training_rows_eta` |
| `prediccion/pipeline/build_dataset.py` | Ampliar `_make_eta_schema()` con 2 columnas nuevas |
| `prediccion/models/eta_dataset.py` | Incluir las 2 features nuevas en el tensor de scalars |
| `prediccion/models/a3_eta.py` | `scalar_dim` 5 → 7, `concat_dim` 149 → 151 |

---

### Distancia mínima de predicción — 100m

El pipeline no genera pares de entrenamiento con `dist_remaining_m < 100m`, y el dataset los filtra también como safety net (`eta_dataset.py`). Por debajo de 100m la incertidumbre de GPS (~10m) y la resolución temporal (30s × 7m/s = 210m por ping) hacen que cualquier predicción sea no confiable. A esa distancia el producto muestra "llegando" directamente sin llamar al modelo.

El caso concreto que motivó el umbral: un bus parado en la terminal proyecta a ~14m del final del shape. Genera el par `dist_remaining=14m, eta=2h` — el modelo intenta aprender "¿cuánto tarda el bus en moverse 14 metros?" cuando en realidad el bus no va a moverse en horas. Esos pares envenenan el entrenamiento en el bucket de distancia corta.

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

### El modelo como predictor de "cuándo pasa el próximo bus"

El Modelo 2 no es solo un "predictor de ETA de un bus corriendo" — es un predictor de cuándo pasa el próximo bus del ramal por el target del usuario. Un bus visible es una feature de alta calidad, no un prerequisito.

**`has_active_bus`** existe en la arquitectura pero es siempre 1.0 en training — el pipeline genera pares solo desde observaciones reales de GPS, donde siempre hay un bus presente. El caso `has_active_bus=False` nunca fue entrenado. En la práctica el modelo actual solo funciona bien cuando hay bus visible.

**Pendiente — `time_since_last_bus_s`:** segundos desde que el último bus del ramal pasó por el target del usuario. Es una feature sobre el bus **anterior**, no el actual — computable desde el historial de trips para cada fila del parquet sin pares sintéticos: dado (ramal, posición, timestamp T), se busca cuándo fue el trip previo del mismo ramal por ese punto. En inferencia se calcula igual desde los últimos buses registrados, independientemente de si hay un bus en camino ahora.

Con esta feature el modelo tiene: `dist_remaining` para señal del bus activo + `time_since_last_bus_s` para señal de headway en tiempo real. La combinación hace a `has_active_bus` redundante — el modelo puede inferir el estado desde ambas. "El último bus pasó hace 3 min, el headway típico es 8 min → quedan ~5 min" es inferible sin un flag explícito.

No reemplazado por las medianas: `schedule_dev_norm` describe si el viaje activo va adelantado o atrasado; `time_since_last_bus_s` describe cuándo fue el bus anterior para el usuario que espera. Señales distintas.

**Ruido intrínseco medido (L39, 2 días):** el dt real entre pings consecutivos es 60s (no 30s como asumía el diseño inicial), lo que introduce una incertidumbre posicional de ~300-600m entre pings. La interpolación lineal para estimar el timestamp de pasaje por el target tiene P50=24s y P90=52s de error. El headway mediano de L39 es ~2.2 min (132s). En el peor caso (P90 de error = 52s sobre headway mediano 132s) el error relativo es ~39%. El modelo debe aprender a trabajar con esta señal ruidosa — no es una señal limpia como `dist_remaining`. Ver §time_since_last_bus_s.

**A1** sigue siendo útil como baseline de medición, no como componente en producción.

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
Z:\grabaciones\                          # SMB desde NUC (192.168.0.18:/mnt/buffer/grabaciones)
  2026-03-28.ndjson.gz
  2026-03-29.ndjson.gz
  ...

prediccion colectivos\data\ml\
  training\
    days\
      39\                                # caché por día × línea (se saltea si ya existe)
        2026-03-28.ndjson.parquet
        2026-03-29.ndjson.parquet
        ...
    eta_train.parquet                    # merge de los últimos 80% de días
    eta_val.parquet                      # merge del 20% restante
  trips\
    days\39\...                          # trips segmentados por día (resumen)
    trips_summary.parquet                # todos los trips mergeados
  models\
    eta_a3_best.pt                       # checkpoint del mejor epoch (val MAE)
    eta_a3_final.onnx                    # exportado para producción
    eta_a3_<config>_<date>.pt            # checkpoints nombrados por run
    eta_a3_<config>_<date>_metrics.json  # métricas de cada run
    a1_v<hash>.pkl                       # modelos A1 (lookup estadística)
    perf_log.jsonl                       # log de performance por epoch
  schedule_dev_medians.json              # medianas históricas por ramal×bucket (generado por build_schedule_dev_table.py)
  experiments\
    arriving_threshold_<date>.json       # resultados de experimentos offline

ramal_lookup\                            # en la raíz del proyecto
  ramal_map.json                         # lookup route_id → shape_id, con first_seen/last_seen
  families_39.json                       # familias de fraccionados por línea
  build_ramal_map.py
  route_lookup.py
```

---

## 9. Hardware: RTX 3080

GPU de entrenamiento. VRAM 10 GB GDDR6X. AMP (mixed precision FP16/FP32) habilitado automáticamente cuando CUDA está disponible.

### Tiempos reales observados (línea 39, no-fleet)

| Métrica | Valor medido |
|---------|-------------|
| VRAM usada por el modelo | ~36 MB — la VRAM no es el bottleneck |
| Throughput | ~40 its/seg con batch_size=8192 |
| Tiempo por epoch (no-fleet) | ~505s ≈ 8.5 min |
| Tiempo por epoch (fleet, cap=20) | ~6235s ≈ 1.7h — bloqueado, ver §fleet |
| Run completo 24 epochs no-fleet | ~3.4h |
| t_fetch_ms (I/O parquet → GPU) | <1ms — no es el bottleneck |
| t_bwd_ms (backward pass) | ~20ms — domina el tiempo de step |

### Pipeline de dataset — tiempos reales

| Paso | Herramienta | Tiempo |
|------|-------------|--------|
| NDJSON → caché por día × línea | `build_dataset.py` (Python + PyArrow) | ~2-5 min/día (solo días nuevos) |
| Merge caché → `eta_train/val.parquet` | PyArrow streaming | ~5-10 min (línea 39, 71.5M filas) |
| Construir `schedule_dev_medians.json` | `build_schedule_dev_table.py` (DuckDB) | ~2-3 min |
| Construir lookup Modelo 1 | `build_ramal_map.py` (Python geométrico) | minutos por línea |

No hay paso de "reconstruir snapshots" separado — `build_dataset.py` lee los NDJSON directamente y hace todo en un pase.

### Setup

- **Python 3.13**, PyTorch 2.x con CUDA 12.x
- Grabaciones en NUC montadas vía SMB en `Z:\grabaciones` (192.168.0.18:/mnt/buffer/grabaciones)
- `eta_train.parquet` línea 39: ~3-6 GB en disco (FixedSizeList float32, zero-copy con numpy)

### Tamaño de los modelos entrenados

| Artefacto | Parámetros | Tamaño en disco |
|--------|------------|------------------------|
| Ramal ID (`ramal_map.json`, lookup) | — | ~KB por línea (JSON) |
| ETA (`eta_a3_final.onnx`) | ~300K | ~1.5 MB |

El modelo ONNX se carga en milisegundos y corre <1ms por inferencia en CPU.

---

## 10. Fases de implementación

### Fase 0 — Grabación ✅

Grabador corriendo en NUC. NDJSON delta + gzip, ~4.3 GB/mes. Sin acción pendiente.

### Fase 1 — Pipeline de datos ✅

Pipeline end-to-end implementado y funcionando:
- `build_dataset.py`: NDJSON → caché por día × línea → `eta_train/val.parquet`
- `build_schedule_dev_table.py`: medianas históricas por ramal × bucket → `schedule_dev_medians.json`
- A1 (lookup estadística por segmento): implementado, disponible en `data/ml/models/a1_v*.pkl`

### Fase 2 — Identificación de ramal ✅

Lookup geométrica offline implementada en `ramal_lookup/`:
- `ramal_map.json`: lookup `route_id → shape_id`, reconstruida en 1-2 días post-rotación
- Validado línea 39: 36/36 route_ids en 3 períodos, incluidos fraccionados (39D/E/F)
- Integración en producción: pendiente (proyectoconsola)

### Fase 3 — ETA con tráfico 🔄

Modelo A3ETAModel entrenado y funcionando. Estado actual:

**No-fleet (activo):**
- Mejor modelo: epoch 24, val MAE **72s** (`eta_a3_nofleet_gfull_ep24_mae72s_20260605`)
- En producción como `eta_a3_best.pt` + `eta_a3_final.onnx`

**Fleet (bloqueado):** ~12× más lento por epoch por el FleetEncoder transformer. Ver opciones en §Estado actual.

**Pendiente de Fase 3:**
- Resolver bottleneck fleet
- Integrar ONNX en proyectoconsola con buffer rolling de 5 min
- Agregar líneas al parquet (actualmente solo línea 39)

### Fase 4 — Fine-tuning automático ⏳

Pendiente post-integración en producción:
- Cron mensual: `build_dataset.py` + `build_schedule_dev_table.py` + reentrenamiento sobre parquet actualizado
- Cron semanal: detectar route_ids nuevos → reconstruir `ramal_map.json`
- Monitoreo de val MAE en producción para detectar drift

### Fase 5 — Modelo enriquecido ⏳

Si la calidad de Fase 3 no alcanza con 6+ meses de datos:
- Reemplazar MLP por Transformer Seq2Seq para capturar correlación temporal entre segmentos
- MAE objetivo: <1 min en viajes de 30 min

### Tabla resumen

| Fase | Estado | MAE ETA | Notas |
|------|--------|---------|-------|
| 0 — Grabación | ✅ corriendo | — | NUC activo |
| 1 — Pipeline | ✅ completo | — | `build_dataset.py` funcional |
| 2 — Ramal lookup | ✅ completo | — | `ramal_map.json`, 36/36 L39 |
| 3 — ETA no-fleet | ✅ entrenado | **72s** | integración a producción pendiente |
| 3 — ETA fleet | 🔄 bloqueado | — | FleetEncoder 12× más lento |
| 4 — Mantenimiento auto | ⏳ pendiente | — | post integración |
| 5 — Transformer ETA | ⏳ pendiente | <60s objetivo | 6+ meses de datos |

---

## 10.1 Scope: 7 líneas es el punto de partida

### Modelo 1 — ramal ID: las 7 líneas son el punto de partida, no el scope completo

La gran mayoría de las líneas de CABA y AMBA tienen múltiples ramales. Contando fraccionados × 2 direcciones, son fácilmente 4-8 route_ids por línea. Con ~100 líneas en CABA más AMBA: **cientos de route_ids a identificar**. 

Las 7 líneas con shapes en `line_shapes.json` son el punto de partida por disponibilidad de shapes — no porque sean las únicas que lo necesitan.

**Escalado trivial:** agregar una línea nueva es crear su `families_{line}.json` (vacío `{}` si no tiene fraccionados) y volver a correr `build_ramal_map.py`. No hay entrenamiento, ni fine-tune, ni transfer learning — la misma lógica geométrica aplica a cualquier línea. 

El bottleneck sigue siendo el mismo en todos los casos: **shapes per-ramal precisos**. Sin shape, no hay ramal ID posible. 

### Modelo 2 — ETA: entrena en 7, funciona en cualquier línea con shape

El modelo unificado de ETA aprende: *"dado X metros restantes, velocidad Y, tráfico actual Z, hora W → N segundos"*. Eso no es específico del 39 o el 42 — es comportamiento de tráfico urbano en CABA. Las 7 líneas cubren diversidad de recorridos: avenidas, barrios, zona norte, zona oeste. El modelo aprende el patrón general.

**Agregar una línea nueva no requiere reentrenar el modelo.** Solo necesitás el shape para proyectar la posición. Sin embargo, `schedule_dev_norm` defaultea a `0.0` para ramales sin entrada en `schedule_dev_medians.json` — el modelo funciona, pero sin señal de desvío histórico para esa línea. Para tenerla hay que agregar la línea al parquet y regenerar `schedule_dev_medians.json` (operación DuckDB de minutos, no entrenamiento).

Con 7 líneas × 30 trips/día × 90 días: ~1.5M ejemplos de entrenamiento. Para un MLP de ~300K parámetros es más que suficiente.

### Inferencia remota: no aplica

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
