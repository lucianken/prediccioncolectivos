# Comparación de pérdidas por banda de ETA real, modelo por tramos

Eval `data/ml/v2b/eval` (30.000 filas por conjunto). Cada celda es la media de las semillas 0 y 1. Llega antes / después = % de filas con |error| > 60 s; espera extra = media de (real - pred) cuando llega después. Banda principal: 3-7 min (principal).

## seen: ETA real 0-2 min (n = 2657)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 38.8 | 77.5 | 19.7 | 0.0 | 13.3 |
| l1 | 24.2 | 55.9 | 7.6 | 0.1 | 14.3 |
| pinball_inv | 18.4 | 49.8 | 4.1 | 0.3 | 14.2 |
| pinball_band | 19.2 | 45.4 | 3.9 | 0.1 | 14.7 |

## seen: ETA real 2-4 min (n = 3595)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 38.0 | 82.2 | 15.9 | 3.8 | 27.9 |
| l1 | 38.3 | 78.7 | 10.5 | 8.5 | 35.6 |
| pinball_inv | 42.2 | 85.5 | 8.3 | 17.1 | 44.0 |
| pinball_band | 38.1 | 77.1 | 4.6 | 15.1 | 40.7 |

## seen: ETA real 4-6 min (n = 3424)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 53.9 | 113.7 | 17.5 | 18.0 | 51.0 |
| l1 | 56.8 | 119.4 | 15.8 | 22.0 | 58.2 |
| pinball_inv | 60.1 | 127.0 | 15.0 | 25.4 | 64.1 |
| pinball_band | 63.0 | 127.8 | 7.1 | 36.9 | 69.0 |

## seen: ETA real 6-8 min (n = 3131)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 66.4 | 139.8 | 18.6 | 24.6 | 67.1 |
| l1 | 68.0 | 145.4 | 18.1 | 26.3 | 70.7 |
| pinball_inv | 69.7 | 149.5 | 17.6 | 27.6 | 74.5 |
| pinball_band | 78.2 | 160.0 | 10.1 | 43.2 | 85.2 |

## seen: ETA real 8-10 min (n = 2193)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 86.6 | 185.6 | 21.0 | 32.2 | 89.3 |
| l1 | 88.3 | 187.3 | 21.7 | 32.3 | 93.8 |
| pinball_inv | 89.0 | 187.8 | 21.6 | 33.2 | 94.9 |
| pinball_band | 100.0 | 205.0 | 15.4 | 45.4 | 108.9 |

## seen: ETA real 10-15 min (n = 4411)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 103.4 | 216.1 | 23.6 | 35.4 | 109.9 |
| l1 | 104.0 | 216.1 | 23.7 | 35.3 | 111.8 |
| pinball_inv | 104.6 | 217.1 | 23.7 | 35.7 | 112.7 |
| pinball_band | 113.5 | 234.8 | 21.3 | 41.6 | 126.3 |

## seen: ETA real 15-20 min (n = 3089)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 119.8 | 245.7 | 27.2 | 35.5 | 131.1 |
| l1 | 120.5 | 243.7 | 27.7 | 35.3 | 134.0 |
| pinball_inv | 120.6 | 242.5 | 27.7 | 35.5 | 133.7 |
| pinball_band | 124.1 | 249.0 | 27.8 | 36.2 | 139.2 |

## seen: ETA real 3-7 min (principal) (n = 6746)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 53.3 | 113.3 | 17.2 | 16.6 | 50.5 |
| l1 | 55.3 | 116.7 | 15.1 | 20.4 | 56.3 |
| pinball_inv | 58.4 | 124.1 | 14.0 | 24.2 | 61.7 |
| pinball_band | 61.4 | 126.4 | 7.0 | 34.7 | 66.9 |

## seen: diferencia entre semillas en 3-7 min (principal)

| pérdida | MAE s0 / s1 (s) | dif. MAE (s) | llega antes s0 / s1 (%) | dif. llega antes (pp) |
|---|---|---:|---|---:|
| pinball | 53.1 / 53.5 | 0.4 | 17.1 / 17.4 | 0.3 |
| l1 | 55.3 / 55.4 | 0.1 | 15.1 / 15.1 | 0.0 |
| pinball_inv | 58.3 / 58.5 | 0.2 | 13.9 / 14.2 | 0.2 |
| pinball_band | 61.3 / 61.6 | 0.3 | 6.8 / 7.2 | 0.4 |

## heldout: ETA real 0-2 min (n = 2565)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 45.8 | 93.9 | 25.5 | 0.3 | 16.5 |
| l1 | 30.2 | 69.4 | 12.4 | 0.3 | 15.9 |
| pinball_inv | 25.1 | 58.5 | 8.6 | 0.6 | 14.9 |
| pinball_band | 25.0 | 58.5 | 8.9 | 0.5 | 15.9 |

## heldout: ETA real 2-4 min (n = 3600)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 54.6 | 109.4 | 20.0 | 10.2 | 39.5 |
| l1 | 55.7 | 112.5 | 15.3 | 17.1 | 47.5 |
| pinball_inv | 61.1 | 118.4 | 13.3 | 26.2 | 55.0 |
| pinball_band | 55.7 | 108.2 | 10.2 | 24.0 | 51.5 |

## heldout: ETA real 4-6 min (n = 3412)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 80.5 | 158.4 | 17.1 | 31.7 | 71.2 |
| l1 | 83.9 | 169.8 | 15.5 | 37.1 | 78.5 |
| pinball_inv | 89.8 | 179.3 | 15.7 | 40.0 | 83.6 |
| pinball_band | 93.3 | 178.6 | 10.9 | 49.5 | 89.9 |

## heldout: ETA real 6-8 min (n = 3192)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 111.1 | 219.5 | 18.1 | 43.4 | 103.3 |
| l1 | 113.6 | 226.9 | 17.7 | 45.6 | 107.4 |
| pinball_inv | 117.4 | 238.2 | 18.0 | 46.3 | 110.6 |
| pinball_band | 128.1 | 246.7 | 13.4 | 57.8 | 122.7 |

## heldout: ETA real 8-10 min (n = 2231)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 132.8 | 264.7 | 19.0 | 49.4 | 122.7 |
| l1 | 134.2 | 268.7 | 18.3 | 50.8 | 128.9 |
| pinball_inv | 138.1 | 274.9 | 19.5 | 50.1 | 129.4 |
| pinball_band | 151.6 | 295.5 | 14.7 | 60.2 | 146.6 |

## heldout: ETA real 10-15 min (n = 4428)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 171.2 | 330.1 | 18.3 | 55.6 | 155.9 |
| l1 | 170.4 | 329.0 | 18.9 | 55.2 | 160.7 |
| pinball_inv | 175.8 | 337.6 | 19.7 | 54.8 | 160.3 |
| pinball_band | 188.5 | 370.8 | 18.3 | 59.5 | 179.4 |

## heldout: ETA real 15-20 min (n = 3072)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 206.7 | 389.7 | 16.7 | 61.5 | 192.4 |
| l1 | 204.8 | 387.2 | 18.2 | 60.8 | 195.9 |
| pinball_inv | 211.4 | 395.7 | 19.1 | 60.1 | 199.1 |
| pinball_band | 218.2 | 422.9 | 19.3 | 60.3 | 208.9 |

## heldout: ETA real 3-7 min (principal) (n = 6793)

| pérdida | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| pinball | 82.8 | 166.5 | 18.1 | 30.7 | 73.9 |
| l1 | 85.5 | 173.8 | 16.4 | 35.7 | 80.0 |
| pinball_inv | 90.9 | 182.5 | 16.1 | 38.8 | 84.9 |
| pinball_band | 94.1 | 184.1 | 11.6 | 47.5 | 90.3 |

## heldout: diferencia entre semillas en 3-7 min (principal)

| pérdida | MAE s0 / s1 (s) | dif. MAE (s) | llega antes s0 / s1 (%) | dif. llega antes (pp) |
|---|---|---:|---|---:|
| pinball | 80.6 / 85.1 | 4.6 | 17.9 / 18.3 | 0.4 |
| l1 | 84.4 / 86.6 | 2.2 | 15.4 / 17.3 | 2.0 |
| pinball_inv | 91.2 / 90.6 | 0.6 | 16.8 / 15.4 | 1.5 |
| pinball_band | 92.6 / 95.6 | 3.0 | 10.0 / 13.3 | 3.3 |
