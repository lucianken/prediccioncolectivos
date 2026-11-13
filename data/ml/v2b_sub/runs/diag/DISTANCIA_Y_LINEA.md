# Distancia y línea: ¿explican la brecha seen vs heldout?

Modelos v2b ya entrenados (sin reentrenar). Eval `data/ml/v2b/eval`: 30.000 filas por conjunto, seen = 12 líneas de train, heldout = 12, 15, 128. Predicciones por fila en `runs/eval2/*/*.pred.npy` (tablas completas por modelo en `runs/eval2/*/*.md`). Generado por `prediccion/scripts/diag_distancia_linea.py`.

## Conclusión

1. **La distancia no explica la brecha.** Las distribuciones de distancia y de ETA real de seen y heldout son casi iguales (el eval balancea 25 % por bucket de ETA; en distancia solo difiere la cola de 12+ km: 5,4 % vs 2,6 %). Re-ponderar seen a la distribución de heldout casi no mueve el MAE: A3 107-109 → 102-109, por tramos 103 → 98-105, mientras heldout sigue en 206-277 (A1 455). Ni por distancia fina ni por distancia × ETA.
2. **La brecha es de línea, y sobre todo de la 15.** MAE heldout por línea (A3 / por tramos): 12 = 203 / 140, 128 = 232 / 160, 15 = 453 / 421. En 5+ km la 15 llega a ~1200-1290 s contra 280-400 s de la 12 y la 128. Pero la 15 sola no explica todo: sin ella, 5+ km heldout sigue en 297-370 s contra 177-190 s de seen, y 2-5 km en 156-284 contra 103-107. Las 12 y 128 también son peores que cualquier línea seen a igual distancia.
3. **El patrón es del modelo, no solo de las líneas.** A3 es peor que por tramos en las líneas no vistas (12: 203 vs 140) y sobreestima mucho (0-5 min: pred − real > 60 s en 40-43 % de filas heldout contra 22 % en seen; por tramos 21 % contra 17-18 %). A1 es lo opuesto: subestima (50 % en 0-5 min heldout). Las líneas problemáticas lo son para todos los modelos (la 15 es la peor en los cuatro), lo que sugiere un componente de la línea (recorrido/segmentación/datos) además de la generalización.

## 1. Sobreestimación y subestimación por modelo

Tablas completas (por ETA, distancia, distancia fina, línea, fase) en `runs/eval2/<modelo>/*.md`. Resumen (sobreest. = pred − real > 60 s; subest. = real − pred > 60 s):

**ETA real 0-5 min**

| modelo | n seen | MAE seen | sobreest. seen % | subest. seen % | n held | MAE held | sobreest. held % | subest. held % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A3 s0 | 7500 | 45 | 22.5 | 3.4 | 7500 | 81 | 42.6 | 9.0 |
| A3 s1 | 7500 | 45 | 22.3 | 3.3 | 7500 | 78 | 40.1 | 9.0 |
| Por tramos s0 | 7500 | 40 | 17.4 | 4.4 | 7500 | 53 | 20.9 | 9.5 |
| Por tramos s1 | 7500 | 41 | 18.1 | 4.4 | 7500 | 56 | 21.9 | 9.8 |
| A1 | 7500 | 40 | 9.6 | 12.1 | 7500 | 73 | 1.8 | 50.6 |

**distancia < 1 km**

| modelo | n seen | MAE seen | sobreest. seen % | subest. seen % | n held | MAE held | sobreest. held % | subest. held % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A3 s0 | 8491 | 66 | 17.8 | 14.6 | 9057 | 97 | 37.2 | 16.4 |
| A3 s1 | 8491 | 65 | 17.9 | 14.1 | 9057 | 94 | 34.8 | 16.6 |
| Por tramos s0 | 8491 | 63 | 13.6 | 15.7 | 9057 | 77 | 14.0 | 24.1 |
| Por tramos s1 | 8491 | 63 | 14.4 | 15.2 | 9057 | 79 | 15.0 | 24.5 |
| A1 | 8491 | 71 | 5.2 | 26.8 | 9057 | 138 | 0.2 | 64.7 |

**global**

| modelo | n seen | MAE seen | sobreest. seen % | subest. seen % | n held | MAE held | sobreest. held % | subest. held % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A3 s0 | 30000 | 109 | 26.3 | 26.7 | 30000 | 277 | 48.9 | 28.1 |
| A3 s1 | 30000 | 107 | 27.0 | 25.4 | 30000 | 268 | 48.3 | 27.5 |
| Por tramos s0 | 30000 | 103 | 22.8 | 27.7 | 30000 | 206 | 18.0 | 45.4 |
| Por tramos s1 | 30000 | 103 | 23.7 | 26.8 | 30000 | 225 | 18.5 | 46.4 |
| A1 | 30000 | 116 | 21.7 | 32.3 | 30000 | 455 | 2.5 | 84.3 |

## 2. Distribuciones de distancia y de ETA real (% de filas)

| distancia | seen % | heldout % |
|---|---:|---:|
| 0-0,5 km | 12.9 | 13.6 |
| 0,5-1 km | 15.4 | 16.6 |
| 1-2 km | 21.0 | 22.6 |
| 2-3 km | 10.4 | 10.1 |
| 3-5 km | 17.5 | 16.1 |
| 5-8 km | 10.0 | 11.9 |
| 8-12 km | 7.3 | 6.4 |
| 12+ km | 5.4 | 2.6 |

| ETA real | seen % | heldout % |
|---|---:|---:|
| 0-5 min | 25.0 | 25.0 |
| 5-10 min | 25.0 | 25.0 |
| 10-20 min | 25.0 | 25.0 |
| 20+ min | 25.0 | 25.0 |

Por línea (% de filas de la línea por distancia fina; mediana de distancia y de ETA real):

| conjunto | línea | n | 0-0,5 km | 0,5-1 km | 1-2 km | 2-3 km | 3-5 km | 5-8 km | 8-12 km | 12+ km | med dist km | med ETA min |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| seen | 26 | 307 | 13 | 17 | 24 | 6 | 18 | 13 | 8 | 1 | 1.81 | 10.0 |
| seen | 39 | 3947 | 13 | 15 | 22 | 11 | 16 | 12 | 8 | 3 | 2.00 | 10.0 |
| seen | 42 | 1899 | 13 | 16 | 21 | 11 | 18 | 9 | 7 | 6 | 2.05 | 10.0 |
| seen | 50 | 2113 | 13 | 14 | 20 | 11 | 19 | 8 | 8 | 7 | 2.33 | 9.5 |
| seen | 92 | 2774 | 13 | 15 | 20 | 12 | 18 | 8 | 6 | 8 | 2.25 | 8.9 |
| seen | 106 | 4604 | 14 | 16 | 20 | 10 | 18 | 9 | 7 | 6 | 2.09 | 9.0 |
| seen | 107 | 1781 | 14 | 17 | 21 | 9 | 16 | 10 | 7 | 6 | 1.93 | 9.5 |
| seen | 108 | 1654 | 13 | 15 | 19 | 10 | 20 | 8 | 6 | 9 | 2.39 | 10.0 |
| seen | 124 | 1653 | 13 | 15 | 21 | 9 | 17 | 8 | 8 | 8 | 2.08 | 11.0 |
| seen | 132 | 4234 | 13 | 15 | 22 | 11 | 17 | 13 | 8 | 2 | 1.99 | 10.1 |
| seen | 151 | 3015 | 12 | 17 | 22 | 10 | 17 | 11 | 7 | 4 | 2.00 | 11.0 |
| seen | 168 | 2019 | 13 | 16 | 21 | 9 | 18 | 8 | 8 | 7 | 2.03 | 10.0 |
| heldout | 12 | 15053 | 14 | 17 | 23 | 11 | 15 | 14 | 6 | 0 | 1.84 | 10.1 |
| heldout | 15 | 7488 | 14 | 15 | 21 | 9 | 18 | 8 | 6 | 9 | 1.99 | 8.4 |
| heldout | 128 | 7459 | 13 | 17 | 23 | 10 | 16 | 13 | 7 | 1 | 1.88 | 10.1 |

## 3. Seen re-ponderado a la distribución de heldout

Peso de cada fila seen = P_heldout(celda) / P_seen(celda). (a) celda = bin de distancia fino (8); (b) celda = distancia fina × bucket de ETA (32). Las celdas con heldout > 0 y seen = 0 no se pueden cubrir: se informa la masa de heldout sin cobertura y el MAE de heldout se calcula solo sobre las celdas cubiertas, para comparar igual con igual.

| modelo | MAE seen | MAE heldout | (a) seen repond. dist | heldout cubierto | sin cubrir % | (b) seen repond. dist×ETA | heldout cubierto | sin cubrir % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A3 s0 | 109 | 277 | 104 | 277 | 0.0 | 109 | 277 | 0.0 |
| A3 s1 | 107 | 268 | 102 | 268 | 0.0 | 107 | 268 | 0.0 |
| Por tramos s0 | 103 | 206 | 98 | 206 | 0.0 | 104 | 206 | 0.0 |
| Por tramos s1 | 103 | 225 | 99 | 225 | 0.0 | 105 | 225 | 0.0 |
| A1 | 116 | 455 | 110 | 455 | 0.0 | 118 | 455 | 0.0 |

Seen re-ponderado a la distribución de distancia fina de **cada línea heldout** por separado:

| familia | línea heldout | n | seen repond. | heldout de la línea | brecha |
|---|---:|---:|---:|---:|---:|
| A3 (media de 2 semillas) | 12 | 15053 | 100 | 203 | 103 |
| A3 (media de 2 semillas) | 15 | 7488 | 111 | 453 | 342 |
| A3 (media de 2 semillas) | 128 | 7459 | 102 | 232 | 130 |
| Por tramos (media de 2 semillas) | 12 | 15053 | 96 | 140 | 45 |
| Por tramos (media de 2 semillas) | 15 | 7488 | 105 | 421 | 315 |
| Por tramos (media de 2 semillas) | 128 | 7459 | 97 | 160 | 63 |

## 4. MAE por línea y por línea × distancia

### A3 (media de 2 semillas)

| conjunto | línea | n | MAE | <0,5 km (n) | 0,5-2 km (n) | 2-5 km (n) | 5+ km (n) |
|---|---:|---:|---:|---:|---:|---:|---:|
| seen | 26 | 307 | 122 | 73 (40) | 85 (128) | 140 (74) | 204 (65) |
| seen | 39 | 3947 | 93 | 44 (523) | 64 (1451) | 94 (1079) | 170 (894) |
| seen | 42 | 1899 | 142 | 106 (239) | 118 (699) | 129 (549) | 221 (412) |
| seen | 50 | 2113 | 100 | 44 (265) | 73 (720) | 94 (635) | 175 (493) |
| seen | 92 | 2774 | 117 | 79 (363) | 80 (955) | 114 (835) | 200 (621) |
| seen | 106 | 4604 | 90 | 44 (627) | 62 (1627) | 90 (1291) | 159 (1059) |
| seen | 107 | 1781 | 112 | 59 (243) | 74 (679) | 108 (455) | 212 (404) |
| seen | 108 | 1654 | 123 | 59 (214) | 88 (553) | 107 (489) | 227 (398) |
| seen | 124 | 1653 | 94 | 49 (210) | 64 (607) | 96 (439) | 162 (397) |
| seen | 132 | 4234 | 107 | 65 (540) | 73 (1591) | 113 (1174) | 182 (929) |
| seen | 151 | 3015 | 125 | 69 (357) | 82 (1155) | 128 (815) | 225 (688) |
| seen | 168 | 2019 | 112 | 60 (260) | 72 (745) | 111 (550) | 208 (464) |
| heldout | 12 | 15053 | 203 | 71 (2092) | 127 (6027) | 272 (3893) | 356 (3041) |
| heldout | 15 | 7488 | 453 | 121 (1038) | 169 (2721) | 378 (2029) | 1198 (1700) |
| heldout | 128 | 7459 | 232 | 69 (953) | 148 (2992) | 309 (1957) | 397 (1557) |

¿La 15 sola explica la cola? Heldout con y sin la 15 (seen de referencia):

| distancia | n heldout | MAE heldout | n (15) | MAE (15) | n (12+128) | MAE (12+128) | MAE seen |
|---|---:|---:|---:|---:|---:|---:|---:|
| <0,5 km | 4083 | 83 | 1038 | 121 | 3045 | 70 | 60 |
| 0,5-2 km | 11740 | 142 | 2721 | 169 | 9019 | 134 | 75 |
| 2-5 km | 7879 | 308 | 2029 | 378 | 5850 | 284 | 107 |
| 5+ km | 6298 | 594 | 1700 | 1198 | 4598 | 370 | 190 |

### Por tramos (media de 2 semillas)

| conjunto | línea | n | MAE | <0,5 km (n) | 0,5-2 km (n) | 2-5 km (n) | 5+ km (n) |
|---|---:|---:|---:|---:|---:|---:|---:|
| seen | 26 | 307 | 115 | 69 (40) | 83 (128) | 126 (74) | 196 (65) |
| seen | 39 | 3947 | 90 | 42 (523) | 61 (1451) | 92 (1079) | 163 (894) |
| seen | 42 | 1899 | 138 | 106 (239) | 117 (699) | 129 (549) | 204 (412) |
| seen | 50 | 2113 | 94 | 42 (265) | 70 (720) | 91 (635) | 163 (493) |
| seen | 92 | 2774 | 115 | 74 (363) | 80 (955) | 113 (835) | 194 (621) |
| seen | 106 | 4604 | 84 | 41 (627) | 60 (1627) | 87 (1291) | 145 (1059) |
| seen | 107 | 1781 | 106 | 58 (243) | 72 (679) | 105 (455) | 193 (404) |
| seen | 108 | 1654 | 122 | 55 (214) | 85 (553) | 103 (489) | 233 (398) |
| seen | 124 | 1653 | 85 | 46 (210) | 61 (607) | 89 (439) | 138 (397) |
| seen | 132 | 4234 | 103 | 61 (540) | 72 (1591) | 109 (1174) | 171 (929) |
| seen | 151 | 3015 | 119 | 63 (357) | 80 (1155) | 121 (815) | 212 (688) |
| seen | 168 | 2019 | 103 | 57 (260) | 70 (745) | 103 (550) | 181 (464) |
| heldout | 12 | 15053 | 140 | 54 (2092) | 93 (6027) | 149 (3893) | 281 (3041) |
| heldout | 15 | 7488 | 421 | 112 (1038) | 123 (2721) | 248 (2029) | 1291 (1700) |
| heldout | 128 | 7459 | 160 | 52 (953) | 102 (2992) | 170 (1957) | 328 (1557) |

¿La 15 sola explica la cola? Heldout con y sin la 15 (seen de referencia):

| distancia | n heldout | MAE heldout | n (15) | MAE (15) | n (12+128) | MAE (12+128) | MAE seen |
|---|---:|---:|---:|---:|---:|---:|---:|
| <0,5 km | 4083 | 68 | 1038 | 112 | 3045 | 54 | 56 |
| 0,5-2 km | 11740 | 102 | 2721 | 123 | 9019 | 96 | 73 |
| 2-5 km | 7879 | 180 | 2029 | 248 | 5850 | 156 | 103 |
| 5+ km | 6298 | 565 | 1700 | 1291 | 4598 | 297 | 177 |

### MAE por bucket de ETA real y línea (media de los 4 modelos A3 y por tramos)

| conjunto | línea | 0-5 min (n) | 5-10 (n) | 10-20 (n) | 20+ (n) |
|---|---:|---:|---:|---:|---:|
| seen | 26 | 53 (72) | 71 (80) | 142 (68) | 198 (87) |
| seen | 39 | 39 (1011) | 58 (960) | 96 (974) | 173 (1002) |
| seen | 42 | 50 (455) | 84 (483) | 147 (492) | 280 (469) |
| seen | 50 | 37 (574) | 65 (503) | 102 (564) | 197 (472) |
| seen | 92 | 43 (748) | 75 (752) | 124 (664) | 247 (610) |
| seen | 106 | 39 (1275) | 63 (1138) | 97 (1163) | 162 (1028) |
| seen | 107 | 45 (470) | 75 (441) | 118 (437) | 204 (433) |
| seen | 108 | 38 (422) | 80 (407) | 134 (423) | 242 (402) |
| seen | 124 | 43 (374) | 62 (401) | 87 (410) | 153 (468) |
| seen | 132 | 46 (957) | 69 (1089) | 114 (1091) | 182 (1097) |
| seen | 151 | 49 (619) | 76 (766) | 125 (745) | 212 (885) |
| seen | 168 | 44 (523) | 66 (480) | 108 (469) | 203 (547) |
| heldout | 12 | 63 (3554) | 114 (3740) | 189 (3866) | 308 (3893) |
| heldout | 15 | 73 (2230) | 183 (1873) | 362 (1745) | 1300 (1640) |
| heldout | 128 | 68 (1716) | 128 (1887) | 222 (1889) | 349 (1967) |
