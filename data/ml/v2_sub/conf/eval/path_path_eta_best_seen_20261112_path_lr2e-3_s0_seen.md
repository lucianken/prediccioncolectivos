### path:data\ml\v2_sub\conf\path_lr2e-3_s0\path_eta_best.pt sobre eval_seen (n=29779)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 29779 | 101.6 | 63.1 | 229.7 | -14.9 | 28.5 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 6696 | 41.4 | 32.3 | 86.4 | 22.6 | 4.5 |
| 5-10 min | 7374 | 69.4 | 54.0 | 145.9 | -9.2 | 26.6 |
| 10-20 min | 7376 | 110.6 | 79.6 | 235.9 | -24.8 | 35.4 |
| 20+ min | 8333 | 170.4 | 124.5 | 359.8 | -41.3 | 43.4 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3512 | 55.2 | 33.7 | 100.1 | -2.0 | 11.6 |
| 0,5-2 km | 10365 | 72.0 | 48.0 | 150.2 | -19.7 | 24.7 |
| 2-5 km | 8381 | 101.7 | 74.0 | 216.2 | -14.8 | 31.3 |
| 5+ km | 7521 | 163.7 | 121.5 | 352.7 | -14.4 | 38.6 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 7320 | 125.9 | 78.0 | 283.0 | -24.5 | 32.6 |
| resto del viaje | 22459 | 93.6 | 59.6 | 212.1 | -11.8 | 27.2 |
| P detenido | 11849 | 105.5 | 66.6 | 238.2 | -16.2 | 29.5 |
| P en movimiento | 17930 | 99.0 | 60.9 | 222.5 | -14.0 | 27.9 |
| inicio y detenido | 3020 | 131.2 | 83.6 | 289.3 | -31.7 | 34.7 |
| inicio y en movimiento | 4300 | 122.2 | 73.8 | 279.8 | -19.4 | 31.1 |
| resto y detenido | 8829 | 96.7 | 62.2 | 222.5 | -10.9 | 27.7 |
| resto y en movimiento | 13630 | 91.6 | 57.8 | 206.4 | -12.3 | 26.9 |
| global | 29779 | 101.6 | 63.1 | 229.7 | -14.9 | 28.5 |
| global sin inicio de viaje | 22459 | 93.6 | 59.6 | 212.1 | -11.8 | 27.2 |

