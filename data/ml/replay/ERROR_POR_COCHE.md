# Error del ETA por coche en el replay (vara corregida, regla de sentido de racha final)

Medido el 2026-11-16 sobre resultados ya existentes del replay (sin volver a predecir ni entrenar). Código: `data/ml/replay/porcoche/calcula.py` (cálculo) y `genera_md.py` (este documento); salidas intermedias en `data/ml/replay/porcoche/` (`filas.parquet`, `instantes.parquet`, `resumen.json`).

## Datos y verdad

- Crudos: `data/ml/replay/vara/run_base_sg` (9 días) + `run_cs_sg` (3-oct, variante `base`), modelo `path_v3_l1_s1`, regla de sentido `trailing_run`, 12 líneas, 40 paradas por línea, instantes cada 10 min de 6 a 23 h; los 10 días de `VARA_CORREGIDA.md` (15-20 sep., 3, 4, 6, 8 oct.). Lo duplicado cuenta una vez. Los crudos traen todo lo pedido salvo la edad del ping y la cantidad de pings de historial: se leen de los pings grabados (solo timestamps), con la regla de `core.evaluate_line` (último ping ≤ t; historial = pings en [t − 15 min, t] incluido el actual).
- **Verdad: la actual (`tp2_s`), que cuenta como paso a coches cuyo recorrido real no tiene la parada (≈ 4 % de los pasos ≤ 10 min, ver `VARA_CORREGIDA.md`).** Otro agente está cambiando la verdad (paso solo si el recorrido ex post del coche tiene la parada): re-correr `python data/ml/replay/porcoche/calcula.py --runs <crudos nuevos> ` y `python data/ml/replay/porcoche/genera_md.py` (las cifras de este documento cambian; ver Re-corrida). Con la verdad actual la reproducción del replay es exacta: 130 159 instantes en la banda 3-7 min, MAE próximo coche 97.0 s, llega antes 14.4 %, llega después 26.3 % (iguales a `VARA_CORREGIDA.md`).
- **Error por coche** = ETA anunciado (`eta0_s`, hora común) − tiempo real hasta SU propio paso firme (`tp2_s`). Positivo = el coche llega antes de lo anunciado; negativo = llega después. Se evalúa cada (parada, t, coche listado entre los 5 mostrados) que cruza la parada en ≤ 40 min con paso firme: 1481138 coches. Excluye los listados sin paso firme (bondi fantasma, ya pasó, no verificable).
- **Banda** = tiempo real hasta el paso del propio coche (0-3, 3-7, 7-15 min). Condicionar por el tiempo real produce sesgo por selección (en la banda cercana el ETA tiende a ser tardío y en la lejana temprano): el sesgo por banda no es un sesgo del modelo.
- **Posición** = orden de pantalla (Viene por ETA, luego Puede venir y Sentido sin confirmar por ETA). **Dispersión**: cada celda es la media de los días ± desvío día a día (días con ≥ 20 coches en la celda; entre paréntesis, cuántos días cuando son menos de 8); P90 = percentil 90 del error absoluto, media de los días.


## Resultado principal: banda de tiempo real 3-7 min

| corte | n coches | MAE (s) | P90 error abs. (s) | llega antes > 60 s % | llega después > 60 s % | sesgo (s; + = llega antes) |
|---|---|---|---|---|---|---|
| **Todos los listados** | 279 873 | 54 ± 5 | 114 ± 11 | 19.2 ± 2.0 | 15.5 ± 2.8 | 5 ± 3 |
| *Grupo de la app* | | | | | | |
| Viene | 255 421 | 54 ± 5 | 114 ± 11 | 19.1 ± 2.0 | 15.4 ± 2.9 | 5 ± 3 |
| Puede venir | 22 903 | 57 ± 6 | 120 ± 13 | 19.7 ± 1.7 | 16.8 ± 3.1 | 2 ± 4 |
| Sentido sin confirmar | 1 549 | 82 ± 9 | 184 ± 28 | 29.9 ± 7.8 | 18.8 ± 4.9 | 13 ± 19 |
| *Posición en la lista* | | | | | | |
| 1.º | 106 835 | 51 ± 4 | 106 ± 9 | 12.8 ± 1.2 | 19.2 ± 4.4 | -10 ± 6 |
| 2.º-5.º | 173 038 | 57 ± 4 | 121 ± 10 | 23.6 ± 1.5 | 13.1 ± 3.0 | 14 ± 4 |
| *Grupo × posición* | | | | | | |
| Viene, 1.º | 98 831 | 51 ± 4 | 105 ± 9 | 12.6 ± 1.2 | 19.1 ± 4.5 | -10 ± 7 |
| Viene, 2.º-5.º | 156 590 | 57 ± 4 | 120 ± 10 | 23.7 ± 1.6 | 12.8 ± 3.2 | 15 ± 4 |
| Puede venir, 1.º | 7 647 | 53 ± 5 | 111 ± 12 | 14.3 ± 2.0 | 19.6 ± 5.1 | -9 ± 8 |
| Puede venir, 2.º-5.º | 15 256 | 59 ± 5 | 125 ± 10 | 22.7 ± 1.7 | 15.5 ± 3.1 | 8 ± 4 |
| Sentido sin confirmar, 1.º | 357 | 80 ± 13 | 183 ± 39 | 20.0 ± 5.6 | 25.4 ± 6.8 | -11 ± 18 |
| Sentido sin confirmar, 2.º-5.º | 1 192 | 83 ± 12 | 181 ± 46 | 33.1 ± 9.0 | 16.5 ± 6.9 | 22 ± 24 |
| *Edad del ping en la consulta* | | | | | | |
| 0-30 s | 209 622 | 52 ± 4 | 109 ± 9 | 18.1 ± 1.8 | 14.9 ± 2.7 | 4 ± 3 |
| 30-60 s | 29 809 | 56 ± 6 | 117 ± 12 | 20.1 ± 2.5 | 15.9 ± 3.3 | 6 ± 4 |
| 60-120 s | 30 014 | 60 ± 5 | 126 ± 9 | 21.3 ± 1.7 | 18.1 ± 4.3 | 5 ± 6 |
| >120 s | 10 428 | 109 ± 20 | 249 ± 57 | 27.2 ± 9.8 | 32.8 ± 11.8 | -25 ± 42 |
| *Pings de historial (en 15 min, incl. el actual)* | | | | | | |
| 1 | 566 | 88 ± 20 | 209 ± 65 | 16.8 ± 8.4 | 33.9 ± 11.5 | -34 ± 28 |
| 2 | 1 131 | 70 ± 9 | 155 ± 21 | 17.3 ± 4.0 | 23.8 ± 6.2 | -16 ± 15 |
| ≥ 3 | 278 176 | 54 ± 5 | 114 ± 11 | 19.2 ± 2.0 | 15.4 ± 2.9 | 5 ± 3 |

Lectura:
1. **Error por coche en 3-7 min: MAE 54 ± 5 s** (P90 114 s; llega antes > 60 s 19.2 %, llega después > 60 s 15.5 %, sesgo 5 s). Es igual a la vara del modelo (~55 s).
2. El coche anunciado como 1.º tiene mejor error que el resto (MAE 51 contra 57 s), pero su sesgo es de signo contrario: llega después de lo anunciado (más que antes). Los 2.º-5.º llegan más seguido antes de lo anunciado.
3. Por grupo: Viene 54 s, Puede venir 57 s, Sentido sin confirmar 82 s (este último, 0,8 % de los coches de la banda). El grupo importa poco para el error del coche que sí llega; importa para si llega (bondi fantasma, ver `VARA_CORREGIDA.md`).
4. Por edad del ping: 0-30 s 52 s, 30-60 s 56 s, 60-120 s 60 s, > 120 s 109 s. Con ping fresco (≤ 30 s, 75 % de los coches) el error ya es ~53 s: la edad del ping no explica la diferencia con la vara. Los pings > 120 s (3,7 % de los coches) casi duplican el error y llegan después de lo anunciado (sesgo negativo).
5. Por historial: ≥ 3 pings 54 s (99,3 % de los coches), 2 pings 70 s, 1 ping 88 s: pocos casos, error mayor, sin peso en el agregado.

## Bandas 0-3 y 7-15 min

### 0-3 min

| corte | n coches | MAE (s) | P90 error abs. (s) | llega antes > 60 s % | llega después > 60 s % | sesgo (s; + = llega antes) |
|---|---|---|---|---|---|---|
| **Todos los listados** | 224 712 | 33 ± 4 | 71 ± 11 | 11.2 ± 3.4 | 3.1 ± 1.0 | 13 ± 3 |
| *Grupo de la app* | | | | | | |
| Viene | 216 678 | 33 ± 4 | 70 ± 10 | 10.9 ± 3.3 | 3.1 ± 1.0 | 13 ± 3 |
| Puede venir | 7 693 | 40 ± 5 | 83 ± 13 | 18.4 ± 5.6 | 2.7 ± 0.8 | 23 ± 5 |
| Sentido sin confirmar | 341 (7 d) | 59 ± 13 | 133 ± 34 | 28.7 ± 7.0 | 7.2 ± 3.6 | 33 ± 17 |
| *Posición en la lista* | | | | | | |
| 1.º | 152 980 | 30 ± 2 | 63 ± 6 | 7.9 ± 1.6 | 3.3 ± 1.1 | 9 ± 1 |
| 2.º-5.º | 71 732 | 40 ± 6 | 87 ± 13 | 18.4 ± 4.4 | 2.8 ± 0.8 | 23 ± 5 |
| *Grupo × posición* | | | | | | |
| Viene, 1.º | 148 628 | 30 ± 2 | 63 ± 6 | 7.7 ± 1.6 | 3.3 ± 1.1 | 9 ± 1 |
| Viene, 2.º-5.º | 68 050 | 40 ± 6 | 86 ± 13 | 18.1 ± 4.4 | 2.8 ± 0.9 | 22 ± 5 |
| Puede venir, 1.º | 4 241 | 36 ± 4 | 77 ± 11 | 14.8 ± 4.8 | 2.5 ± 0.8 | 18 ± 3 |
| Puede venir, 2.º-5.º | 3 452 | 45 ± 6 | 90 ± 13 | 23.4 ± 6.2 | 3.0 ± 1.2 | 30 ± 5 |
| Sentido sin confirmar, 1.º | 111 (1 d) | 33 ± — | 56 ± — | 5.0 ± — | 5.0 ± — | 8 ± — |
| Sentido sin confirmar, 2.º-5.º | 230 (6 d) | 66 ± 22 | 149 ± 92 | 33.2 ± 9.7 | 6.2 ± 0.9 | 43 ± 21 |
| *Edad del ping en la consulta* | | | | | | |
| 0-30 s | 167 889 | 30 ± 3 | 64 ± 7 | 8.8 ± 2.3 | 2.8 ± 0.8 | 10 ± 2 |
| 30-60 s | 24 078 | 34 ± 4 | 72 ± 8 | 11.9 ± 2.6 | 3.6 ± 1.5 | 14 ± 3 |
| 60-120 s | 24 492 | 41 ± 5 | 85 ± 10 | 18.0 ± 3.7 | 4.0 ± 1.5 | 21 ± 4 |
| >120 s | 8 253 | 68 ± 12 | 139 ± 22 | 40.4 ± 11.1 | 5.9 ± 1.6 | 47 ± 12 |
| *Pings de historial (en 15 min, incl. el actual)* | | | | | | |
| 1 | 162 (3 d) | 62 ± 12 | 131 ± 28 | 31.8 ± 5.4 | 10.6 ± 7.6 | 26 ± 6 |
| 2 | 601 | 48 ± 10 | 96 ± 21 | 23.8 ± 8.8 | 4.7 ± 1.4 | 29 ± 12 |
| ≥ 3 | 223 949 | 33 ± 4 | 70 ± 10 | 11.1 ± 3.4 | 3.1 ± 1.0 | 13 ± 3 |

### 7-15 min

| corte | n coches | MAE (s) | P90 error abs. (s) | llega antes > 60 s % | llega después > 60 s % | sesgo (s; + = llega antes) |
|---|---|---|---|---|---|---|
| **Todos los listados** | 444 852 | 89 ± 5 | 182 ± 10 | 23.9 ± 2.5 | 29.9 ± 4.3 | -16 ± 10 |
| *Grupo de la app* | | | | | | |
| Viene | 387 102 | 84 ± 5 | 173 ± 10 | 24.4 ± 2.6 | 28.6 ± 4.4 | -10 ± 11 |
| Puede venir | 51 103 | 113 ± 7 | 248 ± 20 | 21.0 ± 3.2 | 37.0 ± 5.1 | -51 ± 16 |
| Sentido sin confirmar | 6 647 | 152 ± 19 | 370 ± 63 | 16.6 ± 2.7 | 49.6 ± 5.0 | -95 ± 25 |
| *Posición en la lista* | | | | | | |
| 1.º | 73 999 | 96 ± 10 | 190 ± 20 | 12.6 ± 3.1 | 42.2 ± 6.6 | -58 ± 18 |
| 2.º-5.º | 370 853 | 88 ± 4 | 181 ± 9 | 26.5 ± 3.6 | 27.2 ± 5.1 | -7 ± 13 |
| *Grupo × posición* | | | | | | |
| Viene, 1.º | 65 401 | 92 ± 10 | 182 ± 19 | 12.8 ± 3.2 | 41.6 ± 6.8 | -53 ± 18 |
| Viene, 2.º-5.º | 321 701 | 83 ± 4 | 172 ± 9 | 27.2 ± 3.7 | 25.7 ± 5.3 | 0 ± 14 |
| Puede venir, 1.º | 7 736 | 117 ± 17 | 254 ± 59 | 12.1 ± 3.3 | 45.6 ± 6.8 | -82 ± 24 |
| Puede venir, 2.º-5.º | 43 367 | 114 ± 6 | 251 ± 19 | 23.0 ± 4.2 | 35.4 ± 5.6 | -46 ± 16 |
| Sentido sin confirmar, 1.º | 862 | 193 ± 41 | 454 ± 125 | 9.5 ± 6.2 | 60.1 ± 9.7 | -161 ± 58 |
| Sentido sin confirmar, 2.º-5.º | 5 785 | 147 ± 17 | 339 ± 31 | 18.1 ± 2.9 | 47.7 ± 3.5 | -84 ± 17 |
| *Edad del ping en la consulta* | | | | | | |
| 0-30 s | 333 566 | 81 ± 4 | 169 ± 8 | 23.7 ± 2.9 | 28.7 ± 4.5 | -9 ± 11 |
| 30-60 s | 46 124 | 85 ± 5 | 178 ± 13 | 24.5 ± 2.4 | 29.6 ± 3.9 | -10 ± 9 |
| 60-120 s | 45 953 | 100 ± 9 | 212 ± 28 | 24.3 ± 3.4 | 33.2 ± 5.5 | -25 ± 16 |
| >120 s | 19 209 | 283 ± 92 | 639 ± 151 | 18.0 ± 8.5 | 61.0 ± 16.9 | -224 ± 119 |
| *Pings de historial (en 15 min, incl. el actual)* | | | | | | |
| 1 | 1 614 | 176 ± 22 | 419 ± 69 | 13.1 ± 7.9 | 56.6 ± 9.0 | -131 ± 44 |
| 2 | 2 109 | 156 ± 21 | 390 ± 89 | 16.7 ± 6.0 | 49.3 ± 5.6 | -105 ± 30 |
| ≥ 3 | 441 129 | 88 ± 5 | 180 ± 10 | 24.0 ± 2.5 | 29.7 ± 4.3 | -15 ± 10 |

El error crece con el horizonte (35 → 56 → 90 s de MAE por coche). En 7-15 min el sesgo es negativo (llega después) por selección de banda, más fuerte en el 1.º de la lista.

## Descomposición del MAE «próximo coche» (banda 3-7 min)

Instante = (parada, t) con el próximo paso real (`real_next2_s`) en 3-7 min, sin los instantes excluidos por paso previo no verificable (1467 de 128757); 125806 con anuncio (sin aviso firme: 2.3 %, fuera del MAE; es un problema de la app, no del modelo). Error del instante = ETA anunciado del 1.º de la lista (`ann0_any_s`) − tiempo real al primer coche en llegar (cualquiera, listado o no). Verificación: `ann0_any_s` coincide con el `eta0_s` del 1.º de la lista en 99.7 % de los instantes (el resto, empates de ETA).

| caso (banda real 3-7 min, instantes con anuncio) | n instantes | peso % | MAE (s) | aporte al MAE total (s) | llega antes > 60 s % | llega después > 60 s % | sesgo (s; + = llega antes) |
|---|---|---|---|---|---|---|---|
| **A. el anunciado como 1.º es el primero en llegar** (error = su error por coche) | 94 278 | 74.9 | 49 | 36.5 | 13.6 | 16.8 | -5 |
| B1. el primero en llegar es otro coche listado (2.º-5.º); el anunciado 1.º llega después | 11 934 | 9.5 | 115 | 10.9 | 19.1 | 23.5 | 28 |
| B2. ídem, y el anunciado 1.º ya había pasado (entre su último ping y t) | 8 061 | 6.4 | 274 | 17.6 | 0.0 | 99.9 | -274 |
| B3. ídem, y el anunciado 1.º es un bondi fantasma (no pasa en 40 min) | 6 434 | 5.1 | 329 | 16.8 | 7.2 | 71.7 | 17 |
| B4. el primero en llegar es un bondi no anunciado; el anunciado 1.º llega después | 3 245 | 2.6 | 392 | 10.1 | 67.2 | 14.9 | 334 |
| B5. ídem, y el anunciado 1.º ya había pasado | 716 | 0.6 | 289 | 1.6 | 0.0 | 100.0 | -289 |
| B6. ídem, y el anunciado 1.º es un bondi fantasma | 1 086 | 0.9 | 379 | 3.3 | 31.7 | 54.9 | 109 |
| B7. el anunciado 1.º es no verificable (hueco de GPS) | 52 | 0.0 | 435 | 0.2 | 25.0 | 67.3 | 114 |
| **B. total (otro coche llega primero)** | 31 528 | 25.1 | 241 | 60.5 | 16.7 | 54.9 | -24 |
| **Total con anuncio** | 125 806 | 100.0 | 97 | 97.0 | 14.4 | 26.3 | -10 |

Por día (el peso de A y su MAE):

| día | instantes | MAE próximo coche (s) | peso de A % | MAE de A (s) |
|---|---|---|---|---|
| 2026-09-15 | 14081 | 97 | 72.8 | 50 |
| 2026-09-16 | 13934 | 103 | 68.7 | 53 |
| 2026-09-17 | 12618 | 103 | 72.1 | 50 |
| 2026-09-18 | 11763 | 118 | 65.6 | 52 |
| 2026-09-19 | 12574 | 84 | 80.1 | 45 |
| 2026-09-20 | 11059 | 90 | 86.5 | 46 |
| 2026-10-03 | 12990 | 89 | 80.1 | 46 |
| 2026-10-04 | 11362 | 75 | 86.8 | 45 |
| 2026-10-06 | 12662 | 98 | 71.3 | 50 |
| 2026-10-08 | 12763 | 110 | 68.3 | 52 |

Lectura:
1. **Cuando el anunciado como 1.º es el que llega primero (75 % de los instantes) el MAE es ~50 s, igual a su error por coche** (49,5 s; en 3-7 min por coche, 1.º de la lista: 51 s). Aporta 37 s de los 99 s.
2. **El otro 25 % de los instantes aporta 62 s (63 % del MAE)** con error de 110-410 s por instante. No es error de ETA de un coche: el ETA anunciado corresponde a otro coche que llega más tarde, ya pasó o no existe. Pesos: el anunciado 1.º ya pasó entre su último ping y t, mientras otro coche llega primero (B2 + B5: 7,0 % de los instantes, 19,4 s); el anunciado 1.º es un bondi fantasma (B3 + B6: 4,7 %, 18,7 s); otro coche listado llega primero y el 1.º llega después (B1: 10,0 %, 11,4 s); el primero en llegar es un bondi no anunciado (B4 + B5 + B6: 4,7 %, 17,0 s; B5 y B6 ya están contados en las dos líneas anteriores).
3. En B1 (mismo conjunto de coches, orden de llegada distinto) el MAE es 114 s: son errores de orden entre coches con ETA parecido; el error del anunciado contra su propio paso es de 176 s en esos casos, por lo que el modelo tampoco acierta a ese coche, no solo el orden.

## Conclusión

- **El modelo no es peor en producción.** El error por coche en el replay en 3-7 min es **54 s** (media de días ± 5), contra ~55 s de la vara del modelo; con ping fresco ≤ 30 s, 53 s. El 1.º de la lista tiene 52 s.
- **La diferencia (~99 s contra ~55 s) viene de qué coche se anuncia como próximo**, no del ETA de cada coche: en 75 % de los instantes el 1.º anunciado es el primero en llegar y el MAE es ~50 s. En el 25 % restante otro coche llega primero (el anunciado ya pasó, es un bondi fantasma, llega después que otro coche listado, o el primero es un bondi no anunciado) y esos instantes aportan 62 de los 99 s.
- Diferencias de muestra que quedan entre la vara del modelo y el replay (no cuantificadas por separado, excepto la edad del ping): la vara mide filas con ETA real 3-7 min sobre puntos cualquiera (un coche en un punto del trayecto, ping fresco, historial completo) y el replay mide coches listados en 40 paradas por línea, cada 10 min, con la regla de lista (≤ 5 coches, grupos), pings de hasta 10 min de antigüedad, historial de 15 min recortado y paradas y horarios distintos; el replay además condiciona por el paso real firme del propio coche (verdad con la limitación de coches cuyo recorrido no tiene la parada, ≈ 4 % de los pasos). Los coches con 1-2 pings (0,7 %) y con ping > 120 s (3,7 %) tienen error 70-110 s pero no mueven el agregado.
- El «próximo coche» tiene un error propio de selección que el error por coche no ve: coches ya pasados (ping viejo), bondi fantasma y orden equivocado de llegada. Eso es lo que hay que atacar para bajar el ~99 s, no el ETA por coche.

## Re-corrida con la verdad nueva

`python data/ml/replay/porcoche/calcula.py --runs data/ml/replay/vara/run_base_xp [--days ...]` y luego `python data/ml/replay/porcoche/genera_md.py` (regenera este archivo; los textos de «Lectura» y «Conclusión» que citan números fijos hay que revisarlos a mano). Con la verdad nueva se espera: menos coches con paso firme (los pasos de coches cuyo recorrido no tiene la parada dejan de ser verdad), con lo cual algunos coches que hoy cuentan como «llega» pasarían a ser bondi fantasma y, en el cálculo por coche, salen de la muestra (el error por coche se mide solo sobre coches que cruzan). Las filas `run_base_xp` del cálculo actual no se usaron.
