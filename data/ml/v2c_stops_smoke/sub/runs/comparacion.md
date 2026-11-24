# T en paradas reales contra la base `v2c_l1_paradas`

`v2c_l1_paradas`: base (`data/ml/v2c_sub/runs_stops`, T cualquiera del camino); `v2c_l1_paradas_T`: misma receta con T solo en paradas (`data/ml/v2c_stops_sub/runs`). Semillas 0 y 1; cada celda es la media de las semillas salvo donde se aclara. Llega antes = pred - real > 60 s (el coche llega antes de lo anunciado); llega después = real - pred > 60 s; espera extra = media de (real - pred) cuando llega después. Banda principal: ETA real 3-7 min (principal). Veredicto contra la diferencia entre semillas (|MAE s0 - MAE s1|, la mayor de las dos familias). Vara 1 = eval congelado de T en paradas (`data/ml/v2c_stops/eval`); vara 2 = la de siempre, T cualquiera (`data/ml/v2c/eval`).

## vara 1: eval de T en paradas, seen: ETA real 3-7 min (principal) (n = 183, eval de 800 filas)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 58.4 | 111.0 | 15.8 | 18.6 | 51.5 |
| v2c_l1_paradas_T | 62.6 | 114.3 | 20.2 | 25.1 | 62.8 |

Por semilla:

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 57.6 / 59.2 | 1.6 | 15.8 / 15.8 | 18.6 / 18.6 |
| v2c_l1_paradas_T | 62.6 / 62.6 | 0.1 | 19.7 / 20.8 | 24.6 / 25.7 |

MAE (s) por banda de ETA real:

| banda | n | base | nuevo | diferencia (nuevo - base) |
|---|---:|---:|---:|---:|
| 3-7 min (principal) | 183 | 58.4 | 62.6 | +4.2 |
| 0-2 min | 82 | 27.0 | 28.3 | +1.3 |
| 2-4 min | 93 | 42.0 | 43.7 | +1.7 |
| 4-6 min | 86 | 58.7 | 69.6 | +10.9 |
| 6-8 min | 88 | 66.3 | 71.3 | +5.0 |
| 8-10 min | 51 | 84.3 | 97.6 | +13.3 |
| 10-15 min | 119 | 71.4 | 107.6 | +36.2 |
| 15-20 min | 81 | 120.9 | 159.2 | +38.3 |

Por línea, banda 3-7 min (principal):

| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |
|---|---:|---:|---:|---:|---|---|
| 26 | 19 | 64.3 | 59.1 | -5.2 | 23.7 / 15.8 | 10.5 / 26.3 |
| 39 | 13 | 42.6 | 69.9 | +27.3 | 11.5 / 19.2 | 23.1 / 30.8 |
| 42 | 12 | 69.7 | 75.0 | +5.3 | 12.5 / 8.3 | 29.2 / 33.3 |
| 50 | 14 | 49.8 | 50.6 | +0.8 | 7.1 / 7.1 | 21.4 / 32.1 |
| 92 | 13 | 67.1 | 56.9 | -10.2 | 42.3 / 38.5 | 7.7 / 15.4 |
| 106 | 30 | 62.5 | 70.9 | +8.3 | 20.0 / 30.0 | 10.0 / 21.7 |
| 107 | 12 | 49.6 | 71.9 | +22.3 | 8.3 / 16.7 | 8.3 / 20.8 |
| 108 | 9 | 75.2 | 61.0 | -14.2 | 33.3 / 44.4 | 11.1 / 11.1 |
| 124 | 5 | 40.8 | 83.1 | +42.3 | 0.0 / 40.0 | 40.0 / 40.0 |
| 132 | 23 | 44.8 | 59.7 | +14.9 | 4.3 / 13.0 | 21.7 / 30.4 |
| 151 | 16 | 60.0 | 47.9 | -12.1 | 9.4 / 15.6 | 25.0 / 12.5 |
| 168 | 17 | 68.1 | 57.9 | -10.2 | 14.7 / 11.8 | 32.4 / 32.4 |

## vara 1: eval de T en paradas, heldout: ETA real 3-7 min (principal) (n = 173, eval de 800 filas)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 78.7 | 166.0 | 18.5 | 29.2 | 78.2 |
| v2c_l1_paradas_T | 79.1 | 151.5 | 24.3 | 32.1 | 83.8 |

Por semilla:

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 76.2 / 81.1 | 4.8 | 14.5 / 22.5 | 30.1 / 28.3 |
| v2c_l1_paradas_T | 78.8 / 79.4 | 0.6 | 25.4 / 23.1 | 32.9 / 31.2 |

MAE (s) por banda de ETA real:

| banda | n | base | nuevo | diferencia (nuevo - base) |
|---|---:|---:|---:|---:|
| 3-7 min (principal) | 173 | 78.7 | 79.1 | +0.5 |
| 0-2 min | 93 | 32.1 | 29.9 | -2.2 |
| 2-4 min | 81 | 51.4 | 47.6 | -3.8 |
| 4-6 min | 88 | 77.9 | 81.6 | +3.7 |
| 6-8 min | 88 | 89.3 | 85.1 | -4.3 |
| 8-10 min | 50 | 142.2 | 137.1 | -5.1 |
| 10-15 min | 123 | 159.5 | 142.9 | -16.6 |
| 15-20 min | 77 | 219.4 | 209.3 | -10.1 |

Por línea, banda 3-7 min (principal):

| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |
|---|---:|---:|---:|---:|---|---|
| 12 | 85 | 60.5 | 64.1 | +3.6 | 12.4 / 13.5 | 27.1 / 35.3 |
| 15 | 45 | 110.7 | 106.6 | -4.1 | 25.6 / 37.8 | 30.0 / 27.8 |
| 128 | 43 | 81.1 | 80.0 | -1.0 | 23.3 / 31.4 | 32.6 / 30.2 |

## vara 2: eval de siempre (T cualquiera), seen: ETA real 3-7 min (principal) (n = 6738, eval de 30000 filas)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 55.7 | 117.2 | 14.9 | 21.3 | 57.2 |
| v2c_l1_paradas_T | 76.9 | 157.0 | 11.4 | 41.2 | 83.0 |

Por semilla:

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 55.3 / 56.0 | 0.7 | 15.0 / 14.8 | 21.1 / 21.4 |
| v2c_l1_paradas_T | 72.0 / 81.8 | 9.8 | 15.5 / 7.3 | 33.3 / 49.1 |

MAE (s) por banda de ETA real:

| banda | n | base | nuevo | diferencia (nuevo - base) |
|---|---:|---:|---:|---:|
| 3-7 min (principal) | 6738 | 55.7 | 76.9 | +21.2 |
| 0-2 min | 2664 | 23.2 | 26.1 | +2.9 |
| 2-4 min | 3589 | 39.0 | 48.1 | +9.1 |
| 4-6 min | 3448 | 57.2 | 78.9 | +21.8 |
| 6-8 min | 3127 | 67.2 | 98.2 | +31.1 |
| 8-10 min | 2172 | 80.9 | 123.3 | +42.4 |
| 10-15 min | 4432 | 98.4 | 153.8 | +55.5 |
| 15-20 min | 3068 | 112.9 | 186.7 | +73.8 |

Por línea, banda 3-7 min (principal):

| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |
|---|---:|---:|---:|---:|---|---|
| 26 | 62 | 56.2 | 67.9 | +11.7 | 16.1 / 9.7 | 22.6 / 41.1 |
| 39 | 930 | 49.0 | 72.2 | +23.2 | 14.5 / 10.6 | 16.6 / 41.1 |
| 42 | 451 | 61.2 | 84.5 | +23.3 | 16.4 / 12.2 | 22.4 / 45.8 |
| 50 | 448 | 52.4 | 67.2 | +14.8 | 15.3 / 10.7 | 19.4 / 36.8 |
| 92 | 676 | 53.5 | 78.1 | +24.6 | 11.3 / 13.5 | 24.2 / 39.3 |
| 106 | 1020 | 53.9 | 73.2 | +19.3 | 13.9 / 11.8 | 21.4 / 38.1 |
| 107 | 393 | 59.6 | 82.1 | +22.6 | 16.8 / 10.9 | 23.3 / 41.3 |
| 108 | 349 | 63.1 | 83.3 | +20.3 | 16.2 / 10.2 | 23.1 / 44.1 |
| 124 | 365 | 53.1 | 75.7 | +22.6 | 14.2 / 11.4 | 17.8 / 40.0 |
| 132 | 937 | 59.6 | 78.6 | +19.0 | 16.7 / 12.1 | 20.8 / 42.7 |
| 151 | 639 | 59.1 | 79.9 | +20.8 | 15.9 / 10.9 | 24.5 / 42.6 |
| 168 | 468 | 54.2 | 79.7 | +25.5 | 14.4 / 10.0 | 23.2 / 44.1 |

## vara 2: eval de siempre (T cualquiera), heldout: ETA real 3-7 min (principal) (n = 6778, eval de 30000 filas)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 82.3 | 167.3 | 15.3 | 36.8 | 79.2 |
| v2c_l1_paradas_T | 87.1 | 170.6 | 12.7 | 45.1 | 88.1 |

Por semilla:

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 80.4 / 84.3 | 4.0 | 15.7 / 14.8 | 35.8 / 37.8 |
| v2c_l1_paradas_T | 82.9 / 91.3 | 8.5 | 16.1 / 9.2 | 38.1 / 52.1 |

MAE (s) por banda de ETA real:

| banda | n | base | nuevo | diferencia (nuevo - base) |
|---|---:|---:|---:|---:|
| 3-7 min (principal) | 6778 | 82.3 | 87.1 | +4.8 |
| 0-2 min | 2588 | 28.4 | 28.9 | +0.6 |
| 2-4 min | 3595 | 51.4 | 53.1 | +1.7 |
| 4-6 min | 3507 | 85.3 | 89.6 | +4.4 |
| 6-8 min | 3172 | 103.7 | 112.5 | +8.8 |
| 8-10 min | 2138 | 121.9 | 134.2 | +12.3 |
| 10-15 min | 4427 | 155.1 | 181.5 | +26.5 |
| 15-20 min | 3073 | 194.9 | 231.6 | +36.7 |

Por línea, banda 3-7 min (principal):

| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |
|---|---:|---:|---:|---:|---|---|
| 12 | 3363 | 69.0 | 81.9 | +12.9 | 9.4 / 8.2 | 37.6 / 49.4 |
| 15 | 1753 | 115.9 | 102.8 | -13.1 | 28.3 / 26.3 | 33.1 / 31.7 |
| 128 | 1662 | 73.9 | 81.0 | +7.1 | 13.5 / 7.3 | 39.0 / 50.6 |

## Veredicto

- vara 1 (paradas), seen: MAE 58.4 -> 62.6 s (-4.2 s de mejora) contra diferencia entre semillas 1.6 s -> EMPEORA; llega antes 15.8 -> 20.2 %.
- vara 1 (paradas), heldout: MAE 78.7 -> 79.1 s (-0.5 s de mejora) contra diferencia entre semillas 4.8 s -> sin diferencia clara; llega antes 18.5 -> 24.3 %.
- vara 2 (T cualquiera), seen: MAE 55.7 -> 76.9 s (+21.2 s) contra diferencia entre semillas 9.8 s -> EMPEORA fuera de paradas; llega antes 14.9 -> 11.4 %.
- vara 2 (T cualquiera), heldout: MAE 82.3 -> 87.1 s (+4.8 s) contra diferencia entre semillas 8.5 s -> no empeora (dentro de la diferencia entre semillas); llega antes 15.3 -> 12.7 %.
