### a3:data\ml\v2b_sub\runs\a3_lr1e-3_s0\eta_a3_best.pt sobre eval_heldout (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 276.8 | 159.5 | 604.2 | -0.9 | 28.1 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 80.8 | 62.1 | 172.6 | 52.9 | 9.0 |
| 5-10 min | 7500 | 163.1 | 135.4 | 333.9 | 49.5 | 28.8 |
| 10-20 min | 7500 | 293.3 | 253.4 | 595.9 | 60.2 | 33.5 |
| 20+ min | 7500 | 569.9 | 384.9 | 1259.2 | -166.2 | 41.4 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 4083 | 83.7 | 51.4 | 144.5 | 8.3 | 10.6 |
| 0,5-2 km | 11740 | 145.0 | 111.7 | 298.0 | 35.1 | 25.0 |
| 2-5 km | 7879 | 313.9 | 277.2 | 618.3 | 75.7 | 31.4 |
| 5+ km | 6298 | 601.3 | 416.5 | 1362.1 | -170.0 | 41.3 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3551 | 344.4 | 239.9 | 737.3 | 125.2 | 22.6 |
| resto del viaje | 26449 | 267.7 | 151.7 | 578.3 | -17.9 | 28.9 |
| P detenido | 12817 | 271.1 | 161.4 | 599.0 | 6.8 | 27.9 |
| P en movimiento | 17183 | 281.0 | 158.2 | 609.9 | -6.7 | 28.3 |
| inicio y detenido | 1589 | 331.3 | 225.3 | 722.0 | 103.6 | 24.0 |
| inicio y en movimiento | 1962 | 355.0 | 254.1 | 752.9 | 142.8 | 21.4 |
| resto y detenido | 11228 | 262.6 | 153.9 | 576.3 | -6.9 | 28.4 |
| resto y en movimiento | 15221 | 271.4 | 150.0 | 578.8 | -25.9 | 29.2 |
| global | 30000 | 276.8 | 159.5 | 604.2 | -0.9 | 28.1 |
| global sin inicio de viaje | 26449 | 267.7 | 151.7 | 578.3 | -17.9 | 28.9 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 6380 | 377.5 | 208.9 | 861.9 | -186.5 | 47.0 |
| inicio conocido | 23620 | 249.6 | 148.9 | 552.7 | 49.2 | 23.1 |

