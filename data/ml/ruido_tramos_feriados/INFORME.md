# Piso de ruido de la verdad, error por tramo y feriados (v4, 2026-11-23)

Modelo: `path_v4_l1_s1` (`data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt`). Eval congelado: `data/ml/v4/eval/eval_seen.parquet` (160.000 filas, 25 días de val 2026-09-15 → 10-14; banda de ETA real 3–7 min = [180, 420) s, n = 34.808). Convenciones: error = real − predicho; negativo = llega antes de lo anunciado; «antes/después > 60 s» = |error| > 60 s con ese signo. MAE de la banda 3–7 min en el eval congelado completo: 55,99 s (global del eval estratificado: 103,08 s). Prioridad Idle, afinidad 8 núcleos; todas las corridas < 3 min. Scripts en `scripts/`, tablas crudas en `A_tablas*.md`, `B_tablas*.md`, `C_tablas.md`, `C_por_dia.csv`, `*_resultados.json`.

## Resumen

| Tema | Resultado |
|---|---|
| A. Ruido de interpolación de la verdad | Error de interpolar un cruce entre dos pings consecutivos (≈ 69 s de intervalo medio): MAE 7,2 s (P90 16,6 s) con la vara por tramos; 14,9 s (P90 32,2 s) con el objetivo en la posición de un ping (caso de coche detenido en parada). Con tránsito lento (< 3 m/s) el doble: 11–24 s de MAE. La separación entre paradas no empeora la interpolación: a igual velocidad, las paradas lejanas dan +0,7 a +1,4 s de MAE (≈ 5–7 %) que las cercanas; el marginal las muestra mejores solo porque van más rápido. Sumado al error del modelo agrega 0,7–2,4 s al MAE de 56 s (1–4 %). |
| B. Error por tramo | Primeros 300 m del shape: 74,5 s de MAE en 3–7 min (70,0 s sin 7 filas con salto de GPS) contra 55 s en el resto. Peso de los primeros 600 m: 4,7 % de las filas y 5,6–6,1 % del error en 3–7 min. Techo de un modelo de cabecera (primeros 600 m con el error del resto): −0,3 s de MAE en 3–7 min emparejado por ETA y distancia (55,5 → 55,2; −0,5 s con la cuenta simple), −0,5 s global emparejado (−2,0 s simple). No justifica un modelo aparte. |
| C. Feriados | Hay diferencia grande y significativa. 2026-10-12 (val) contra lunes no feriados: MAE 3–7 min 58,5 contra 53,3 s (+5,2 s, IC95 4,2–6,4); sesgo −28,7 contra +4,8 s; llega antes > 60 s 28,1 contra 14,7 %. El modelo trata el feriado como lunes; pasarle `dow` = domingo baja el MAE a 43,6 s y llega antes a 10,0 %. |

## A. Piso de ruido de la verdad

### A.0 Dónde se usa la interpolación

- El eval congelado y el dataset v4 (`targets = any`, `meta.json` de cada día) usan como objetivo F un ping real del viaje: `observed_eta_s = ts[F] − ts[P]`, sin interpolar. El ruido de interpolación no está en las cifras del eval congelado (55,99 s en 3–7 min).
- La interpolación está en la verdad del replay (`replay/core.py::crossings_v2`: `tc = t0 + (ds − d0)/(d1 − d0)·dt` entre los dos pings compatibles consecutivos que encierran la parada, `dt` ≤ 600 s, velocidad ≤ 25 m/s + 50 m) y en el dataset de objetivos en paradas (`v2/stop_targets.py::stop_crossings`, misma fórmula; descartado, §7). El replay da 54,8 s por coche contra 53,9 s de la vara del modelo (ARQUITECTURA §7, «Descomposición»): +0,9 s, coherente con el ruido estimado abajo.
- `v2/stop_targets.interpolation_noise` ya medía el ping central de ternas: P50 17 s, P90 42 s (ARQUITECTURA §7, objetivos en paradas). Esta medición lo extiende por estratos y extrapola al espaciado real.

### A.1 Método

- Fuente: cadenas de hasta 10 pings válidos consecutivos que guarda cada fila (`traj_flat`: distancia/L, velocidad, dt) de `data/ml/v4/daily`, 16 días (9 hábiles, 4 sábados, 3 domingos entre 2026-08-04 y 10-13), 40.000 cadenas por día, una por ping P (deduplicado por línea, shape, ts, distancia), 129 líneas. No se reprocesó el NDJSON. Pings compatibles con el shape (los del pipeline geo2/geo3), distancia no decreciente, cada intervalo con 0 < dt ≤ 300 s y velocidad ≤ 25 m/s + 50 m, avance p0–p2 ≥ 30 m.
- Para cada cadena y cada salto k = 2, 3, 4, 6, 8 intervalos entre p0 y p2 (k = 2 es la terna p0, p1, p2 consecutiva; k = 4, 6 y 8 equivalen a saltar 1, 2 y 3 pings a cada lado del ping central; k = 3 es asimétrico; se evalúan todos los pings intermedios, no solo el central): cruce estimado con p0–p2 (lineal en la distancia, igual que el pipeline) contra la referencia que usa los pings intermedios (lineal por tramos).
  - Modo `obj`: objetivo en f = 0,2 / 0,4 / 0,6 / 0,8 del tramo p0–p2 (la definición pedida). Referencia = interpolación por tramos, que es en sí una interpolación: subestima el error en posiciones sin ping.
  - Modo `ping`: objetivo en la distancia de cada ping intermedio; la referencia es la hora observada de ese ping. Sobrerrepresenta las posiciones donde el coche se detiene (muchos pings a la misma distancia), que son las de una parada con dársena y semáforo. Es el caso del cruce de una parada con espera.
- Extrapolación: por estrato, MAE y P90 contra la amplitud temporal media S de p0–p2 para k = 2…8, ajuste log-log (MAE ∝ S^b), evaluado en el intervalo real medio del estrato (S/k). El replay interpola en un solo intervalo: p0–p1 consecutivos.
- Total: 21,0 M de evaluaciones de error (obj 11,3 M; ping 9,7 M). Los exponentes son b = 0,77 (obj) y 0,42 (ping); nunca se observa un intervalo único, la extrapolación a S = 1 intervalo no se puede validar.

Espaciado real entre pings consecutivos (muestra de 3,2 M de intervalos con avance ≥ 0): P10 54 s, P25 60 s, P50 60 s, P75 64 s, P90 120 s, P99 234 s; media 70,7 s. 78 % ≤ 75 s. Distancia mediana por intervalo 310 m.

### A.2 Total por salto (error absoluto de la hora de cruce, s)

| k | S medio (s) | obj MAE | obj P50 | obj P90 | obj P99 | ping MAE | ping P50 | ping P90 | ping P99 |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 138,6 | 12,0 | 8,4 | 27,2 | 50,8 | 20,3 | 16,1 | 44,1 | 77,0 |
| 3 | 207,5 | 17,4 | 13,0 | 37,4 | 75,0 | 23,3 | 18,4 | 49,2 | 92,5 |
| 4 | 276,3 | 21,6 | 16,5 | 45,7 | 90,8 | 26,0 | 20,5 | 54,5 | 105,8 |
| 6 | 413,9 | 28,8 | 22,5 | 60,5 | 120,0 | 31,2 | 24,3 | 65,6 | 129,0 |
| 8 | 551,4 | 35,1 | 27,3 | 74,3 | 146,0 | 36,0 | 27,7 | 76,9 | 151,2 |
| **1 intervalo (extrap., S = 69 s)** | 69 | **7,2** | 4,9 | **16,6** | — | **14,9** | 12,0 | **32,2** | — |

Con S = 60 s (intervalo mediano): obj 6,5 s (P90 15,0), ping 14,1 s (P90 30,4). El sesgo (hora estimada − observada) es ≈ 0 (−0,4 a +0,1 s): el ruido es simétrico.

### A.3 Por estrato (k = 2 medido y extrapolación a 1 intervalo, s)

Columnas: n = evaluaciones `obj` con k = 2; MAE y P90 medidos con k = 2; «extrap.» = valor ajustado al intervalo real medio del estrato; «% > 30 s» = fracción de |error| > 30 s con k = 2 (modo ping).

**Espaciado temporal medio entre pings (S/k)**

| estrato | n | obj MAE k=2 | obj P90 k=2 | obj MAE extrap. | obj P90 extrap. | ping MAE k=2 | ping P90 k=2 | ping MAE extrap. | ping P90 extrap. | ping % > 30 s |
|---|---|---|---|---|---|---|---|---|---|---|
| < 50 s | 185.660 | 8,8 | 19,9 | 4,7 | 11,3 | 15,2 | 29,9 | 12,0 | 21,9 | 9,5 |
| 50–65 s | 1.534.876 | 10,9 | 24,6 | 6,8 | 15,8 | 18,6 | 40,7 | 14,0 | 30,9 | 20,7 |
| 65–90 s | 318.124 | 13,5 | 31,2 | 7,8 | 18,6 | 22,9 | 49,3 | 16,5 | 35,1 | 28,5 |
| 90–130 s | 378.472 | 14,9 | 33,6 | 8,6 | 19,9 | 25,2 | 53,5 | 17,8 | 37,4 | 31,7 |
| ≥ 130 s | 60.488 | 21,5 | 48,0 | 9,9 | 21,9 | 36,4 | 76,9 | 20,7 | 42,8 | 44,9 |

**Distancia entre pings (D/k)**

| estrato | n | obj MAE k=2 | obj P90 k=2 | obj MAE extrap. | obj P90 extrap. | ping MAE k=2 | ping P90 k=2 | ping MAE extrap. | ping P90 extrap. | ping % > 30 s |
|---|---|---|---|---|---|---|---|---|---|---|
| < 150 m | 244.112 | 16,6 | 36,0 | 9,3 | 20,0 | 29,0 | 55,8 | 20,0 | 35,9 | 40,4 |
| 150–300 m | 859.596 | 13,2 | 29,4 | 8,3 | 18,6 | 22,5 | 46,7 | 17,1 | 34,7 | 27,6 |
| 300–500 m | 914.840 | 10,6 | 23,8 | 6,4 | 14,6 | 17,8 | 37,9 | 13,0 | 27,5 | 17,7 |
| ≥ 500 m | 459.072 | 10,0 | 23,4 | 4,8 | 11,5 | 16,8 | 37,6 | 10,0 | 22,6 | 16,3 |

**Velocidad media del tramo (D/S; proxy de tránsito)**

| estrato | n | obj MAE k=2 | obj P90 k=2 | obj MAE extrap. | obj P90 extrap. | ping MAE k=2 | ping P90 k=2 | ping MAE extrap. | ping P90 extrap. | ping % > 30 s |
|---|---|---|---|---|---|---|---|---|---|---|
| < 1,5 m/s | 85.984 | 20,6 | 44,1 | 10,9 | 23,5 | 35,8 | 62,3 | 23,7 | 40,4 | 49,5 |
| 1,5–3 m/s | 348.052 | 16,6 | 36,2 | 9,8 | 21,2 | 28,8 | 55,6 | 20,8 | 37,7 | 40,5 |
| 3–5 m/s | 870.808 | 12,9 | 28,6 | 7,9 | 17,7 | 22,0 | 45,4 | 16,4 | 33,2 | 26,7 |
| 5–8 m/s | 856.684 | 9,8 | 22,1 | 5,8 | 13,3 | 16,5 | 35,0 | 11,7 | 24,9 | 15,0 |
| ≥ 8 m/s | 316.092 | 7,7 | 18,0 | 3,9 | 9,3 | 12,9 | 28,8 | 7,9 | 17,7 | 9,0 |

**Separación entre las paradas del shape que rodean al objetivo (proxy de paradas lejanas / cercanas)**

| estrato | n | obj MAE k=2 | obj P90 k=2 | obj MAE extrap. | obj P90 extrap. | ping MAE k=2 | ping P90 k=2 | ping MAE extrap. | ping P90 extrap. | ping % > 30 s |
|---|---|---|---|---|---|---|---|---|---|---|
| < 250 m | 304.233 | 11,5 | 26,1 | 7,0 | 16,2 | 19,8 | 43,1 | 14,6 | 31,9 | 21,7 |
| 250–400 m | 683.542 | 12,2 | 27,6 | 7,5 | 17,0 | 20,8 | 44,8 | 15,4 | 32,9 | 24,1 |
| 400–700 m | 626.522 | 12,6 | 28,2 | 7,8 | 17,5 | 21,4 | 45,2 | 16,0 | 33,4 | 25,0 |
| 0,7–1,5 km | 307.228 | 12,6 | 28,4 | 7,7 | 17,7 | 21,3 | 45,4 | 15,8 | 33,4 | 25,3 |
| ≥ 1,5 km | 461.599 | 10,9 | 25,1 | 6,2 | 14,6 | 18,4 | 41,3 | 12,8 | 28,8 | 19,5 |
| sin paradas / sin dato | 94.496 | 10,9 | 24,9 | 6,4 | 14,9 | 18,6 | 41,5 | 13,3 | 30,0 | 19,0 |

**Paradas por km dentro del tramo p0–p2**

| estrato | n | obj MAE k=2 | obj P90 k=2 | obj MAE extrap. | obj P90 extrap. | ping MAE k=2 | ping P90 k=2 | ping MAE extrap. | ping P90 extrap. | ping % > 30 s |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 en el tramo | 637.628 | 12,0 | 27,9 | 7,5 | 17,6 | 20,5 | 46,0 | 15,4 | 34,7 | 23,6 |
| < 2 por km | 510.324 | 11,4 | 25,5 | 6,5 | 14,8 | 19,2 | 40,6 | 13,5 | 28,1 | 20,5 |
| 2–4 por km | 932.984 | 12,0 | 26,8 | 7,2 | 16,4 | 20,3 | 43,3 | 14,9 | 31,5 | 23,0 |
| ≥ 4 por km | 396.348 | 12,7 | 29,2 | 8,2 | 19,0 | 21,7 | 47,2 | 16,9 | 36,9 | 25,9 |

**Franja horaria (hora local BA)**

| estrato | n | obj MAE k=2 | obj P90 k=2 | obj MAE extrap. | obj P90 extrap. | ping MAE k=2 | ping P90 k=2 | ping MAE extrap. | ping P90 extrap. | ping % > 30 s |
|---|---|---|---|---|---|---|---|---|---|---|
| fin de semana | 1.090.692 | 11,0 | 24,6 | 6,8 | 15,5 | 18,6 | 40,2 | 13,9 | 30,3 | 19,7 |
| hábil noche / madrugada | 350.008 | 10,7 | 24,0 | 6,5 | 15,1 | 18,0 | 39,3 | 13,4 | 29,4 | 18,8 |
| hábil valle 10–17 | 566.532 | 13,4 | 30,5 | 8,0 | 18,5 | 22,8 | 48,7 | 16,5 | 34,5 | 28,0 |
| hábil pico 7–10 | 226.648 | 13,7 | 31,3 | 8,1 | 18,6 | 23,4 | 50,0 | 16,7 | 34,8 | 28,5 |
| hábil pico 17–20 | 243.740 | 13,3 | 30,5 | 7,8 | 18,1 | 22,7 | 48,5 | 16,2 | 33,8 | 28,0 |

**Distancia del objetivo al ping usado más cercano (p0 o p2)**

| estrato | n | obj MAE k=2 | obj MAE extrap. | ping MAE k=2 | ping MAE extrap. | ping % > 30 s |
|---|---|---|---|---|---|---|
| < 50 m | 96.726 | 16,8 | 7,8 | 42,2 | 38,5 | 64,9 |
| 50–100 m | 369.780 | 13,3 | 6,8 | 29,9 | 25,3 | 52,0 |
| 100–200 m | 930.708 | 11,3 | 4,7 | 20,9 | 16,6 | 23,0 |
| ≥ 200 m | 1.080.406 | 11,6 | 6,5 | 13,7 | 8,6 | 8,9 |

**Velocidad × separación de paradas, MAE k = 2 modo `obj` (s)**

| velocidad | < 250 m | 250–400 m | 400–700 m | 0,7–1,5 km | ≥ 1,5 km |
|---|---|---|---|---|---|
| < 1,5 m/s | 20,9 | 19,5 | 20,8 | 21,1 | 21,8 |
| 1,5–3 m/s | 16,1 | 16,2 | 16,8 | 17,1 | 17,5 |
| 3–5 m/s | 11,8 | 12,6 | 13,5 | 13,9 | 13,0 |
| 5–8 m/s | 8,6 | 9,3 | 10,4 | 11,3 | 9,7 |
| ≥ 8 m/s | 7,2 | 7,3 | 7,4 | 8,1 | 7,9 |

### A.4 Lectura sobre las dudas del usuario

- **Paradas lejanas.** La separación entre paradas no empeora la interpolación: de < 250 m a ≥ 1,5 km el MAE extrapolado baja de 7,0 a 6,2 s (obj) y de 14,6 a 12,8 s (ping), porque los tramos con paradas lejanas son más rápidos. A igual velocidad (tabla cruzada) las paradas ≥ 1,5 km dan +0,7 a +1,4 s de MAE (obj, k = 2) que las < 250 m, y la dispersión entre columnas es ≤ 2,7 s: el efecto propio de la separación es chico y de signo contrario al marginal. Lo que sí importa es la distancia del objetivo al ping más cercano cuando el coche está quieto (modo `ping`, < 50 m: 38,5 s, 65 % de los casos con error > 30 s a k = 2): un cruce en una parada con espera es ambiguo entre llegada y salida, y la interpolación lo coloca en cualquier punto de la espera.
- **Tránsito.** Es el factor dominante. Por debajo de 3 m/s el MAE extrapolado es 2,5–3,0 veces el de ≥ 8 m/s (obj 9,8–10,9 contra 3,9 s; ping 20,8–23,7 contra 7,9 s) y el P90 llega a 38–40 s (ping). En picos hábiles 7–10 y 17–20 el MAE es 15–20 % mayor que en fin de semana (obj 8,1 y 7,8 contra 6,8 s; ping 16,7 y 16,2 contra 13,9 s). Un intervalo ≥ 130 s entre pings da 1,7–2,1 veces el error de uno < 50 s (ping 20,7 contra 12,0 s; obj 9,9 contra 4,7 s).
- **Piso en la vara.** Para el cruce del replay con un intervalo típico de 60–70 s el error de la hora de verdad es ≈ 7 s (P90 16 s) cuando el coche avanza y ≈ 15 s (P90 32 s) cuando se detiene en el objetivo; con tránsito lento (< 3 m/s) 10–11 s (obj) o 21–24 s (ping). Frente a la banda de 3–7 min (MAE 56 s, P90 117 s) es un componente chico.

### A.5 Qué parte del MAE de ~54–56 s puede ser ruido de la verdad

Suma de un ruido independiente (muestras empíricas del k = 2 reescaladas al intervalo real) al error observado del modelo (eval congelado, real − predicho):

| ruido agregado | MAE del ruido | Δ MAE banda 3–7 min (56,0 s) | Δ MAE global (103,1 s) |
|---|---|---|---|
| interpolación 1 intervalo, `obj` | 7,2 s | +0,7 s | +0,7 s |
| interpolación 1 intervalo, `ping` | 14,9 s | +2,4 s | +2,3 s |
| hipotético: retraso del sello por lote U[0, 60) s independiente en P y F | 20,0 s | +3,7 s | +3,4 s |
| gaussiano, MAE 10 / 20 / 30 s | 10 / 20 / 30 s | +1,0 / +3,8 / +8,3 s | +1,1 / +3,5 / +7,2 s |

- El eval congelado no contiene ruido de interpolación (A.0); el componente que sí contiene es el del sello por lote de CABA, que no se puede medir sin verdad de campo. La fila «hipotético» no es una medición: supone un retraso uniforme de 0–60 s independiente en cada ping y sirve de orden de magnitud (≈ 4 s, ≈ 7 % del MAE).
- En la verdad del replay (cruce interpolado) el ruido de interpolación suma 0,7–2,4 s a un MAE por coche de ~54 s: 1–4 %. La diferencia medida entre replay y vara del modelo (+0,9 s) cae dentro de ese rango.
- Con ruido independiente, quitarlo del error observado reduce el MAE en a lo sumo el Δ de la tabla (la resta pesa menos que la suma): ≤ 0,7–2,4 s por interpolación (replay) y ≈ 4 s bajo el supuesto hipotético del sello por lote. El ruido de verdad medible no explica el MAE de la banda 3–7 min.

## B. Error del modelo por tramo (eval congelado seen, banda 3–7 min y global)

Se informan las tablas sin las 236 filas con velocidad implícita `dist_remaining/ETA` > 25 m/s (0,15 %; 50 de ellas en 3–7 min). Son saltos de GPS o ETAs imposibles (por ejemplo, 13 filas con 3–7 min de ETA a > 10 km) y suman 0,5 s de los 55,99 s de la banda (55,49 s sin ellas). Con ellas, tablas en `B_tablas.md`. El eval está estratificado por ETA (40.000 filas por bucket): el «global» pesa más las ETAs largas que el tráfico real; el peso real de cada tramo se da con una muestra natural (`muestra_dias.parquet`: 100.000 filas válidas por día, 25 días de val, 2,5 M filas, mismo modelo).

Sesgo = real − predicho (negativo: llega antes). `n` y métricas con 3–7 min a la izquierda, global a la derecha.

### B.1 Distancia recorrida desde el inicio del shape de P (`dist_along_m`)

| tramo | n 3–7 | MAE | sesgo | P90 | antes > 60 s | después > 60 s | n glob | MAE glob | sesgo glob | P90 glob | antes glob | después glob |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0–300 m | 1.069 | 70,0 | +18,9 | 148,6 | 15,2 % | 27,1 % | 6.064 | 136,1 | +38,6 | 300,1 | 24,3 % | 35,4 % |
| 300–600 m | 563 | 59,4 | +6,5 | 121,6 | 16,7 % | 21,7 % | 3.426 | 130,8 | +34,6 | 295,6 | 24,6 % | 31,8 % |
| 600–1000 m | 681 | 51,8 | +9,3 | 110,2 | 13,2 % | 19,7 % | 4.007 | 116,8 | +22,5 | 268,3 | 24,4 % | 30,0 % |
| 1–2 km | 1.562 | 55,9 | +5,1 | 114,2 | 15,9 % | 21,5 % | 9.323 | 116,6 | +22,3 | 261,6 | 24,6 % | 30,3 % |
| 2–5 km | 4.671 | 54,9 | +3,9 | 117,3 | 15,5 % | 18,7 % | 26.025 | 111,2 | +19,7 | 249,4 | 23,5 % | 29,2 % |
| > 5 km | 26.212 | 55,0 | +10,5 | 116,8 | 13,3 % | 21,0 % | 110.919 | 96,6 | +26,6 | 209,3 | 18,8 % | 27,2 % |

Peso real (muestra natural, val, 2,5 M filas; 3–7 min: 679.190 filas): 0–300 m 3,1 % de las filas (MAE 62,7 s en 3–7 min, 113,7 s global); 300–600 m 1,6 %; 600–1000 m 1,9 %; 1–2 km 4,5 %; 2–5 km 13,3 %; > 5 km 75,5 %. Los primeros 300 m cuestan +12 a +15 s de MAE en 3–7 min frente al resto (50,8 s en la muestra natural).

### B.2 `start_unknown`

| grupo | n 3–7 | MAE | sesgo | P90 | antes > 60 s | después > 60 s | n glob | MAE glob | sesgo glob | antes glob | después glob |
|---|---|---|---|---|---|---|---|---|---|---|---|
| start_unknown = 0 | 25.823 | 53,9 | +9,7 | 114,7 | 13,5 % | 20,5 % | 120.777 | 98,4 | +21,4 | 20,6 % | 27,8 % |
| start_unknown = 1 | 8.935 | 60,1 | +9,1 | 127,8 | 14,8 % | 22,1 % | 38.987 | 117,0 | +39,2 | 19,8 % | 29,3 % |

`start_unknown = 1` casi no ocurre en cabecera (< 0,5 % de las filas de los primeros 1000 m): el viaje no arranca en su cabecera. En cabecera `start_unknown = 0` y `time_since_start` es real.

### B.3 `time_since_start` (solo viajes con inicio conocido; el resto cae en `start_unknown`)

| tiempo desde el inicio | n 3–7 | MAE | sesgo | P90 | antes > 60 s | después > 60 s | n glob | MAE glob | sesgo glob |
|---|---|---|---|---|---|---|---|---|---|
| 0–1 min | 818 | 71,1 | +17,6 | 149,3 | 15,9 % | 27,9 % | 4.690 | 142,7 | +44,7 |
| 1–3 min | 956 | 55,6 | +8,6 | 115,5 | 14,4 % | 20,9 % | 5.362 | 118,3 | +25,7 |
| 3–7 min | 1.718 | 55,0 | +8,8 | 113,8 | 13,7 % | 20,5 % | 10.234 | 116,7 | +23,4 |
| 7–15 min | 3.184 | 52,1 | +7,9 | 112,4 | 13,6 % | 19,2 % | 18.011 | 106,8 | +17,4 |
| 15–30 min | 5.350 | 53,8 | +6,7 | 115,1 | 14,7 % | 19,5 % | 27.268 | 100,2 | +16,0 |
| > 30 min | 13.797 | 53,1 | +11,0 | 112,5 | 12,8 % | 20,7 % | 55.212 | 85,6 | +22,6 |
| start_unknown | 8.935 | 60,1 | +9,1 | 127,8 | 14,8 % | 22,1 % | 38.987 | 117,0 | +39,2 |

### B.4 Distancia restante al objetivo

| restante | n 3–7 | MAE | sesgo | P90 | antes > 60 s | después > 60 s | n glob | MAE glob | sesgo glob | antes glob | después glob |
|---|---|---|---|---|---|---|---|---|---|---|---|
| < 0,5 km | 2.144 | 107,9 | +98,0 | 216,0 | 2,1 % | 66,6 % | 18.451 | 61,7 | +40,6 | 3,3 % | 14,9 % |
| 0,5–1 km | 10.600 | 56,1 | +33,4 | 118,8 | 5,9 % | 30,6 % | 21.165 | 69,9 | +37,4 | 8,1 % | 22,9 % |
| 1–2 km | 17.428 | 47,2 | −4,1 | 99,2 | 15,8 % | 13,0 % | 30.419 | 73,7 | +29,1 | 13,6 % | 25,7 % |
| 2–5 km | 4.223 | 60,8 | −34,6 | 129,0 | 30,9 % | 7,3 % | 45.533 | 93,2 | +17,3 | 24,2 % | 29,1 % |
| 5–10 km | 363 | 63,5 | −40,6 | 133,3 | 23,7 % | 5,0 % | 24.770 | 135,8 | +17,8 | 32,3 % | 34,5 % |
| > 10 km | — | — | — | — | — | — | 19.426 | 204,6 | +23,5 | 36,5 % | 40,2 % |

La banda 3–7 min se define por la ETA real: condiciona el resultado y mezcla distancias; los sesgos por distancia restante dentro de la banda (+98 s a < 0,5 km; −35 s a 2–5 km) son efecto de esa selección (un coche a < 0,5 km con ETA de 3–7 min está detenido o muy lento; a 2–5 km está yendo rápido), no sesgo del modelo.

### B.5 Cabecera detenida (primeros 600 m de P)

No hay una columna que diga «coche detenido en cabecera». Se derivó de la trayectoria de la fila: detenido = velocidad de P ≤ 0,5 m/s y al menos 1 ping previo consecutivo a < 30 m de P (2–3 pings quietos incluyendo P, ≈ 1–3 min) o ≥ 4 pings quietos (≥ 3 min); 10 pings de historia como máximo.

| estado en los primeros 600 m | n glob | MAE glob | sesgo glob | antes > 60 s | después > 60 s | n 3–7 | MAE 3–7 | sesgo 3–7 |
|---|---|---|---|---|---|---|---|---|
| en movimiento | 9.008 | 129,3 | +31,4 | 24,8 % | 33,2 % | 1.542 | 65,0 | +11,9 |
| detenido 2–3 pings | 402 | 197,9 | +116,7 | 19,2 % | 49,5 % | 84 | 86,9 | +58,0 |
| detenido ≥ 4 pings | 80 | 362,8 | +288,6 | 15,0 % | 63,7 % | 6 | 134,2 | +110,5 |

Resto del recorrido (≥ 600 m), mismo desglose: en movimiento 97,8 s global y 54,2 s en 3–7 min; detenido 2–3 pings 142,3 y 68,8 s; detenido ≥ 4 pings 561,9 y 160,4 s (n 3–7 = 83). El coche detenido es una causa de error en cualquier tramo, con sesgo positivo (llega después de lo anunciado); en cabecera pesa 5,1 % de las filas de los primeros 600 m en el eval (482 de 9.490) y 0,3 % del eval; no explica la diferencia de MAE del tramo (en movimiento, la cabecera también es peor: 65,0 contra 54,2 s).

### B.6 Techo de un modelo específico de cabecera

Reemplazo del error absoluto de las filas con `dist_along_m` < H por el error medio del resto. «Simple» usa el MAE del resto; «por ETA y distancia restante» lo empareja con filas del resto de la misma ETA real (bins de 60–600 s) y la misma distancia restante, que es la estimación correcta (la cabecera tiene otra mezcla de ETA que el resto).

| H | vara | filas | peso filas | peso del error | MAE actual | MAE cabecera | MAE resto | techo simple | techo emparejado | ganancia emparejada |
|---|---|---|---|---|---|---|---|---|---|---|
| 300 m | 3–7 min | 1.069 | 3,1 % | 3,9 % | 55,49 | 70,04 | 55,03 | 55,03 | 55,27 | −0,22 |
| 300 m | global | 6.064 | 3,8 % | 5,0 % | 102,92 | 136,12 | 101,61 | 101,61 | 102,58 | −0,34 |
| 600 m | 3–7 min | 1.632 | 4,7 % | 5,6 % | 55,49 | 66,38 | 54,95 | 54,95 | 55,22 | −0,27 |
| 600 m | global | 9.490 | 5,9 % | 7,8 % | 102,92 | 134,21 | 100,94 | 100,94 | 102,42 | −0,50 |
| 1000 m | 3–7 min | 2.313 | 6,7 % | 7,5 % | 55,49 | 62,09 | 55,02 | 55,02 | 55,24 | −0,25 |
| 1000 m | global | 13.497 | 8,4 % | 10,6 % | 102,92 | 129,06 | 100,51 | 100,51 | 102,49 | −0,43 |

Sobre la muestra natural de val (2,5 M filas; 679.190 en 3–7 min), primeros 600 m: 4,8 % de las filas y 5,5 % del error en 3–7 min; MAE actual 51,13 s, techo 50,71 s (simple) y 50,91 s (emparejado): −0,2 s; global 78,47 → 76,57 (simple) y 77,98 (emparejado): −0,5 s. Con las filas sin filtrar (MAE 3–7 min de 55,99 s) el techo es −0,5 s emparejado y −0,8 s simple.

Lectura B: los primeros 300 m (y el primer minuto: 71,1 s) tienen 12–15 s más de MAE en 3–7 min que el resto, pero pesan 3–5 % de las filas. Un modelo de cabecera perfecto, igual al resto del recorrido, baja el MAE de 3–7 min en 0,2–0,3 s y el global en 0,3–0,5 s (estimación emparejada; hasta −2,0 s global con el cálculo simple, que ignora que las ETAs de cabecera son otras). Está por debajo de la diferencia entre semillas (0,4 s, ARQUITECTURA §7, v4). El sesgo de cabecera es positivo (llega después de lo anunciado, +19 s en 0–300 m), no el error grave. Descartable.

## C. Feriados

### C.1 Feriados nacionales de Argentina 2026 en el rango

`holidays` no está instalado (no se instaló el paquete). Lista explícita, Ley 27.399 y decreto de días puente de 2026 (23-mar, 10-jul, 7-dic):

| fecha | feriado | día | en datos |
|---|---|---|---|
| 2026-08-17 | Paso a la Inmortalidad del Gral. San Martín (trasladable; cae lunes, no se mueve) | lunes | train (805.748 filas válidas contra ~2,2 M un lunes) |
| 2026-10-12 | Día del Respeto a la Diversidad Cultural (trasladable; cae lunes, no se mueve) | lunes | val (788.212 filas) |

Sin feriados ni puentes entre 2026-07-20 y 2026-10-14 aparte de estos dos (9 y 10 de julio quedan antes del inicio de los datos; el 20-nov / 23-nov, después). El volumen de cada uno (~0,8 M filas) es el de un domingo (~0,9 M), lo que confirma la fecha en los datos. Días sin datos en el rango: 07-25 a 07-27, 09-04 a 09-11 (09-03 y 09-12 parciales: 56.646 y 114.847 filas), 09-27 a 10-01. El lunes 2026-09-21 tiene el volumen reducido (1,55 M) por causa no identificada.

### C.2 Datos y método

Muestra natural por día (100.000 filas válidas por día, aleatoria con semilla; `muestra_dias.parquet`) de `data/ml/v4/daily` para los 71 días disponibles, predicha con `path_v4_l1_s1`. Los 25 días de val (09-15 → 10-14) son datos no vistos por el modelo; los días anteriores son de train (el modelo los vio). El eval congelado contiene 2.764 filas del 12-oct (1,7 %); no basta para el análisis por día. Intervalos: bootstrap por cluster (día, línea, ventana de 30 min), 1.000 repeticiones.

### C.3 MAE por tipo de día (media sobre los días del tipo)

| período | tipo de día | días | MAE 3–7 min | sesgo | antes > 60 s | después > 60 s | MAE global | sesgo global | antes global |
|---|---|---|---|---|---|---|---|---|---|
| val | **feriado (lunes 12-oct)** | 1 | **58,5** | **−28,7** | **28,1 %** | 8,0 % | **111,2** | **−70,4** | **33,7 %** |
| val | lunes no feriados (21-sep, 5-oct) | 2 | 53,3 | +4,8 | 14,7 % | 18,7 % | 78,7 | +6,4 | 18,8 % |
| val | hábiles mar–vie | 15 | 53,8 | +8,4 | 13,3 % | 20,1 % | 81,1 | +18,5 | 16,5 % |
| val | sábados | 4 | 45,9 | +7,1 | 10,7 % | 15,5 % | 69,0 | +13,0 | 14,3 % |
| val | domingos (20-sep, 4-oct, 11-oct) | 3 | 44,9 | +8,4 | 9,8 % | 15,3 % | 69,2 | +17,1 | 13,2 % |
| train | **feriado (lunes 17-ago, en muestra)** | 1 | **57,3** | **−28,0** | **27,6 %** | 7,7 % | **112,0** | **−70,2** | **33,8 %** |
| train | lunes no feriados (6) | 6 | 51,4 | +5,3 | 13,1 % | 17,7 % | 78,8 | +12,5 | 17,0 % |
| train | hábiles mar–vie (27) | 27 | 50,9 | +5,1 | 13,2 % | 17,3 % | 80,3 | +12,4 | 17,2 % |
| train | domingos (6) | 6 | 43,7 | +7,7 | 9,5 % | 14,7 % | 64,8 | +14,0 | 13,0 % |

### C.4 Diferencia del feriado contra cada referencia (banda 3–7 min)

| feriado | contra | días ref. | MAE fer. | MAE ref. | dif. MAE (IC95) | sesgo fer. | sesgo ref. | dif. sesgo (IC95) |
|---|---|---|---|---|---|---|---|---|
| 12-oct (val) | lunes no feriados | 2 | 58,5 | 53,3 | +5,2 (4,2 a 6,4) | −28,7 | +4,8 | −33,5 (−35,0 a −32,0) |
| 12-oct (val) | domingos | 3 | 58,5 | 44,9 | +13,6 (12,5 a 14,7) | −28,7 | +8,4 | −37,1 (−38,5 a −35,7) |
| 12-oct (val) | hábiles mar–vie | 15 | 58,5 | 53,8 | +4,8 (3,8 a 5,8) | −28,7 | +8,4 | −37,1 (−38,5 a −35,9) |
| 17-ago (train) | lunes no feriados | 6 | 57,3 | 51,4 | +5,9 (4,9 a 6,8) | −28,0 | +5,3 | −33,4 (−34,8 a −32,1) |
| 17-ago (train) | domingos | 6 | 57,3 | 43,7 | +13,6 (12,7 a 14,5) | −28,0 | +7,7 | −35,8 (−37,1 a −34,5) |

- Estandarizado por línea × bloque horario de 4 h (misma composición que el feriado): MAE de referencia 51,9 s (lunes) y 44,7 s (domingos) contra 58,5 s del 12-oct; sesgo de referencia +5,2 y +8,3 s contra −28,7 s. La composición no explica la diferencia.
- Ruido entre días: MAE de 3–7 min de los 17 hábiles de val: media 53,7 s, sd 1,4 s (50,2–56,3). El feriado (58,5) queda 3,3 sd sobre la media de hábiles; el 17-ago lo repite con +5,9 s en train.
- Contraste de sesgo: el feriado llega antes de lo anunciado en promedio 28 s (28 % de las filas con > 60 s antes, el doble que un lunes) y el domingo/lunes normal llegan después en promedio (+5 a +8 s). Es un error sistemático, no ruido.

### C.5 Causa y contrafactual

El modelo recibe `dow` = lunes el 12-oct y predice la velocidad de un lunes laboral; el tránsito de un feriado es el de un domingo. La app tampoco tiene ningún tratamiento de feriados (`proyectoconsola/lib/eta_predict.js` calcula `dow` con el calendario). Reemplazando `dow` por domingo (6) en la entrada, sin reentrenar, mismas 100.000 filas por día:

| día | `dow` | MAE 3–7 min | sesgo 3–7 | antes > 60 s | después > 60 s | MAE global | sesgo global |
|---|---|---|---|---|---|---|---|
| 12-oct (val) | lunes (hoy) | 58,5 | −28,7 | 28,1 % | 8,0 % | 111,2 | −70,4 |
| 12-oct (val) | domingo | 43,6 | +6,9 | 10,0 % | 14,5 % | 64,6 | +11,7 |
| 17-ago (train) | lunes (hoy) | 57,3 | −28,0 | 27,5 % | 7,7 % | 112,0 | −70,2 |
| 17-ago (train) | domingo | 42,8 | +6,2 | 9,8 % | 14,0 % | 64,2 | +11,9 |

Con `dow` = domingo el feriado queda en el nivel de un domingo (44,9 s en val). El 17-ago estuvo en train con `dow` = lunes (1 de 71 días) y el modelo no lo aprendió: su error es igual al del 12-oct fuera de muestra. No se entrenó un modelo con día-tipo; la prueba es solo cambiar la entrada.

### C.6 Lectura

- Diferencia significativa en MAE (+5 s contra lunes, +14 s contra domingos), en sesgo (−29 s contra +5 a +8 s) y en llega antes > 60 s (28 contra 10–15 %), en los dos feriados, uno de ellos fuera de muestra.
- Alcance: 2 feriados en 71 días con datos (3 % de los días). Sobre el eval congelado el 12-oct pesa 1,7 % de las filas.
- Acción medible sin reentrenar: tratar los feriados nacionales como `dow` = domingo (en la app y en el replay; en el dataset, un día-tipo en el pipeline de entrenamiento es la versión estructural). No se tocó `proyectoconsola` ni ARQUITECTURA.md.

## Reproducción

```
PY=C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe   # PYTHONPATH=. desde "prediccion colectivos"
$PY data/ml/ruido_tramos_feriados/scripts/c1_muestra_dias.py 100000       # muestra natural por día + predicción
$PY data/ml/ruido_tramos_feriados/scripts/a1_extraer_cadenas.py 40000     # errores de interpolación
$PY data/ml/ruido_tramos_feriados/scripts/a2_tablas.py; ...a3_ruido_vs_mae.py; ...a4_merge.py
$PY data/ml/ruido_tramos_feriados/scripts/b_tramos.py [plaus]
$PY data/ml/ruido_tramos_feriados/scripts/c2_feriados.py
```

Todos corren con `psutil` en prioridad Idle y afinidad 0–7.
