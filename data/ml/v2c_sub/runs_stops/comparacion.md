# Paradas por tramo contra v2c L1, mismo eval (`data/ml/v2c/eval`)

`v2c_l1`: modelo por tramos L1 sin la feature (`data/ml/v2c_sub/runs`); `v2c_l1_paradas`: igual con `--stops-feature`. Cada celda es la media de las semillas 0 y 1. Llega antes / después = % de filas con error > 60 s; espera extra = media de (real - pred) cuando llega después. Banda principal: 3-7 min (principal). Criterio de adopción (ARQUITECTURA §6.2): mejora del MAE en 3-7 min mayor que la diferencia entre semillas.

## seen: ETA real 3-7 min (principal) (n = 6738)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 55.8 | 117.8 | 15.3 | 21.0 | 57.7 |
| v2c_l1_paradas | 55.7 | 117.2 | 14.9 | 21.3 | 57.2 |

## seen: ETA real 0-2 min (n = 2664)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 23.6 | 53.4 | 7.1 | 0.1 | 13.6 |
| v2c_l1_paradas | 23.2 | 52.7 | 6.9 | 0.1 | 13.7 |

## seen: ETA real 2-4 min (n = 3589)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 39.3 | 79.5 | 11.7 | 8.7 | 36.1 |
| v2c_l1_paradas | 39.0 | 80.0 | 11.2 | 8.6 | 35.7 |

## seen: ETA real 4-6 min (n = 3448)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 57.3 | 121.0 | 15.3 | 21.6 | 58.7 |
| v2c_l1_paradas | 57.2 | 119.2 | 15.0 | 22.0 | 58.0 |

## seen: ETA real 6-8 min (n = 3127)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 67.1 | 143.5 | 18.3 | 26.4 | 69.6 |
| v2c_l1_paradas | 67.2 | 142.5 | 17.9 | 27.0 | 69.8 |

## seen: ETA real 8-10 min (n = 2172)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 80.1 | 165.1 | 20.6 | 31.4 | 83.4 |
| v2c_l1_paradas | 80.9 | 166.9 | 20.7 | 32.2 | 83.3 |

## seen: ETA real 10-15 min (n = 4432)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 98.6 | 201.4 | 25.3 | 33.2 | 104.3 |
| v2c_l1_paradas | 98.4 | 203.7 | 24.6 | 33.4 | 104.1 |

## seen: ETA real 15-20 min (n = 3068)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 112.3 | 232.0 | 27.8 | 34.5 | 118.5 |
| v2c_l1_paradas | 112.9 | 233.3 | 27.1 | 35.3 | 119.6 |

## seen: semillas 0 / 1 en 3-7 min (principal)

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) |
|---|---|---:|---|
| v2c_l1 | 55.7 / 55.9 | 0.3 | 14.8 / 15.9 |
| v2c_l1_paradas | 55.3 / 56.0 | 0.7 | 15.0 / 14.8 |

Mejora del MAE medio en 3-7 min (principal): +0.1 s (diferencia entre semillas: 0.7 s, la mayor de las dos familias) -> no supera el criterio.

## heldout: ETA real 3-7 min (principal) (n = 6778)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 87.9 | 176.0 | 18.9 | 34.0 | 79.5 |
| v2c_l1_paradas | 82.3 | 167.3 | 15.3 | 36.8 | 79.2 |

## heldout: ETA real 0-2 min (n = 2588)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 32.0 | 72.2 | 14.0 | 0.5 | 15.0 |
| v2c_l1_paradas | 28.4 | 64.9 | 11.2 | 0.5 | 15.3 |

## heldout: ETA real 2-4 min (n = 3595)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 55.8 | 110.9 | 15.9 | 16.9 | 46.9 |
| v2c_l1_paradas | 51.4 | 103.0 | 12.9 | 18.6 | 46.8 |

## heldout: ETA real 4-6 min (n = 3507)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 92.3 | 179.2 | 19.2 | 35.3 | 80.6 |
| v2c_l1_paradas | 85.3 | 169.3 | 15.7 | 38.3 | 80.4 |

## heldout: ETA real 6-8 min (n = 3172)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 109.0 | 216.7 | 20.2 | 41.3 | 100.7 |
| v2c_l1_paradas | 103.7 | 206.6 | 16.8 | 45.0 | 99.8 |

## heldout: ETA real 8-10 min (n = 2138)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 131.2 | 271.3 | 20.9 | 44.9 | 121.0 |
| v2c_l1_paradas | 121.9 | 244.1 | 17.3 | 50.1 | 118.7 |

## heldout: ETA real 10-15 min (n = 4427)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 162.0 | 320.8 | 21.7 | 51.0 | 150.8 |
| v2c_l1_paradas | 155.1 | 302.6 | 18.0 | 56.1 | 150.6 |

## heldout: ETA real 15-20 min (n = 3073)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v2c_l1 | 200.8 | 377.0 | 22.2 | 53.7 | 181.6 |
| v2c_l1_paradas | 194.9 | 366.9 | 17.8 | 59.7 | 185.5 |

## heldout: semillas 0 / 1 en 3-7 min (principal)

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) |
|---|---|---:|---|
| v2c_l1 | 88.5 / 87.3 | 1.2 | 19.0 / 18.7 |
| v2c_l1_paradas | 80.4 / 84.3 | 4.0 | 15.7 / 14.8 |

Mejora del MAE medio en 3-7 min (principal): +5.6 s (diferencia entre semillas: 4.0 s, la mayor de las dos familias) -> supera el criterio.

## Veredicto

- seen: mejora +0.1 s contra diferencia entre semillas 0.7 s -> no supera
- heldout: mejora +5.6 s contra diferencia entre semillas 4.0 s -> SUPERA
