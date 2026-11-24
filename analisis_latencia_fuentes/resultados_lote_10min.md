# Estampado por lote, Δts y plausibilidad (analisis_lote.py)

Archivo: `captura_20261113-204553.ndjson`. Primer poll 2026-11-13 20:45:59, último 20:55:48 (hora local, corregida por NTP +0.261 s). Duración 9.8 min. Requests OBA: 40; incidentes: 0.

## b) Firmas de lote

### Por respuesta (ts distintos vs coches)

| fuente | respuestas | coches/resp p50 | ts distintos/resp p10 / p50 / p90 | distintos / coches p50 | mayor grupo con mismo ts (% de la respuesta) p50 / p90 | coches con dato de ≤ 120 s de edad p50 | ts distintos entre esos p50 |
|---|---|---|---|---|---|---|---|
| CABA | 40 | 135 | 29 / 31 / 34 | 0.231 | 26 % / 28 % | 111 | 9 |
| OBA | 40 | 78.5 | 39 / 48 / 58 | 0.609 | 10 % / 12 % | 22 | 6.5 |

### Sobre puntos únicos (coche, ts) por fuente

| fuente | puntos únicos | con milisegundos | pares (sobre ts enteros) | pares (sobre floor de todos) | en segundos 40-59 del minuto |
|---|---|---|---|---|---|
| CABA | 1232 | 0.0 % | 100.0 % | 100.0 % | 94.2 % |
| OBA | 998 | 6.3 % | 45.0 % | 44.5 % | 42.4 % |

Reparto por segundo del minuto (ts mod 60), % por franja de 10 s (uniforme = 16.7 %):

| fuente | 0-9 | 10-19 | 20-29 | 30-39 | 40-49 | 50-59 | top 6 segundos (% c/u; uniforme 1.7 %) |
|---|---|---|---|---|---|---|---|
| CABA | 0.0 | 3.1 | 2.8 | 0.0 | 56.2 | 37.9 | 48: 31.2, 50: 25.4, 46: 23.9, 52: 12.5, 18: 1.7, 22: 1.5 |
| OBA | 4.0 | 32.0 | 19.2 | 2.4 | 2.7 | 39.7 | 55: 12.1, 20: 10.9, 17: 10.6, 19: 9.9, 18: 9.0, 21: 7.9 |

Evolución de la firma por bloque de 10 min (según hora de primera recepción del punto; pares / milisegundos / segundos 40-59, sobre puntos únicos):

| bloque (min) | CABA n | CABA pares | CABA ms | CABA 40-59 | OBA n | OBA pares | OBA ms | OBA 40-59 |
|---|---|---|---|---|---|---|---|---|
| 0-10 | 1232 | 100.0 % | 0.0 % | 94.2 % | 998 | 44.5 % | 6.3 % | 42.4 % |

## a) ts_CABA − ts_OBA para el mismo punto

Match por id y posición ≤ 2 m, sólo pares inequívocos (un solo fix CABA y un solo fix OBA del coche dentro de 2 m entre sí; se excluyen coches detenidos con posiciones repetidas). Bloques de 15 min contados desde el primer poll, según el ts de OBA del punto.

Pares inequívocos: 848 de 969 fixes OBA de coches comunes (87.5 %).

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| Δts s [39] | 460 | 27.0 | 29.0 | 58.0 | -4.0 | 85.0 |
| Δts s [168] | 388 | 27.0 | 29.0 | 58.0 | -44.6 | 63.0 |
| Δts s [todas] | 848 | 27.0 | 29.0 | 58.0 | -44.6 | 85.0 |

Por bloque de 15 min (n, p10 / p50 / p90 en s):

| bloque | 39 | 168 | ambas |
|---|---|---|---|
| 0 (min 0-9) | n=351, 27.0 / 29.0 / 58.0 | n=300, 27.0 / 29.0 / 58.0 | n=651, 27.0 / 29.0 / 58.0 |

Por bloque de 5 min (ambas líneas; hora local de inicio según ts de OBA; Δts ≥ 20 s = régimen desfasado):

| inicio | n | p10 / p50 / p90 | % con Δts ≥ 20 s |
|---|---|---|---|
| 20:45 | 409 | 27.0 / 29.0 / 58.0 | 98.3 % |
| 20:50 | 242 | 27.0 / 29.0 / 57.0 | 96.7 % |

Histograma por valor (Δts redondeado al segundo; sólo valores con ≥ 2 % de los pares):

- 39 (n=460): 29 s: 88 (19.1 %), 28 s: 85 (18.5 %), 57 s: 60 (13.0 %), 27 s: 40 (8.7 %), 56 s: 33 (7.2 %), 58 s: 28 (6.1 %), 30 s: 17 (3.7 %), 55 s: 16 (3.5 %), 59 s: 16 (3.5 %). En 27-31 s: 51.7 %; en 55-61 s: 34.1 %; fuera de ambas ventanas: 14.1 %.
- 168 (n=388): 29 s: 71 (18.3 %), 28 s: 65 (16.8 %), 57 s: 53 (13.7 %), 27 s: 41 (10.6 %), 58 s: 37 (9.5 %), 56 s: 32 (8.2 %), 55 s: 16 (4.1 %), 59 s: 10 (2.6 %), 30 s: 10 (2.6 %). En 27-31 s: 49.5 %; en 55-61 s: 39.7 %; fuera de ambas ventanas: 10.8 %.
- todas (n=848): 29 s: 159 (18.8 %), 28 s: 150 (17.7 %), 57 s: 113 (13.3 %), 27 s: 81 (9.6 %), 58 s: 65 (7.7 %), 56 s: 65 (7.7 %), 55 s: 32 (3.8 %), 30 s: 27 (3.2 %), 59 s: 26 (3.1 %). En 27-31 s: 50.7 %; en 55-61 s: 36.7 %; fuera de ambas ventanas: 12.6 %.

### a2) Retraso de publicación (primera recepción − ts) y reparto de segundos por régimen

No hay cambio de régimen en esta captura (Δts ≥ 20 s no pasa de mayoría a minoría).

## c) Prueba de plausibilidad: velocidades entre fixes consecutivos con cada base de tiempo

### c1) Mismos puntos, distinta base de tiempo (control: la distancia es idéntica, sólo cambia el reloj)

Puntos emparejados por posición (sección a), consecutivos por ts de OBA. Régimen "desfasado": ts_CABA − ts_OBA ≥ 20 s en ambos extremos del intervalo; "alineado": < 20 s en ambos (ver sección a: el desfase no es constante en el tiempo). Distancia sobre el shape si ambos puntos proyectan (≤ 120 m), si no haversine.

**c1-todos**

| base | intervalos | v > 25 m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ 20 m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \|Δln v\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |
|---|---|---|---|---|---|---|---|---|
| ts OBA | 740 | 0 (0.0 %) | 1 / 226 | 718 | 3.98 | 0.581 | 0.649 | 0.359 |
| ts CABA | 740 | 0 (0.0 %) | 0 / 238 | 718 | 3.92 | 0.558 | 0.616 | 0.333 |

Intervalos con distancia sobre el shape: 732; por haversine: 8. Coches con intervalos: 97.
Intervalos con `speed` reportada > 3 m/s y movimiento ≥ 20 m: la base CABA queda más cerca de la `speed` reportada en 157, la base OBA en 130 (empates excluidos).
Intervalo de tiempo entre puntos consecutivos (p10 / p50 / p90): OBA 57.0 / 60.0 / 80.0; CABA 57.8 / 60.0 / 62.0.

**c1-desfasado**

| base | intervalos | v > 25 m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ 20 m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \|Δln v\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |
|---|---|---|---|---|---|---|---|---|
| ts OBA | 704 | 0 (0.0 %) | 1 / 210 | 683 | 3.98 | 0.566 | 0.637 | 0.357 |
| ts CABA | 704 | 0 (0.0 %) | 0 / 221 | 683 | 3.91 | 0.559 | 0.613 | 0.333 |

Intervalos con distancia sobre el shape: 696; por haversine: 8. Coches con intervalos: 97.
Intervalos con `speed` reportada > 3 m/s y movimiento ≥ 20 m: la base CABA queda más cerca de la `speed` reportada en 142, la base OBA en 120 (empates excluidos).
Intervalo de tiempo entre puntos consecutivos (p10 / p50 / p90): OBA 58.0 / 60.0 / 66.4; CABA 58.0 / 60.0 / 62.0.

**c1-alineado**

| base | intervalos | v > 25 m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ 20 m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \|Δln v\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |
|---|---|---|---|---|---|---|---|---|
| ts OBA | 0 | 0 (-) | 0 / 0 | 0 | None | nan | None | None |
| ts CABA | 0 | 0 (-) | 0 / 0 | 0 | None | nan | None | None |

Intervalos con distancia sobre el shape: 0; por haversine: 0. Coches con intervalos: 0.
Intervalos con `speed` reportada > 3 m/s y movimiento ≥ 20 m: la base CABA queda más cerca de la `speed` reportada en 0, la base OBA en 0 (empates excluidos).
### c2) Todos los fixes de cada fuente (con su propio ts)

| base | intervalos | v > 25 m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ 20 m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \|Δln v\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |
|---|---|---|---|---|---|---|---|---|
| OBA (todos los fixes) | 838 | 0 (0.0 %) | 7 / 238 | 767 | 3.96 | 0.582 | 0.65 | None |
| CABA (todos los fixes) | 1095 | 0 (0.0 %) | 2 / 349 | 1001 | 3.84 | 0.576 | 0.632 | 0.337 |

`speed` reportada sólo existe en CABA; en OBA la columna queda vacía. Un CV robusto o jitter menores indican velocidades más estables con esa base de tiempo; esto no prueba cuál reloj coincide con el tiempo real, sólo cuál es más coherente con un movimiento regular.

