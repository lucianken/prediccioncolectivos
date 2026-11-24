### a3:data\ml\v2_sub\conf\a3_lr2e-3_s0\eta_a3_best.pt sobre eval_heldout (n=26537)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 26537 | 284.2 | 170.4 | 635.2 | -5.3 | 30.8 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 5637 | 92.2 | 68.7 | 183.8 | 66.8 | 8.2 |
| 5-10 min | 6740 | 169.4 | 132.0 | 342.5 | 56.4 | 29.2 |
| 10-20 min | 6778 | 287.1 | 248.5 | 577.2 | 60.6 | 34.4 |
| 20+ min | 7382 | 533.1 | 383.0 | 1110.3 | -177.1 | 46.3 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3088 | 86.3 | 57.7 | 168.8 | 23.1 | 11.1 |
| 0,5-2 km | 9757 | 152.4 | 112.1 | 314.2 | 38.4 | 25.2 |
| 2-5 km | 7549 | 301.9 | 256.5 | 609.7 | 77.2 | 33.0 |
| 5+ km | 6143 | 571.5 | 414.9 | 1218.4 | -190.2 | 47.0 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 6896 | 326.4 | 226.3 | 707.5 | 11.2 | 34.9 |
| resto del viaje | 19641 | 269.4 | 153.5 | 600.7 | -11.0 | 29.4 |
| P detenido | 11388 | 276.9 | 167.3 | 619.9 | -3.7 | 30.5 |
| P en movimiento | 15149 | 289.7 | 172.8 | 649.4 | -6.4 | 31.0 |
| inicio y detenido | 2992 | 324.0 | 224.5 | 712.1 | 3.7 | 35.7 |
| inicio y en movimiento | 3904 | 328.2 | 228.9 | 705.9 | 16.9 | 34.2 |
| resto y detenido | 8396 | 260.1 | 149.0 | 582.1 | -6.4 | 28.7 |
| resto y en movimiento | 11245 | 276.4 | 157.3 | 618.3 | -14.5 | 29.9 |
| global | 26537 | 284.2 | 170.4 | 635.2 | -5.3 | 30.8 |
| global sin inicio de viaje | 19641 | 269.4 | 153.5 | 600.7 | -11.0 | 29.4 |

