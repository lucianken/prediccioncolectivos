### path:data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt sobre eval_seen (n=1169)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| global | 1169 | 119.0 | 65.7 | 263.7 | -24.5 | 24.9 | 28.1 | 139.8 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0-5 min | 257 | 34.8 | 26.3 | 79.5 | 2.3 | 8.2 | 8.6 | 34.8 |
| 5-10 min | 307 | 77.2 | 55.7 | 177.9 | -13.9 | 20.5 | 26.4 | 79.0 |
| 10-20 min | 314 | 127.2 | 94.8 | 248.8 | -11.3 | 35.0 | 34.4 | 150.0 |
| 20+ min | 291 | 228.6 | 142.1 | 447.2 | -73.7 | 33.3 | 40.2 | 278.3 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| <500 m | 152 | 79.5 | 29.7 | 176.1 | -52.1 | 5.3 | 18.4 | 128.2 |
| 0,5-2 km | 405 | 89.2 | 47.3 | 169.9 | -42.4 | 14.3 | 27.2 | 108.8 |
| 2-5 km | 330 | 108.6 | 80.1 | 220.7 | 5.1 | 35.5 | 28.2 | 121.1 |
| 5+ km | 282 | 195.2 | 134.4 | 388.5 | -18.7 | 38.3 | 34.4 | 221.8 |

**Por distancia restante (fina)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0-0,5 km | 152 | 79.5 | 29.7 | 176.1 | -52.1 | 5.3 | 18.4 | 128.2 |
| 0,5-1 km | 149 | 91.0 | 37.1 | 157.3 | -57.1 | 8.7 | 26.8 | 120.0 |
| 1-2 km | 256 | 88.2 | 53.8 | 171.9 | -33.8 | 17.6 | 27.3 | 102.0 |
| 2-3 km | 121 | 96.9 | 74.8 | 178.6 | -4.6 | 31.4 | 28.9 | 107.7 |
| 3-5 km | 209 | 115.3 | 88.8 | 232.7 | 10.7 | 37.8 | 27.8 | 130.1 |
| 5-8 km | 117 | 175.9 | 118.1 | 323.7 | -32.9 | 34.2 | 31.6 | 222.1 |
| 8-12 km | 110 | 183.1 | 140.0 | 375.4 | 5.0 | 44.5 | 34.5 | 195.9 |
| 12+ km | 55 | 260.5 | 229.5 | 535.3 | -36.2 | 34.5 | 40.0 | 263.2 |

**Por línea**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | 1169 | 119.0 | 65.7 | 263.7 | -24.5 | 24.9 | 28.1 | 139.8 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 69 | 99.0 | 69.4 | 233.0 | -14.3 | 18.8 | 33.3 | 102.9 |
| resto del viaje | 1100 | 120.2 | 65.5 | 267.5 | -25.2 | 25.3 | 27.7 | 142.3 |
| P detenido | 486 | 122.7 | 65.6 | 291.0 | -25.8 | 24.9 | 28.8 | 143.7 |
| P en movimiento | 683 | 116.3 | 66.3 | 253.2 | -23.7 | 24.9 | 27.5 | 137.0 |
| inicio y detenido | 24 | 128.6 | 104.3 | 238.9 | -34.4 | 20.8 | 50.0 | 108.7 |
| inicio y en movimiento | 45 | 83.3 | 51.6 | 214.7 | -3.5 | 17.8 | 24.4 | 97.7 |
| resto y detenido | 462 | 122.4 | 64.5 | 292.9 | -25.3 | 25.1 | 27.7 | 146.4 |
| resto y en movimiento | 638 | 118.7 | 67.1 | 256.2 | -25.1 | 25.4 | 27.7 | 139.4 |
| global | 1169 | 119.0 | 65.7 | 263.7 | -24.5 | 24.9 | 28.1 | 139.8 |
| global sin inicio de viaje | 1100 | 120.2 | 65.5 | 267.5 | -25.2 | 25.3 | 27.7 | 142.3 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 467 | 134.5 | 65.7 | 292.8 | -40.6 | 24.4 | 28.7 | 171.8 |
| inicio conocido | 702 | 108.7 | 65.9 | 253.3 | -13.9 | 25.2 | 27.6 | 118.8 |

