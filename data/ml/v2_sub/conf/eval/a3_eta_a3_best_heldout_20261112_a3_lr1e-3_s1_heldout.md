### a3:data\ml\v2_sub\conf\a3_lr1e-3_s1\eta_a3_best.pt sobre eval_heldout (n=26537)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 26537 | 287.6 | 176.7 | 638.3 | -14.7 | 32.4 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 5637 | 79.2 | 61.6 | 166.3 | 48.0 | 10.5 |
| 5-10 min | 6740 | 165.4 | 140.1 | 331.9 | 35.6 | 32.4 |
| 10-20 min | 6778 | 300.8 | 273.2 | 584.3 | 57.5 | 35.3 |
| 20+ min | 7382 | 546.3 | 395.1 | 1149.9 | -174.6 | 46.3 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 3088 | 76.0 | 51.1 | 147.4 | 8.0 | 13.3 |
| 0,5-2 km | 9757 | 150.8 | 117.6 | 307.0 | 22.6 | 28.1 |
| 2-5 km | 7549 | 312.5 | 277.3 | 612.3 | 69.6 | 33.7 |
| 5+ km | 6143 | 580.7 | 427.8 | 1235.2 | -188.8 | 47.1 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 6896 | 333.0 | 227.7 | 728.6 | 3.8 | 35.6 |
| resto del viaje | 19641 | 271.7 | 160.9 | 598.5 | -21.1 | 31.2 |
| P detenido | 11388 | 281.4 | 176.4 | 627.2 | -13.3 | 32.2 |
| P en movimiento | 15149 | 292.3 | 177.1 | 646.7 | -15.6 | 32.4 |
| inicio y detenido | 2992 | 335.1 | 230.5 | 740.5 | -3.9 | 36.6 |
| inicio y en movimiento | 3904 | 331.4 | 224.9 | 721.2 | 9.7 | 34.9 |
| resto y detenido | 8396 | 262.2 | 159.8 | 575.2 | -16.7 | 30.7 |
| resto y en movimiento | 11245 | 278.7 | 161.8 | 614.6 | -24.4 | 31.6 |
| global | 26537 | 287.6 | 176.7 | 638.3 | -14.7 | 32.4 |
| global sin inicio de viaje | 19641 | 271.7 | 160.9 | 598.5 | -21.1 | 31.2 |

