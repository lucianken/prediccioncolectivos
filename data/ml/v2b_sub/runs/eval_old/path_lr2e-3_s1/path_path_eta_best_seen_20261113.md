### path:data/ml/v2_sub/conf/path_lr2e-3_s1/path_eta_best.pt sobre eval_seen (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 103.5 | 61.5 | 227.6 | -10.6 | 26.3 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 41.1 | 31.9 | 86.4 | 22.6 | 4.4 |
| 5-10 min | 7500 | 69.2 | 52.2 | 145.0 | -6.2 | 24.8 |
| 10-20 min | 7500 | 111.0 | 80.0 | 229.1 | -17.5 | 34.9 |
| 20+ min | 7500 | 192.8 | 131.6 | 396.0 | -41.2 | 41.0 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3881 | 57.0 | 32.7 | 95.1 | -2.2 | 9.3 |
| 0,5-2 km | 10910 | 73.5 | 47.3 | 146.3 | -19.8 | 23.5 |
| 2-5 km | 8385 | 103.9 | 74.3 | 216.0 | -8.3 | 29.9 |
| 5+ km | 6824 | 177.7 | 125.2 | 379.8 | -3.2 | 35.9 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3275 | 133.5 | 80.9 | 298.1 | -8.4 | 29.9 |
| resto del viaje | 26725 | 99.9 | 59.6 | 219.3 | -10.8 | 25.8 |
| P detenido | 11807 | 109.6 | 65.2 | 242.6 | -11.6 | 26.4 |
| P en movimiento | 18193 | 99.6 | 59.3 | 218.9 | -9.9 | 26.2 |
| inicio y detenido | 1401 | 140.1 | 86.7 | 316.5 | -21.1 | 31.9 |
| inicio y en movimiento | 1874 | 128.6 | 77.3 | 283.5 | 1.1 | 28.4 |
| resto y detenido | 10406 | 105.5 | 63.1 | 233.2 | -10.4 | 25.7 |
| resto y en movimiento | 16319 | 96.3 | 57.5 | 211.1 | -11.1 | 25.9 |
| global | 30000 | 103.5 | 61.5 | 227.6 | -10.6 | 26.3 |
| global sin inicio de viaje | 26725 | 99.9 | 59.6 | 219.3 | -10.8 | 25.8 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 4969 | 123.3 | 66.8 | 258.1 | -24.9 | 29.4 |
| inicio conocido | 25031 | 99.6 | 60.5 | 222.1 | -7.7 | 25.6 |

