### a3:data\ml\v2_sub\conf\a3_lr2e-3_s0\eta_a3_best.pt sobre eval_seen (n=29779)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 29779 | 107.1 | 67.6 | 242.3 | -21.4 | 30.0 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 6696 | 46.5 | 37.7 | 94.7 | 32.1 | 3.1 |
| 5-10 min | 7374 | 69.6 | 54.3 | 148.0 | -11.1 | 27.1 |
| 10-20 min | 7376 | 113.8 | 82.2 | 243.5 | -27.2 | 36.7 |
| 20+ min | 8333 | 183.1 | 134.6 | 385.4 | -68.5 | 48.3 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3512 | 59.8 | 39.4 | 110.4 | 9.0 | 10.0 |
| 0,5-2 km | 10365 | 74.8 | 50.9 | 153.7 | -20.2 | 25.2 |
| 2-5 km | 8381 | 104.5 | 76.7 | 221.4 | -17.5 | 32.5 |
| 5+ km | 7521 | 176.4 | 132.3 | 379.3 | -41.8 | 43.3 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 7320 | 132.7 | 82.3 | 303.2 | -31.5 | 33.9 |
| resto del viaje | 22459 | 98.7 | 63.9 | 222.4 | -18.1 | 28.8 |
| P detenido | 11849 | 111.0 | 70.6 | 252.2 | -30.1 | 32.8 |
| P en movimiento | 17930 | 104.5 | 66.0 | 236.5 | -15.7 | 28.2 |
| inicio y detenido | 3020 | 137.6 | 86.5 | 317.3 | -48.7 | 38.4 |
| inicio y en movimiento | 4300 | 129.2 | 79.8 | 297.1 | -19.5 | 30.7 |
| resto y detenido | 8829 | 101.8 | 65.8 | 230.9 | -23.7 | 30.9 |
| resto y en movimiento | 13630 | 96.7 | 62.8 | 217.5 | -14.6 | 27.4 |
| global | 29779 | 107.1 | 67.6 | 242.3 | -21.4 | 30.0 |
| global sin inicio de viaje | 22459 | 98.7 | 63.9 | 222.4 | -18.1 | 28.8 |

