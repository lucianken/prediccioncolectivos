# Análisis de ramales línea 168 — metodología y resultados

Análisis exhaustivo realizado en junio 2026 sobre 66 días de datos (2026-03-28 → 2026-06-01).
Scripts en `prediccion colectivos/explore_168_*.py`.

---

## Estructura física de la línea 168

**2 ramales reales**, no 3:

| Ramal | Recorrido | Shapes OSM |
|-------|-----------|------------|
| **168A** | La Boca ↔ San Isidro via Lacroze/Cabildo | 5188890 (d0), 4681272 (d1) |
| **168C** | La Boca ↔ Pte. Saavedra via Concepción Arenal | 5188889 (d0), 4049352 (d1) |

El "168D a Darwin" **no es un ramal real**. Es un bug del API (ver abajo).

---

## Mapa de route_ids por período

### Período 1 (mar 29 – may 7/8, 2026)

| route_id | ramal | obs/día | rol |
|----------|-------|---------|-----|
| 1773 | **168A-d0** | 1337/día | La Boca → San Isidro |
| 1781 | **168A-d1** | 2088/día | San Isidro → La Boca |
| 1775 | **168C-d0** | 694/día  | La Boca → Pte. Saavedra |
| 1783 | **168C-d1** | 1508/día | Pte. Saavedra → La Boca |
| **1780** | **DARWIN** | 2170/día | segmento compartido (bug) |
| 1784 | DARWIN-terminal | 106/día | artefacto de terminal |
| 1774 | DARWIN-trans | 170/día  | sub-segmento transitional |
| 1782 | skip | 36/día   | ruido |

### Período 1.5 (may 8–22, 2026)

| route_id | rol |
|----------|-----|
| 1310 | indeterminado — sus transiciones van a 1308/1309/1311/1313 (no son route_ids de 168). Probablemente vehículos haciendo otra línea en transición. |

### Período 2 (may 23+, 2026)

| route_id | ramal | obs/día | rol |
|----------|-------|---------|-----|
| 1254 | **168A-d0** | 1210/día | La Boca → San Isidro |
| 1255 | **168A-d1** | 1945/día | San Isidro → La Boca |
| 1258 | **168C-d0** | 548/día  | La Boca → Pte. Saavedra |
| 1259 | **168C-d1** | 1183/día | Pte. Saavedra → La Boca |
| **1260** | **DARWIN** | 1773/día | segmento compartido (bug) |
| 1261 | DARWIN-terminal | 99/día  | artefacto de terminal |
| 1256 | DARWIN-trans | 205/día | sub-segmento transitional |
| 1257 | skip | 35/día  | ruido |

**Correspondencia entre períodos** (verificada por tasa obs/día):
- 1773 → 1254 (168A-d0)
- 1781 → 1255 (168A-d1)
- 1775 → 1258 (168C-d0)
- 1783 → 1259 (168C-d1)
- 1780 → 1260 (DARWIN)
- 1784 → 1261 (DARWIN-terminal)
- 1774 → 1256 (DARWIN-trans)
- 1782 → 1257 (skip)

---

## El bug Darwin

**Qué pasa:** desde La Boca, tanto 168A como 168C salen hacia el norte por el mismo tramo inicial. El API CuandoSubo asigna route_id 1260/1780 a TODOS los vehículos en ese tramo compartido, etiquetándolos como "168D → a Av. Córdoba y Darwin". Al llegar a la zona Darwin (~lat -34.59, lon -58.44), el API dropea el route_id a vacío por 5 min (max 10) y luego reasigna el route_id correcto (1254 o 1258).

**Ventana horaria del bug:** solo ocurre entre las 05h y las 21h aproximadamente. El servicio nocturno (22h–04h) asigna 1254/1258 directamente sin pasar por Darwin. El bug está asociado al turno diurno — probablemente el sistema arranca flota masivamente a las 06:00 sin distinguir ramal.

**Evidencia:**
- 1260 → next: 168A×304, 168C×304 — exactamente 50/50
- 1780 → next: 168A×1628, 168C×1928 — 46/54
- Drop siempre ocurre en zona lat≈-34.58–34.59, lon≈-58.43–58.44
- El viaje dura ~45 min (La Boca → Darwin) antes del drop
- 1261/1784 son artefactos de terminal: el vehículo se asigna brevemente al retorno del Darwin (dirección 1) mientras espera en la dársena, luego arranca como 1260

**1256/1774 (DARWIN-trans):** sub-segmento entre Darwin y algún punto intermedio, también mixto (185→A, 122→C). Se comporta igual que Darwin.

---

## Features testeadas para predecir el ramal durante Darwin

Análisis sobre 9341 viajes Darwin resueltos (66 días). **Ninguna feature alcanza utilidad operacional.**

### Features descartadas (≤55% accuracy o sin cobertura)

| Feature | Accuracy | Cobertura | Conclusión |
|---------|----------|-----------|------------|
| Patente del vehículo (global) | 54% | 100% | flota rota entre ramales |
| Patente × día de semana | 62% con 7 días → **61% con 65 días** | 100% | efecto muestras chicas, colapsa con más datos |
| Ramal del viaje previo (inbound 1255/1259) | 50% | 93% | exactamente 50/50 |
| Historial intra-día (prior viajes hoy) | 48–56% | variable | no hay consistencia intra-día |
| start_time durante Darwin | ~50% | baja | 65/93 slots son compartidos entre ramales |
| Odómetro delta | 59% | 29% | captura solo movimiento en terminal |
| trip_id (paridad, mod N) | ~50% | 100% | completamente aleatorio |
| trip_id (rango numérico) | gradiente 20–65% | parcial | señal débil, no confiable |
| GPS durante 1261 (terminal) | 56% | 60% | diferencia de 28m, no separable |
| Hora del día | ~50% | — | sin patrón horario |

### Feature con señal real: viaje previo inmediato (mismo día)

```
P(A | prev=A) = 0.616
P(C | prev=C) = 0.629
```

- **62% accuracy, cubre 70% de viajes** (cuando hay viaje previo ese día)
- Primer viaje del día: 52% (sin información)

### Combinación Bayesiana (prior vehículo + viaje previo)

No mejora sobre viaje previo solo. El prior del vehículo es ruido para el 95% de la flota (39/81 vehículos son 45-55% neutros, solo 4 tienen prior fuerte >65%).

```
Curva de confianza del modelo combinado:
  umbral 60%: accuracy=64%  cobertura=51%
  umbral 70%: accuracy=70%  cobertura= 8%
```

### Consistencia intra-día

- 35% de los días-vehículo el vehículo hace un solo ramal todo el día
- 65% cambia de ramal durante el día
- El primer switch ocurre mayoritariamente en el **viaje #2** (56% de los switches)
- Tiempo hasta el primer switch: median=5.3h

La rotación es granular (vuelta a vuelta según planilla), no por turno completo.

---

## Estrategia recomendada para el sistema de ETA

```
1. Si hay viaje Darwin previo del vehículo hoy:
   → usar ese ramal como hint (62% acc)
   → mostrar ETA con baja confianza, ambas opciones si la app lo soporta

2. Si no hay viaje previo hoy:
   → mostrar ambas ETAs (168A y 168C) hasta resolver
   → no ocultar el colectivo

3. En cuanto el API asigna route_id limpio (1254/1258 o 1773/1775):
   → resolver definitivamente, abandonar el hint

4. Stop_ids exclusivos de 168A observados durante el segmento Darwin:
   [201187, 201188, 202182, 202185, 202188, 202190, 203088, 20723, 20840, 20994]
   → si el vehículo reporta uno de esos stops → es 168A con certeza
   → no hay stops exclusivos de 168C en ese tramo (comparten todo hasta Darwin)
```

---

## Metodología general para analizar bugs de route_id

Este análisis es generalizable a cualquier línea con un "route_id ambiguo".

### Paso 1: identificar el Darwin de otra línea

Buscar route_ids que, al dropear a vacío y reasignarse, vayan a **múltiples ramales distintos**. Un Darwin genuino tiene ratio to_A / to_C entre 0.3 y 3.0 con volumen >=20.

```python
# triple-transición: X → '' → Y
drop_to_next[rid][next_rid] += 1
# Si to_clean_A >= 5 y to_clean_C >= 5 → es Darwin
```

### Paso 2: verificar la asignación de route_ids "limpios"

Un route_id limpio (168A, 168C) debe tener sus destinos post-drop dominados (>80%) por un solo ramal. Si tiene mix → puede ser también Darwin o transitional.

### Paso 3: correspondencia entre períodos tras rotación

Usar obs/día normalizada para parear route_ids entre períodos. La tasa se conserva porque el servicio físico no cambia.

### Paso 4: testear predictores en orden

Para cualquier línea con Darwin, testear en este orden (por costo de implementación):

1. **Patente × día de semana** — fácil, inútil si hay muchos días de datos
2. **Ramal del viaje previo** — señal real ~62%, usar como hint suave
3. **GPS durante terminal (1261/análogo)** — si el terminal tiene dársenas separadas, puede funcionar. Buscar diferencia de medias >50m entre ramales.
4. **Stop_ids exclusivos** — buscar stops que aparezcan en el segmento ambiguo solo para un ramal
5. **Combinación Bayesiana** — solo útil si el prior del vehículo es fuerte (>65%)

### Qué NO sirve para este tipo de problema

- trip_id (GTFS obsoleto, no mapea a ramal en tiempo real)
- start_time del segmento ambiguo (demasiado compartido entre ramales)
- Análisis de secuencia/frecuencia entre ramales (proceso ~Markoviano de orden 0.5)
- Patente fija por período largo (flota rota entre ramales con granularidad de vuelta)

---

## Archivos de análisis

Todos en `prediccion colectivos/`:

| Archivo | Qué hace |
|---------|----------|
| `explore_168_transitions.py` | Triple-transiciones, identificación de Darwin |
| `explore_168_features.py` | Features F1–F10, análisis de patente/start_time/GPS/stop_id |
| `explore_168_sequence.py` | Secuencia temporal, headways, start_time inter-día |
| `explore_168_predictors.py` | Features #1 (ramal previo), #2 (intra-día), #4 (odo delta) |
| `explore_168_pred2.py` | Features #7 (plate×weekday), #10 (trip_id), #6 (GPS 1261) |
| `explore_168_full.py` | Análisis completo 66 días: ramal map + Darwin + plate×weekday |
| `explore_168_intraday.py` | Consistencia intra-día, posición del switch |
| `explore_168_bayes.py` | Combinación Bayesiana prior_veh + viaje_previo |
| `route_id_explorer_results.json` | Estadísticas de route_ids hasta 2026-05-29 |
| `research_direction_routeid.md` | Análisis de direction_id y patrones de rotación |
