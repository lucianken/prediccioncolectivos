### path:data/ml/v2_sub/models_path/path_eta_best.pt sobre eval_heldout (n=26537)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 26537 | 211.1 | 104.1 | 443.2 | -32.6 | 46.5 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 5637 | 56.7 | 40.4 | 117.2 | 25.0 | 9.6 |
| 5-10 min | 6740 | 116.0 | 81.7 | 230.6 | -17.4 | 41.9 |
| 10-20 min | 6778 | 184.6 | 128.7 | 370.8 | -55.8 | 55.2 |
| 20+ min | 7382 | 440.1 | 264.8 | 799.0 | -69.2 | 70.7 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3088 | 64.8 | 36.9 | 126.5 | -15.5 | 15.6 |
| 0,5-2 km | 9757 | 107.3 | 74.3 | 221.8 | -53.9 | 40.7 |
| 2-5 km | 7549 | 178.1 | 132.8 | 383.5 | -72.2 | 52.9 |
| 5+ km | 6143 | 490.0 | 274.1 | 1007.6 | 41.2 | 63.1 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 6896 | 254.6 | 145.7 | 558.1 | -83.5 | 54.9 |
| resto del viaje | 19641 | 195.8 | 93.2 | 390.1 | -14.8 | 43.5 |
| P detenido | 11388 | 195.8 | 102.7 | 409.9 | -63.3 | 48.8 |
| P en movimiento | 15149 | 222.6 | 105.0 | 462.9 | -9.5 | 44.7 |
| inicio y detenido | 2992 | 240.7 | 147.7 | 532.8 | -123.3 | 58.1 |
| inicio y en movimiento | 3904 | 265.3 | 143.5 | 582.9 | -52.9 | 52.5 |
| resto y detenido | 8396 | 179.8 | 90.8 | 358.1 | -41.9 | 45.5 |
| resto y en movimiento | 11245 | 207.7 | 94.8 | 418.9 | 5.5 | 42.0 |
| global | 26537 | 211.1 | 104.1 | 443.2 | -32.6 | 46.5 |
| global sin inicio de viaje | 19641 | 195.8 | 93.2 | 390.1 | -14.8 | 43.5 |

