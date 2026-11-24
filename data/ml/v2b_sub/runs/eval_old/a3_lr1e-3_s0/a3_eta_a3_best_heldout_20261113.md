### a3:data/ml/v2_sub/conf/a3_lr1e-3_s0/eta_a3_best.pt sobre eval_heldout (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 283.4 | 165.4 | 620.5 | -0.4 | 28.5 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 79.9 | 61.1 | 168.8 | 50.4 | 9.1 |
| 5-10 min | 7500 | 165.6 | 140.0 | 333.5 | 50.2 | 29.1 |
| 10-20 min | 7500 | 299.7 | 266.2 | 590.2 | 63.3 | 32.9 |
| 20+ min | 7500 | 588.6 | 405.4 | 1286.5 | -165.4 | 42.7 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 4083 | 83.4 | 51.2 | 142.6 | 8.0 | 10.7 |
| 0,5-2 km | 11740 | 147.8 | 115.4 | 305.5 | 37.4 | 24.5 |
| 2-5 km | 7879 | 319.3 | 281.0 | 618.8 | 76.0 | 32.1 |
| 5+ km | 6298 | 621.1 | 438.2 | 1392.8 | -171.7 | 42.7 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3551 | 351.8 | 253.0 | 730.4 | 132.8 | 20.6 |
| resto del viaje | 26449 | 274.3 | 156.8 | 598.9 | -18.2 | 29.5 |
| P detenido | 12817 | 279.8 | 169.3 | 623.4 | 13.6 | 27.4 |
| P en movimiento | 17183 | 286.2 | 161.6 | 618.5 | -10.8 | 29.2 |
| inicio y detenido | 1589 | 345.8 | 243.3 | 715.1 | 120.8 | 20.9 |
| inicio y en movimiento | 1962 | 356.6 | 260.8 | 742.2 | 142.5 | 20.4 |
| resto y detenido | 11228 | 270.5 | 161.5 | 600.1 | -1.5 | 28.4 |
| resto y en movimiento | 15221 | 277.1 | 153.0 | 596.7 | -30.6 | 30.4 |
| global | 30000 | 283.4 | 165.4 | 620.5 | -0.4 | 28.5 |
| global sin inicio de viaje | 26449 | 274.3 | 156.8 | 598.9 | -18.2 | 29.5 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 6380 | 396.2 | 216.6 | 929.2 | -189.1 | 49.4 |
| inicio conocido | 23620 | 253.0 | 154.9 | 554.7 | 50.6 | 22.8 |

