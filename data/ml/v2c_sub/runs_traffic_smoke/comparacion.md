# Tránsito actual por tramo contra la base `v2c_l1_paradas`, mismo eval (`data/ml/v2c/eval`)

`v2c_l1_paradas`: modelo por tramos L1 + `--stops-feature` (`data/ml/v2c_sub/runs_stops`); `v2c_l1_paradas_traffic`: igual + `--traffic-feature` (`data/ml/v2c_sub/runs_traffic`). Un solo cambio; semillas 0 y 1; cada celda es la media de las semillas salvo donde se aclara. Llega antes / después = % de filas con error > 60 s (llega antes = pred - real > 60 s); espera extra = media de (real - pred) cuando llega después. Banda principal: 3-7 min (principal). **% tramos con dato** = tramos de 250 m del camino P->T cuya celda tiene algún coche de la flota en las 2 ventanas completas previas a ts_p (= la información real que ve el modelo; el resto entra como máscara); **% con velocidad** = además con algún coche en movimiento. Se calcula sobre las filas de la banda (tramos acumulados, no promedio de promedios) y es igual para base y nuevo (la base no usa tránsito).

## seen: ETA real 3-7 min (principal) (n = 6738)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) | % tramos con dato | % con velocidad |
|---|---:|---:|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 55.7 | 117.2 | 14.9 | 21.3 | 57.2 | 93.0 | 92.8 |
| v2c_l1_paradas_traffic | 71.1 | 148.3 | 9.2 | 39.0 | 78.8 | 93.0 | 92.8 |

### seen: semillas 0 / 1 en 3-7 min (principal)

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 55.3 / 56.0 | 0.7 | 15.0 / 14.8 | 21.1 / 21.4 |
| v2c_l1_paradas_traffic | 69.3 / 72.8 | 3.5 | 11.1 / 7.3 | 36.0 / 42.0 |

Mejora del MAE medio en 3-7 min (principal): -15.4 s (diferencia entre semillas: 3.5 s, la mayor de las dos familias) -> no supera el criterio.

### seen: MAE (s) por banda de ETA real y % de tramos con dato

| banda | n | v2c_l1_paradas MAE | v2c_l1_paradas_traffic MAE | diferencia | llega antes base / nuevo (%) | % tramos con dato |
|---|---:|---:|---:|---:|---|---:|
| 3-7 min (principal) | 6738 | 55.7 | 71.1 | +15.4 | 14.9 / 9.2 | 93.0 |
| 0-2 min | 2664 | 23.2 | 24.6 | +1.4 | 6.9 / 5.0 | 92.8 |
| 2-4 min | 3589 | 39.0 | 44.0 | +5.0 | 11.2 / 7.3 | 93.1 |
| 4-6 min | 3448 | 57.2 | 73.4 | +16.2 | 15.0 / 9.6 | 92.8 |
| 6-8 min | 3127 | 67.2 | 89.9 | +22.7 | 17.9 / 10.4 | 94.0 |
| 8-10 min | 2172 | 80.9 | 112.9 | +32.1 | 20.7 / 11.3 | 93.3 |
| 10-15 min | 4432 | 98.4 | 141.9 | +43.5 | 24.6 / 15.5 | 92.9 |
| 15-20 min | 3068 | 112.9 | 168.8 | +55.9 | 27.1 / 14.5 | 93.6 |

### seen: desglose por línea, banda 3-7 min (principal)

| línea | n | MAE v2c_l1_paradas | MAE v2c_l1_paradas_traffic | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) | % tramos con dato |
|---|---:|---:|---:|---:|---|---|---:|
| 26 | 62 | 56.2 | 69.3 | +13.0 | 16.1 / 6.5 | 22.6 / 42.7 | 91.5 |
| 39 | 930 | 49.0 | 63.9 | +14.9 | 14.5 / 8.3 | 16.6 / 36.4 | 96.7 |
| 42 | 451 | 61.2 | 81.4 | +20.2 | 16.4 / 11.0 | 22.4 / 44.7 | 92.2 |
| 50 | 448 | 52.4 | 63.2 | +10.8 | 15.3 / 9.8 | 19.4 / 34.8 | 91.8 |
| 92 | 676 | 53.5 | 72.0 | +18.4 | 11.3 / 10.9 | 24.2 / 37.8 | 87.6 |
| 106 | 1020 | 53.9 | 69.3 | +15.4 | 13.9 / 8.7 | 21.4 / 38.9 | 94.1 |
| 107 | 393 | 59.6 | 77.1 | +17.5 | 16.8 / 11.7 | 23.3 / 39.3 | 84.7 |
| 108 | 349 | 63.1 | 76.9 | +13.8 | 16.2 / 9.3 | 23.1 / 39.8 | 92.8 |
| 124 | 365 | 53.1 | 67.3 | +14.1 | 14.2 / 11.2 | 17.8 / 32.2 | 94.5 |
| 132 | 937 | 59.6 | 70.6 | +10.9 | 16.7 / 8.4 | 20.8 / 38.3 | 95.5 |
| 151 | 639 | 59.1 | 77.6 | +18.5 | 15.9 / 6.6 | 24.5 / 46.3 | 94.8 |
| 168 | 468 | 54.2 | 71.3 | +17.1 | 14.4 / 8.7 | 23.2 / 40.2 | 93.2 |

## heldout: ETA real 3-7 min (principal) (n = 6778)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) | % tramos con dato | % con velocidad |
|---|---:|---:|---:|---:|---:|---:|---:|
| v2c_l1_paradas | 82.3 | 167.3 | 15.3 | 36.8 | 79.2 | 95.2 | 95.1 |
| v2c_l1_paradas_traffic | 80.2 | 162.0 | 8.3 | 45.4 | 84.0 | 95.2 | 95.1 |

### heldout: semillas 0 / 1 en 3-7 min (principal)

| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |
|---|---|---:|---|---|
| v2c_l1_paradas | 80.4 / 84.3 | 4.0 | 15.7 / 14.8 | 35.8 / 37.8 |
| v2c_l1_paradas_traffic | 77.7 / 82.7 | 5.0 | 8.9 / 7.7 | 42.7 / 48.0 |

Mejora del MAE medio en 3-7 min (principal): +2.1 s (diferencia entre semillas: 5.0 s, la mayor de las dos familias) -> no supera el criterio.

### heldout: MAE (s) por banda de ETA real y % de tramos con dato

| banda | n | v2c_l1_paradas MAE | v2c_l1_paradas_traffic MAE | diferencia | llega antes base / nuevo (%) | % tramos con dato |
|---|---:|---:|---:|---:|---|---:|
| 3-7 min (principal) | 6778 | 82.3 | 80.2 | -2.1 | 15.3 / 8.3 | 95.2 |
| 0-2 min | 2588 | 28.4 | 25.4 | -3.0 | 11.2 / 4.9 | 94.9 |
| 2-4 min | 3595 | 51.4 | 47.2 | -4.2 | 12.9 / 7.3 | 95.0 |
| 4-6 min | 3507 | 85.3 | 82.8 | -2.5 | 15.7 / 8.6 | 95.2 |
| 6-8 min | 3172 | 103.7 | 105.2 | +1.5 | 16.8 / 9.4 | 95.2 |
| 8-10 min | 2138 | 121.9 | 127.6 | +5.7 | 17.3 / 9.0 | 95.5 |
| 10-15 min | 4427 | 155.1 | 171.8 | +16.7 | 18.0 / 11.3 | 95.1 |
| 15-20 min | 3073 | 194.9 | 214.0 | +19.1 | 17.8 / 12.3 | 95.9 |

### heldout: desglose por línea, banda 3-7 min (principal)

| línea | n | MAE v2c_l1_paradas | MAE v2c_l1_paradas_traffic | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) | % tramos con dato |
|---|---:|---:|---:|---:|---|---|---:|
| 12 | 3363 | 69.0 | 77.3 | +8.3 | 9.4 / 5.0 | 37.6 / 48.6 | 97.0 |
| 15 | 1753 | 115.9 | 88.5 | -27.5 | 28.3 / 16.9 | 33.1 / 35.1 | 92.8 |
| 128 | 1662 | 73.9 | 77.5 | +3.5 | 13.5 / 6.0 | 39.0 / 49.7 | 94.9 |

## Veredicto

- seen: mejora -15.4 s contra diferencia entre semillas 3.5 s -> no supera
- heldout: mejora +2.1 s contra diferencia entre semillas 5.0 s -> no supera
