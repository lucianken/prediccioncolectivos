### a3:data\ml\v2b_sub\runs\a3_lr1e-3_s0\eta_a3_best.pt sobre eval_seen (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 108.9 | 65.1 | 245.0 | -11.2 | 26.7 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 44.6 | 35.9 | 93.2 | 29.4 | 3.4 |
| 5-10 min | 7500 | 69.4 | 53.4 | 146.9 | -4.5 | 24.4 |
| 10-20 min | 7500 | 114.8 | 83.8 | 239.1 | -16.0 | 34.8 |
| 20+ min | 7500 | 206.8 | 145.0 | 428.5 | -53.7 | 44.1 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3881 | 60.1 | 36.5 | 102.9 | 5.3 | 8.3 |
| 0,5-2 km | 10910 | 75.2 | 49.1 | 148.8 | -18.1 | 23.4 |
| 2-5 km | 8385 | 107.5 | 77.8 | 225.8 | -7.0 | 29.6 |
| 5+ km | 6824 | 192.2 | 139.4 | 411.5 | -14.7 | 38.8 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3275 | 140.2 | 85.0 | 331.3 | -19.2 | 31.6 |
| resto del viaje | 26725 | 105.1 | 63.1 | 233.9 | -10.2 | 26.1 |
| P detenido | 11807 | 114.9 | 67.4 | 259.6 | -16.9 | 27.9 |
| P en movimiento | 18193 | 105.0 | 63.8 | 235.1 | -7.5 | 25.9 |
| inicio y detenido | 1401 | 144.9 | 84.0 | 339.0 | -37.2 | 35.5 |
| inicio y en movimiento | 1874 | 136.7 | 85.3 | 318.5 | -5.8 | 28.8 |
| resto y detenido | 10406 | 110.8 | 65.4 | 247.9 | -14.1 | 26.9 |
| resto y en movimiento | 16319 | 101.4 | 61.9 | 224.5 | -7.7 | 25.6 |
| global | 30000 | 108.9 | 65.1 | 245.0 | -11.2 | 26.7 |
| global sin inicio de viaje | 26725 | 105.1 | 63.1 | 233.9 | -10.2 | 26.1 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 4969 | 129.3 | 72.5 | 281.5 | -18.4 | 28.5 |
| inicio conocido | 25031 | 104.9 | 63.8 | 237.3 | -9.8 | 26.3 |

