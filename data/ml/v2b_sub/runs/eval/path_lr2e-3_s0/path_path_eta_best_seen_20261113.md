### path:data\ml\v2b_sub\runs\path_lr2e-3_s0\path_eta_best.pt sobre eval_seen (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 102.7 | 60.7 | 225.1 | -17.4 | 27.7 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 40.4 | 31.7 | 85.5 | 21.3 | 4.4 |
| 5-10 min | 7500 | 68.7 | 52.5 | 143.3 | -8.7 | 25.7 |
| 10-20 min | 7500 | 109.8 | 79.3 | 226.1 | -23.4 | 35.9 |
| 20+ min | 7500 | 192.2 | 129.7 | 394.7 | -59.0 | 44.6 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3881 | 56.2 | 31.8 | 93.5 | -3.4 | 9.3 |
| 0,5-2 km | 10910 | 73.1 | 47.5 | 145.0 | -22.5 | 24.3 |
| 2-5 km | 8385 | 102.7 | 73.4 | 214.5 | -15.5 | 31.3 |
| 5+ km | 6824 | 176.6 | 123.3 | 378.1 | -19.6 | 39.1 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3275 | 130.4 | 78.1 | 297.7 | -21.5 | 31.7 |
| resto del viaje | 26725 | 99.4 | 59.2 | 217.0 | -16.9 | 27.2 |
| P detenido | 11807 | 108.7 | 64.9 | 239.8 | -19.2 | 28.1 |
| P en movimiento | 18193 | 98.9 | 58.4 | 217.3 | -16.2 | 27.4 |
| inicio y detenido | 1401 | 137.3 | 86.0 | 303.4 | -31.9 | 33.6 |
| inicio y en movimiento | 1874 | 125.3 | 73.9 | 291.0 | -13.8 | 30.3 |
| resto y detenido | 10406 | 104.9 | 62.9 | 230.6 | -17.5 | 27.4 |
| resto y en movimiento | 16319 | 95.9 | 56.9 | 209.9 | -16.5 | 27.0 |
| global | 30000 | 102.7 | 60.7 | 225.1 | -17.4 | 27.7 |
| global sin inicio de viaje | 26725 | 99.4 | 59.2 | 217.0 | -16.9 | 27.2 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 4969 | 122.8 | 66.3 | 258.9 | -25.7 | 29.0 |
| inicio conocido | 25031 | 98.8 | 59.8 | 219.5 | -15.8 | 27.4 |

