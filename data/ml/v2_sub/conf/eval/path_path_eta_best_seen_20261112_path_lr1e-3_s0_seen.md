### path:data\ml\v2_sub\conf\path_lr1e-3_s0\path_eta_best.pt sobre eval_seen (n=29779)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 29779 | 102.6 | 63.7 | 230.2 | -15.4 | 28.7 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 6696 | 41.9 | 33.0 | 88.1 | 22.9 | 4.7 |
| 5-10 min | 7374 | 69.8 | 53.2 | 147.6 | -9.5 | 26.6 |
| 10-20 min | 7376 | 111.5 | 80.3 | 236.6 | -25.4 | 35.8 |
| 20+ min | 8333 | 172.5 | 128.0 | 362.9 | -42.5 | 43.6 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3512 | 56.2 | 34.5 | 102.3 | -2.6 | 12.0 |
| 0,5-2 km | 10365 | 72.5 | 47.9 | 150.7 | -19.9 | 24.7 |
| 2-5 km | 8381 | 102.5 | 74.7 | 215.1 | -15.3 | 31.8 |
| 5+ km | 7521 | 165.7 | 125.4 | 353.8 | -15.3 | 38.6 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 7320 | 127.2 | 77.6 | 286.5 | -24.5 | 32.5 |
| resto del viaje | 22459 | 94.6 | 60.1 | 213.8 | -12.4 | 27.4 |
| P detenido | 11849 | 106.4 | 67.6 | 237.5 | -16.7 | 29.8 |
| P en movimiento | 17930 | 100.0 | 61.1 | 225.6 | -14.5 | 28.0 |
| inicio y detenido | 3020 | 132.8 | 84.0 | 298.2 | -32.6 | 35.0 |
| inicio y en movimiento | 4300 | 123.2 | 72.1 | 278.4 | -18.8 | 30.8 |
| resto y detenido | 8829 | 97.4 | 63.2 | 219.0 | -11.3 | 28.0 |
| resto y en movimiento | 13630 | 92.7 | 58.1 | 208.9 | -13.2 | 27.1 |
| global | 29779 | 102.6 | 63.7 | 230.2 | -15.4 | 28.7 |
| global sin inicio de viaje | 22459 | 94.6 | 60.1 | 213.8 | -12.4 | 27.4 |

