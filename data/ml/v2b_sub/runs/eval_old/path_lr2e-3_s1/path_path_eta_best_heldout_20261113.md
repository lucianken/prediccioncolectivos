### path:data/ml/v2_sub/conf/path_lr2e-3_s1/path_eta_best.pt sobre eval_heldout (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 214.6 | 98.8 | 430.4 | -40.6 | 47.9 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 52.7 | 37.3 | 108.7 | 19.2 | 10.1 |
| 5-10 min | 7500 | 109.4 | 79.8 | 214.0 | -30.0 | 45.0 |
| 10-20 min | 7500 | 185.3 | 136.6 | 345.5 | -73.7 | 60.9 |
| 20+ min | 7500 | 511.1 | 288.8 | 866.3 | -77.8 | 75.5 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 4083 | 68.4 | 34.0 | 111.1 | -22.1 | 14.3 |
| 0,5-2 km | 11740 | 102.6 | 70.6 | 219.2 | -54.5 | 41.6 |
| 2-5 km | 7879 | 181.0 | 137.4 | 382.7 | -95.2 | 58.3 |
| 5+ km | 6298 | 560.4 | 297.6 | 1051.8 | 41.7 | 68.2 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3551 | 254.1 | 164.3 | 554.2 | -170.7 | 66.6 |
| resto del viaje | 26449 | 209.3 | 92.3 | 406.1 | -23.1 | 45.3 |
| P detenido | 12817 | 197.0 | 97.1 | 408.9 | -68.2 | 49.9 |
| P en movimiento | 17183 | 227.8 | 99.9 | 449.1 | -20.0 | 46.3 |
| inicio y detenido | 1589 | 261.4 | 163.4 | 561.9 | -153.3 | 65.9 |
| inicio y en movimiento | 1962 | 248.2 | 165.2 | 551.8 | -184.8 | 67.2 |
| resto y detenido | 11228 | 187.8 | 90.8 | 379.0 | -56.1 | 47.6 |
| resto y en movimiento | 15221 | 225.2 | 93.6 | 428.9 | 1.3 | 43.6 |
| global | 30000 | 214.6 | 98.8 | 430.4 | -40.6 | 47.9 |
| global sin inicio de viaje | 26449 | 209.3 | 92.3 | 406.1 | -23.1 | 45.3 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 6380 | 309.9 | 118.0 | 623.9 | 54.1 | 44.7 |
| inicio conocido | 23620 | 188.9 | 94.8 | 392.7 | -66.2 | 48.7 |

