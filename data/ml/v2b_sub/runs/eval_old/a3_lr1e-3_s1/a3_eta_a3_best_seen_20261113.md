### a3:data/ml/v2_sub/conf/a3_lr1e-3_s1/eta_a3_best.pt sobre eval_seen (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 115.6 | 66.7 | 262.2 | -38.1 | 32.8 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 41.7 | 33.2 | 87.7 | 21.1 | 5.1 |
| 5-10 min | 7500 | 72.8 | 56.9 | 152.6 | -21.3 | 31.1 |
| 10-20 min | 7500 | 123.0 | 90.4 | 260.5 | -45.0 | 42.5 |
| 20+ min | 7500 | 224.9 | 153.9 | 480.6 | -107.2 | 52.5 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3881 | 58.6 | 33.0 | 100.0 | -2.9 | 9.6 |
| 0,5-2 km | 10910 | 79.0 | 50.3 | 160.0 | -33.7 | 28.8 |
| 2-5 km | 8385 | 115.2 | 82.6 | 241.0 | -35.2 | 37.1 |
| 5+ km | 6824 | 207.1 | 148.6 | 453.2 | -68.6 | 47.2 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3275 | 144.0 | 86.4 | 325.6 | -33.4 | 34.7 |
| resto del viaje | 26725 | 112.1 | 64.8 | 251.6 | -38.7 | 32.6 |
| P detenido | 11807 | 121.8 | 70.1 | 275.8 | -47.0 | 34.9 |
| P en movimiento | 18193 | 111.6 | 64.8 | 251.5 | -32.3 | 31.5 |
| inicio y detenido | 1401 | 150.8 | 91.6 | 347.2 | -55.9 | 39.5 |
| inicio y en movimiento | 1874 | 138.9 | 83.1 | 313.3 | -16.5 | 31.2 |
| resto y detenido | 10406 | 117.9 | 68.1 | 264.3 | -45.8 | 34.3 |
| resto y en movimiento | 16319 | 108.5 | 63.1 | 243.3 | -34.1 | 31.5 |
| global | 30000 | 115.6 | 66.7 | 262.2 | -38.1 | 32.8 |
| global sin inicio de viaje | 26725 | 112.1 | 64.8 | 251.6 | -38.7 | 32.6 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 4969 | 163.7 | 88.6 | 380.1 | -99.1 | 46.7 |
| inicio conocido | 25031 | 106.1 | 63.5 | 239.7 | -26.0 | 30.0 |

