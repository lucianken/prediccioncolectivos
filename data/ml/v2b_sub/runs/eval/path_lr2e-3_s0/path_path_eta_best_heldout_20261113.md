### path:data\ml\v2b_sub\runs\path_lr2e-3_s0\path_eta_best.pt sobre eval_heldout (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 205.7 | 93.2 | 414.6 | -34.3 | 45.4 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 53.3 | 38.1 | 108.9 | 21.5 | 9.5 |
| 5-10 min | 7500 | 107.5 | 77.9 | 216.8 | -25.5 | 42.3 |
| 10-20 min | 7500 | 180.0 | 125.2 | 349.5 | -62.9 | 57.2 |
| 20+ min | 7500 | 481.9 | 267.3 | 841.7 | -70.4 | 72.7 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 4083 | 67.8 | 34.7 | 105.8 | -20.6 | 13.5 |
| 0,5-2 km | 11740 | 100.9 | 69.8 | 214.1 | -49.4 | 39.5 |
| 2-5 km | 7879 | 173.9 | 127.3 | 371.0 | -83.8 | 55.0 |
| 5+ km | 6298 | 530.0 | 276.7 | 1075.4 | 46.6 | 65.2 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3551 | 241.5 | 155.8 | 527.9 | -166.5 | 66.7 |
| resto del viaje | 26449 | 200.9 | 87.1 | 392.8 | -16.6 | 42.6 |
| P detenido | 12817 | 187.6 | 91.6 | 389.9 | -60.4 | 46.9 |
| P en movimiento | 17183 | 219.2 | 94.6 | 435.7 | -14.9 | 44.4 |
| inicio y detenido | 1589 | 247.8 | 152.8 | 527.5 | -150.7 | 66.1 |
| inicio y en movimiento | 1962 | 236.4 | 157.1 | 528.1 | -179.2 | 67.2 |
| resto y detenido | 11228 | 179.1 | 85.1 | 361.7 | -47.6 | 44.2 |
| resto y en movimiento | 15221 | 216.9 | 88.7 | 415.1 | 6.3 | 41.4 |
| global | 30000 | 205.7 | 93.2 | 414.6 | -34.3 | 45.4 |
| global sin inicio de viaje | 26449 | 200.9 | 87.1 | 392.8 | -16.6 | 42.6 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 6380 | 294.9 | 112.0 | 608.5 | 56.7 | 40.7 |
| inicio conocido | 23620 | 181.6 | 88.8 | 377.6 | -58.9 | 46.7 |

