Días: 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18, 2026-09-19, 2026-09-20, 2026-10-03, 2026-10-04, 2026-10-06, 2026-10-08. Líneas: 26, 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168.

### Global

| métrica | anterior | corregida |
|---|---|---|
| Coches listados (los 5 mostrados) | 2093900 | 2093900 |
| Falsas alarmas %, todo ETA anunciado | 25.0 | 14.3 |
| Falsas alarmas %, ETA anunciado 3–7 min | 14.6 | 9.4 |
|   «viene» (seguro) % | 14.3 | 5.6 |
|   «puede venir» % | 60.0 | 43.7 |
|   «sentido sin confirmar» (provisional) % | 53.1 | 39.8 |
| Omisión ≤10 min % | 9.1 | 11.1 |
|   n coches que pasan en ≤10 min con ping vigente | 795776 | 854352 |
| «Viene» vacío % | 10.2 | 11.8 |
|   n instantes con paso ≤10 min | 382125 | 392204 |
| MAE próximo coche, banda 3–7 min (s) | 97 | 98 |
|   n instantes en la banda | 140275 | 142405 |
| Llega antes >60 s % (banda 3–7) | 14.3 | 15.8 |
| Llega después >60 s % (banda 3–7) | 25.7 | 24.8 |
| Sin anuncio % (banda 3–7) | 2.6 | 2.5 |
| MAE solo «viene», banda 3–7 (s) | 96 | 96 |
|   llega antes / después >60 s % (solo «viene») | 14.3 / 24.7 | 14.8 / 24.4 |

Lo que la vara corregida deja afuera o reclasifica (no es lo mismo que «falsa alarma resuelta»):

| concepto | n |
|---|---|
| listados con ETA anunciado > 40 min (fuera del horizonte; no entran en el denominador) | 114185 |
| listados «no verificables» (par de pings con hueco de 10–40 min que encierra la parada; no entran) | 19384 |
| listados que ya habían pasado entre su último ping y t (llega antes; no es falsa alarma, entran en el denominador) | 37100 |
| listados evaluados (denominador de la falsa alarma corregida) | 1960331 |
| instantes en la banda 3–7 min excluidos por paso previo no verificable | 1499 |
| instantes con paso ≤10 min excluidos del «viene» vacío por lo mismo | 4230 |
| coches que pasan ≤10 min solo por un shape no asociado por nombre a la parada (omisiones que la app no puede evitar) | 10933 |
| omisión ≤10 min % sin esos coches | 10.5 |

### Por línea

| línea | listados | falsas alarmas % ant → corr | FA 3–7 min % ant → corr | omisión % ant → corr | «viene» vacío % ant → corr | MAE 3–7 (s) ant → corr | llega antes % ant → corr | llega después % ant → corr |
|---|---|---|---|---|---|---|---|---|
| 26 | 42306 | 7.0 → 2.4 | 4.2 → 2.2 | 5.7 → 6.0 | 2.6 → 2.0 | 76 → 76 | 12.2 → 12.3 | 28.9 → 28.6 |
| 39 | 206472 | 31.2 → 23.3 | 18.7 → 13.5 | 6.8 → 9.2 | 23.3 → 24.9 | 86 → 87 | 10.8 → 13.0 | 28.7 → 27.4 |
| 42 | 191481 | 39.6 → 31.6 | 34.4 → 28.5 | 7.9 → 9.3 | 12.1 → 13.9 | 193 → 192 | 16.7 → 16.4 | 32.2 → 33.4 |
| 50 | 173496 | 33.0 → 22.5 | 15.8 → 10.9 | 5.5 → 7.4 | 14.5 → 14.5 | 77 → 78 | 15.9 → 16.9 | 22.4 → 21.8 |
| 92 | 204777 | 14.6 → 6.6 | 4.4 → 2.5 | 4.6 → 5.0 | 3.1 → 2.9 | 66 → 66 | 13.5 → 14.0 | 20.1 → 19.8 |
| 106 | 216381 | 22.9 → 14.2 | 14.0 → 10.8 | 14.5 → 16.7 | 5.9 → 5.7 | 153 → 148 | 14.8 → 15.2 | 29.4 → 28.6 |
| 107 | 140621 | 18.9 → 5.3 | 14.2 → 4.0 | 10.2 → 14.8 | 12.2 → 19.5 | 105 → 113 | 20.9 → 27.0 | 21.5 → 19.4 |
| 108 | 176705 | 25.2 → 11.3 | 11.5 → 8.1 | 6.5 → 7.1 | 4.1 → 3.8 | 73 → 73 | 13.7 → 13.7 | 23.1 → 23.2 |
| 124 | 178992 | 11.3 → 4.3 | 4.6 → 2.5 | 3.9 → 4.1 | 2.9 → 2.8 | 73 → 70 | 13.1 → 13.2 | 22.0 → 21.1 |
| 132 | 203074 | 24.9 → 10.4 | 18.4 → 8.8 | 12.6 → 16.7 | 16.6 → 20.3 | 81 → 87 | 11.4 → 15.6 | 29.8 → 26.3 |
| 151 | 168301 | 12.7 → 5.1 | 5.4 → 1.8 | 12.7 → 13.0 | 9.0 → 9.6 | 83 → 82 | 13.7 → 14.1 | 30.0 → 29.1 |
| 168 | 191294 | 41.9 → 22.3 | 18.1 → 9.1 | 7.0 → 8.9 | 10.3 → 14.5 | 93 → 95 | 16.3 → 17.7 | 22.5 → 21.8 |

### Falsa alarma por ETA anunciado

| ETA anunciado (min) | listados | FA anterior % | listados evaluados | FA corregida % | ya pasó % | no verificable % |
|---|---|---|---|---|---|---|
| 0-2 | 231263 | 31.5 | 225613 | 11.4 | 15.9 | 2.4 |
| 2-3 | 91750 | 11.4 | 90977 | 7.0 | 0.3 | 0.8 |
| 3-5 | 185185 | 13.2 | 183643 | 8.2 | 0.0 | 0.8 |
| 5-7 | 181933 | 16.1 | 180525 | 10.5 | 0.0 | 0.8 |
| 7-10 | 250258 | 19.1 | 248169 | 13.2 | 0.0 | 0.8 |
| 10-20 | 590090 | 19.3 | 584923 | 13.9 | 0.0 | 0.9 |
| 20-40 | 449236 | 26.2 | 446481 | 22.3 | 0.0 | 0.6 |
| >40 | 114185 | 93.7 | 0 | — | 0.0 | 0.0 |

### Qué le pasa a cada causa de FALSAS_ALARMAS

| causa (FALSAS_ALARMAS) | FA anteriores | fuera del horizonte | pasa (cruce firme) | no verificable | ya pasó | sigue falsa alarma | % que sale de las FA |
|---|---|---|---|---|---|---|---|
| X0 | 106944 | 106944 | 0 | 0 | 0 | 0 | 100 |
| X3 | 15107 | 0 | 11613 | 191 | 58 | 3245 | 79 |
| X2a | 21825 | 0 | 1 | 15209 | 0 | 6615 | 70 |
| X2b | 1929 | 0 | 446 | 9 | 7 | 1467 | 24 |
| X2c | 10730 | 0 | 6041 | 7 | 59 | 4623 | 57 |
| X2d | 20657 | 0 | 11810 | 103 | 2255 | 6489 | 69 |
| X1 | 24466 | 0 | 1 | 0 | 0 | 24465 | 0 |
| X4 | 10132 | 0 | 9283 | 25 | 7 | 817 | 92 |
| P | 34230 | 0 | 14 | 1 | 34094 | 121 | 100 |
| S | 24708 | 0 | 861 | 96 | 21 | 23730 | 4 |
| R1 | 166411 | 0 | 33159 | 240 | 285 | 132727 | 20 |
| T1 | 24273 | 0 | 52 | 48 | 13 | 24160 | 0 |
| T2 | 8154 | 0 | 3 | 32 | 0 | 8119 | 0 |
| C | 28046 | 0 | 23 | 34 | 0 | 27989 | 0 |
| G | 6542 | 0 | 351 | 3318 | 24 | 2849 | 56 |
| D | 15010 | 0 | 7674 | 69 | 99 | 7168 | 52 |
| O | 4239 | 0 | 1173 | 2 | 143 | 2921 | 31 |
| **total** | 523403 | 106944 | 82505 | 19384 | 37065 | 277505 | 47.0 |

(Filas de FALSAS_ALARMAS sin par en esta corrida: 0 de 523403.)
