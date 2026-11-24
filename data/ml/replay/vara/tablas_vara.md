Días: 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18, 2026-09-19, 2026-09-20, 2026-10-03, 2026-10-04, 2026-10-06, 2026-10-08. Líneas: 26, 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168.

### Global

| métrica | anterior | corregida |
|---|---|---|
| Coches listados (los 5 mostrados) | 1933795 | 1933795 |
| Falsas alarmas %, todo ETA anunciado | 24.5 | 17.1 |
| Falsas alarmas %, ETA anunciado 3–7 min | 14.6 | 12.7 |
|   «viene» (seguro) % | 14.1 | 5.7 |
|   «puede venir» % | 59.7 | 56.7 |
|   «sentido sin confirmar» (provisional) % | 53.4 | 48.8 |
| Omisión ≤10 min % | 9.3 | 9.5 |
|   n coches que pasan en ≤10 min con ping vigente | 755260 | 766262 |
| «Viene» vacío % | 10.0 | 9.8 |
|   n instantes con paso ≤10 min | 353337 | 353875 |
| MAE próximo coche, banda 3–7 min (s) | 98 | 97 |
|   n instantes en la banda | 128566 | 128757 |
| Llega antes >60 s % (banda 3–7) | 14.4 | 14.4 |
| Llega después >60 s % (banda 3–7) | 26.4 | 26.3 |
| Sin anuncio % (banda 3–7) | 2.5 | 2.3 |
| MAE solo «viene», banda 3–7 (s) | 97 | 96 |
|   llega antes / después >60 s % (solo «viene») | 14.3 / 25.4 | 14.5 / 25.1 |

Lo que la vara corregida deja afuera o reclasifica (no es lo mismo que «falsa alarma resuelta»):

| concepto | n |
|---|---|
| listados con ETA anunciado > 40 min (fuera del horizonte; no entran en el denominador) | 93296 |
| listados «no verificables» (par de pings con hueco de 10–40 min que encierra la parada; no entran) | 19856 |
| listados que ya habían pasado entre su último ping y t (llega antes; no es falsa alarma, entran en el denominador) | 35099 |
| listados evaluados (denominador de la falsa alarma corregida) | 1820643 |
| instantes en la banda 3–7 min excluidos por paso previo no verificable | 1467 |
| instantes con paso ≤10 min excluidos del «viene» vacío por lo mismo | 4044 |

### Por línea

| línea | listados | falsas alarmas % ant → corr | FA 3–7 min % ant → corr | omisión % ant → corr | «viene» vacío % ant → corr | MAE 3–7 (s) ant → corr | llega antes % ant → corr | llega después % ant → corr |
|---|---|---|---|---|---|---|---|---|
| 26 | 42306 | 7.0 → 2.6 | 4.2 → 2.4 | 5.7 → 5.9 | 2.6 → 2.0 | 76 → 76 | 12.2 → 12.3 | 28.9 → 28.7 |
| 39 | 189045 | 31.5 → 29.8 | 18.9 → 20.9 | 7.0 → 6.5 | 23.2 → 22.6 | 88 → 89 | 10.8 → 10.2 | 29.3 → 30.8 |
| 42 | 176034 | 38.8 → 32.2 | 33.3 → 28.9 | 7.5 → 8.6 | 12.0 → 12.5 | 195 → 190 | 17.0 → 16.7 | 32.2 → 33.2 |
| 50 | 160942 | 32.3 → 24.9 | 15.7 → 14.2 | 5.7 → 6.7 | 14.4 → 12.9 | 79 → 79 | 15.9 → 16.4 | 23.0 → 23.2 |
| 92 | 187319 | 14.2 → 6.7 | 4.6 → 2.7 | 4.7 → 4.9 | 3.0 → 2.8 | 67 → 67 | 13.8 → 14.2 | 20.8 → 20.5 |
| 106 | 197402 | 22.4 → 14.2 | 13.9 → 11.0 | 15.1 → 15.7 | 5.6 → 5.4 | 155 → 148 | 14.8 → 14.8 | 30.4 → 29.5 |
| 107 | 131301 | 18.3 → 9.0 | 14.3 → 12.3 | 10.3 → 10.4 | 12.3 → 11.9 | 106 → 106 | 21.1 → 21.0 | 21.9 → 22.0 |
| 108 | 164417 | 24.5 → 11.7 | 11.9 → 8.5 | 6.6 → 6.6 | 3.8 → 3.6 | 75 → 74 | 13.9 → 13.7 | 23.7 → 23.9 |
| 124 | 165783 | 11.1 → 4.3 | 4.8 → 2.7 | 3.9 → 4.0 | 2.8 → 2.6 | 75 → 72 | 13.0 → 13.0 | 22.9 → 21.9 |
| 132 | 185838 | 25.0 → 20.8 | 18.4 → 16.9 | 13.0 → 13.1 | 16.0 → 15.7 | 84 → 83 | 11.2 → 11.3 | 31.1 → 30.8 |
| 151 | 157139 | 12.4 → 7.5 | 5.5 → 4.2 | 12.8 → 12.8 | 8.7 → 7.9 | 84 → 83 | 13.5 → 13.6 | 30.6 → 30.1 |
| 168 | 176269 | 40.8 → 26.7 | 18.1 → 13.5 | 7.0 → 7.2 | 10.1 → 12.1 | 95 → 94 | 16.3 → 16.4 | 23.0 → 22.6 |

### Falsa alarma por ETA anunciado

| ETA anunciado (min) | listados | FA anterior % | listados evaluados | FA corregida % | ya pasó % | no verificable % |
|---|---|---|---|---|---|---|
| 0-2 | 219376 | 31.5 | 213180 | 12.9 | 15.8 | 2.8 |
| 2-3 | 87048 | 11.4 | 86267 | 9.2 | 0.3 | 0.9 |
| 3-5 | 175560 | 13.2 | 173972 | 11.2 | 0.0 | 0.9 |
| 5-7 | 171784 | 16.0 | 170377 | 14.2 | 0.0 | 0.8 |
| 7-10 | 236004 | 18.9 | 233948 | 17.0 | 0.0 | 0.9 |
| 10-20 | 549361 | 19.4 | 544262 | 17.2 | 0.0 | 0.9 |
| 20-40 | 401366 | 26.4 | 398637 | 24.5 | 0.0 | 0.7 |
| >40 | 93296 | 93.5 | 0 | — | 0.0 | 0.0 |

### Qué le pasa a cada causa de FALSAS_ALARMAS

| causa (FALSAS_ALARMAS) | FA anteriores | fuera del horizonte | pasa (cruce firme) | no verificable | ya pasó | sigue falsa alarma | % que sale de las FA |
|---|---|---|---|---|---|---|---|
| X0 | 87276 | 87276 | 0 | 0 | 0 | 0 | 100 |
| X3 | 14131 | 0 | 9230 | 625 | 45 | 4231 | 70 |
| X2a | 21654 | 0 | 0 | 14233 | 0 | 7421 | 66 |
| X2b | 1844 | 0 | 214 | 11 | 6 | 1613 | 13 |
| X2c | 10101 | 0 | 3772 | 63 | 49 | 6217 | 38 |
| X2d | 19089 | 0 | 305 | 120 | 2118 | 16546 | 13 |
| X1 | 21549 | 0 | 0 | 1 | 0 | 21548 | 0 |
| X4 | 9944 | 0 | 9093 | 31 | 6 | 814 | 92 |
| P | 33059 | 0 | 9 | 139 | 32583 | 328 | 99 |
| S | 23117 | 0 | 344 | 34 | 0 | 22739 | 2 |
| R1 | 152202 | 0 | 0 | 8 | 0 | 152194 | 0 |
| T1 | 23448 | 0 | 52 | 49 | 13 | 23334 | 0 |
| T2 | 7687 | 0 | 2 | 22 | 0 | 7663 | 0 |
| C | 24232 | 0 | 0 | 45 | 0 | 24187 | 0 |
| G | 6458 | 0 | 348 | 3304 | 23 | 2783 | 57 |
| D | 14447 | 0 | 7407 | 75 | 97 | 6868 | 52 |
| O | 4047 | 0 | 1137 | 20 | 130 | 2760 | 32 |
| **total** | 474285 | 87276 | 31913 | 18780 | 35070 | 301246 | 36.5 |

(Filas de FALSAS_ALARMAS sin par en esta corrida: 0 de 474285.)
