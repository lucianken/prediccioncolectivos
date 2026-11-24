### a3:data/ml/v2_sub/conf/a3_lr1e-3_s0/eta_a3_best.pt sobre eval_seen (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 113.0 | 65.6 | 257.4 | -33.7 | 31.6 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 41.9 | 33.2 | 87.5 | 22.9 | 4.5 |
| 5-10 min | 7500 | 71.1 | 55.1 | 151.0 | -17.3 | 29.3 |
| 10-20 min | 7500 | 119.4 | 88.0 | 254.2 | -40.1 | 41.1 |
| 20+ min | 7500 | 219.6 | 149.7 | 462.1 | -100.5 | 51.7 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3881 | 57.4 | 32.8 | 96.7 | -1.0 | 9.1 |
| 0,5-2 km | 10910 | 77.7 | 49.5 | 157.8 | -29.4 | 27.2 |
| 2-5 km | 8385 | 112.1 | 79.9 | 236.8 | -30.2 | 35.8 |
| 5+ km | 6824 | 202.1 | 142.7 | 434.3 | -63.7 | 46.5 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3275 | 140.4 | 83.9 | 321.0 | -22.2 | 32.7 |
| resto del viaje | 26725 | 109.6 | 63.8 | 247.4 | -35.2 | 31.5 |
| P detenido | 11807 | 119.2 | 69.4 | 271.3 | -36.0 | 32.4 |
| P en movimiento | 18193 | 109.0 | 63.2 | 247.8 | -32.3 | 31.2 |
| inicio y detenido | 1401 | 148.5 | 92.0 | 344.4 | -35.2 | 35.8 |
| inicio y en movimiento | 1874 | 134.4 | 77.7 | 304.3 | -12.5 | 30.4 |
| resto y detenido | 10406 | 115.3 | 67.4 | 261.0 | -36.1 | 31.9 |
| resto y en movimiento | 16319 | 106.0 | 61.5 | 239.2 | -34.5 | 31.3 |
| global | 30000 | 113.0 | 65.6 | 257.4 | -33.7 | 31.6 |
| global sin inicio de viaje | 26725 | 109.6 | 63.8 | 247.4 | -35.2 | 31.5 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 4969 | 158.4 | 87.2 | 361.8 | -89.9 | 44.9 |
| inicio conocido | 25031 | 104.0 | 62.3 | 234.9 | -22.6 | 29.0 |

