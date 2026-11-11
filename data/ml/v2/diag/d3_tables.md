## 1. Qué shape usan la evaluación, A1 y A3

`eval_seen` toma `shape_id` del parquet diario; ese valor sale de `process_day` -> `geometry_for_trip` -> `best_shape_for_trip(lats, lons, ...)` aplicado a **todos los puntos del viaje completo** (también los posteriores a P) y `dist_along_m`, `dist_remaining_m`, `dist_along_norm` (÷ largo de ese shape) y la trayectoria salen de proyectar el viaje sobre ese shape. A1 recibe `ramal_id` = ese shape_id (`predict_a1`, tabla indexada por `(ramal_id, tramo, hora, día)`). A3 no recibe el id, pero las medianas de `schedule_dev_norm` se buscan por `ramal_id`, y `dist_remaining_norm` / `dist_along_norm` se normalizan por el largo de ese shape. Además el segmentador geométrico corta viajes usando los shapes de la línea (fuga menor y común a todos los modelos). **Confirmado: es el shape ex post del viaje completo para A1 y A3.**

## 2. Filas con P en tramo ambiguo

Definición: shapes con perp < 30 m en los últimos 5 pings hasta P y avance hacia adelante. Filas con historial recuperado: 3768 de 3770.

| candidatos | filas | % |
|---|---|---|
| 0 | 213 | 5.6 |
| 1 | 633 | 16.8 |
| 2 | 497 | 13.2 |
| 3 | 2316 | 61.4 |
| 4 | 9 | 0.2 |
| 5 | 2 | 0.1 |
| 6 | 100 | 2.7 |

**Ambiguas (>= 2 candidatos): 77.6 %** de las filas. El shape ex post está entre los candidatos en 94.3 % de las filas. De las ambiguas, 11.3 % quedan resueltas por la parada objetivo (solo un candidato contiene a T).

Sensibilidad de la definición:

| N pings | perp (m) | % ambiguas |
|---|---|---|
| 3 | 30 | 81.9 |
| 5 | 30 | 77.6 |
| 10 | 30 | 69.9 |
| 5 | 50 | 79.7 |
| 5 | 15 | 68.7 |

Ambiguas por shape ex post (n): 39A ida: 630, 39A vuelta: 659, 39B ida: 463, 39B vuelta: 365, 39C ida: 473, 39C vuelta: 334.

## 3. Error por clase de ambigüedad (A1 y A3 con shape ex post)

| cls | n | MAE A1 | MAE A3 | Δ (A3-A1) | ep Δ | sesgo A1 | sesgo A3 | rem media (km) |
|---|---|---|---|---|---|---|---|---|
| ambiguo, T compartido | 2156.0 | 90.9 | 98.8 | 7.9 | 1.6 | -26.0 | -6.6 | 3.2 |
| ambiguo, T tras la divergencia | 768.0 | 105.2 | 117.0 | 11.8 | 2.9 | -33.8 | -50.6 | 4.5 |
| no ambiguo | 844.0 | 103.9 | 112.7 | 8.9 | 2.5 | -25.2 | -21.4 | 3.5 |
| sin historial | 2.0 | 56.2 | 46.6 | -9.7 | 38.2 | -56.2 | 9.0 | 3.4 |
| TOTAL | 3770.0 | 96.7 | 105.6 | 8.9 | 1.2 | -27.4 | -18.9 | 3.5 |

Mismo corte controlando por distancia restante:

| amb2 | rem | n | MAE A1 | MAE A3 | Δ |
|---|---|---|---|---|---|
| ambiguo | <2 km | 1359.0 | 64.0 | 66.7 | 2.7 |
| ambiguo | 2-5 km | 802.0 | 94.7 | 102.7 | 8.1 |
| ambiguo | 5+ km | 763.0 | 149.3 | 170.2 | 20.8 |
| no ambiguo | <2 km | 400.0 | 65.3 | 66.9 | 1.5 |
| no ambiguo | 2-5 km | 230.0 | 119.5 | 130.4 | 10.9 |
| no ambiguo | 5+ km | 216.0 | 158.1 | 178.3 | 20.1 |

## 4. Modelos sin fuga (diagnóstico)

A1 se consulta con cada candidato compatible con los pings hasta P que además contiene al punto objetivo T, y se promedia o se elige el de mejor ajuste hasta P (menor perp mediano en el historial). A3: misma idea pero la sustitución es aproximada (se recalculan posición, distancia restante y la columna de distancia de la trayectoria; el resto de las entradas queda igual).

| filas | n | A1 ex post | A1 sin fuga (prom.) | A1 sin fuga (mejor ajuste) | A3 ex post | A3 sin fuga (prom., aprox.) | A3 sin fuga (mejor ajuste, aprox.) |
|---|---|---|---|---|---|---|---|
| todas | 3770 | 96.7 | 97.6 | 100.5 | 105.6 | 105.3 | 106.6 |
| >= 2 candidatos con P y T | 2593 | 94.8 | 96.0 | 100.2 | 103.1 | 102.7 | 104.6 |
| resto | 1177 | 101.1 | 101.1 | 101.1 | 111.0 | 111.0 | 111.0 |
| no ambiguo | 844 | 103.9 | 103.9 | 103.9 | 112.7 | 112.7 | 112.7 |
| ambiguo, T compartido | 2156 | 90.9 | 91.7 | 95.8 | 98.8 | 97.9 | 99.8 |
| ambiguo, T tras la divergencia | 768 | 105.2 | 107.5 | 109.9 | 117.0 | 118.2 | 119.3 |

Pareado (diferencia de MAE en s):

| index | n | A1_expost_minus_A1_lf_mean | A3_minus_A1_expost | A3_minus_A1_leakfree_mean | A3lf_minus_A1lf_mean | se_A3_minus_A1_leakfree_mean |
|---|---|---|---|---|---|---|
| todas | 3770.0 | -0.89 | 8.9 | 8.0 | 7.7 | 1.2 |
| ambiguas (>=2 cand. con P y T) | 2593.0 | -1.3 | 8.4 | 7.1 | 6.7 | 1.5 |
