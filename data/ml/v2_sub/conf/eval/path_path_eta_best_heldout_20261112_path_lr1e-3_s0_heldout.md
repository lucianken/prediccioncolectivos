### path:data\ml\v2_sub\conf\path_lr1e-3_s0\path_eta_best.pt sobre eval_heldout (n=26537)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 26537 | 221.2 | 106.4 | 469.5 | -19.9 | 45.8 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 5637 | 59.4 | 41.7 | 122.4 | 25.0 | 11.0 |
| 5-10 min | 6740 | 122.4 | 82.8 | 250.4 | -14.2 | 41.8 |
| 10-20 min | 6778 | 196.7 | 132.7 | 417.4 | -44.5 | 54.2 |
| 20+ min | 7382 | 457.3 | 271.4 | 819.9 | -37.0 | 68.4 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3088 | 65.5 | 37.3 | 122.7 | -14.2 | 15.6 |
| 0,5-2 km | 9757 | 109.8 | 74.2 | 231.1 | -48.6 | 40.2 |
| 2-5 km | 7549 | 188.1 | 140.0 | 412.3 | -60.3 | 52.6 |
| 5+ km | 6143 | 517.0 | 290.9 | 1086.6 | 72.4 | 61.7 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 6896 | 260.1 | 149.1 | 565.5 | -77.6 | 55.4 |
| resto del viaje | 19641 | 207.5 | 94.8 | 422.7 | 0.3 | 42.5 |
| P detenido | 11388 | 203.2 | 104.5 | 433.4 | -48.8 | 47.9 |
| P en movimiento | 15149 | 234.6 | 108.0 | 493.8 | 1.8 | 44.3 |
| inicio y detenido | 2992 | 244.7 | 151.4 | 528.3 | -119.5 | 58.6 |
| inicio y en movimiento | 3904 | 271.9 | 147.5 | 594.1 | -45.5 | 53.0 |
| resto y detenido | 8396 | 188.5 | 92.0 | 381.0 | -23.7 | 44.1 |
| resto y en movimiento | 11245 | 221.7 | 97.9 | 455.3 | 18.2 | 41.3 |
| global | 26537 | 221.2 | 106.4 | 469.5 | -19.9 | 45.8 |
| global sin inicio de viaje | 19641 | 207.5 | 94.8 | 422.7 | 0.3 | 42.5 |

