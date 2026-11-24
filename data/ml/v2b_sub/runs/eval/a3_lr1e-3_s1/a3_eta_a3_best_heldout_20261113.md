### a3:data\ml\v2b_sub\runs\a3_lr1e-3_s1\eta_a3_best.pt sobre eval_heldout (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 268.3 | 153.1 | 583.9 | 3.6 | 27.5 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 77.5 | 59.1 | 163.3 | 49.2 | 9.0 |
| 5-10 min | 7500 | 155.4 | 128.5 | 319.6 | 44.0 | 28.8 |
| 10-20 min | 7500 | 285.6 | 250.8 | 575.3 | 61.2 | 32.8 |
| 20+ min | 7500 | 554.6 | 364.6 | 1268.8 | -140.1 | 39.5 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 4083 | 82.8 | 49.7 | 141.7 | 11.4 | 10.5 |
| 0,5-2 km | 11740 | 139.0 | 107.8 | 284.7 | 29.8 | 25.1 |
| 2-5 km | 7879 | 303.0 | 266.3 | 591.3 | 76.7 | 30.5 |
| 5+ km | 6298 | 586.1 | 392.8 | 1375.5 | -141.9 | 39.4 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3551 | 353.7 | 238.4 | 750.6 | 155.3 | 19.2 |
| resto del viaje | 26449 | 256.8 | 144.2 | 554.1 | -16.8 | 28.7 |
| P detenido | 12817 | 263.6 | 157.4 | 573.8 | 17.6 | 26.7 |
| P en movimiento | 17183 | 271.8 | 149.8 | 591.1 | -6.9 | 28.1 |
| inicio y detenido | 1589 | 340.9 | 231.2 | 713.2 | 137.1 | 19.7 |
| inicio y en movimiento | 1962 | 364.1 | 246.1 | 773.3 | 170.1 | 18.8 |
| resto y detenido | 11228 | 252.6 | 149.1 | 550.2 | 0.7 | 27.7 |
| resto y en movimiento | 15221 | 259.9 | 140.1 | 558.3 | -29.7 | 29.3 |
| global | 30000 | 268.3 | 153.1 | 583.9 | 3.6 | 27.5 |
| global sin inicio de viaje | 26449 | 256.8 | 144.2 | 554.1 | -16.8 | 28.7 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 6380 | 366.3 | 205.8 | 829.5 | -175.4 | 46.3 |
| inicio conocido | 23620 | 241.8 | 142.4 | 535.7 | 51.9 | 22.5 |

