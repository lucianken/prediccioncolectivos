### a3:data\ml\v2_sub\conf\a3_lr1e-3_s1\eta_a3_best.pt sobre eval_seen (n=29779)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 29779 | 109.3 | 68.1 | 250.1 | -29.7 | 32.4 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 6696 | 42.9 | 34.1 | 89.4 | 23.8 | 4.5 |
| 5-10 min | 7374 | 71.1 | 55.8 | 150.7 | -17.5 | 30.0 |
| 10-20 min | 7376 | 117.0 | 87.0 | 247.9 | -37.1 | 40.1 |
| 20+ min | 8333 | 189.8 | 140.6 | 399.6 | -77.1 | 50.3 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3512 | 57.3 | 35.5 | 108.8 | 0.5 | 11.2 |
| 0,5-2 km | 10365 | 75.8 | 50.7 | 157.2 | -28.1 | 27.9 |
| 2-5 km | 8381 | 107.1 | 79.1 | 227.1 | -26.6 | 35.6 |
| 5+ km | 7521 | 182.3 | 137.0 | 391.0 | -49.6 | 45.1 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 7320 | 135.8 | 84.0 | 316.6 | -40.1 | 36.1 |
| resto del viaje | 22459 | 100.7 | 64.0 | 230.5 | -26.4 | 31.2 |
| P detenido | 11849 | 113.5 | 71.1 | 260.4 | -38.8 | 34.9 |
| P en movimiento | 17930 | 106.5 | 66.3 | 243.0 | -23.8 | 30.8 |
| inicio y detenido | 3020 | 142.2 | 86.7 | 333.1 | -57.3 | 40.5 |
| inicio y en movimiento | 4300 | 131.3 | 82.1 | 301.9 | -28.0 | 33.1 |
| resto y detenido | 8829 | 103.7 | 66.5 | 237.9 | -32.4 | 33.1 |
| resto y en movimiento | 13630 | 98.7 | 62.5 | 226.1 | -22.4 | 30.1 |
| global | 29779 | 109.3 | 68.1 | 250.1 | -29.7 | 32.4 |
| global sin inicio de viaje | 22459 | 100.7 | 64.0 | 230.5 | -26.4 | 31.2 |

