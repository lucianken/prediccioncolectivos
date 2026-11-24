# Estampado por lote, Δts y plausibilidad (analisis_lote.py)

Archivo: `captura_20261113-211401.ndjson`. Primer poll 2026-11-13 21:14:08, último 22:44:14 (hora local, corregida por NTP +0.273 s). Duración 90.1 min. Requests OBA: 360; incidentes: 0.

## b) Firmas de lote

### Por respuesta (ts distintos vs coches)

| fuente | respuestas | coches/resp p50 | ts distintos/resp p10 / p50 / p90 | distintos / coches p50 | mayor grupo con mismo ts (% de la respuesta) p50 / p90 | coches con dato de ≤ 120 s de edad p50 | ts distintos entre esos p50 |
|---|---|---|---|---|---|---|---|
| CABA | 360 | 118 | 30 / 34 / 38 | 0.283 | 32 % / 39 % | 88 | 6 |
| OBA | 360 | 77.5 | 37 / 50 / 66 | 0.667 | 10 % / 16 % | 32 | 8 |

### Sobre puntos únicos (coche, ts) por fuente

| fuente | puntos únicos | con milisegundos | pares (sobre ts enteros) | pares (sobre floor de todos) | en segundos 40-59 del minuto |
|---|---|---|---|---|---|
| CABA | 7838 | 0.0 % | 100.0 % | 100.0 % | 92.9 % |
| OBA | 6688 | 7.6 % | 50.7 % | 50.3 % | 59.6 % |

Reparto por segundo del minuto (ts mod 60), % por franja de 10 s (uniforme = 16.7 %):

| fuente | 0-9 | 10-19 | 20-29 | 30-39 | 40-49 | 50-59 | top 6 segundos (% c/u; uniforme 1.7 %) |
|---|---|---|---|---|---|---|---|
| CABA | 0.0 | 4.3 | 2.8 | 0.0 | 64.6 | 28.3 | 48: 41.6, 50: 27.8, 46: 23.1, 20: 2.8, 18: 2.7, 16: 1.6 |
| OBA | 2.3 | 17.6 | 18.9 | 1.7 | 20.4 | 39.2 | 52: 9.2, 49: 8.6, 48: 8.6, 51: 8.4, 50: 8.3, 53: 6.5 |

Evolución de la firma por bloque de 10 min (según hora de primera recepción del punto; pares / milisegundos / segundos 40-59, sobre puntos únicos):

| bloque (min) | CABA n | CABA pares | CABA ms | CABA 40-59 | OBA n | OBA pares | OBA ms | OBA 40-59 |
|---|---|---|---|---|---|---|---|---|
| 0-10 | 978 | 100.0 % | 0.0 % | 84.3 % | 985 | 49.8 % | 7.9 % | 32.4 % |
| 10-20 | 1066 | 100.0 % | 0.0 % | 94.4 % | 806 | 52.6 % | 3.5 % | 29.7 % |
| 20-30 | 948 | 100.0 % | 0.0 % | 94.7 % | 764 | 46.1 % | 8.6 % | 24.1 % |
| 30-40 | 897 | 100.0 % | 0.0 % | 93.8 % | 710 | 50.1 % | 4.2 % | 25.5 % |
| 40-50 | 782 | 100.0 % | 0.0 % | 93.6 % | 728 | 48.2 % | 9.3 % | 79.1 % |
| 50-60 | 863 | 100.0 % | 0.0 % | 93.9 % | 685 | 48.8 % | 11.1 % | 87.4 % |
| 60-70 | 759 | 100.0 % | 0.0 % | 94.5 % | 741 | 48.2 % | 7.6 % | 91.2 % |
| 70-80 | 818 | 100.0 % | 0.0 % | 94.1 % | 689 | 54.9 % | 7.0 % | 96.4 % |
| 80-90 | 727 | 100.0 % | 0.0 % | 94.1 % | 579 | 55.1 % | 9.7 % | 94.1 % |
| 90-100 | 0 | - | - | - | 1 | 0.0 % | 100.0 % | 100.0 % |

## a) ts_CABA − ts_OBA para el mismo punto

Match por id y posición ≤ 2 m, sólo pares inequívocos (un solo fix CABA y un solo fix OBA del coche dentro de 2 m entre sí; se excluyen coches detenidos con posiciones repetidas). Bloques de 15 min contados desde el primer poll, según el ts de OBA del punto.

Pares inequívocos: 5777 de 6638 fixes OBA de coches comunes (87.0 %).

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| Δts s [39] | 3118 | -3.0 | -1.0 | 56.0 | -46.1 | 89.0 |
| Δts s [168] | 2659 | -3.0 | -1.0 | 54.0 | -44.7 | 88.0 |
| Δts s [todas] | 5777 | -3.0 | -1.0 | 56.0 | -46.1 | 89.0 |

Por bloque de 15 min (n, p10 / p50 / p90 en s):

| bloque | 39 | 168 | ambas |
|---|---|---|---|
| 0 (min 0-15) | n=591, 27.0 / 29.0 / 58.0 | n=520, 27.0 / 29.0 / 58.0 | n=1111, 27.0 / 29.0 / 58.0 |
| 1 (min 15-30) | n=556, 27.0 / 29.0 / 57.0 | n=455, 27.0 / 29.0 / 57.0 | n=1011, 27.0 / 29.0 / 57.0 |
| 2 (min 30-45) | n=507, -2.4 / 27.0 / 33.0 | n=448, -3.0 / 27.0 / 30.0 | n=955, -3.0 / 27.0 / 30.0 |
| 3 (min 45-60) | n=460, -3.0 / -2.0 / -1.0 | n=443, -3.0 / -2.0 / -1.0 | n=903, -3.0 / -2.0 / -1.0 |
| 4 (min 60-75) | n=533, -3.0 / -2.0 / -1.0 | n=427, -3.0 / -2.0 / -1.0 | n=960, -3.0 / -2.0 / -1.0 |
| 5 (min 75-90) | n=418, -3.0 / -2.0 / -1.0 | n=320, -3.0 / -2.0 / -1.0 | n=738, -3.0 / -2.0 / -1.0 |
| 6 (min 90-90) | n=0 | n=0 | n=0 |

Por bloque de 5 min (ambas líneas; hora local de inicio según ts de OBA; Δts ≥ 20 s = régimen desfasado):

| inicio | n | p10 / p50 / p90 | % con Δts ≥ 20 s |
|---|---|---|---|
| 21:14 | 368 | 27.0 / 30.0 / 59.0 | 97.6 % |
| 21:19 | 366 | 27.0 / 29.0 / 57.0 | 96.7 % |
| 21:24 | 377 | 27.0 / 29.0 / 57.0 | 97.6 % |
| 21:29 | 353 | 27.0 / 29.0 / 57.0 | 97.7 % |
| 21:34 | 326 | 27.0 / 28.0 / 57.0 | 95.1 % |
| 21:39 | 332 | 27.0 / 29.0 / 55.8 | 97.3 % |
| 21:44 | 309 | -2.0 / 28.0 / 56.0 | 78.0 % |
| 21:49 | 330 | 27.0 / 28.0 / 33.0 | 96.4 % |
| 21:54 | 316 | -3.0 / -2.0 / -1.0 | 2.2 % |
| 21:59 | 319 | -3.0 / -2.0 / -1.0 | 0.6 % |
| 22:04 | 261 | -3.0 / -2.0 / -1.0 | 0.0 % |
| 22:09 | 323 | -3.0 / -2.0 / -1.0 | 1.2 % |
| 22:14 | 329 | -3.0 / -2.0 / -1.0 | 0.9 % |
| 22:19 | 316 | -3.0 / -2.0 / -1.0 | 0.3 % |
| 22:24 | 315 | -3.0 / -2.0 / -1.0 | 1.9 % |
| 22:29 | 282 | -3.0 / -2.0 / -1.0 | 1.1 % |
| 22:34 | 258 | -2.0 / -2.0 / -1.0 | 1.2 % |
| 22:39 | 198 | -3.0 / -2.0 / -1.0 | 1.0 % |

Histograma por valor (Δts redondeado al segundo; sólo valores con ≥ 2 % de los pares):

- 39 (n=3118): -2 s: 816 (26.2 %), -1 s: 454 (14.6 %), 28 s: 393 (12.6 %), 29 s: 360 (11.5 %), -3 s: 261 (8.4 %), 27 s: 149 (4.8 %), 56 s: 96 (3.1 %), 57 s: 95 (3.0 %), 58 s: 65 (2.1 %). En 27-31 s: 31.3 %; en 55-61 s: 11.0 %; fuera de ambas ventanas: 57.7 %.
- 168 (n=2659): -2 s: 660 (24.8 %), -1 s: 412 (15.5 %), 28 s: 399 (15.0 %), 29 s: 297 (11.2 %), -3 s: 253 (9.5 %), 27 s: 142 (5.3 %), 57 s: 87 (3.3 %), 58 s: 58 (2.2 %), 56 s: 55 (2.1 %). En 27-31 s: 33.8 %; en 55-61 s: 9.6 %; fuera de ambas ventanas: 56.6 %.
- todas (n=5777): -2 s: 1476 (25.5 %), -1 s: 866 (15.0 %), 28 s: 792 (13.7 %), 29 s: 657 (11.4 %), -3 s: 514 (8.9 %), 27 s: 291 (5.0 %), 57 s: 182 (3.2 %), 56 s: 151 (2.6 %), 58 s: 123 (2.1 %). En 27-31 s: 32.5 %; en 55-61 s: 10.3 %; fuera de ambas ventanas: 57.2 %.

### a2) Retraso de publicación (primera recepción − ts) y reparto de segundos por régimen

Corte automático: primer bloque de 5 min a partir del cual < 50 % de los pares tiene Δts ≥ 20 s y no vuelve: 21:54 (hora local). A = antes del corte, B = desde el corte. Retraso: sólo fixes de coches ya vistos antes en esa fuente, aparecidos después del primer poll; cota superior con error de hasta +15 s (CABA) / +30 s (OBA) por la resolución de poll.

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| retraso CABA A | 3669 | 17.5 | 20.0 | 24.0 | 15.6 | 96.6 |
| retraso CABA B | 4036 | 18.9 | 22.1 | 27.1 | 17.2 | 59.0 |
| retraso OBA A | 3105 | 72.0 | 89.7 | 119.4 | 3.4 | 197374.6 |
| retraso OBA B | 3422 | 36.1 | 51.3 | 66.4 | 3.2 | 36830.3 |

Segundos del minuto (ts mod 60) más frecuentes por régimen (% de puntos únicos):

- CABA A (n=3801): 48: 34.9, 50: 32.2, 46: 23.4, 20: 3.5, 18: 2.9, 16: 1.8; en 40-59: 91.6 %
- CABA B (n=4037): 48: 47.8, 50: 23.6, 46: 22.7, 18: 2.5, 20: 2.1, 16: 1.3; en 40-59: 94.1 %
- OBA A (n=3265): 19: 12.3, 18: 11.6, 20: 11.1, 21: 10.6, 22: 9.7, 17: 9.4; en 40-59: 28.3 %
- OBA B (n=3423): 48: 15.6, 49: 15.5, 51: 15.1, 50: 15.1, 52: 14.9, 53: 7.0; en 40-59: 89.4 %

## c) Prueba de plausibilidad: velocidades entre fixes consecutivos con cada base de tiempo

### c1) Mismos puntos, distinta base de tiempo (control: la distancia es idéntica, sólo cambia el reloj)

Puntos emparejados por posición (sección a), consecutivos por ts de OBA. Régimen "desfasado": ts_CABA − ts_OBA ≥ 20 s en ambos extremos del intervalo; "alineado": < 20 s en ambos (ver sección a: el desfase no es constante en el tiempo). Distancia sobre el shape si ambos puntos proyectan (≤ 120 m), si no haversine.

**c1-todos**

| base | intervalos | v > 25 m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ 20 m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \|Δln v\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |
|---|---|---|---|---|---|---|---|---|
| ts OBA | 5665 | 1 (0.0 %) | 5 / 2388 | 5507 | 4.03 | 0.585 | 0.62 | 0.378 |
| ts CABA | 5665 | 0 (0.0 %) | 4 / 2484 | 5507 | 4.03 | 0.536 | 0.553 | 0.342 |

Intervalos con distancia sobre el shape: 5257; por haversine: 408. Coches con intervalos: 111.
Intervalos con `speed` reportada > 3 m/s y movimiento ≥ 20 m: la base CABA queda más cerca de la `speed` reportada en 1146, la base OBA en 744 (empates excluidos).
Intervalo de tiempo entre puntos consecutivos (p10 / p50 / p90): OBA 57.0 / 60.0 / 87.0; CABA 58.0 / 60.0 / 86.0.

**c1-desfasado**

| base | intervalos | v > 25 m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ 20 m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \|Δln v\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |
|---|---|---|---|---|---|---|---|---|
| ts OBA | 2481 | 0 (0.0 %) | 4 / 977 | 2425 | 3.88 | 0.574 | 0.645 | 0.39 |
| ts CABA | 2481 | 0 (0.0 %) | 4 / 1026 | 2425 | 3.92 | 0.529 | 0.569 | 0.353 |

Intervalos con distancia sobre el shape: 2295; por haversine: 186. Coches con intervalos: 108.
Intervalos con `speed` reportada > 3 m/s y movimiento ≥ 20 m: la base CABA queda más cerca de la `speed` reportada en 557, la base OBA en 339 (empates excluidos).
Intervalo de tiempo entre puntos consecutivos (p10 / p50 / p90): OBA 56.0 / 60.0 / 85.0; CABA 58.0 / 60.0 / 62.0.

**c1-alineado**

| base | intervalos | v > 25 m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ 20 m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \|Δln v\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |
|---|---|---|---|---|---|---|---|---|
| ts OBA | 2785 | 0 (0.0 %) | 0 / 1216 | 2706 | 4.2 | 0.554 | 0.56 | 0.341 |
| ts CABA | 2785 | 0 (0.0 %) | 0 / 1236 | 2706 | 4.19 | 0.535 | 0.542 | 0.335 |

Intervalos con distancia sobre el shape: 2599; por haversine: 186. Coches con intervalos: 96.
Intervalos con `speed` reportada > 3 m/s y movimiento ≥ 20 m: la base CABA queda más cerca de la `speed` reportada en 400, la base OBA en 347 (empates excluidos).
Intervalo de tiempo entre puntos consecutivos (p10 / p50 / p90): OBA 58.0 / 60.0 / 63.0; CABA 58.0 / 60.0 / 86.0.

### c2) Todos los fixes de cada fuente (con su propio ts)

| base | intervalos | v > 25 m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ 20 m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \|Δln v\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |
|---|---|---|---|---|---|---|---|---|
| OBA (todos los fixes) | 6523 | 7 (0.1 %) | 90 / 2511 | 5852 | 4.07 | 0.603 | 0.62 | None |
| CABA (todos los fixes) | 7705 | 0 (0.0 %) | 26 / 3173 | 6941 | 4.07 | 0.548 | 0.564 | 0.348 |

`speed` reportada sólo existe en CABA; en OBA la columna queda vacía. Un CV robusto o jitter menores indican velocidades más estables con esa base de tiempo; esto no prueba cuál reloj coincide con el tiempo real, sólo cuál es más coherente con un movimiento regular.

