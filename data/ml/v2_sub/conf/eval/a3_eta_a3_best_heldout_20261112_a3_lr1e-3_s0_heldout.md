### a3:data\ml\v2_sub\conf\a3_lr1e-3_s0\eta_a3_best.pt sobre eval_heldout (n=26537)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 26537 | 298.6 | 185.7 | 660.6 | 5.6 | 30.3 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 5637 | 82.9 | 63.0 | 174.2 | 53.4 | 9.4 |
| 5-10 min | 6740 | 172.3 | 147.4 | 340.0 | 47.9 | 31.0 |
| 10-20 min | 6778 | 312.9 | 287.1 | 599.3 | 74.5 | 33.9 |
| 20+ min | 7382 | 565.6 | 418.0 | 1186.0 | -132.6 | 42.4 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3088 | 77.0 | 52.7 | 152.3 | 17.1 | 11.3 |
| 0,5-2 km | 9757 | 156.2 | 122.2 | 317.1 | 37.4 | 26.0 |
| 2-5 km | 7549 | 326.5 | 295.7 | 630.1 | 82.6 | 33.2 |
| 5+ km | 6143 | 602.0 | 448.5 | 1268.6 | -145.1 | 43.2 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 6896 | 355.2 | 250.1 | 770.6 | 66.3 | 30.2 |
| resto del viaje | 19641 | 278.7 | 166.0 | 609.6 | -15.6 | 30.4 |
| P detenido | 11388 | 295.8 | 187.3 | 656.7 | 20.9 | 28.9 |
| P en movimiento | 15149 | 300.8 | 184.6 | 665.4 | -5.8 | 31.4 |
| inicio y detenido | 2992 | 356.8 | 252.9 | 787.8 | 77.1 | 29.0 |
| inicio y en movimiento | 3904 | 354.0 | 247.8 | 757.1 | 58.1 | 31.1 |
| resto y detenido | 8396 | 274.0 | 167.5 | 598.2 | 0.8 | 28.9 |
| resto y en movimiento | 11245 | 282.3 | 164.9 | 620.1 | -27.9 | 31.5 |
| global | 26537 | 298.6 | 185.7 | 660.6 | 5.6 | 30.3 |
| global sin inicio de viaje | 19641 | 278.7 | 166.0 | 609.6 | -15.6 | 30.4 |

