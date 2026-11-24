### path:data\ml\v2_sub\conf\path_lr2e-3_s1\path_eta_best.pt sobre eval_seen (n=29779)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 29779 | 102.2 | 63.6 | 230.5 | -10.0 | 27.5 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 6696 | 42.2 | 33.0 | 88.0 | 23.7 | 4.2 |
| 5-10 min | 7374 | 69.8 | 53.5 | 147.5 | -7.1 | 25.8 |
| 10-20 min | 7376 | 111.4 | 80.7 | 236.1 | -20.3 | 34.4 |
| 20+ min | 8333 | 170.8 | 125.5 | 360.9 | -30.6 | 41.6 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3512 | 55.9 | 33.8 | 103.2 | -0.4 | 11.0 |
| 0,5-2 km | 10365 | 72.3 | 48.0 | 150.4 | -17.9 | 24.0 |
| 2-5 km | 8381 | 102.5 | 74.8 | 216.5 | -9.5 | 30.2 |
| 5+ km | 7521 | 164.6 | 121.0 | 353.2 | -4.2 | 37.0 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 7320 | 126.1 | 77.6 | 285.0 | -19.0 | 31.3 |
| resto del viaje | 22459 | 94.4 | 60.2 | 213.7 | -7.1 | 26.3 |
| P detenido | 11849 | 106.2 | 67.7 | 238.0 | -10.5 | 28.3 |
| P en movimiento | 17930 | 99.5 | 61.1 | 225.4 | -9.8 | 26.9 |
| inicio y detenido | 3020 | 131.6 | 84.3 | 301.5 | -25.0 | 33.4 |
| inicio y en movimiento | 4300 | 122.3 | 72.7 | 277.6 | -14.7 | 29.9 |
| resto y detenido | 8829 | 97.5 | 63.0 | 220.0 | -5.5 | 26.6 |
| resto y en movimiento | 13630 | 92.3 | 58.4 | 209.9 | -8.2 | 26.0 |
| global | 29779 | 102.2 | 63.6 | 230.5 | -10.0 | 27.5 |
| global sin inicio de viaje | 22459 | 94.4 | 60.2 | 213.7 | -7.1 | 26.3 |

