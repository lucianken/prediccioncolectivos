### a3:data\ml\v2b_sub\runs\a3_lr1e-3_s1\eta_a3_best.pt sobre eval_seen (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 107.1 | 64.3 | 239.7 | -7.0 | 25.4 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 45.0 | 35.4 | 93.7 | 29.9 | 3.3 |
| 5-10 min | 7500 | 69.5 | 52.4 | 146.8 | -0.5 | 23.1 |
| 10-20 min | 7500 | 112.8 | 83.9 | 234.2 | -8.9 | 32.3 |
| 20+ min | 7500 | 201.1 | 141.1 | 419.5 | -48.5 | 42.9 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3881 | 59.7 | 35.6 | 101.7 | 7.8 | 8.0 |
| 0,5-2 km | 10910 | 74.4 | 48.1 | 147.5 | -14.8 | 22.1 |
| 2-5 km | 8385 | 106.2 | 78.0 | 221.3 | 0.1 | 27.6 |
| 5+ km | 6824 | 187.5 | 137.3 | 406.4 | -11.7 | 37.8 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3275 | 137.3 | 84.4 | 319.7 | -19.0 | 31.9 |
| resto del viaje | 26725 | 103.4 | 62.3 | 229.7 | -5.5 | 24.6 |
| P detenido | 11807 | 113.8 | 68.3 | 255.2 | -6.2 | 25.4 |
| P en movimiento | 18193 | 102.8 | 61.9 | 230.1 | -7.5 | 25.4 |
| inicio y detenido | 1401 | 143.1 | 87.9 | 337.7 | -27.1 | 34.1 |
| inicio y en movimiento | 1874 | 133.0 | 82.1 | 305.4 | -12.9 | 30.3 |
| resto y detenido | 10406 | 109.8 | 66.1 | 242.3 | -3.4 | 24.2 |
| resto y en movimiento | 16319 | 99.3 | 60.0 | 219.7 | -6.9 | 24.8 |
| global | 30000 | 107.1 | 64.3 | 239.7 | -7.0 | 25.4 |
| global sin inicio de viaje | 26725 | 103.4 | 62.3 | 229.7 | -5.5 | 24.6 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 4969 | 126.8 | 70.6 | 280.1 | -6.8 | 25.4 |
| inicio conocido | 25031 | 103.2 | 63.4 | 231.8 | -7.0 | 25.4 |

