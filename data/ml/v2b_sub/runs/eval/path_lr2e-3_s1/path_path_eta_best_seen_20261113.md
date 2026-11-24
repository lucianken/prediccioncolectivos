### path:data\ml\v2b_sub\runs\path_lr2e-3_s1\path_eta_best.pt sobre eval_seen (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 103.5 | 60.9 | 228.5 | -13.6 | 26.8 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 40.9 | 32.2 | 86.4 | 22.0 | 4.4 |
| 5-10 min | 7500 | 69.3 | 52.0 | 145.6 | -6.8 | 25.1 |
| 10-20 min | 7500 | 110.5 | 79.6 | 227.7 | -19.7 | 34.9 |
| 20+ min | 7500 | 193.3 | 131.8 | 395.8 | -49.9 | 43.0 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3881 | 56.7 | 32.6 | 94.7 | -1.9 | 9.0 |
| 0,5-2 km | 10910 | 73.3 | 47.0 | 145.5 | -20.7 | 23.6 |
| 2-5 km | 8385 | 103.6 | 74.2 | 215.7 | -11.3 | 30.2 |
| 5+ km | 6824 | 178.3 | 125.5 | 381.2 | -11.7 | 37.9 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3275 | 131.2 | 76.5 | 302.3 | -19.0 | 31.1 |
| resto del viaje | 26725 | 100.1 | 59.5 | 220.4 | -12.9 | 26.3 |
| P detenido | 11807 | 109.6 | 64.6 | 241.1 | -15.1 | 27.3 |
| P en movimiento | 18193 | 99.5 | 58.6 | 220.0 | -12.6 | 26.6 |
| inicio y detenido | 1401 | 137.6 | 85.2 | 317.2 | -30.6 | 33.0 |
| inicio y en movimiento | 1874 | 126.5 | 72.3 | 294.8 | -10.4 | 29.6 |
| resto y detenido | 10406 | 105.8 | 63.0 | 232.7 | -13.0 | 26.5 |
| resto y en movimiento | 16319 | 96.4 | 57.2 | 211.8 | -12.9 | 26.2 |
| global | 30000 | 103.5 | 60.9 | 228.5 | -13.6 | 26.8 |
| global sin inicio de viaje | 26725 | 100.1 | 59.5 | 220.4 | -12.9 | 26.3 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 4969 | 123.7 | 67.2 | 261.1 | -21.9 | 28.8 |
| inicio conocido | 25031 | 99.5 | 59.8 | 221.7 | -11.9 | 26.5 |

