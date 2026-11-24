### path:data\ml\v2_sub\conf\path_lr2e-3_s1\path_eta_best.pt sobre eval_heldout (n=26537)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 26537 | 229.8 | 107.1 | 467.0 | -33.2 | 49.5 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 5637 | 58.0 | 39.7 | 114.6 | 25.2 | 10.3 |
| 5-10 min | 6740 | 121.0 | 83.0 | 228.8 | -17.3 | 44.7 |
| 10-20 min | 6778 | 196.2 | 135.7 | 372.0 | -63.5 | 59.7 |
| 20+ min | 7382 | 491.2 | 283.9 | 839.7 | -64.6 | 74.5 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3088 | 63.8 | 36.0 | 116.1 | -16.3 | 15.6 |
| 0,5-2 km | 9757 | 107.6 | 74.9 | 224.3 | -57.0 | 43.0 |
| 2-5 km | 7549 | 189.0 | 140.3 | 403.9 | -85.8 | 57.8 |
| 5+ km | 6143 | 557.5 | 297.2 | 1147.7 | 60.7 | 66.5 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 6896 | 270.1 | 148.8 | 571.1 | -87.3 | 56.9 |
| resto del viaje | 19641 | 215.7 | 96.0 | 412.7 | -14.2 | 46.9 |
| P detenido | 11388 | 208.4 | 104.3 | 424.8 | -66.8 | 51.3 |
| P en movimiento | 15149 | 245.9 | 109.0 | 497.1 | -8.0 | 48.1 |
| inicio y detenido | 2992 | 248.1 | 151.7 | 540.9 | -133.2 | 59.6 |
| inicio y en movimiento | 3904 | 286.9 | 147.1 | 597.7 | -52.1 | 54.9 |
| resto y detenido | 8396 | 194.3 | 93.1 | 374.2 | -43.1 | 48.4 |
| resto y en movimiento | 11245 | 231.6 | 98.5 | 448.6 | 7.3 | 45.8 |
| global | 26537 | 229.8 | 107.1 | 467.0 | -33.2 | 49.5 |
| global sin inicio de viaje | 19641 | 215.7 | 96.0 | 412.7 | -14.2 | 46.9 |

