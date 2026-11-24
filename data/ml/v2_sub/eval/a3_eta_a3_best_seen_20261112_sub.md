### a3:data/ml/v2_sub/models/eta_a3_best.pt sobre eval_seen (n=29779)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 29779 | 110.5 | 67.7 | 254.4 | -41.1 | 34.8 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 6696 | 41.6 | 33.2 | 86.4 | 21.1 | 5.1 |
| 5-10 min | 7374 | 71.3 | 55.8 | 150.1 | -22.2 | 31.5 |
| 10-20 min | 7376 | 117.3 | 86.6 | 250.4 | -46.2 | 42.4 |
| 20+ min | 8333 | 194.6 | 145.7 | 407.5 | -103.3 | 54.8 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3512 | 56.5 | 34.4 | 108.9 | -1.9 | 11.3 |
| 0,5-2 km | 10365 | 76.3 | 50.2 | 158.2 | -32.4 | 29.4 |
| 2-5 km | 8381 | 107.8 | 78.7 | 232.5 | -36.4 | 37.8 |
| 5+ km | 7521 | 186.0 | 138.9 | 398.0 | -76.6 | 49.7 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 7320 | 136.5 | 83.2 | 320.3 | -51.4 | 37.9 |
| resto del viaje | 22459 | 102.1 | 63.6 | 236.4 | -37.8 | 33.7 |
| P detenido | 11849 | 115.1 | 70.9 | 266.8 | -47.5 | 36.7 |
| P en movimiento | 17930 | 107.5 | 65.6 | 247.9 | -36.9 | 33.5 |
| inicio y detenido | 3020 | 143.5 | 87.7 | 335.0 | -66.2 | 41.9 |
| inicio y en movimiento | 4300 | 131.6 | 80.4 | 308.9 | -40.9 | 35.1 |
| resto y detenido | 8829 | 105.3 | 65.9 | 244.0 | -41.0 | 34.9 |
| resto y en movimiento | 13630 | 99.9 | 62.2 | 230.7 | -35.6 | 33.0 |
| global | 29779 | 110.5 | 67.7 | 254.4 | -41.1 | 34.8 |
| global sin inicio de viaje | 22459 | 102.1 | 63.6 | 236.4 | -37.8 | 33.7 |

