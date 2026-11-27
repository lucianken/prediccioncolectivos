### path:data/ml/replay/recorridos_nuevos_42/cache/ckpt_nuevos_shapes.pt sobre eval_seen (n=1169)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| global | 1169 | 126.7 | 75.1 | 278.2 | -26.5 | 26.0 | 29.9 | 148.3 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0-5 min | 257 | 42.2 | 32.5 | 98.6 | 6.1 | 12.5 | 8.2 | 39.9 |
| 5-10 min | 307 | 88.2 | 64.7 | 193.1 | -15.4 | 22.8 | 29.6 | 95.8 |
| 10-20 min | 314 | 130.0 | 98.7 | 267.2 | -11.0 | 33.4 | 34.1 | 142.7 |
| 20+ min | 291 | 238.6 | 162.7 | 455.3 | -84.0 | 33.3 | 44.7 | 281.0 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| <500 m | 152 | 90.4 | 37.3 | 180.0 | -58.0 | 7.9 | 20.4 | 137.6 |
| 0,5-2 km | 405 | 98.7 | 55.1 | 193.1 | -41.3 | 17.3 | 28.9 | 124.3 |
| 2-5 km | 330 | 113.9 | 88.1 | 243.1 | 4.4 | 34.5 | 28.2 | 121.2 |
| 5+ km | 282 | 201.7 | 150.6 | 438.4 | -24.6 | 38.3 | 38.3 | 220.0 |

**Por distancia restante (fina)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0-0,5 km | 152 | 90.4 | 37.3 | 180.0 | -58.0 | 7.9 | 20.4 | 137.6 |
| 0,5-1 km | 149 | 100.7 | 48.9 | 193.0 | -55.3 | 13.4 | 24.8 | 132.0 |
| 1-2 km | 256 | 97.5 | 62.0 | 193.7 | -33.2 | 19.5 | 31.2 | 119.4 |
| 2-3 km | 121 | 96.2 | 63.2 | 220.6 | -0.8 | 27.3 | 26.4 | 106.7 |
| 3-5 km | 209 | 124.1 | 100.2 | 257.6 | 7.4 | 38.8 | 29.2 | 129.7 |
| 5-8 km | 117 | 184.2 | 119.2 | 355.1 | -42.6 | 34.2 | 35.9 | 214.0 |
| 8-12 km | 110 | 184.7 | 150.6 | 361.1 | -2.7 | 41.8 | 40.0 | 194.5 |
| 12+ km | 55 | 272.6 | 225.8 | 567.1 | -30.1 | 40.0 | 40.0 | 277.5 |

**Por línea**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | 1169 | 126.7 | 75.1 | 278.2 | -26.5 | 26.0 | 29.9 | 148.3 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 69 | 105.4 | 70.8 | 238.1 | -12.6 | 21.7 | 33.3 | 107.1 |
| resto del viaje | 1100 | 128.1 | 76.0 | 281.3 | -27.4 | 26.3 | 29.6 | 151.1 |
| P detenido | 486 | 129.5 | 77.2 | 300.6 | -33.5 | 24.1 | 31.7 | 150.1 |
| P en movimiento | 683 | 124.7 | 74.4 | 263.2 | -21.6 | 27.4 | 28.6 | 147.0 |
| inicio y detenido | 24 | 136.5 | 104.3 | 268.3 | -38.1 | 20.8 | 50.0 | 123.2 |
| inicio y en movimiento | 45 | 88.8 | 58.1 | 216.2 | 1.0 | 22.2 | 24.4 | 94.1 |
| resto y detenido | 462 | 129.1 | 74.5 | 301.3 | -33.3 | 24.2 | 30.7 | 151.9 |
| resto y en movimiento | 638 | 127.3 | 78.5 | 267.7 | -23.2 | 27.7 | 28.8 | 150.5 |
| global | 1169 | 126.7 | 75.1 | 278.2 | -26.5 | 26.0 | 29.9 | 148.3 |
| global sin inicio de viaje | 1100 | 128.1 | 76.0 | 281.3 | -27.4 | 26.3 | 29.6 | 151.1 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 467 | 145.5 | 79.1 | 319.3 | -49.4 | 24.8 | 33.0 | 177.8 |
| inicio conocido | 702 | 114.2 | 74.3 | 260.4 | -11.4 | 26.8 | 27.8 | 126.7 |

