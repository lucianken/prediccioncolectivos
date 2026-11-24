### path:data\ml\v2b_sub\runs\path_lr2e-3_s1\path_eta_best.pt sobre eval_heldout (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 224.7 | 99.1 | 449.8 | -24.1 | 46.4 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 55.9 | 38.9 | 114.3 | 24.0 | 9.8 |
| 5-10 min | 7500 | 113.9 | 82.5 | 221.3 | -21.2 | 43.5 |
| 10-20 min | 7500 | 191.5 | 134.6 | 363.5 | -59.5 | 58.8 |
| 20+ min | 7500 | 537.6 | 288.5 | 887.4 | -39.8 | 73.3 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 4083 | 69.0 | 35.2 | 112.0 | -18.6 | 13.8 |
| 0,5-2 km | 11740 | 103.8 | 72.4 | 220.7 | -46.7 | 40.1 |
| 2-5 km | 7879 | 185.3 | 137.3 | 394.9 | -80.7 | 56.5 |
| 5+ km | 6298 | 600.3 | 306.7 | 1143.7 | 85.3 | 66.5 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3551 | 257.2 | 157.5 | 570.3 | -170.4 | 65.7 |
| resto del viaje | 26449 | 220.3 | 93.7 | 423.3 | -4.5 | 43.8 |
| P detenido | 12817 | 201.5 | 97.6 | 416.4 | -54.6 | 48.0 |
| P en movimiento | 17183 | 242.0 | 100.5 | 479.9 | -1.4 | 45.2 |
| inicio y detenido | 1589 | 260.7 | 155.7 | 575.0 | -147.0 | 63.8 |
| inicio y en movimiento | 1962 | 254.3 | 158.7 | 565.5 | -189.3 | 67.3 |
| resto y detenido | 11228 | 193.2 | 91.9 | 385.2 | -41.5 | 45.8 |
| resto y en movimiento | 15221 | 240.4 | 95.0 | 458.6 | 22.9 | 42.3 |
| global | 30000 | 224.7 | 99.1 | 449.8 | -24.1 | 46.4 |
| global sin inicio de viaje | 26449 | 220.3 | 93.7 | 423.3 | -4.5 | 43.8 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 6380 | 325.2 | 111.6 | 666.5 | 121.0 | 37.9 |
| inicio conocido | 23620 | 197.5 | 96.5 | 414.0 | -63.3 | 48.6 |

