# Comparación sobre el eval de v2c, modelo por tramos con pérdida L1

Eval `data/ml/v2c/eval` (30.000 filas por conjunto, asignación geo3). `v2b_l1`: entrenado sobre v2b (`data/ml/v2b_sub/runs_l1`); `v2c_l1`: entrenado sobre v2c. Cada celda es la media de las semillas 0 y 1. Llega antes / después = % de filas con |error| > 60 s; espera extra = media de (real - pred) cuando llega después. Banda principal: 3-7 min (principal).

## seen: ETA real 3-7 min (principal) (n = 6738)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 55.7 | 117.5 | 15.3 | 20.7 | 57.1 |
| v2c_l1 | 55.8 | 117.8 | 15.3 | 21.0 | 57.7 |

## seen: ETA real 0-2 min (n = 2664)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 23.6 | 54.2 | 7.5 | 0.1 | 13.3 |
| v2c_l1 | 23.6 | 53.4 | 7.1 | 0.1 | 13.6 |

## seen: ETA real 2-4 min (n = 3589)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 39.5 | 80.7 | 11.7 | 8.5 | 36.0 |
| v2c_l1 | 39.3 | 79.5 | 11.7 | 8.7 | 36.1 |

## seen: ETA real 4-6 min (n = 3448)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 57.4 | 120.5 | 15.3 | 21.6 | 57.8 |
| v2c_l1 | 57.3 | 121.0 | 15.3 | 21.6 | 58.7 |

## seen: ETA real 6-8 min (n = 3127)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 66.8 | 142.4 | 17.7 | 26.3 | 69.5 |
| v2c_l1 | 67.1 | 143.5 | 18.3 | 26.4 | 69.6 |

## seen: ETA real 8-10 min (n = 2172)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 80.7 | 165.6 | 20.8 | 31.6 | 82.9 |
| v2c_l1 | 80.1 | 165.1 | 20.6 | 31.4 | 83.4 |

## seen: ETA real 10-15 min (n = 4432)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 98.8 | 203.8 | 25.2 | 32.8 | 103.9 |
| v2c_l1 | 98.6 | 201.4 | 25.3 | 33.2 | 104.3 |

## seen: ETA real 15-20 min (n = 3068)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 113.0 | 232.8 | 27.7 | 35.1 | 119.9 |
| v2c_l1 | 112.3 | 232.0 | 27.8 | 34.5 | 118.5 |

## seen: semillas 0 / 1 en 3-7 min (principal)

| modelo | MAE s0 / s1 (s) | llega antes s0 / s1 (%) |
|---|---|---|
| v2b_l1 | 55.5 / 55.8 | 15.1 / 15.4 |
| v2c_l1 | 55.7 / 55.9 | 14.8 / 15.9 |

## heldout: ETA real 3-7 min (principal) (n = 6778)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 86.4 | 171.6 | 16.1 | 36.2 | 79.2 |
| v2c_l1 | 87.9 | 176.0 | 18.9 | 34.0 | 79.5 |

## heldout: ETA real 0-2 min (n = 2588)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 30.1 | 70.4 | 12.6 | 0.3 | 14.8 |
| v2c_l1 | 32.0 | 72.2 | 14.0 | 0.5 | 15.0 |

## heldout: ETA real 2-4 min (n = 3595)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 54.1 | 106.1 | 14.1 | 17.5 | 46.8 |
| v2c_l1 | 55.8 | 110.9 | 15.9 | 16.9 | 46.9 |

## heldout: ETA real 4-6 min (n = 3507)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 90.4 | 174.5 | 16.6 | 37.4 | 80.3 |
| v2c_l1 | 92.3 | 179.2 | 19.2 | 35.3 | 80.6 |

## heldout: ETA real 6-8 min (n = 3172)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 108.0 | 210.0 | 17.1 | 45.3 | 99.9 |
| v2c_l1 | 109.0 | 216.7 | 20.2 | 41.3 | 100.7 |

## heldout: ETA real 8-10 min (n = 2138)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 127.9 | 253.6 | 17.8 | 49.1 | 120.3 |
| v2c_l1 | 131.2 | 271.3 | 20.9 | 44.9 | 121.0 |

## heldout: ETA real 10-15 min (n = 4427)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 163.2 | 311.4 | 18.5 | 55.6 | 153.2 |
| v2c_l1 | 162.0 | 320.8 | 21.7 | 51.0 | 150.8 |

## heldout: ETA real 15-20 min (n = 3073)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2b_l1 | 203.7 | 368.6 | 18.4 | 59.9 | 185.0 |
| v2c_l1 | 200.8 | 377.0 | 22.2 | 53.7 | 181.6 |

## heldout: semillas 0 / 1 en 3-7 min (principal)

| modelo | MAE s0 / s1 (s) | llega antes s0 / s1 (%) |
|---|---|---|
| v2b_l1 | 86.0 / 86.9 | 15.3 / 16.9 |
| v2c_l1 | 88.5 / 87.3 | 19.0 / 18.7 |
