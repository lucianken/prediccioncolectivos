### path:data/ml/v2_sub/conf/path_lr2e-3_s0/path_eta_best.pt sobre eval_heldout (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 198.7 | 94.5 | 408.8 | -37.6 | 44.9 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 52.2 | 38.0 | 110.3 | 20.2 | 9.6 |
| 5-10 min | 7500 | 106.3 | 79.1 | 216.6 | -26.2 | 42.1 |
| 10-20 min | 7500 | 174.9 | 128.8 | 340.7 | -63.6 | 56.4 |
| 20+ min | 7500 | 461.2 | 269.6 | 831.4 | -81.0 | 71.6 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 4083 | 69.1 | 34.5 | 113.2 | -21.7 | 14.2 |
| 0,5-2 km | 11740 | 102.0 | 70.3 | 217.8 | -49.7 | 39.2 |
| 2-5 km | 7879 | 170.6 | 128.2 | 364.4 | -80.6 | 53.8 |
| 5+ km | 6298 | 498.1 | 276.2 | 990.0 | 28.3 | 64.3 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3551 | 250.8 | 164.3 | 541.8 | -167.1 | 65.7 |
| resto del viaje | 26449 | 191.7 | 88.6 | 382.6 | -20.3 | 42.1 |
| P detenido | 12817 | 185.0 | 94.7 | 390.3 | -62.2 | 46.8 |
| P en movimiento | 17183 | 208.9 | 94.2 | 425.5 | -19.3 | 43.6 |
| inicio y detenido | 1589 | 255.1 | 168.3 | 538.8 | -152.9 | 64.9 |
| inicio y en movimiento | 1962 | 247.4 | 161.2 | 544.6 | -178.6 | 66.4 |
| resto y detenido | 11228 | 175.0 | 88.6 | 363.6 | -49.4 | 44.2 |
| resto y en movimiento | 15221 | 203.9 | 88.7 | 399.5 | 1.2 | 40.6 |
| global | 30000 | 198.7 | 94.5 | 408.8 | -37.6 | 44.9 |
| global sin inicio de viaje | 26449 | 191.7 | 88.6 | 382.6 | -20.3 | 42.1 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 6380 | 259.6 | 102.2 | 500.8 | 86.6 | 33.4 |
| inicio conocido | 23620 | 182.2 | 92.2 | 391.9 | -71.2 | 48.0 |

