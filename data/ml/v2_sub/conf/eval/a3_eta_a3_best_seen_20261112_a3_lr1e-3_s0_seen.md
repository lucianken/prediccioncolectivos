### a3:data\ml\v2_sub\conf\a3_lr1e-3_s0\eta_a3_best.pt sobre eval_seen (n=29779)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 29779 | 106.5 | 66.2 | 243.2 | -24.1 | 30.6 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 6696 | 43.7 | 34.5 | 91.1 | 26.7 | 3.7 |
| 5-10 min | 7374 | 69.2 | 54.4 | 146.3 | -12.0 | 27.5 |
| 10-20 min | 7376 | 113.2 | 83.6 | 241.3 | -30.2 | 37.4 |
| 20+ min | 8333 | 183.9 | 138.6 | 382.5 | -70.1 | 48.9 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3512 | 55.8 | 35.1 | 107.0 | 5.0 | 10.2 |
| 0,5-2 km | 10365 | 73.7 | 49.8 | 152.1 | -22.4 | 25.8 |
| 2-5 km | 8381 | 104.8 | 77.0 | 222.6 | -21.1 | 33.4 |
| 5+ km | 7521 | 177.1 | 135.2 | 377.2 | -43.2 | 43.5 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 7320 | 131.2 | 81.2 | 303.7 | -29.3 | 33.4 |
| resto del viaje | 22459 | 98.4 | 62.0 | 222.3 | -22.4 | 29.7 |
| P detenido | 11849 | 109.7 | 69.3 | 251.2 | -25.2 | 31.5 |
| P en movimiento | 17930 | 104.3 | 64.2 | 236.7 | -23.3 | 30.0 |
| inicio y detenido | 3020 | 134.6 | 84.9 | 304.7 | -35.3 | 35.4 |
| inicio y en movimiento | 4300 | 128.8 | 79.5 | 303.5 | -25.1 | 32.0 |
| resto y detenido | 8829 | 101.2 | 64.8 | 230.3 | -21.8 | 30.2 |
| resto y en movimiento | 13630 | 96.6 | 60.1 | 218.7 | -22.7 | 29.3 |
| global | 29779 | 106.5 | 66.2 | 243.2 | -24.1 | 30.6 |
| global sin inicio de viaje | 22459 | 98.4 | 62.0 | 222.3 | -22.4 | 29.7 |

