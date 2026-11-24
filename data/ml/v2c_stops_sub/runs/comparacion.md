# T en paradas reales contra la base `v2c_l1_paradas`

`v2c_l1_paradas`: base (`data/ml/v2c_sub/runs_stops`, T cualquiera del camino); `v2c_l1_paradas_T`: misma receta con T solo en paradas (`data/ml/v2c_stops_sub/runs`). Semillas 0 y 1; cada celda es la media de las semillas salvo donde se aclara. Llega antes = pred - real > 60 s (el coche llega antes de lo anunciado); llega después = real - pred > 60 s; espera extra = media de (real - pred) cuando llega después. Banda principal: ETA real 3-7 min (principal). Veredicto contra la diferencia entre semillas (|MAE s0 - MAE s1|, la mayor de las dos familias). Vara 1 = eval congelado de T en paradas (`data/ml/v2c_stops/eval`); vara 2 = la de siempre, T cualquiera (`data/ml/v2c/eval`).

## vara 1: eval de T en paradas, seen: ETA real 3-7 min (principal) (n = 6262, eval de 30000 filas)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 53.4 | 113.3 | 16.1 | 17.9 | 52.1 |
| v2c_l1_paradas_T | 52.9 | 112.0 | 14.1 | 19.6 | 54.2 |

Por semilla:

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 53.0 / 53.8 | 0.8 | 16.0 / 16.1 | 17.9 / 17.9 |
| v2c_l1_paradas_T | 52.8 / 53.1 | 0.3 | 13.2 / 15.0 | 20.1 / 19.1 |

MAE (s) por banda de ETA real:

| banda | n | base | nuevo | diferencia (nuevo - base) |
|---|---:|---:|---:|---:|
| 3-7 min (principal) | 6262 | 53.4 | 52.9 | -0.4 |
| 0-2 min | 3387 | 26.2 | 21.9 | -4.3 |
| 2-4 min | 3094 | 38.8 | 37.0 | -1.7 |
| 4-6 min | 3140 | 52.8 | 52.8 | +0.0 |
| 6-8 min | 3207 | 66.2 | 66.0 | -0.2 |
| 8-10 min | 2172 | 76.9 | 77.5 | +0.6 |
| 10-15 min | 4459 | 90.2 | 90.6 | +0.4 |
| 15-20 min | 3041 | 107.2 | 108.4 | +1.2 |

Por línea, banda 3-7 min (principal):

| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |
|---|---:|---:|---:|---:|---|---|
| 26 | 77 | 57.8 | 56.1 | -1.7 | 22.1 / 18.8 | 17.5 / 24.0 |
| 39 | 863 | 48.0 | 47.7 | -0.2 | 13.7 / 12.3 | 16.4 / 17.6 |
| 42 | 394 | 59.5 | 57.9 | -1.6 | 20.6 / 16.5 | 19.4 / 22.5 |
| 50 | 489 | 54.2 | 53.7 | -0.6 | 14.4 / 12.5 | 20.4 / 21.6 |
| 92 | 543 | 53.7 | 53.0 | -0.7 | 14.8 / 13.2 | 18.3 / 19.2 |
| 106 | 1011 | 51.2 | 51.3 | +0.2 | 14.9 / 13.2 | 19.1 / 21.0 |
| 107 | 330 | 52.1 | 51.8 | -0.4 | 12.9 / 12.0 | 17.4 / 18.3 |
| 108 | 344 | 47.6 | 49.0 | +1.4 | 11.0 / 11.2 | 17.0 / 19.2 |
| 124 | 337 | 50.1 | 48.6 | -1.5 | 18.0 / 15.9 | 13.8 / 12.9 |
| 132 | 902 | 59.2 | 57.7 | -1.4 | 19.7 / 16.2 | 18.3 / 19.7 |
| 151 | 589 | 57.6 | 57.6 | +0.0 | 18.7 / 16.8 | 16.9 / 19.7 |
| 168 | 383 | 51.9 | 52.1 | +0.2 | 15.4 / 14.0 | 18.3 / 21.0 |

## vara 1: eval de T en paradas, heldout: ETA real 3-7 min (principal) (n = 6396, eval de 30000 filas)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 80.8 | 162.9 | 17.0 | 33.6 | 76.5 |
| v2c_l1_paradas_T | 85.5 | 172.4 | 15.6 | 38.1 | 81.7 |

Por semilla:

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 79.7 / 81.9 | 2.2 | 17.6 / 16.4 | 32.8 / 34.5 |
| v2c_l1_paradas_T | 84.7 / 86.4 | 1.8 | 14.8 / 16.4 | 38.9 / 37.3 |

MAE (s) por banda de ETA real:

| banda | n | base | nuevo | diferencia (nuevo - base) |
|---|---:|---:|---:|---:|
| 3-7 min (principal) | 6396 | 80.8 | 85.5 | +4.7 |
| 0-2 min | 3191 | 32.7 | 31.2 | -1.5 |
| 2-4 min | 3161 | 53.0 | 55.5 | +2.5 |
| 4-6 min | 3193 | 79.6 | 84.7 | +5.0 |
| 6-8 min | 3186 | 103.0 | 108.4 | +5.4 |
| 8-10 min | 2269 | 118.1 | 124.1 | +6.0 |
| 10-15 min | 4483 | 150.0 | 157.6 | +7.6 |
| 15-20 min | 3017 | 184.7 | 194.3 | +9.6 |

Por línea, banda 3-7 min (principal):

| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |
|---|---:|---:|---:|---:|---|---|
| 12 | 3166 | 66.2 | 67.8 | +1.6 | 11.7 / 9.5 | 33.0 / 37.2 |
| 15 | 1639 | 114.1 | 123.3 | +9.2 | 30.0 / 31.8 | 30.0 / 30.9 |
| 128 | 1591 | 75.6 | 81.9 | +6.3 | 14.0 / 11.0 | 38.7 / 47.3 |

## vara 2: eval de siempre (T cualquiera), seen: ETA real 3-7 min (principal) (n = 6738, eval de 30000 filas)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 55.7 | 117.2 | 14.9 | 21.3 | 57.2 |
| v2c_l1_paradas_T | 56.8 | 120.9 | 13.1 | 23.7 | 59.8 |

Por semilla:

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 55.3 / 56.0 | 0.7 | 15.0 / 14.8 | 21.1 / 21.4 |
| v2c_l1_paradas_T | 56.9 / 56.8 | 0.1 | 12.5 / 13.6 | 24.3 / 23.1 |

MAE (s) por banda de ETA real:

| banda | n | base | nuevo | diferencia (nuevo - base) |
|---|---:|---:|---:|---:|
| 3-7 min (principal) | 6738 | 55.7 | 56.8 | +1.2 |
| 0-2 min | 2664 | 23.2 | 24.6 | +1.5 |
| 2-4 min | 3589 | 39.0 | 39.0 | +0.0 |
| 4-6 min | 3448 | 57.2 | 59.0 | +1.8 |
| 6-8 min | 3127 | 67.2 | 68.8 | +1.6 |
| 8-10 min | 2172 | 80.9 | 83.4 | +2.5 |
| 10-15 min | 4432 | 98.4 | 100.5 | +2.2 |
| 15-20 min | 3068 | 112.9 | 113.5 | +0.7 |

Por línea, banda 3-7 min (principal):

| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |
|---|---:|---:|---:|---:|---|---|
| 26 | 62 | 56.2 | 53.9 | -2.4 | 16.1 / 13.7 | 22.6 / 19.4 |
| 39 | 930 | 49.0 | 49.2 | +0.1 | 14.5 / 12.9 | 16.6 / 18.3 |
| 42 | 451 | 61.2 | 63.3 | +2.1 | 16.4 / 13.4 | 22.4 / 27.3 |
| 50 | 448 | 52.4 | 52.1 | -0.3 | 15.3 / 13.5 | 19.4 / 20.5 |
| 92 | 676 | 53.5 | 57.3 | +3.8 | 11.3 / 12.4 | 24.2 / 24.5 |
| 106 | 1020 | 53.9 | 55.1 | +1.2 | 13.9 / 12.7 | 21.4 / 23.3 |
| 107 | 393 | 59.6 | 61.4 | +1.8 | 16.8 / 14.6 | 23.3 / 26.6 |
| 108 | 349 | 63.1 | 64.9 | +1.8 | 16.2 / 12.5 | 23.1 / 27.1 |
| 124 | 365 | 53.1 | 52.4 | -0.8 | 14.2 / 11.9 | 17.8 / 20.0 |
| 132 | 937 | 59.6 | 59.7 | +0.0 | 16.7 / 14.1 | 20.8 / 23.6 |
| 151 | 639 | 59.1 | 61.6 | +2.5 | 15.9 / 13.8 | 24.5 / 28.0 |
| 168 | 468 | 54.2 | 55.2 | +1.0 | 14.4 / 11.2 | 23.2 / 26.0 |

## vara 2: eval de siempre (T cualquiera), heldout: ETA real 3-7 min (principal) (n = 6778, eval de 30000 filas)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 82.3 | 167.3 | 15.3 | 36.8 | 79.2 |
| v2c_l1_paradas_T | 87.8 | 177.9 | 14.5 | 40.5 | 84.7 |

Por semilla:

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 80.4 / 84.3 | 4.0 | 15.7 / 14.8 | 35.8 / 37.8 |
| v2c_l1_paradas_T | 87.4 / 88.2 | 0.8 | 13.8 / 15.2 | 41.1 / 40.0 |

MAE (s) por banda de ETA real:

| banda | n | base | nuevo | diferencia (nuevo - base) |
|---|---:|---:|---:|---:|
| 3-7 min (principal) | 6778 | 82.3 | 87.8 | +5.5 |
| 0-2 min | 2588 | 28.4 | 32.5 | +4.1 |
| 2-4 min | 3595 | 51.4 | 55.2 | +3.8 |
| 4-6 min | 3507 | 85.3 | 91.1 | +5.9 |
| 6-8 min | 3172 | 103.7 | 109.9 | +6.3 |
| 8-10 min | 2138 | 121.9 | 129.1 | +7.2 |
| 10-15 min | 4427 | 155.1 | 162.8 | +7.7 |
| 15-20 min | 3073 | 194.9 | 202.0 | +7.1 |

Por línea, banda 3-7 min (principal):

| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |
|---|---:|---:|---:|---:|---|---|
| 12 | 3363 | 69.0 | 71.3 | +2.3 | 9.4 / 8.1 | 37.6 / 40.5 |
| 15 | 1753 | 115.9 | 126.1 | +10.2 | 28.3 / 29.8 | 33.1 / 35.6 |
| 128 | 1662 | 73.9 | 80.7 | +6.8 | 13.5 / 11.2 | 39.0 / 45.8 |

## Veredicto

- vara 1 (paradas), seen: MAE 53.4 -> 52.9 s (+0.4 s de mejora) contra diferencia entre semillas 0.8 s -> sin diferencia clara; llega antes 16.1 -> 14.1 %.
- vara 1 (paradas), heldout: MAE 80.8 -> 85.5 s (-4.7 s de mejora) contra diferencia entre semillas 2.2 s -> EMPEORA; llega antes 17.0 -> 15.6 %.
- vara 2 (T cualquiera), seen: MAE 55.7 -> 56.8 s (+1.2 s) contra diferencia entre semillas 0.7 s -> EMPEORA fuera de paradas; llega antes 14.9 -> 13.1 %.
- vara 2 (T cualquiera), heldout: MAE 82.3 -> 87.8 s (+5.5 s) contra diferencia entre semillas 4.0 s -> EMPEORA fuera de paradas; llega antes 15.3 -> 14.5 %.
