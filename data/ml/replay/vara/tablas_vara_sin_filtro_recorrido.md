Días: 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18, 2026-09-19, 2026-09-20, 2026-10-03, 2026-10-04, 2026-10-06, 2026-10-08. Líneas: 26, 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168.

### Global

| métrica | anterior | corregida |
|---|---|---|
| Coches listados (los 5 mostrados) | 1933795 | 1933795 |
| Falsas alarmas %, todo ETA anunciado | 24.5 | 14.7 |
| Falsas alarmas %, ETA anunciado 3–7 min | 14.6 | 9.9 |
|   «viene» (seguro) % | 14.1 | 5.6 |
|   «puede venir» % | 59.7 | 46.6 |
|   «sentido sin confirmar» (provisional) % | 53.4 | 41.3 |
| Omisión ≤10 min % | 9.3 | 10.7 |
|   n coches que pasan en ≤10 min con ping vigente | 755260 | 800465 |
| «Viene» vacío % | 10.0 | 11.2 |
|   n instantes con paso ≤10 min | 353337 | 360740 |
| MAE próximo coche, banda 3–7 min (s) | 98 | 99 |
|   n instantes en la banda | 128566 | 130159 |
| Llega antes >60 s % (banda 3–7) | 14.4 | 15.6 |
| Llega después >60 s % (banda 3–7) | 26.4 | 25.5 |
| Sin anuncio % (banda 3–7) | 2.5 | 2.5 |
| MAE solo «viene», banda 3–7 (s) | 97 | 97 |
|   llega antes / después >60 s % (solo «viene») | 14.3 / 25.4 | 14.7 / 25.1 |

Lo que la vara corregida deja afuera o reclasifica (no es lo mismo que «falsa alarma resuelta»):

| concepto | n |
|---|---|
| listados con ETA anunciado > 40 min (fuera del horizonte; no entran en el denominador) | 93296 |
| listados «no verificables» (par de pings con hueco de 10–40 min que encierra la parada; no entran) | 19026 |
| listados que ya habían pasado entre su último ping y t (llega antes; no es falsa alarma, entran en el denominador) | 35664 |
| listados evaluados (denominador de la falsa alarma corregida) | 1821473 |
| instantes en la banda 3–7 min excluidos por paso previo no verificable | 1418 |
| instantes con paso ≤10 min excluidos del «viene» vacío por lo mismo | 4021 |

### Por línea

| línea | listados | falsas alarmas % ant → corr | FA 3–7 min % ant → corr | omisión % ant → corr | «viene» vacío % ant → corr | MAE 3–7 (s) ant → corr | llega antes % ant → corr | llega después % ant → corr |
|---|---|---|---|---|---|---|---|---|
| 26 | 42306 | 7.0 → 2.4 | 4.2 → 2.2 | 5.7 → 6.0 | 2.6 → 2.0 | 76 → 76 | 12.2 → 12.3 | 28.9 → 28.6 |
| 39 | 189045 | 31.5 → 23.6 | 18.9 → 13.6 | 7.0 → 8.7 | 23.2 → 24.6 | 88 → 88 | 10.8 → 12.6 | 29.3 → 27.9 |
| 42 | 176034 | 38.8 → 31.6 | 33.3 → 28.2 | 7.5 → 8.9 | 12.0 → 12.9 | 195 → 197 | 17.0 → 16.8 | 32.2 → 33.4 |
| 50 | 160942 | 32.3 → 23.0 | 15.7 → 11.8 | 5.7 → 6.7 | 14.4 → 14.1 | 79 → 78 | 15.9 → 16.4 | 23.0 → 22.8 |
| 92 | 187319 | 14.2 → 6.7 | 4.6 → 2.6 | 4.7 → 5.1 | 3.0 → 2.8 | 67 → 67 | 13.8 → 14.3 | 20.8 → 20.5 |
| 106 | 197402 | 22.4 → 13.8 | 13.9 → 10.7 | 15.1 → 16.2 | 5.6 → 5.4 | 155 → 148 | 14.8 → 14.9 | 30.4 → 29.6 |
| 107 | 131301 | 18.3 → 5.2 | 14.3 → 4.1 | 10.3 → 14.9 | 12.3 → 19.2 | 106 → 114 | 21.1 → 27.0 | 21.9 → 19.9 |
| 108 | 164417 | 24.5 → 11.5 | 11.9 → 8.3 | 6.6 → 7.2 | 3.8 → 3.6 | 75 → 75 | 13.9 → 13.9 | 23.7 → 23.8 |
| 124 | 165783 | 11.1 → 4.3 | 4.8 → 2.7 | 3.9 → 4.1 | 2.8 → 2.6 | 75 → 72 | 13.0 → 13.1 | 22.9 → 21.9 |
| 132 | 185838 | 25.0 → 13.5 | 18.4 → 11.2 | 13.0 → 15.7 | 16.0 → 17.7 | 84 → 88 | 11.2 → 14.8 | 31.1 → 27.8 |
| 151 | 157139 | 12.4 → 6.6 | 5.5 → 3.3 | 12.8 → 12.9 | 8.7 → 8.9 | 84 → 84 | 13.5 → 13.7 | 30.6 → 30.2 |
| 168 | 176269 | 40.8 → 22.3 | 18.1 → 9.1 | 7.0 → 8.9 | 10.1 → 14.2 | 95 → 96 | 16.3 → 17.7 | 23.0 → 22.1 |

### Falsa alarma por ETA anunciado

| ETA anunciado (min) | listados | FA anterior % | listados evaluados | FA corregida % | ya pasó % | no verificable % |
|---|---|---|---|---|---|---|
| 0-2 | 219376 | 31.5 | 213814 | 11.5 | 16.1 | 2.5 |
| 2-3 | 87048 | 11.4 | 86289 | 7.5 | 0.4 | 0.9 |
| 3-5 | 175560 | 13.2 | 174031 | 8.8 | 0.0 | 0.9 |
| 5-7 | 171784 | 16.0 | 170395 | 11.0 | 0.0 | 0.8 |
| 7-10 | 236004 | 18.9 | 233955 | 13.7 | 0.0 | 0.9 |
| 10-20 | 549361 | 19.4 | 544286 | 14.7 | 0.0 | 0.9 |
| 20-40 | 401366 | 26.4 | 398703 | 22.9 | 0.0 | 0.7 |
| >40 | 93296 | 93.5 | 0 | — | 0.0 | 0.0 |

### Qué le pasa a cada causa de FALSAS_ALARMAS

| causa (FALSAS_ALARMAS) | FA anteriores | fuera del horizonte | pasa (cruce firme) | no verificable | ya pasó | sigue falsa alarma | % que sale de las FA |
|---|---|---|---|---|---|---|---|
| X0 | 87276 | 87276 | 0 | 0 | 0 | 0 | 100 |
| X3 | 14131 | 0 | 10699 | 164 | 54 | 3214 | 77 |
| X2a | 21654 | 0 | 1 | 15064 | 0 | 6589 | 70 |
| X2b | 1844 | 0 | 438 | 9 | 7 | 1390 | 25 |
| X2c | 10101 | 0 | 3972 | 6 | 58 | 6065 | 40 |
| X2d | 19089 | 0 | 2470 | 103 | 2156 | 14360 | 25 |
| X1 | 21549 | 0 | 0 | 0 | 0 | 21549 | 0 |
| X4 | 9944 | 0 | 9106 | 25 | 6 | 807 | 92 |
| P | 33059 | 0 | 13 | 1 | 32942 | 103 | 100 |
| S | 23117 | 0 | 793 | 94 | 10 | 22220 | 4 |
| R1 | 152202 | 0 | 29661 | 100 | 122 | 122319 | 20 |
| T1 | 23448 | 0 | 52 | 48 | 13 | 23335 | 0 |
| T2 | 7687 | 0 | 2 | 21 | 0 | 7664 | 0 |
| C | 24232 | 0 | 23 | 22 | 0 | 24187 | 0 |
| G | 6458 | 0 | 349 | 3303 | 23 | 2783 | 57 |
| D | 14447 | 0 | 7416 | 64 | 99 | 6868 | 52 |
| O | 4047 | 0 | 1145 | 2 | 140 | 2760 | 32 |
| **total** | 474285 | 87276 | 66140 | 19026 | 35630 | 266213 | 43.9 |

(Filas de FALSAS_ALARMAS sin par en esta corrida: 0 de 474285.)
