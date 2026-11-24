### a3:data/ml/v2_sub/models/eta_a3_best.pt sobre eval_heldout (n=26537)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 26537 | 282.3 | 171.7 | 623.5 | -21.2 | 32.3 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 5637 | 76.4 | 59.6 | 161.4 | 45.4 | 10.3 |
| 5-10 min | 6740 | 163.1 | 139.8 | 324.8 | 31.1 | 32.7 |
| 10-20 min | 6778 | 290.8 | 259.9 | 577.1 | 49.1 | 34.3 |
| 20+ min | 7382 | 540.5 | 387.1 | 1158.0 | -184.6 | 46.7 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3088 | 74.4 | 48.7 | 142.9 | 6.3 | 12.7 |
| 0,5-2 km | 9757 | 148.4 | 114.8 | 303.5 | 22.6 | 27.4 |
| 2-5 km | 7549 | 300.2 | 261.9 | 593.6 | 55.6 | 33.9 |
| 5+ km | 6143 | 577.5 | 421.8 | 1243.4 | -199.2 | 47.7 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 6896 | 330.6 | 233.7 | 721.6 | 5.9 | 35.2 |
| resto del viaje | 19641 | 265.3 | 154.6 | 576.0 | -30.8 | 31.2 |
| P detenido | 11388 | 278.2 | 173.3 | 612.0 | -15.8 | 31.7 |
| P en movimiento | 15149 | 285.4 | 170.8 | 631.1 | -25.4 | 32.7 |
| inicio y detenido | 2992 | 333.8 | 238.5 | 730.9 | 2.1 | 36.0 |
| inicio y en movimiento | 3904 | 328.2 | 229.8 | 713.2 | 8.9 | 34.6 |
| resto y detenido | 8396 | 258.4 | 153.3 | 551.6 | -22.2 | 30.2 |
| resto y en movimiento | 11245 | 270.5 | 155.2 | 594.0 | -37.2 | 32.0 |
| global | 26537 | 282.3 | 171.7 | 623.5 | -21.2 | 32.3 |
| global sin inicio de viaje | 19641 | 265.3 | 154.6 | 576.0 | -30.8 | 31.2 |

