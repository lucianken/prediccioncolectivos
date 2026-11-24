# Tránsito actual por tramo contra la base `v2c_l1_paradas`, mismo eval (`data/ml/v2c/eval`)

`v2c_l1_paradas`: modelo por tramos L1 + `--stops-feature` (`data/ml/v2c_sub/runs_stops`); `v2c_l1_paradas_traffic`: igual + `--traffic-feature` (`data/ml/v2c_sub/runs_traffic`). Un solo cambio; semillas 0 y 1; cada celda es la media de las semillas salvo donde se aclara. Llega antes / después = % de filas con error > 60 s (llega antes = pred - real > 60 s); espera extra = media de (real - pred) cuando llega después. Banda principal: 3-7 min (principal). **% tramos con dato** = tramos de 250 m del camino P->T cuya celda tiene algún coche de la flota en las 2 ventanas completas previas a ts_p (= la información real que ve el modelo; el resto entra como máscara); **% con velocidad** = además con algún coche en movimiento. Se calcula sobre las filas de la banda (tramos acumulados, no promedio de promedios) y es igual para base y nuevo (la base no usa tránsito).

## seen: ETA real 3-7 min (principal) (n = 6738)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) | % tramos con dato | % con velocidad |
|---|---:|---:|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 55.7 | 117.2 | 14.9 | 21.3 | 57.2 | 93.0 | 92.8 |
| v2c_l1_paradas_traffic | 54.7 | 115.0 | 14.7 | 21.2 | 56.8 | 93.0 | 92.8 |

### seen: semillas 0 / 1 en 3-7 min (principal)

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 55.3 / 56.0 | 0.7 | 15.0 / 14.8 | 21.1 / 21.4 |
| v2c_l1_paradas_traffic | 54.6 / 54.8 | 0.2 | 14.8 / 14.6 | 21.3 / 21.2 |

Mejora del MAE medio en 3-7 min (principal): +0.9 s (diferencia entre semillas: 0.7 s, la mayor de las dos familias) -> supera el criterio.

### seen: MAE (s) por banda de ETA real y % de tramos con dato

| banda | n | v2c_l1_paradas MAE | v2c_l1_paradas_traffic MAE | diferencia | llega antes base / nuevo (%) | % tramos con dato |
|---|---:|---:|---:|---:|---|---:|
| 3-7 min (principal) | 6738 | 55.7 | 54.7 | -0.9 | 14.9 / 14.7 | 93.0 |
| 0-2 min | 2664 | 23.2 | 23.2 | +0.1 | 6.9 / 7.1 | 92.8 |
| 2-4 min | 3589 | 39.0 | 38.6 | -0.4 | 11.2 / 11.1 | 93.1 |
| 4-6 min | 3448 | 57.2 | 56.2 | -1.0 | 15.0 / 14.9 | 92.8 |
| 6-8 min | 3127 | 67.2 | 66.3 | -0.9 | 17.9 / 17.6 | 94.0 |
| 8-10 min | 2172 | 80.9 | 78.4 | -2.4 | 20.7 / 19.4 | 93.3 |
| 10-15 min | 4432 | 98.4 | 96.9 | -1.5 | 24.6 / 24.9 | 92.9 |
| 15-20 min | 3068 | 112.9 | 109.9 | -3.0 | 27.1 / 27.0 | 93.6 |

### seen: desglose por línea, banda 3-7 min (principal)

| línea | n | MAE v2c_l1_paradas | MAE v2c_l1_paradas_traffic | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) | % tramos con dato |
|---|---:|---:|---:|---:|---|---|---:|
| 26 | 62 | 56.2 | 49.3 | -6.9 | 16.1 / 11.3 | 22.6 / 16.9 | 91.5 |
| 39 | 930 | 49.0 | 49.3 | +0.2 | 14.5 / 15.4 | 16.6 / 16.8 | 96.7 |
| 42 | 451 | 61.2 | 60.0 | -1.2 | 16.4 / 17.0 | 22.4 / 21.6 | 92.2 |
| 50 | 448 | 52.4 | 52.5 | +0.1 | 15.3 / 15.6 | 19.4 / 18.8 | 91.8 |
| 92 | 676 | 53.5 | 52.1 | -1.4 | 11.3 / 10.3 | 24.2 / 24.0 | 87.6 |
| 106 | 1020 | 53.9 | 52.1 | -1.7 | 13.9 / 13.2 | 21.4 / 21.1 | 94.1 |
| 107 | 393 | 59.6 | 59.0 | -0.6 | 16.8 / 17.3 | 23.3 / 23.7 | 84.7 |
| 108 | 349 | 63.1 | 62.5 | -0.6 | 16.2 / 14.5 | 23.1 / 25.4 | 92.8 |
| 124 | 365 | 53.1 | 53.1 | -0.0 | 14.2 / 14.8 | 17.8 / 18.1 | 94.5 |
| 132 | 937 | 59.6 | 57.3 | -2.4 | 16.7 / 16.2 | 20.8 / 20.3 | 95.5 |
| 151 | 639 | 59.1 | 59.3 | +0.2 | 15.9 / 16.4 | 24.5 / 24.7 | 94.8 |
| 168 | 468 | 54.2 | 53.4 | -0.8 | 14.4 / 12.8 | 23.2 / 23.5 | 93.2 |

## heldout: ETA real 3-7 min (principal) (n = 6778)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) | % tramos con dato | % con velocidad |
|---|---:|---:|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 82.3 | 167.3 | 15.3 | 36.8 | 79.2 | 95.2 | 95.1 |
| v2c_l1_paradas_traffic | 80.2 | 162.3 | 16.1 | 34.7 | 76.1 | 95.2 | 95.1 |

### heldout: semillas 0 / 1 en 3-7 min (principal)

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 80.4 / 84.3 | 4.0 | 15.7 / 14.8 | 35.8 / 37.8 |
| v2c_l1_paradas_traffic | 79.8 / 80.7 | 0.9 | 17.5 / 14.8 | 32.6 / 36.9 |

Mejora del MAE medio en 3-7 min (principal): +2.1 s (diferencia entre semillas: 4.0 s, la mayor de las dos familias) -> no supera el criterio.

### heldout: MAE (s) por banda de ETA real y % de tramos con dato

| banda | n | v2c_l1_paradas MAE | v2c_l1_paradas_traffic MAE | diferencia | llega antes base / nuevo (%) | % tramos con dato |
|---|---:|---:|---:|---:|---|---:|
| 3-7 min (principal) | 6778 | 82.3 | 80.2 | -2.1 | 15.3 / 16.1 | 95.2 |
| 0-2 min | 2588 | 28.4 | 28.7 | +0.3 | 11.2 / 11.5 | 94.9 |
| 2-4 min | 3595 | 51.4 | 51.1 | -0.3 | 12.9 / 13.5 | 95.0 |
| 4-6 min | 3507 | 85.3 | 83.5 | -1.8 | 15.7 / 16.8 | 95.2 |
| 6-8 min | 3172 | 103.7 | 99.7 | -3.9 | 16.8 / 18.1 | 95.2 |
| 8-10 min | 2138 | 121.9 | 116.6 | -5.3 | 17.3 / 17.5 | 95.5 |
| 10-15 min | 4427 | 155.1 | 149.3 | -5.8 | 18.0 / 19.0 | 95.1 |
| 15-20 min | 3073 | 194.9 | 185.7 | -9.2 | 17.8 / 20.3 | 95.9 |

### heldout: desglose por línea, banda 3-7 min (principal)

| línea | n | MAE v2c_l1_paradas | MAE v2c_l1_paradas_traffic | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) | % tramos con dato |
|---|---:|---:|---:|---:|---|---|---:|
| 12 | 3363 | 69.0 | 65.8 | -3.2 | 9.4 / 9.2 | 37.6 / 35.9 | 97.0 |
| 15 | 1753 | 115.9 | 116.3 | +0.4 | 28.3 / 30.8 | 33.1 / 30.9 | 92.8 |
| 128 | 1662 | 73.9 | 71.3 | -2.6 | 13.5 / 14.6 | 39.0 / 36.4 | 94.9 |

## Veredicto

- seen: mejora +0.9 s contra diferencia entre semillas 0.7 s -> SUPERA
- heldout: mejora +2.1 s contra diferencia entre semillas 4.0 s -> no supera
