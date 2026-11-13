# Asignación de recorrido en v2b: ¿cuánto error de datos hay con el criterio de 150 m?

Diagnóstico de solo lectura sobre `data/ml/v2b` (15 líneas, 183 días, 2026-03-28 a 2026-10-14). No se entrenó nada ni se tocó el pipeline ni `data/ml/v2*`. Todo lo generado está en `data/ml/v2b/diag/asignacion/`.

## 0. Método

- Se releyó el NDJSON crudo de los 183 días y se volvió a segmentar con el segmentador v2b (`geo2`) con el mismo carry del build (`data/ml/v2b/daily/*.carry.json`). Reproduce exactamente los viajes del build (comprobado: misma cantidad de viajes por línea y en total en el día de prueba). Total: 1.392.759 viajes y 93.577.212 pings.
- Por viaje se proyecta cada ping sobre **todos** los recorridos de la línea (`ShapeIndex.project_many`) y se toma el recorrido asignado por `geometry_for_trip` (el del build).
- «Otro shape más cerca» = algún otro recorrido de la línea con perp menor que el asignado **en más de 10 m**. Con comparación estricta (cualquier diferencia) el control en ≤45 m da ~11 %, porque ramales que comparten tronco empatan por ruido; por eso el margen de 10 m. Los valores estrictos están en `resumen.json`.
- «Sentido opuesto del mismo ramal» se deduce del nombre del recorrido (`A → B` contra `B → A`); no se usa route_id, trip_id ni start_time.
- Filas de entrenamiento: se leyeron los parquet diarios y se emparejó cada fila (P y F) con su ping por (recorrido, ts, distancia a lo largo). Se emparejaron 44.137.181 de 44.140.750 filas (99,99 %).
- Punto 5: simulación con `FIT_M = 45` en 40 días de muestra (1 de cada 5 más 4 días hábiles de la validación del segmentador), sin escribir en v2b.
- Punto 6: modelo `path_lr2e-3_s0`, evaluado con `prediccion.eval --save-preds` con salida en `eval/`. Las filas de eval se emparejan con las filas de entrenamiento de los días de validación (por recorrido, ts_p y dist_along).
- Ping «válido» = perp ≤ 150 m al recorrido asignado (la máscara de v2b). Los percentiles salen de histogramas de 0,5 m.

## 1. Ruido GPS real (perp al recorrido asignado ex post)

Percentiles sobre los pings válidos (≤ 150 m); la columna «> 150 m» es la fracción de pings de viaje fuera de la máscara.

| Línea | Pings | > 150 m | p50 (m) | p90 (m) | p95 (m) | p99 (m) |
|---|---|---|---|---|---|---|
| 26 | 4.886.314 | 1,4 % | 4,0 | 11,0 | 15,0 | 48,0 |
| 39 | 8.643.238 | 0,7 % | 4,0 | 10,5 | 14,5 | 44,5 |
| 42 | 4.798.483 | 3,1 % | 4,0 | 10,5 | 19,0 | 108,5 |
| 92 | 7.717.068 | 2,3 % | 3,5 | 10,5 | 15,5 | 77,0 |
| 124 | 4.500.502 | 1,5 % | 4,0 | 11,0 | 15,0 | 67,5 |
| 151 | 6.508.955 | 1,5 % | 3,5 | 11,0 | 22,0 | 81,0 |
| 168 | 6.343.730 | 1,6 % | 3,5 | 8,5 | 11,0 | 62,0 |
| 50 | 5.090.289 | 2,8 % | 3,5 | 9,0 | 13,0 | 108,5 |
| 106 | 10.788.742 | 1,0 % | 3,5 | 9,0 | 12,0 | 33,5 |
| 107 | 4.023.972 | 2,7 % | 3,0 | 8,0 | 10,5 | 86,5 |
| 108 | 3.981.242 | 1,3 % | 3,5 | 10,5 | 15,0 | 90,5 |
| 132 | 8.630.594 | 1,0 % | 4,0 | 11,5 | 16,0 | 86,0 |
| 12 | 7.050.352 | 1,0 % | 4,0 | 12,0 | 16,5 | 48,5 |
| 15 | 6.896.186 | 1,1 % | 4,0 | 10,5 | 15,0 | 99,5 |
| 128 | 3.717.545 | 1,4 % | 3,5 | 9,5 | 13,0 | 63,5 |
| TODAS | 93.577.212 | 1,5 % | 3,5 | 10,5 | 14,5 | 73,0 |

Fracción de los pings válidos por debajo de cada umbral:

| Umbral (m) | 10 | 15 | 20 | 30 | 45 | 60 | 100 |
|---|---|---|---|---|---|---|---|
| % de pings válidos por debajo | 90,0 % | 95,4 % | 96,9 % | 97,8 % | 98,4 % | 98,8 % | 99,4 % |

Lectura: la mitad de los pings cae a ≤ 3,5 m del recorrido y el 95 % a ≤ 14,5 m. Entre 15 y 45 m queda un 3,0 % y entre 45 y 150 m un 1,6 % de los pings válidos. El p99 (73 m) ya no es ruido de GPS sino desvíos reales, calles paralelas y tramos fuera de recorrido. Por línea el p95 va de 10,5 m (107) a 22 m (151) y 19 m (42).

**Umbral físico razonable: 45 m** (98,4 % de los pings válidos, unas 3 veces el p95). Con 30 m se retiene 97,8 %; con 20 m, 96,9 %. Entre 45 y 100 m no hay ruido de GPS sino otra calle o un desvío, y una cuadra porteña (100–130 m) cae dentro de 150 m.

## 2. Filas contaminadas (perp 45–150 m)

Pings válidos (total 92.153.508): 1,60 % están a 45–150 m. En 42,2 % de ellos otro recorrido de la línea está ≥ 10 m más cerca (comparación estricta: 48,8 %) y en 59 % de esos el más cercano es el sentido opuesto del mismo ramal (el resto, otro ramal). Control: dentro de ≤ 45 m el «otro más cerca» ocurre en 0,55 % de los pings.

| Línea | Pings válidos | 45–150 m | con otro shape ≥10 m más cerca | de esos, el otro es el sentido opuesto | Control: ≤45 m con otro ≥10 m más cerca |
|---|---|---|---|---|---|
| 26 | 4.818.428 | 1,11 % | 46,7 % | 100 % | 0,22 % |
| 39 | 8.584.556 | 0,98 % | 38,7 % | 54 % | 0,47 % |
| 42 | 4.647.333 | 2,89 % | 49,7 % | 39 % | 0,68 % |
| 92 | 7.538.718 | 1,63 % | 36,5 % | 67 % | 0,82 % |
| 124 | 4.434.502 | 1,26 % | 23,0 % | 100 % | 0,52 % |
| 151 | 6.410.260 | 2,73 % | 62,5 % | 30 % | 1,36 % |
| 168 | 6.243.734 | 1,28 % | 51,4 % | 47 % | 0,26 % |
| 50 | 4.946.571 | 2,32 % | 18,3 % | 95 % | 0,06 % |
| 106 | 10.676.452 | 0,80 % | 67,1 % | 82 % | 0,37 % |
| 107 | 3.915.023 | 1,65 % | 39,0 % | 0 % | 0,16 % |
| 108 | 3.929.042 | 1,97 % | 54,0 % | 100 % | 0,62 % |
| 132 | 8.542.251 | 1,87 % | 42,2 % | 58 % | 0,36 % |
| 12 | 6.977.791 | 1,12 % | 37,7 % | 91 % | 0,82 % |
| 15 | 6.821.888 | 2,07 % | 29,6 % | 55 % | 1,02 % |
| 128 | 3.666.959 | 1,21 % | 12,0 % | 100 % | 0,12 % |
| TODAS | 92.153.508 | 1,60 % | 42,2 % | 59 % | 0,55 % |

Filas de entrenamiento (par P, F; 44.137.181 emparejadas): P o F a 45–150 m en 2,87 %; de esas, 45,0 % con otro recorrido más cerca. **Sucias** (45–150 m en P o F, o algún otro recorrido ≥ 10 m más cerca en P o F): **3,76 %**.

| Línea | Filas | P en 45–150 | F en 45–150 | P o F en 45–150 | con otro más cerca | Sucias (45–150 u otro más cerca) | Limpias |
|---|---|---|---|---|---|---|---|
| 26 | 2.573.968 | 1,15 % | 0,65 % | 1,77 % | 46,8 % | 2,12 % | 97,88 % |
| 39 | 4.597.060 | 1,04 % | 0,79 % | 1,73 % | 44,7 % | 2,57 % | 97,43 % |
| 42 | 2.224.198 | 1,94 % | 2,86 % | 4,58 % | 45,6 % | 5,57 % | 94,43 % |
| 92 | 3.208.192 | 2,42 % | 3,01 % | 4,90 % | 45,2 % | 6,46 % | 93,54 % |
| 124 | 1.836.353 | 1,04 % | 1,33 % | 2,30 % | 24,7 % | 3,11 % | 96,89 % |
| 151 | 2.932.927 | 1,99 % | 3,03 % | 4,90 % | 61,5 % | 6,86 % | 93,14 % |
| 168 | 2.249.123 | 1,11 % | 1,01 % | 2,07 % | 47,8 % | 2,46 % | 97,54 % |
| 50 | 2.266.148 | 2,17 % | 1,60 % | 3,67 % | 21,1 % | 3,77 % | 96,23 % |
| 106 | 5.340.765 | 1,04 % | 0,47 % | 1,46 % | 67,7 % | 2,10 % | 97,90 % |
| 107 | 1.653.108 | 1,40 % | 1,69 % | 2,86 % | 40,5 % | 3,06 % | 96,94 % |
| 108 | 1.657.245 | 1,28 % | 2,63 % | 3,73 % | 52,2 % | 4,76 % | 95,24 % |
| 132 | 4.780.945 | 2,07 % | 1,30 % | 3,29 % | 48,1 % | 3,93 % | 96,07 % |
| 12 | 4.385.630 | 1,00 % | 1,16 % | 2,11 % | 38,9 % | 3,54 % | 96,46 % |
| 15 | 2.370.984 | 1,78 % | 2,22 % | 3,81 % | 39,1 % | 5,50 % | 94,50 % |
| 128 | 2.060.535 | 1,18 % | 0,76 % | 1,86 % | 13,0 % | 2,04 % | 97,96 % |
| TODAS | 44.137.181 | 1,49 % | 1,50 % | 2,87 % | 45,0 % | 3,76 % | 96,24 % |

Las peores líneas son 92, 151 y 42 (5,6–6,9 % de filas sucias); las mejores, 128, 106, 26 y 168 (2,0–2,5 %).

## 3. Ambigüedad de la asignación del viaje

Diferencia = (mediana de perp del mejor otro recorrido) menos (mediana de perp del elegido), sobre todos los pings del viaje. Sobre 1.392.759 viajes.

| Línea | Viajes | Mediana perp. del viaje, p50 | dif. < 20 m | dif. < 20 m y 2º es sentido opuesto | 2º es sentido opuesto | Elegido > 20 m peor que otro | Mediana perp. del viaje > 45 m |
|---|---|---|---|---|---|---|---|
| 26 | 80.635 | 3,6 m | 0,2 % | 0,2 % | 100,0 % | 0,03 % | 0,10 % |
| 39 | 144.251 | 3,5 m | 99,6 % | 0,3 % | 0,6 % | 0,02 % | 0,18 % |
| 42 | 71.761 | 3,8 m | 99,8 % | 0,8 % | 0,9 % | 0,48 % | 2,73 % |
| 92 | 106.011 | 3,4 m | 55,8 % | 14,5 % | 55,0 % | 0,37 % | 7,41 % |
| 124 | 57.514 | 3,6 m | 0,1 % | 0,1 % | 100,0 % | 0,02 % | 0,04 % |
| 151 | 92.121 | 3,4 m | 98,8 % | 2,1 % | 3,1 % | 0,23 % | 0,60 % |
| 168 | 70.428 | 3,0 m | 99,6 % | 1,8 % | 2,1 % | 0,01 % | 0,03 % |
| 50 | 71.025 | 3,3 m | 89,2 % | 19,0 % | 25,8 % | 0,02 % | 0,22 % |
| 106 | 167.636 | 3,2 m | 11,5 % | 0,7 % | 79,1 % | 0,21 % | 0,46 % |
| 107 | 53.004 | 2,8 m | 52,0 % | 0,0 % | 0,0 % | 0,06 % | 2,40 % |
| 108 | 51.991 | 3,5 m | 87,0 % | 87,0 % | 100,0 % | 0,15 % | 0,30 % |
| 132 | 149.797 | 4,0 m | 100,0 % | 0,6 % | 0,6 % | 0,02 % | 0,10 % |
| 12 | 137.376 | 4,0 m | 100,0 % | 0,1 % | 0,1 % | 0,03 % | 0,05 % |
| 15 | 74.687 | 3,6 m | 98,1 % | 0,8 % | 1,0 % | 0,07 % | 0,70 % |
| 128 | 64.522 | 3,3 m | 1,2 % | 1,2 % | 100,0 % | 0,01 % | 0,13 % |
| TODAS | 1.392.759 | 3,5 m | 68,4 % | 5,9 % | 33,9 % | 0,12 % | 1,00 % |

- «dif. < 20 m» es muy alto (68,4 %) pero **no es error por sí mismo**: son ramales que comparten casi todo el trazado (39, 12, 132, 42, 151, 168 y 15 pasan del 98 %), y la elección arbitraria entre ellos ya estaba aceptada en ARQUITECTURA §4.1 (ruido de normalización, no de etiqueta).
- Lo que sí importa es que el segundo mejor sea el **sentido opuesto del mismo ramal**: 33,9 % de los viajes (100 % en 26, 124, 128, que tienen solo ida y vuelta; 79 % en 106). Con diferencia < 20 m: **5,9 %** de los viajes, concentrado en 108 (87 %), 50 (19 %) y 92 (15 %). Ahí la perp no decide el sentido: lo decide `_forward_fraction ≥ 0,6` (avance hacia adelante).
- **Elegido claramente peor que otro (> 20 m)**: 0,12 % de los viajes (1.612), 80 % de ellos con el mejor alternativo en sentido opuesto: el coche circula por una calle y el recorrido que cumple la regla de avance es el de la calle paralela. Son 0,02 % de los pings válidos. Viajes con mediana de perp > 45 m: 1,00 % (92: 7,4 %, 42: 2,7 %, 107: 2,4 %).

## 4. Proyección en el sentido equivocado (retroceso de la distancia a lo largo > 150 m)

Entre pings válidos consecutivos del mismo viaje. Total: 177.993 retrocesos en 90.760.760 pares (**0,196 %**). Pero 8,7 % de los viajes tienen al menos uno, y esos viajes reúnen 10,7 % de los pings válidos.

| Línea | Pares de pings válidos consecutivos | Retroceso > 150 m | Viajes con 1 o más retrocesos |
|---|---|---|---|
| 26 | 4.737.793 | 0,070 % | 2,2 % |
| 39 | 8.440.306 | 0,032 % | 1,5 % |
| 42 | 4.575.572 | 1,165 % | 31,8 % |
| 92 | 7.432.714 | 0,447 % | 25,5 % |
| 124 | 4.376.988 | 0,376 % | 27,7 % |
| 151 | 6.318.139 | 0,049 % | 2,9 % |
| 168 | 6.173.306 | 0,028 % | 2,3 % |
| 50 | 4.875.546 | 0,022 % | 1,4 % |
| 106 | 10.508.816 | 0,035 % | 1,2 % |
| 107 | 3.862.019 | 0,106 % | 6,4 % |
| 108 | 3.877.051 | 0,141 % | 9,8 % |
| 132 | 8.392.454 | 0,073 % | 3,1 % |
| 12 | 6.840.415 | 0,042 % | 2,0 % |
| 15 | 6.747.204 | 0,565 % | 34,5 % |
| 128 | 3.602.437 | 0,074 % | 4,0 % |
| TODAS | 90.760.760 | 0,196 % | 8,7 % |

Concentrado en 15 (34 % de los viajes), 42 (32 %), 124 (28 %) y 92 (26 %). No se verificó la causa; es consistente con recorridos con bucles o tramos que pasan dos veces por la misma calle (la proyección salta a otro pasaje), pero hay que mirarlo en el mapa (§7, tipo D). A nivel de filas el efecto queda acotado por las reglas del par (`dist[F] − dist[P] ≥ 100 m`, `ts[F] > ts[P]`); no se midió por separado.

## 5. Segmentador con FIT_M = 45 m en vez de 150 m

Simulación en 40 días (mismos NDJSON y mismo carry; `FIT_M` cambiado solo en memoria). `start_unknown` se calcula con la máscara perp ≤ FIT_M de cada caso (45 o 150 m) y el umbral de 1 km.

|  | FIT_M = 150 (v2b) | FIT_M = 45 | Cambio |
|---|---|---|---|
| Viajes | 305.617 | 304.009 | -1 % |
| Pings válidos | 19.971.227 | 19.653.256 | -2 % |
| Cortes por «reverse» (inversión de sentido sostenida) | 34.956 | 20.237 | -42 % |
| Cortes por «off» (salida del recorrido, p. ej. cambio de ramal) | 5.261 | 16.131 | +207 % |
| Cortes por «gap» (hueco > 5 min no unido) | 17.486 | 35.423 | +103 % |
| Cortes por «end» (llegada al final) | 227.382 | 211.808 | -7 % |
| Cortes por «stop» (detenido en cabecera o final) | 8.521 | 5.795 | -32 % |
| Cortes por «data_end» (fin de datos) | 12.011 | 14.615 | +22 % |
| start_unknown (% de viajes) | 15,5 % | 16,4 % | 0,9 pp |
| start_unknown (% de pings válidos) | 12,1 % | 12,7 % | 0,6 pp |
| Viajes consecutivos del mismo coche (hueco ≤ 5 min): sentido opuesto del mismo ramal | 70.276 | 68.399 | -3 % |
| idem: otro ramal | 18.868 | 18.304 | -3 % |
| idem: mismo recorrido | 1.294 | 952 | -26 % |

Entre las dos segmentaciones, 18.491 viajes de 150 m (6,1 %) quedan partidos en 2 o más de 45 m y 17.916 viajes de 45 m reúnen 2 o más de 150 m (solapamiento ≥ 60 s).

Lectura: con 45 m **desaparece el 42 % de los cortes por inversión de sentido**, aparecen **3,1 veces más** cortes por salida del recorrido y el doble de huecos no unidos (con 45 m más huecos y excursiones no cumplen «vuelve a ≤ FIT_M»). El número de viajes casi no cambia (-1 %), pero se cortan en otro lugar; `start_unknown` sube 0,9 pp (viajes) y 0,6 pp (pings). Los pasos entre viajes consecutivos de un mismo coche (inversión de sentido, cambio de ramal) casi no cambian (-3 % y -3 %); lo que cambia es en qué ping se corta y con qué causa. Bajar FIT_M **del segmentador** a 45 m no mejora los datos y los fragmenta más; conviene separar el umbral de segmentación del de asignación y validez.

## 6. Impacto en la evaluación (modelo por tramos `path_lr2e-3_s0`)

MAE global del modelo: seen 102,75 s (coincide con ARQUITECTURA: 102,7), heldout 205,65 s. Limpia = P y F con perp ≤ 45 m y ningún otro recorrido ≥ 10 m más cerca. Se emparejaron 29.996 de 30.000 filas (seen) y 29.999 de 30.000 (heldout). Sesgo = predicción menos ETA real (negativo = predice antes de lo real, el coche llega más tarde).

**seen**

| Banda | Grupo | n | % filas | MAE (s) | p90 error abs (s) | Sesgo (s) | Predice tarde >60 s | Predice temprano >60 s |
|---|---|---|---|---|---|---|---|---|
| Global | Limpias | 28.736 | 95,8 % | 98,1 | 217,4 | -13,8 | 27 % | 23 % |
| Global | Contaminadas | 1.260 | 4,2 % | 208,1 | 467,0 | -100,5 | 45 % | 24 % |
| Global | Todas | 29.996 | 100,0 % | 102,8 | 225,1 | -17,4 | 28 % | 23 % |
| ETA real 3–7 min | Limpias | 6.816 | 96,3 % | 52,6 | 111,7 | 1,2 | 17 % | 17 % |
| ETA real 3–7 min | Contaminadas | 265 | 3,7 % | 84,5 | 180,8 | -3,5 | 28 % | 21 % |
| ETA real 3–7 min | Todas | 7.081 | 100,0 % | 53,8 | 114,4 | 1,1 | 17 % | 17 % |

**heldout**

| Banda | Grupo | n | % filas | MAE (s) | p90 error abs (s) | Sesgo (s) | Predice tarde >60 s | Predice temprano >60 s |
|---|---|---|---|---|---|---|---|---|
| Global | Limpias | 28.811 | 96,0 % | 197,6 | 395,2 | -32,7 | 45 % | 18 % |
| Global | Contaminadas | 1.188 | 4,0 % | 401,8 | 871,5 | -75,3 | 59 % | 21 % |
| Global | Todas | 29.999 | 100,0 % | 205,7 | 414,6 | -34,4 | 45 % | 18 % |
| ETA real 3–7 min | Limpias | 6.891 | 96,5 % | 79,4 | 161,6 | -7,6 | 30 % | 18 % |
| ETA real 3–7 min | Contaminadas | 250 | 3,5 % | 158,4 | 299,6 | -1,6 | 48 % | 23 % |
| ETA real 3–7 min | Todas | 7.141 | 100,0 % | 82,2 | 166,8 | -7,3 | 31 % | 18 % |

MAE por grupo de contaminación, seen:

| Banda | Grupo | n | MAE (s) |
|---|---|---|---|
| Global | limpia | 28.736 | 98,1 |
| Global | 45–150 m | 529 | 183,9 |
| Global | ≤45 m y otro más cerca | 285 | 206,7 |
| Global | 45–150 m y otro más cerca | 446 | 237,7 |
| 3–7 min | limpia | 6.816 | 52,6 |
| 3–7 min | 45–150 m | 103 | 71,4 |
| 3–7 min | ≤45 m y otro más cerca | 62 | 79,5 |
| 3–7 min | 45–150 m y otro más cerca | 100 | 101,2 |

heldout:

| Banda | Grupo | n | MAE (s) |
|---|---|---|---|
| Global | limpia | 28.811 | 197,6 |
| Global | 45–150 m | 587 | 422,2 |
| Global | ≤45 m y otro más cerca | 368 | 391,0 |
| Global | 45–150 m y otro más cerca | 233 | 367,7 |
| 3–7 min | limpia | 6.891 | 79,4 |
| 3–7 min | 45–150 m | 116 | 137,8 |
| 3–7 min | ≤45 m y otro más cerca | 75 | 168,3 |
| 3–7 min | 45–150 m y otro más cerca | 59 | 186,2 |

MAE por perp máxima del par, para ver si el error crece con la distancia al recorrido. seen:

| Banda | max(perp P, perp F) | n | MAE (s) |
|---|---|---|---|
| Global | 0-10 m | 24.540 | 95,9 |
| Global | 10-20 m | 3.662 | 107,3 |
| Global | 20-45 m | 819 | 162,1 |
| Global | 45-75 m | 364 | 209,5 |
| Global | 75-150 m | 611 | 207,9 |
| 3–7 min | 0-10 m | 5.827 | 51,6 |
| 3–7 min | 10-20 m | 877 | 56,9 |
| 3–7 min | 20-45 m | 174 | 71,2 |
| 3–7 min | 45-75 m | 76 | 73,1 |
| 3–7 min | 75-150 m | 127 | 93,8 |

heldout:

| Banda | max(perp P, perp F) | n | MAE (s) |
|---|---|---|---|
| Global | 0-10 m | 23.604 | 198,1 |
| Global | 10-20 m | 4.576 | 191,9 |
| Global | 20-45 m | 999 | 280,9 |
| Global | 45-75 m | 368 | 352,8 |
| Global | 75-150 m | 452 | 450,6 |
| 3–7 min | 0-10 m | 5.696 | 80,5 |
| 3–7 min | 10-20 m | 1.054 | 71,4 |
| 3–7 min | 20-45 m | 216 | 122,1 |
| 3–7 min | 45-75 m | 89 | 173,3 |
| 3–7 min | 75-150 m | 86 | 134,3 |

Lectura: las filas sucias tienen **aproximadamente el doble de error** (global: seen 208 s contra 98 s; heldout 402 contra 198; banda 3–7 min: 85 contra 53 s en seen y 158 contra 79 s en heldout). El error crece de forma monótona con la perp (banda 3–7 min, seen: 52 s a ≤ 10 m, 71 s a 20–45 m, 94 s a 75–150 m). Pero son solo 4,2 % (seen) y 4,0 % (heldout) de las filas: sacarlas bajaría el MAE global 4,5 % (seen) y 3,9 % (heldout), y en la banda 3–7 min 2,2 % y 3,4 %. Advertencia: no se puede separar «etiqueta ruidosa» de «situación difícil»; las filas lejos del recorrido son también las de desvíos, cabeceras y cruces, donde el modelo yerra más aunque el recorrido fuera el correcto.

## 7. Ejemplos para mirar en el mapa

Hora local = UTC−3; el día es el del archivo de grabación. Lat/lon es la posición del ping indicado (en A y D el primer ping con el problema; en B, C y E el primer ping del viaje o del corte). Coche = `label` de la API (`<n>-<sufijo>`).

**A. Pings a 45–150 m con otro recorrido más cerca (calle paralela u otro ramal)**

| Línea | Coche (label) | Día y hora local | Lat, lon | Qué pasó |
|---|---|---|---|---|
| 151 | 454-4852 | 2026-08-06 13:30:32 | -34.6092, -58.39638 | Viaje de 70 pings: 21 de 66 válidos a 45–150 m del recorrido 19481774 (en 20 hay otro más cerca; medianas 14,0 m contra 12,7 m del 4020922): ramales casi superpuestos. |
| 39 | 1-1350 | 2026-10-05 21:27:38 | -34.61938, -58.38015 | 25 de 71 pings válidos a 45–150 m del 382202 (39A), todos con el 382208 (39B) más cerca; medianas 7,1 y 11,6 m. |
| 92 | 22-131 | 2026-09-25 07:13:00 | -34.6182, -58.44866 | 22 de 60 pings a 45–150 m del 6750274, todos con otro recorrido más cerca (medianas 6,4 y 22,2 m). El viaje termina por salida del recorrido. |
| 108 | 2443-4868 | 2026-08-26 18:22:54 | -34.63845, -58.52569 | 26 de 77 pings a 45–150 m del 4240252, todos con el sentido opuesto (4237146) más cerca; medianas 4,4 y 19,3 m. Termina detenido. |

**B. Asignación frágil: el sentido opuesto del mismo ramal tiene casi la misma perp**

| Línea | Coche (label) | Día y hora local | Lat, lon | Qué pasó |
|---|---|---|---|---|
| 108 | 2414-4868 | 2026-06-15 18:21:00 | -34.60481, -58.51026 | Viaje de 21 pings. Mediana 8,4 m al recorrido elegido (4240252) y 10,2 m al sentido opuesto (4237146): la geometría no decide; decide el avance hacia adelante (≥ 60 %). |
| 168 | 3005-133 | 2026-09-17 23:19:36 | -34.46087, -58.50668 | 36 pings; medianas 3,0 m (4681272) y 7,1 m (5188890, sentido opuesto). Misma situación. |

**C. Recorrido elegido peor que el opuesto (sentido equivocado a nivel de viaje)**

| Línea | Coche (label) | Día y hora local | Lat, lon | Qué pasó |
|---|---|---|---|---|
| 128 | 8713-77 | 2026-05-11 15:04:56 | -34.5815, -58.41966 | Se eligió el 374958 con mediana de 101 m (167 de 176 pings a 45–150 m); el 374959, sentido opuesto, tenía 5,0 m. El coche circula por una calle y el recorrido elegido pasa por la paralela. |
| 42 | 35-1338 | 2026-04-05 17:59:38 | -34.55628, -58.4478 | Elegido 3464448, mediana 104 m; el sentido opuesto (3464362) tenía 3,6 m. Termina por inversión de sentido. |
| 106 | 4565-1343 | 2026-08-24 17:22:28 | -34.59876, -58.43995 | Elegido 3663267, mediana 143 m; el sentido opuesto (3008238) tenía 19,0 m. Termina por salida del recorrido. |

**D. Retroceso de la distancia a lo largo > 150 m**

| Línea | Coche (label) | Día y hora local | Lat, lon | Qué pasó |
|---|---|---|---|---|
| 42 | 52-1338 | 2026-05-07 13:47:46 | -34.54064, -58.44893 | Viaje de 245 pings con solo 33 válidos (mediana 159 m al elegido): 22 retrocesos > 150 m; la proyección salta entre tramos. |
| 92 | 37-131 | 2026-08-03 21:20:22 | -34.62997, -58.46709 | 61 pings, 57 válidos, mediana 6,0 m: 18 retrocesos > 150 m aun con buen ajuste; la proyección pasa a otro pasaje del recorrido. |

**E. Segmentador: con 150 m un viaje, con 45 m un corte en este punto**

| Línea | Coche (label) | Día y hora local | Lat, lon | Qué pasó |
|---|---|---|---|---|
| 12 | 50-4756 | 2026-07-14 11:58:56 | -34.57781, -58.42761 | Con 150 m: un viaje (370813, termina por inversión). Con 45 m: el tramo se reparte en dos viajes que se cortan en este ping (19336740 y luego 370813). |
| 151 | 419-4852 | 2026-08-12 15:25:46 | -34.62758, -58.38049 | Con 150 m: un viaje que termina por inversión (19481774). Con 45 m: corte por hueco no unido y un viaje nuevo (4020850) que arranca después. |
| 26 | 253-1336 | 2026-09-16 23:20:18 | -34.59413, -58.37338 | Con 150 m: un viaje hasta fin de datos (23555). Con 45 m: se parte en este ping, entre 23305 y 23555. |
| 151 | 455-4852 | 2026-09-16 11:09:38 | -34.62697, -58.3909 | Con 150 m: un viaje (4020850). Con 45 m: salida del recorrido y se parte entre 19481774 y 19481773. |

## 8. Conclusión

1. **¿Error de datos relevante en el entrenamiento? No en volumen.** El 96,2 % de las filas es limpia (ruido GPS real: p50 3,5 m, p95 14,5 m); el 3,8 % está sucia (2,9 % con P o F a 45–150 m, de las cuales 45 % con otro recorrido más cerca, 59 % de ellos el sentido opuesto), y el recorrido elegido es claramente peor que otro en 0,12 % de los viajes. La asignación ex post con el viaje completo es mucho más limpia que el criterio en vivo de 150 m.
2. **Umbral: 45 m** para validez de un ping o fila (98,4 % de los pings válidos; 30 m da 97,8 %), y que el sentido salga del avance sostenido y no de la perp: en 5,9 % de los viajes la perp no distingue ida de vuelta (108, 50, 92). En producción 150 m no sirve porque caben dos calles.
3. **Impacto en el modelo:** las filas sucias tienen el doble de MAE (3–7 min: 85 contra 53 s en seen), pero al ser 4 % de la evaluación, limpiarlas mejora el MAE solo 2–5 %; no se puede separar etiqueta ruidosa de situación difícil.
4. **Segmentador:** FIT_M = 45 m no sirve (−42 % de cortes por inversión, 3 veces más por salida del recorrido, +0,9 pp de `start_unknown`); mantener 150 m ahí y usar 45 m solo en la máscara de filas y en la asignación.
5. **¿Reconstruir v2b con umbral menor? No por esto:** la ganancia esperada es de hasta 5 % del MAE. Si se reconstruye por otra razón, usar máscara de filas de 45 m (segmentador en 150 m) y revisar los retrocesos de 15, 42, 124 y 92 (8,7 % de los viajes en total). El problema de producción (asignación en vivo sin ver el viaje completo) no se mide acá y es el que hay que arreglar en `inference`.

## Archivos

- `diag_asignacion.py` (diagnóstico por día, escribe `_days/*.pkl`), `analizar.py` (agregación, `resumen.json`), `eval_impacto.py` (`eval_impacto.json`), `ejemplos.py` (`ejemplos.txt`), `informe.py` (genera este documento).
- `eval/` (predicciones y métricas del modelo en seen y heldout), `_days/*.rows.parquet` (filas de los días de validación con perp y banderas).
