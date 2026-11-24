### a3:data/ml/v2_sub/conf/a3_lr1e-3_s1/eta_a3_best.pt sobre eval_heldout (n=30000)

**Global (informativo, no decide)**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| global | 30000 | 276.9 | 159.6 | 609.8 | -18.1 | 30.2 |

**Por ETA real**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| 0-5 min | 7500 | 77.6 | 60.4 | 164.7 | 47.9 | 9.6 |
| 5-10 min | 7500 | 160.1 | 135.7 | 323.7 | 40.6 | 30.1 |
| 10-20 min | 7500 | 289.6 | 252.9 | 578.7 | 53.1 | 34.1 |
| 20+ min | 7500 | 580.4 | 393.5 | 1255.6 | -214.1 | 46.8 |

**Por distancia restante**

| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| <500 m | 4083 | 83.5 | 50.7 | 145.2 | 3.3 | 11.8 |
| 0,5-2 km | 11740 | 143.5 | 111.8 | 294.1 | 28.2 | 26.0 |
| 2-5 km | 7879 | 307.6 | 272.2 | 596.0 | 66.5 | 32.2 |
| 5+ km | 6298 | 612.7 | 425.3 | 1349.6 | -224.2 | 47.3 |


**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)

| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio de viaje | 3551 | 342.0 | 224.2 | 751.3 | 21.6 | 30.8 |
| resto del viaje | 26449 | 268.2 | 153.2 | 585.6 | -23.5 | 30.1 |
| P detenido | 12817 | 270.4 | 158.2 | 601.0 | -17.3 | 30.4 |
| P en movimiento | 17183 | 281.8 | 160.6 | 615.2 | -18.8 | 30.0 |
| inicio y detenido | 1589 | 329.5 | 208.8 | 718.8 | -13.6 | 33.1 |
| inicio y en movimiento | 1962 | 352.2 | 237.7 | 777.1 | 50.1 | 29.0 |
| resto y detenido | 11228 | 262.1 | 152.8 | 581.7 | -17.8 | 30.0 |
| resto y en movimiento | 15221 | 272.7 | 153.4 | 588.6 | -27.7 | 30.1 |
| global | 30000 | 276.9 | 159.6 | 609.8 | -18.1 | 30.2 |
| global sin inicio de viaje | 26449 | 268.2 | 153.2 | 585.6 | -23.5 | 30.1 |

**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)

| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) |
|---|---:|---:|---:|---:|---:|---:|
| inicio desconocido | 6380 | 373.4 | 202.8 | 852.7 | -189.3 | 48.8 |
| inicio conocido | 23620 | 250.9 | 150.1 | 557.0 | 28.1 | 25.1 |

