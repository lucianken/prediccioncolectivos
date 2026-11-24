### path:data/ml/v2_sub/conf/path_lr2e-3_s0/path_eta_best.pt sobre eval_seen (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 103.0 | 61.0 | 226.0 | -15.6 | 27.3 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 40.7 | 32.1 | 85.8 | 21.5 | 4.5 |
| 5-10 min | 7500 | 68.6 | 52.2 | 143.5 | -8.0 | 25.4 |
| 10-20 min | 7500 | 109.6 | 80.2 | 225.7 | -22.5 | 35.7 |
| 20+ min | 7500 | 192.9 | 131.8 | 394.1 | -53.6 | 43.6 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3881 | 56.4 | 32.0 | 94.4 | -3.7 | 9.5 |
| 0,5-2 km | 10910 | 73.3 | 47.0 | 145.1 | -21.6 | 23.9 |
| 2-5 km | 8385 | 103.1 | 74.5 | 213.2 | -13.6 | 30.9 |
| 5+ km | 6824 | 176.7 | 124.9 | 378.4 | -15.4 | 38.4 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3275 | 131.7 | 78.6 | 299.6 | -15.7 | 31.2 |
| resto del viaje | 26725 | 99.4 | 59.2 | 216.7 | -15.6 | 26.8 |
| P detenido | 11807 | 109.1 | 64.9 | 239.2 | -17.3 | 27.6 |
| P en movimiento | 18193 | 99.0 | 58.8 | 216.8 | -14.5 | 27.1 |
| inicio y detenido | 1401 | 138.9 | 85.4 | 315.4 | -29.1 | 34.0 |
| inicio y en movimiento | 1874 | 126.3 | 74.4 | 286.5 | -5.7 | 29.1 |
| resto y detenido | 10406 | 105.1 | 62.7 | 229.2 | -15.7 | 26.7 |
| resto y en movimiento | 16319 | 95.8 | 57.0 | 209.0 | -15.6 | 26.9 |
| global | 30000 | 103.0 | 61.0 | 226.0 | -15.6 | 27.3 |
| global sin inicio de viaje | 26725 | 99.4 | 59.2 | 216.7 | -15.6 | 26.8 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 4969 | 122.9 | 66.1 | 258.5 | -30.3 | 30.0 |
| inicio conocido | 25031 | 99.0 | 60.2 | 220.5 | -12.7 | 26.8 |

