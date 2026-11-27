# Piso del error de ETA por coche con gemelos (2026-11-27)

Pregunta: cuánto error de ETA por coche queda aunque se conozca perfectamente el tránsito. Medición, sin entrenar ni tocar pipeline ni app. Tablas completas: `raw/tablas.md`; resumen numérico: `raw/resumen.json`.

## Método

- **Gemelos.** B recorre un tramo de un shape; A (otro coche) recorre el mismo tramo, en el mismo sentido, entrando a ≤ Δ de B (Δ = 60 s, sensibilidad 120 y 300 s). Se predice la duración de B con la duración real de A: error = t_A − t_B. El MAE de ese error es la cota de un predictor con oráculo de tránsito: incluye la variabilidad propia de cada coche (paradas, semáforos, pasajeros) y el ruido de interpolación de los 4 cruces.
- **Tramos.** Nodos cada 250 m sobre cada shape de las líneas 39, 42, 92, 107, 132 y 168 (26 shapes); tramos de 1000 m (principal) y 1500 m, también 2000 y 2500 m (solo para elegir el largo). Largo elegido con los datos: 1000 m deja el 73 % de los B en 3–7 min (mediana 4,0 min) y 1500 m el 62 % (6,2 min); 2000 m, 27 %; 2500 m, 10 %.
- **Shapes.** Los del export de `path_v4_l1_s1` (copia `../proyectoconsola/data/backup_line_shapes_2026-11-26/`; los ids coinciden con `export/.../lines/`). Los `line_shapes` regenerados el 2026-11-26 no se usaron: una primera corrida con ellos se descartó y se rehízo entera.
- **Quién es A.** Cualquier coche de las 98 líneas con algún tramo geométricamente equivalente (todas las muestras cada 50 m del tramo a ≤ 25 m de otro shape, con avance equivalente a lo largo de él, sentido igual). Tipos por el recorrido ex post del viaje de A (segmentador geo2 + asignación geo3 de `replay/run.py::load_day`): *misma línea y recorrido* (mismo shape que B), *misma línea, otro ramal*, *otra línea (tronco compartido)*. B solo cuenta si su viaje ex post es el shape del tramo. A sin viaje ex post identificado se descarta.
- **Cruces.** Entrada y salida interpoladas entre pings compatibles consecutivos (geo3: T = 45 m, M = 20 m) separados ≤ 600 s, con la misma regla que `replay/core.py::crossings_v2` (versión vectorizada en `gemelos.py::cross_nodes`; velocidad media ≤ 25 m/s + 50 m; cruce firme solamente). Entrada y salida del mismo coche y recorrido, sin otra entrada en el medio, duración 30 s–40 min.
- **Gemelo.** Por cada B y tipo: el A de entrada más cercana a la de B (excluye el mismo coche). Variante «mejor de varios»: mediana de las duraciones de todos los A del tipo dentro de Δ.
- **Días.** 12 días de la validación 2026-09-15 → 10-14: hábiles 09-15, 16, 17, 18, 22, 23, 24, 10-06, 10-07, 10-08 y fin de semana 09-19 (sáb), 09-20 (dom). (No hay grabación de 09-27 ni 09-29.) Franja de entrada 6–23 h. 9,95 M de casos B (tramos solapados, muy correlacionados), 4793 coches-día.
- **Banda.** ETA real = t_B (duración real del tramo desde la entrada) en 3–7 min.
- **Modelo.** `path_v4_l1_s1` con `path_reference.predict_from_raw` (pinned del replay), en una muestra de 114.038 casos B (tramos de 1000 y 1500 m, hasta 800 por línea, día y largo, la mitad con gemelo de otro ramal u otra línea). Origen: último ping de B ≤ entrada (hasta 90 s antes), solo pings ≤ t (historial de 900 s de B y de los otros coches de la línea de los últimos 20 min para el coche de adelante), `only_shapes = [shape del tramo]`, objetivo el nodo de salida; ETA crudo del modelo (sin el descuento de 60 s de la app). Error del modelo = (ping + ETA) − t_salida real, medido contra la salida de B interpolada, en los mismos casos y banda que el gemelo.
- **Ruido de interpolación.** `ruido_interp.py`, día 2026-09-16: cadenas de k intervalos consecutivos, error del instante interpolado contra los pings intermedios, objetivo uniforme. MAE: k=2 13,8 s; k=3 20,0; k=4 25,2; k=5 29,8; k=6 34,2. Extrapolación log-log a un intervalo (no validable): 7,9 s por cruce (exponente 0,83); con cruces en coche detenido, §7 da hasta 14,9 s.

## Resultados (B en 3–7 min, gemelo más cercano en entrada)

**Piso por tipo de gemelo, Δ ≤ 60 s.**

| Tramo | Tipo de gemelo | n B | MAE | P50 | P90 | sesgo (real−pred) | % abs > 60 s | % llega antes > 60 s |
|---|---|---|---|---|---|---|---|---|
| 1000 m | cualquiera | 1.083.753 | 49,9 | 37,7 | 109,7 | +5,3 | 32,1 | 13,8 |
| 1000 m | misma línea y recorrido | 389.925 | 46,3 | 34,8 | 101,5 | +3,3 | 28,6 | 12,9 |
| 1000 m | misma línea, otro ramal | 463.055 | 47,8 | 36,2 | 104,8 | +3,9 | 29,9 | 13,3 |
| 1000 m | otra línea, tronco compartido | 604.630 | 54,9 | 43,0 | 117,8 | +5,5 | 36,5 | 15,9 |
| 1500 m | cualquiera | 770.930 | 55,4 | 41,5 | 121,0 | −13,0 | 35,9 | 22,3 |
| 1500 m | misma línea y recorrido | 296.036 | 51,2 | 37,9 | 112,7 | −13,2 | 32,1 | 20,6 |
| 1500 m | misma línea, otro ramal | 337.716 | 53,3 | 39,8 | 116,1 | −14,1 | 33,9 | 21,8 |
| 1500 m | otra línea, tronco compartido | 361.699 | 62,8 | 49,7 | 133,1 | −15,1 | 42,4 | 26,2 |

**Sensibilidad a Δ (cualquier gemelo, 1000 m):** MAE 49,9 / 50,8 / 52,3 s para Δ ≤ 60 / 120 / 300 s (misma línea y recorrido: 46,3 / 48,9 / 52,4). Reducir Δ casi no mueve el piso: la mayor parte del error no es de tránsito común.

**Mejor de varios gemelos (mediana de los A dentro de Δ).** 1000 m, cualquiera: 45,9 s (A medio 2,3; Δ ≤ 60 s), 45,0 s (Δ ≤ 120 s, A medio 3,5), 45,0 s (Δ ≤ 300 s, A medio 6,8); P90 96–99 s. 1500 m: 51,5 / 51,1 / 51,8 s. Promediar gemelos recorta 4–5 s, no más: el error es en gran parte ruido propio de cada coche.

**Por línea (1000 m, cualquiera, Δ ≤ 60 s), MAE / P90:** 107 45,5 / 100,4; 92 46,2 / 102,9; 168 47,9 / 105,0; 42 49,6 / 107,7; 39 51,3 / 111,9; 132 53,6 / 116,8. Fin de semana 42,7 s contra hábil 50,5 s.

**Por banda de ETA real (1000 y 1500 m juntos, Δ ≤ 60 s):** 3–5 min 47,7 s; 5–7 min 57,7 s; 7–10 min 72,3 s; 10–15 min 95,2 s. Las bandas cortas y largas tienen sesgo por seleccionar sobre el valor real (ver salvedades).

**Comparación con el modelo, mismos casos de B (muestra), banda 3–7 min, Δ ≤ 60 s:**

| Tramo | Tipo de gemelo | n | Gemelo MAE | Gemelo P90 | Modelo MAE | Modelo P90 | Modelo % llega antes > 60 s | Gemelo % llega antes > 60 s |
|---|---|---|---|---|---|---|---|---|
| 1000 m | cualquiera | 41.606 | 47,5 | 104,2 | 49,6 | 105,3 | 19,5 | 13,0 |
| 1000 m | misma línea y recorrido | 25.111 | 45,4 | 99,6 | 50,3 | 107,0 | 20,5 | 12,7 |
| 1000 m | misma línea, otro ramal | 10.587 | 47,3 | 104,6 | 50,0 | 105,1 | 19,6 | 12,7 |
| 1000 m | otra línea, tronco compartido | 13.271 | 53,3 | 113,8 | 47,8 | 101,9 | 17,2 | 15,0 |
| 1500 m | cualquiera | 36.241 | 52,5 | 115,1 | 59,4 | 124,4 | 33,9 | 20,7 |
| 1500 m | misma línea y recorrido | 20.810 | 49,4 | 109,8 | 61,3 | 129,4 | 35,7 | 19,9 |
| 1500 m | misma línea, otro ramal | 10.712 | 51,5 | 112,6 | 58,0 | 121,3 | 31,5 | 19,5 |
| 1500 m | otra línea, tronco compartido | 10.547 | 61,9 | 129,8 | 57,0 | 118,4 | 31,5 | 25,4 |

Por línea (1000 y 1500 m, cualquiera, Δ ≤ 60 s; gemelo MAE / modelo MAE): 39 50,9 / 50,9; 92 47,2 / 50,0; 168 48,5 / 52,3; 42 50,1 / 55,4; 107 46,9 / 55,9; 132 55,2 / 60,8. En la banda 3–7 min definida por el ETA real desde el ping (vara del modelo) el modelo da en esta muestra 54,0 s de MAE y P90 114,6 s (n = 75.772), en línea con los ~54–56 s de §7.

**Ruido de interpolación en el piso** (1000 y 1500 m, cualquiera, Δ ≤ 60 s; MAE observado 52,2 s; modelo, mismos casos, 54,2 s). El gemelo tiene 4 cruces interpolados (error de la diferencia ≈ 2 × el de un cruce si son independientes y gaussianos); el modelo, 1 (la salida de B).

| Ruido por cruce (MAE) | Ruido del gemelo | Piso neto del gemelo | Modelo neto |
|---|---|---|---|
| 7,2 s | 14,4 s | 50,2 s | 53,7 s |
| 8,0 s | 16,0 s | 49,7 s | 53,6 s |
| 14,9 s | 29,8 s | 42,9 s | 52,1 s |

## Lectura

- **Piso con oráculo de tránsito: ~50 s de MAE y P90 ~105–110 s** en la banda 3–7 min (1000 m, Δ ≤ 60 s; 55 s a 1500 m). Neto de interpolación: 43–50 s. Con la mediana de varios gemelos, 45–46 s.
- **El modelo está pegado al piso.** En los mismos casos: 49,6 contra 47,5 s (1000 m) y 59,4 contra 52,5 s (1500 m); P90 105 contra 104 s y 124 contra 115 s. Margen a un predictor tipo oráculo de tránsito: ~2 s a 1000 m y ~7 s a 1500 m (14 % en el peor tipo, misma línea y recorrido, 1500 m: 61,3 contra 49,4 s). Con tronco compartido de otra línea el modelo incluso supera al gemelo (47,8 contra 53,3 s), porque el gemelo hereda el ritmo de otra línea.
- **Casi todo el error es propio de cada coche** (paradas, semáforos, pasajeros), no de tránsito compartido: acortar Δ de 300 a 60 s baja 2–6 s, y la mediana de varios gemelos solo 4–5 s. Una señal dinámica tipo «ritmo propio del coche» o «tramos que recorrió el coche de adelante» tiene como mucho unos pocos segundos de margen en MAE (el techo está entre ~2 y ~7 s según el largo, más ~4–5 s si la señal fuera tan buena como promediar varios coches adelante), dentro de lo que ya hace el promedio de pares (`last_bus`, historial de 20 min: sin valor, §7).
- **El error grave (llega antes > 60 s) sí tiene margen relativo:** el modelo 19,5 % (1000 m) y 33,9 % (1500 m) contra 13,0 % y 20,7 % del gemelo; en parte es el sesgo del modelo en esa banda y en parte el sesgo de seleccionar la banda por ETA real (el gemelo también llega a 21–26 % a 1500 m). Un corrimiento del anuncio no es una señal dinámica (§5).
- **Tipos de gemelo:** misma línea y recorrido es el mejor (46,3 s), otro ramal casi igual (47,8 s) y otra línea la peor (54,9 s). El ramal desconocido cuesta ~1,5 s en este piso; el costo grande del ramal está en qué coche se anuncia primero, no en el ETA por coche (§7 «Descomposición»).

## Salvedades

- **No es un piso estricto.** Un solo gemelo con duración observada es un predictor con ruido propio; mezclar gemelos baja 4–5 s, y modelos que combinen ritmo propio con tránsito podrían pasar por debajo del gemelo (el modelo ya lo hace con tronco compartido de otra línea). Es un orden de magnitud del error irreducible desde el tránsito observable, no una cota demostrada.
- **Selección por ETA real.** La banda 3–7 min se define por t_B real (como la vara): los B largos de la banda reciben gemelos más rápidos y viceversa; por eso el sesgo cambia de signo entre 1000 y 1500 m y entre bandas. Afecta igual al modelo y al gemelo en la comparación.
- **Origen distinto.** El gemelo predice desde la entrada (cruce interpolado); el modelo, desde el ping anterior a la entrada (hasta 90 s antes), con horizonte algo mayor; error del modelo medido contra una salida interpolada. Se compara en el mismo B y la misma banda de t_B, no por ETA real desde el ping.
- **Casos correlacionados.** Los tramos solapan (inicios cada 250 m) y un coche aparece en muchos tramos: los 9,95 M de casos son 4793 coches-día; los n son de casos, no de muestras independientes. El modelo se midió en una muestra de 114.038 casos.
- **Ruido de interpolación.** El valor de 7,9 s por cruce es extrapolación log-log a un intervalo desde k = 2–6 (no validable), medido con pings de CABA, cuyo `ts` es un estampado por lote (~1/min, no la hora del GPS): ese ruido de sello no se mide y no está en el piso neto (hipótesis de ~3,7 s por ping, §7). El piso neto supone errores independientes y gaussianos entre los 4 cruces.
- **Cruces firmes únicamente:** gemelos con hueco de GPS de 10–40 min no cuentan. Tramos desde el nodo 0 (cabecera) incluidos; no se filtraron coches detenidos en cabecera.
- **Corrida con shapes del export.** Los `line_shapes` regenerados el 2026-11-26 cambian 28 líneas (entre ellas 39, 42, 107 y 132 y varias candidatas a gemelo); no se usaron. Los shapes de respaldo tienen la mitad de puntos que los del export (mismos ids; el export densifica).
- Un día con dato real de interpolación (2026-09-16) para el ruido; los otros 11 no se repitieron.

## Archivos

- `equiv.py`: equivalencia geométrica de tramos entre shapes; `gemelos.py`: cruces, pasadas, gemelos y predicción del modelo por día (`python experiments/piso_gemelos/gemelos.py --days ... --workers 3 --model-n 800`, ~24 min por día con 3 workers; los parquet por día de `raw/` no se versionan, ~100 MB cada uno); `ruido_interp.py`; `analisis.py` (tablas).
- `raw/tablas.md`, `raw/resumen.json`, `raw/ruido_interp_2026-09-16.json`: resultados.
