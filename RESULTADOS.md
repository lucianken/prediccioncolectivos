# Resultados, registros de error y pendientes cerrados

Movido desde `ARQUITECTURA.md` (la sección Resultados Resultados completa, registros de error y de cambio, pendientes cerrados de §11) el 2026-11-27. El texto es el original; las referencias `§N` sin otra indicación son secciones de `ARQUITECTURA.md`; `§6.3`, `§6.4` y `§9` están ahora en `docs_old/ARQUITECTURA_historia.md`. Las subsecciones de Resultados están en el orden en que estaban en la sección Resultados (por tema y fecha mezclados).

## Índice

- Resultados
  - E0–E2, E1c (2026-11-11 / 12)
  - Paso 6.2.1: techo y cobertura del tránsito (2026-11-12)
  - Pasos 6.2.2–6.2.4: A1 / A3 + grilla / por tramos en el subconjunto (2026-11-12)
  - Confirmación con 2 semillas (2026-11-12)
  - Paso 6.2.5: segmentador v2b (2026-11-12)
  - Reentrenamiento sobre v2b (2026-11-13)
  - Pérdida asimétrica vs ajuste en producto (2026-11-13)
  - Validación de la asignación geo3 (2026-11-13)
  - Paradas por tramo (2026-11-13)
  - Oráculo de ramal (2026-11-14)
  - v3: escalado a 48 líneas (2026-11-15)
  - v4: todas las líneas AMBA < 200 (2026-11-21)
  - Descomposición del error del próximo coche, v4 (2026-11-22)
  - Primer arribo anunciado dentro de ±2 min y caso (d) (2026-11-27)
  - Ruido de la verdad, error por tramo y feriados (2026-11-23)
  - Historial para "coche de adelante": 20 min contra 60 min o el día (2026-11-23): sin valor
  - Coche que ya pasó: bajarlo o sacarlo de la lista (2026-11-23)
  - ETA de CuandoSubo contra el modelo (2026-11-22)
  - v3full: train con todo el período (2026-11-15)
  - Causas de bondi no anunciado (2026-11-15)
  - Regla de sentido por racha final (2026-11-16)
  - Causas de bondis fantasma (2026-11-16)
  - Parche de ramal de CuandoSubo en el replay (2026-11-16)
  - Error de ETA por coche contra «próximo coche» (2026-11-16)
  - Consistencia temporal del ETA (2026-11-17)
  - Objetivos de entrenamiento en paradas reales (2026-11-17): descartado
  - Feature de tránsito actual por tramo (2026-11-16)
  - Factor de anuncio (2026-11-16): sin valor, no se usa
  - Regla de coche detenido (2026-11-16): descartada
- Registros de error (por fecha)
- Pendientes cerrados

## Resultados


Resultados en orden cronológico. Hay dos varas (§5): la del modelo (filas de eval, ETA a un punto del camino) y la de producto (replay en condiciones de la app). Las cifras absolutas de bondis fantasma, bondi no anunciado y sin aviso firme anteriores a la corrección de la vara de producto (2026-11-16, §5) sirven solo para comparar variantes medidas con la misma vara.

### E0–E2, E1c (2026-11-11 / 12)

MAE (s) por bucket de ETA real **0–5 / 5–10 / 10–20 / 20+ min**, y % de filas en que el coche llega después de lo anunciado > 60 s en 0–5 min ("Llega después 0–5"; rotulado "subest." en las evaluaciones anteriores a 2026-11-13, registro de error en §5). Archivos en `data/ml/v2/eval/`.

| Fecha | Experimento | Conjunto | MAE por bucket | Llega después 0–5 | Notas |
|---|---|---|---|---|---|
| 2026-11-11 | E0 A0 naive | seen (100k) | 72 / 192 / 386 / 962 | 22 % | |
| 2026-11-11 | E0 A1 (`a1_v1794415690`) | seen (100k) | **42 / 89 / 134 / 213** | 12 % | piso a superar |
| 2026-11-11 | E0 A0 naive | heldout (100k) | 68 / 186 / 377 / 890 | 22 % | A1 sin tabla para heldout cae a 7 m/s (= a0c:7) |
| 2026-11-11 | E0 A1 | seen, solo 39 (3770) | **36 / 72 / 101 / 160** | 11 % | |
| 2026-11-11 | E0 A3 viejo ep21 | seen, solo 39 | 53 / 74 / 114 / 178 | **2,8 %** | más conservador (pinball), menos preciso |
| 2026-11-11 | E1 A3 v2 K=64 (corte ep 9) | seen, solo 39 | 39 / 75 / 112 / 180 | 8,5 % | val ruidosa con lr fija, cortó temprano |
| 2026-11-11 | E1 A3 v2 K=32 (corte ep 21) | seen, solo 39 | 46 / 69 / 109 / 179 | 3,5 % | lr bajó a 5e-4 y 2,5e-4 |
| 2026-11-11 | **E1c** A3 K=32 + `--city-grid` (corte ep 26, mejor ep 21) | seen, solo 39 | **38** / **61** / **93** / **153** | 4,7 % | global 90,7 s (A1 96,7); gana a A1 salvo en 0–5 min (38 vs 36); +645 k parámetros |

**Lectura E1:** K=32 rinde igual que K=64: K=32 alcanza. El pipeline v2 (geometría, sin trip_id) iguala o mejora apenas al A3 viejo. **Ningún A3 le gana a A1 en la 39**, salvo en el % que llega después de lo anunciado. A3 recibe solo distancia normalizada y no sabe *dónde* está el coche en la ciudad; A1 sí (velocidad típica por tramo, hora y día). E1c (abajo) confirma esa causa.

| Fecha | Experimento | Conjunto | MAE por bucket | Llega después 0–5 | Notas |
|---|---|---|---|---|---|
| 2026-11-12 | E2 A3 + grilla, 48 líneas (corte ep 11, mejor ep 6) | seen (100k) | 46 / 78 / 122 / 211 | 4,5 % | vs A1 42 / 89 / 134 / 213: gana en 5–20 min, pierde en 0–5 |
| 2026-11-12 | E2 A3 + grilla | heldout (100k) | 93 / 169 / 268 / 488 | 5,9 % | vs A0 68 / 186 / 377 / 890; sesgo +75 s (en líneas no vistas el coche llega antes de lo anunciado en promedio) |
| 2026-11-12 | E2 A3 + grilla | seen, solo 39 | 45 / 70 / 99 / 171 | 3,3 % | **peor que E1c** (38 / 61 / 93 / 153) |

**Lectura E2:** con 48 líneas la 39 empeora respecto de E1c, y en líneas no vistas generaliza a medias (le gana al naive salvo en 0–5 min, con sesgo +75 s). **Inconcluso sobre "más líneas":** E2 cortó por paciencia en la época 11 con la lr fija en 1e-3 (nunca bajó; E1c bajó la lr y entrenó 26 épocas), y el error de train seguía bajando: probable subentrenamiento. Hipótesis para heldout: las celdas de la grilla que ninguna línea de train recorre tienen embeddings sin entrenar.

**Lectura E1c:** la ubicación física de P y T (grilla aprendida de ~500 m, sin ramal ni sentido) es la información que le faltaba a A3: pasa de 105,6 a 90,7 s de MAE global y **le gana a A1 (96,7 s) en los buckets de 5–10, 10–20 y 20+ min**, y por distancia en los cuatro tramos (<500 m: 48 vs 54; 5+ km: 147 vs 151). La anticorrelación ida/vuelta del error de nivel baja de −0,60 a −0,14 (muestra de train; diag en `data/ml/v2/diag/e1c_tables.md`) y el MAE a >2 km de 141 a 124 s en train (A1 133). Una sola corrida (una semilla), solo línea 39.

### Paso 6.2.1: techo y cobertura del tránsito (2026-11-12)

Fuente: `data/ml/v2/diag/TECHO_TRANSITO.md`, subconjunto 12+3 líneas.
- Ruido de etiqueta chico: estimado ~6–19 s de MAE (cota superior 18,6 s con hueco de 120 s).
- Cobertura de tránsito 97–99 % del camino; los tramos de una sola línea son ~3 % de los pasos (casi todo es compartido).
- Sustituir la velocidad típica por la observada por celda (500 m × 2 min) **no le gana a A1**: la mejor mezcla gana 2,2 % con oráculo (usa futuro) y 1,2 % realista. Ni en tramos de una línea, ni con la misma línea, ni con otras.
- Límite: es una sustitución directa en un sumador por tramos, no un modelo aprendido, con celdas gruesas y velocidad solo en movimiento. No descarta que un modelo aprendido saque algo del tránsito, pero no hay señal fuerte a la vista.
- El error que queda está en otro lado: **cabecera** (MAE 143 s a <5 min de la salida vs 105 s el resto), **coche detenido** (120 vs 109 s) y variabilidad entre coches.
- Decisión: tránsito **no es prioridad**. El foco pasa a lo que explica el error: cabecera, paradas, estado del coche.

### Pasos 6.2.2–6.2.4: A1 / A3 + grilla / por tramos en el subconjunto (2026-11-12)

Archivos en `data/ml/v2_sub/`, evals en `data/ml/v2_sub/eval/`.
Receta fija: train 2026-07-20 → 2026-09-14 (10,25 M filas, 46 días; todos < 2026-09-15, sin superposición con la validación), val = muestra reproducible del 40 % de la val de siempre en las 12 líneas (2,28 M filas, 25 días), 12 épocas, batch 1024, OneCycle (coseno), sin early stopping. Se toma el **mejor checkpoint sobre esa val** (muestra grande y estable; en los dos modelos coincidió con la última época). Eval = la vara de siempre filtrada: train = `eval_seen` en las 12 líneas (29.779 filas), control = `eval_heldout` en 12, 15, 128 (26.537 filas). MAE (s) por bucket de ETA 0–5 / 5–10 / 10–20 / 20+ min; "Llega después 0–5" = % de filas en que el coche llega después de lo anunciado > 60 s en 0–5 min; entre paréntesis, el mismo % global.

| Fecha | Experimento | Conjunto | MAE por bucket | Llega después 0–5 | Notas |
|---|---|---|---|---|---|
| 2026-11-12 | A1 reentrenado (ventana del subconjunto) | train 12 líneas | 41 / 82 / 125 / 198 | 12,4 % (33,7 %) | global 116,0; sesgo −29; por distancia 62 / 83 / 112 / 192 |
| 2026-11-12 | A3 + grilla (E1c), 12 líneas, 12 ép. (44,5 min) | train 12 líneas | 42 / 71 / 117 / 195 | 5,1 % (34,8 %) | global 110,5; sesgo −41; por distancia 57 / 76 / 108 / 186 |
| 2026-11-12 | **Por tramos** (sin tránsito, 21,4 min) | train 12 líneas | **41 / 69 / 111 / 170** | **4,5 %** (28,5 %) | global **101,6**; sesgo −15; por distancia 55 / 72 / 102 / 164 |
| 2026-11-12 | A1 | control 12, 15, 128 | 73 / 216 / 428 / 1034 | 50,4 % (85,4 %) | global 467; sin tabla para esas líneas: es el naive de 7 m/s |
| 2026-11-12 | A3 + grilla | control | 76 / 163 / 291 / 541 | 10,3 % (32,3 %) | global 282; sesgo −21 |
| 2026-11-12 | **Por tramos** | control | 57 / 116 / 185 / 440 | 9,6 % (46,5 %) | global **211**; sesgo −33; por distancia 65 / 107 / 178 / 490 |

Desglose por fase del viaje (MAE s; inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s; solo reporte):

| Conjunto / modelo | inicio | resto | detenido | en movimiento | global sin inicio |
|---|---|---|---|---|---|
| train, A1 | 147,5 | 105,7 | 122,6 | 111,6 | 105,7 (global 116,0) |
| train, A3 + grilla | 136,5 | 102,1 | 115,1 | 107,5 | 102,1 (110,5) |
| train, por tramos | 125,9 | 93,6 | 105,5 | 99,0 | 93,6 (101,6) |
| control, A1 | 570,9 | 431,0 | 491,5 | 449,3 | 431,0 (467,4) |
| control, A3 + grilla | 330,6 | 265,3 | 278,2 | 285,4 | 265,3 (282,3) |
| control, por tramos | 254,6 | 195,8 | 195,8 | 222,6 | 195,8 (211,1) |

**Lectura.** (1) En líneas vistas el modelo por tramos le gana a A1 y a A3+grilla en casi todo (global −12 % vs A1, −8 % vs A3; −14 % en 20+ min vs A1) y tiene el menor % de llega después >60 s global; en 0–5 min empata con A1 en MAE (41) y con A3 en llega después. Es una sola corrida por modelo (sin repetir semillas) y la val del modelo por tramos saltó entre épocas finales (86 → 98 → 82 s con lr casi nula): está mal condicionado y el ruido entre corridas no está medido en esta tabla (se mide en la confirmación con 2 semillas, abajo). (2) En control gana por mucho a A3 (211 vs 282) y a A1; el control es solo de 3 líneas y el por tramos tiene más sesgo y más llega después >60 s que A3 (46 % vs 32 % global): generaliza mejor en nivel, pero más coches llegan después de lo anunciado. Línea desconocida = índice de "línea no vista" (se entrena con 10 % de dropout de la línea); la geometría de las líneas de control está en la tabla de tramos y la grilla da el lugar. (3) Inicio de viaje: el error es 1,3–1,4× el del resto en los tres modelos; excluirlo baja el MAE medio de A1 de 116,0 a 105,7 s (−9 %), de A3 de 110,5 a 102,1 y del modelo por tramos de 101,6 a 93,6. El ajuste global del modelo por tramos no cierra esa brecha: inicio 125,9 vs resto 93,6. (4) Causa del error de inicio (A1, `eval_seen` de 12 líneas): 26 % de las filas de eval cumplen "inicio", pero solo 9 % son inicio verdadero (<5 min Y <1 km del shape; MAE 172 s); 13 % tienen tss <5 min pero ya están a >1 km del shape (viajes que el segmentador empieza a mitad de recorrido tras un corte; MAE 122 s) y 2 % llevan >5 min dentro del primer km (MAE 161 s). Las filas a <200 m del inicio del shape (1.555) tienen MAE 200–210 s y sesgo −62 / −110 s (detenidas): el coche espera en la cabecera dentro del viaje, hasta 5–10 min, porque el segmentador solo corta tras >10 min detenido; A1 ignora esa espera. El segundo término es que `time_since_start` mide desde el primer punto válido (a ≤150 m del shape), no desde la salida de cabecera, y en el 52 % de las filas con time_since_start ≈ 0 (primer punto válido del viaje) ese punto está a >1 km del inicio del shape.
Receta: A3 usó el trainer actual (pérdida pinball de val como criterio de "mejor"), el modelo por tramos su propio loop (`prediccion/train_path.py`, MAE de val como criterio) con lr 2e-3 contra 1e-3 del A3; no son idénticos en lr ni en métrica de selección.
### Confirmación con 2 semillas (2026-11-12)

Fuente: `data/ml/v2_sub/conf/resumen.md` (`prediccion/scripts/resumen_confirmacion.py`). Misma receta, 6 corridas: A3 + grilla LR 1e-3 (semillas 0, 1) y por tramos LR 2e-3 (semillas 0, 1; el mejor checkpoint se elige por MAE de val). LR elegido: A3 1e-3, por tramos 2e-3.

| Conjunto | Modelo | Global (semillas) | Media | Dif. entre semillas | Ventaja del por tramos | Notas |
|---|---|---|---|---|---|---|
| train (12 líneas) | A3 + grilla | 106,5 / 109,3 | 107,9 | 2,9 | | 20+ min: 187 |
| train (12 líneas) | por tramos | 101,6 / 102,2 | 101,9 | 0,6 | 6,0 s (5,6 %), 2,1× la dif. entre semillas | 20+ min: 171 |
| control (12, 15, 128) | A3 + grilla | 298,6 / 287,6 | 293,1 | 11,0 | | llega después >60 s ~30 % |
| control (12, 15, 128) | por tramos | 211,1 / 229,8 | 220,4 | 18,7 | 72,7 s (24,8 %), 3,9× la dif. entre semillas | llega después >60 s ~46–50 %, sesgo −20 a −33 s |

**Conclusión:** la ventaja del modelo por tramos es real (supera la varianza entre semillas) en ambos conjuntos; es el candidato. La ganancia en train se concentra en 20+ min (187 → 171). Pendiente: en líneas no vistas, con el por tramos llegan después de lo anunciado más coches que con A3.
### Paso 6.2.5: segmentador v2b (2026-11-12)

Código `segmenter_version=2` / `--segmentation geo2`; el v2 sigue de default. Validación antes de construir (4 días hábiles 2026-07-14, 08-12, 09-16, 10-07 + sábado 09-12; las 15 líneas; `data/ml/v2b/validation/summary.md`, `cars.md`; `python -m prediccion.v2.validate_segmenter_v2`): viajes 46.484 → 38.600; filas de viajes que arrancan a >1 km del inicio del recorrido **31,2 % → 17,7 %** (marcadas `start_unknown`, `time_since_start` = NaN); filas con `time_since_start` < 5 min pero a >1 km (el defecto medido en el paso 2) 11,0 % → 1,2 %; huecos >5 min dentro de un viaje 12.953: **9.962 unidos (77 %)**, 2.991 no (parado en el hueco o retroceso; ninguno >1 h se une; 93 % de los de 5–7 min se unen), más 6.008 excursiones fuera del recorrido, 4.780 unidas; velocidad implícita `dist_along / time_since_start` p10/p50/p90 2,7 / 4,3 / 14,3 → 2,6 / 3,7 / 5,3 m/s (filas a >60 km/h 8,5 % → 0,01 %); duración de viajes completos por línea p50 de 67–151 min, 11,7–20,7 km/h, consistente con el largo del recorrido; 16.809 esperas en cabecera (93.304 pings, 3,9 % de los pings de viaje; mediana 6 min, p90 18 min, máx 108) pasan a `daily/*.waiting.parquet`. Lo que queda `start_unknown` (~15–18 %) son inversiones de sentido a mitad de recorrido, cambios de ramal y el primer viaje del día de cada coche. Cotas de unión sacadas de los datos (hueco con coche en movimiento: 1,4–16,7 m/s, retroceso ≤150 m, ≤1 h; coche quieto a mitad de recorrido: ≤15 min). Build: `python -m prediccion.v2.build --lines-file data/ml/v2/lines.json --lines 26,39,42,92,124,151,168,50,106,107,108,132,12,15,128 --days 2026-03-28:2026-10-14 --pairs-per-trip 32 --workers 3 --segmentation geo2 --low-priority --out-dir data/ml/v2b --no-assemble` (35 min con 3 workers; 44,1 M filas; 14,6 % `start_unknown`); subconjunto en `data/ml/v2b_sub` (`assemble --v2-dir data/ml/v2b --lines-file data/ml/v2b/lines.json --only-lines <las 12> --dest data/ml/v2b_sub --train-start 2026-07-20 --val-sample-frac 0.4`: 9,41 M filas de train, 1,92 M de val) y eval en `data/ml/v2b/eval` (`make_eval --v2-dir data/ml/v2b --lines-file data/ml/v2b/lines.json --n-per-bucket 7500`, 30.000 filas por conjunto). **Los viajes cambian, así que los conjuntos y los números de v2_sub y v2b no se comparan directamente.** Los trainers no leen `start_unknown`: A3 recibe NaN en `time_since_start` (requiere enmascarar o imputar); el modelo por tramos aplica `nan_to_num`.
### Reentrenamiento sobre v2b (2026-11-13)

Evaluación en `data/ml/v2b/eval` (30.000 filas por conjunto); resultados en `data/ml/v2b_sub/runs/eval/`; lanzador `prediccion/scripts/run_v2b.py`; modelos de `v2_sub`/`conf` evaluados sobre el eval nuevo en `data/ml/v2b_sub/runs/eval_old/`.

| Modelo | seen (12 líneas de train), MAE global s | heldout (12, 15, 128), MAE global s | Notas |
|---|---|---|---|
| A1 v2b | 116,3 | 455,4 | heldout: sesgo −436 s, llega después >60 s 84 % |
| A3 + grilla v2b, LR 1e-3 (semillas 0 / 1) | 108,9 / 107,1 (media 108,0) | 276,8 / 268,3 (media 272,6) | sesgo ~0, llega después >60 s 27–28 % |
| Por tramos v2b, LR 2e-3 (semillas 0 / 1) | 102,7 / 103,5 (media 103,1) | 205,7 / 224,7 (media 215,2) | sesgo −24 / −34 s, llega después >60 s 45–46 % |
| A3 viejo (entrenado en `v2_sub`) | 113,0 / 115,6 (media 114,3) | 283,4 / 276,9 (media 280,2) | evaluado en el eval v2b |
| Por tramos viejo (entrenado en `v2_sub`) | 103,0 / 103,5 (media 103,3) | 198,7 / 214,6 (media 206,7) | evaluado en el eval v2b |

MAE en seen por inicio de viaje (desconocido / conocido): A3 v2b 128 / 104; A3 viejo 161 / 105; por tramos v2b 123 / 99; por tramos viejo 123 / 99. El 17 % de las filas seen y el 21 % de las heldout son de inicio desconocido. MAE en seen por bucket de ETA 0–5 / 5–10 / 10–20 / 20+ min: A3 v2b 45 / 70 / 114 / 204; por tramos v2b 40 / 69 / 110 / 192.

**Conclusiones:**
1. El orden se mantiene: por tramos < A3 < A1 en ambos conjuntos. La ventaja del por tramos sobre A3 es de ~5 s en seen y ~57 s en heldout, por encima de la diferencia entre semillas (seen ≤1,8 s; heldout hasta 19 s en el por tramos).
2. El segmentador nuevo mejora a A3 (seen 114 → 108; heldout 280 → 273), casi todo en filas de inicio desconocido (161 → 128): A3 depende de `time_since_start` y el 0 falso del segmentador anterior lo degradaba.
3. El modelo por tramos no cambia (103,3 → 103,1 en seen; 206,7 → 215,2 en heldout, dentro de la varianza entre semillas): usa poco `time_since_start`. Los datos v2b son la base por sus etiquetas y su eval más fieles; el error restante no proviene del corte de viajes.
4. Pendientes abiertos: en líneas no vistas, el por tramos tiene 45 % de llega después >60 s (sesgo −24 a −34 s); filas de inicio desconocido ~25 % peores que las de inicio conocido; error en 20+ min.

### Pérdida asimétrica vs ajuste en producto (2026-11-13)

Banda de ETA real 3–7 min, eval v2b (`data/ml/v2b/eval`), media de 2 semillas; resultados en `data/ml/v2b_sub/runs_band/comparacion.md`. Cada celda: MAE (s) / % llega antes >60 s / % llega después >60 s.

| Pérdida de entrenamiento | seen | heldout |
|---|---|---|
| `pinball` (q 0,5 → 0,8 bajo 1 km) | 53,3 / 17,2 / 16,6 | 82,8 / 18,1 / 30,7 |
| `l1` | 55,3 / 15,1 / 20,4 | 85,5 / 16,4 / 35,7 |
| `pinball_inv` (q 0,5 → 0,2 bajo 1 km) | 58,4 / 14,0 / 24,2 | 90,9 / 16,1 / 38,8 |
| `pinball_band` (q 0,3 con distancia 532–2074 m, rampa 300 m) | 61,4 / 7,0 / 34,7 | 94,1 / 11,6 / 47,5 |

Ajuste multiplicativo posterior de la ETA predicha, misma banda, sin reentrenar:

| Modelo base | Factor | seen | heldout |
|---|---|---|---|
| `pinball` (s0) | ×1,00 | 53,1 / 17,1 / 16,6 | |
| `pinball` (s0) | ×0,95 | 52,6 / 11,9 / 21,8 | |
| `pinball` (s0) | ×0,92 | 53,8 / 9,0 / 26,0 | |
| `pinball` (s0) | ×0,89 | 55,9 / 6,8 / 30,7 | 83,8 / 10,3 / 43,0 |
| `l1` (s0) | ×0,95 | 55,8 / 9,9 / 26,5 | |
| `l1` (s0) | ×0,92 | 57,4 / 7,7 / 30,9 | |

**Conclusión:** la pérdida asimétrica no mejora la información del modelo, solo desplaza el anuncio; un factor posterior logra el mismo desplazamiento con menor MAE y sin reentrenar. Por eso la pérdida es L1 (§5). El factor posterior tampoco se usa: «Factor de anuncio (2026-11-16)». Configuración de `pinball_band`: §6.2.

### Validación de la asignación geo3 (2026-11-13)

5 días (2026-08-11 a 2026-08-15), 15 líneas, segmentación geo2, K=32; `data/ml/v2c/validation`. Mismos días de `data/ml/v2b`:

| | v2b (150 m) | v2c (geo3: T = 45 m, M = 20 m) |
|---|---|---|
| Viajes | 46.881 | 46.929 |
| Filas | 1.487.183 | 1.484.231 |
| Filas con `start_unknown` | 15,12 % | 15,35 % |
| Viajes con `start_unknown` | 15,44 % | 15,83 % |
| Pings de viajes con recorrido descartados (no compatibles) | 1,42 % | 3,08 % |

De 46.785 viajes emparejados (mismo coche e inicio), 768 (1,6 %) cambian de recorrido elegido; sobre ellos y el resto se pierden 50.116 de 2.982.732 pings válidos (1,7 %). Lo descartado de más son sobre todo coches parados a ~75–115 m de la cabecera o del final del recorrido (estacionados; en v2b generaban filas con la etiqueta de un coche que no está en el recorrido), pings sobre otro ramal o sentido más cercano y pings de la calle paralela. Ejemplos revisados (2026-08-12, hora local UTC−3; recorrido y distancias en m): línea 151, coche 96230, 14:48:48, (-34,62880, -58,37909): v2b lo asignaba al recorrido 19481773 a 129 m y otro recorrido de la línea (4020850) pasa a 1 m; línea 151, coche 97380, 15:54:44, (-34,61010, -58,40878): 95 m al recorrido elegido y 24 m al más cercano; línea 15, coche 33659, 08:12:36, (-34,45473, -58,69512): 55 m al elegido y 3 m al más cercano; línea 15, coche 35941, 19:59:52: viaje de 175 pings con el coche parado a ~100 m del recorrido (mediana de perp 105 m): 32 filas en v2b, 0 en v2c.

### Paradas por tramo (2026-11-13)

Entrada nueva por tramo de 250 m: cantidad de paradas del recorrido dentro del tramo (opción `--stops-feature`). Recetas idénticas a v2c L1 (datos `v2c_sub`, LR 2e-3, 12 épocas, semillas 0 y 1). Eval `data/ml/v2c/eval`, banda de ETA real 3–7 min, media de 2 semillas; comparación en `data/ml/v2c_sub/runs_stops/comparacion.md`. Cada celda: MAE (s) (% llega antes >60 s).

| Modelo | seen (12 líneas de train) | heldout (líneas no vistas 12, 15, 128) |
|---|---|---|
| v2c L1 | 55,8 (15,3 %) | 87,9 (18,9 %) |
| v2c L1 con paradas por tramo | 55,7 (14,9 %) | 82,3 (15,3 %) |
| Diferencia entre semillas | 0,7 | 4,0 |

**Lectura:** en seen el efecto es nulo (0,1 s contra 0,7 s entre semillas). En heldout mejora 5,6 s (6 %), por encima de los 4,0 s entre semillas: supera el criterio por poco. En líneas entrenadas la memoria por tramo ya captura el efecto de las paradas; la feature es transferible y ayuda en recorridos no vistos o con pocos datos.

### Oráculo de ramal (2026-11-14)

Replay de la vara de producto (§5, vara anterior a la corrección del 2026-11-16): 12 líneas habilitadas (26, 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168), 40 paradas por línea (mitad tronco compartido, mitad tramo exclusivo), instantes cada 10 min de 6 a 23 h, 10 días del período de evaluación (15, 16, 17, 18, 19, 20 de sep. y 3, 4, 6, 8 de oct.; la línea 26 solo tiene datos 15–17 de sep.). Lógica de `geo_assign.py` y `path_reference.py` fijada en el commit e7479f7 (contrato 2.1); modelo `path_v2c_l1_s1`. Variantes: `base` (producción: ramal y sentido por historial + geometría), `solo sentido` (shapes restringidos al sentido del recorrido ex post) y `oráculo ramal` (shapes restringidos al recorrido ex post del viaje en curso; sin restricción si el coche no tiene viaje ex post). Informe y tablas completas: `data/ml/replay/ORACULO_RAMAL.md`.

Global (465.560 pares parada-instante). MAE del próximo coche en la banda 3–7 min (s); bondis fantasma; bondi no anunciado con coche en ≤10 min; sin aviso firme con coche en ≤10 min:

| Variante | MAE 3–7 min | Bondis fantasma | Bondi no anunciado ≤10 min | Sin aviso firme |
|---|---|---|---|---|
| base | 107 | 24,0 % | 17,0 % | 13,7 % |
| solo sentido | 104 | 23,5 % | 17,2 % | 13,6 % |
| oráculo ramal | 94 | 17,4 % | 17,0 % | 7,9 % |

Tramo exclusivo contra tronco compartido (base → oráculo ramal):

| Tipo de parada | MAE 3–7 min | Bondis fantasma | Sin aviso firme |
|---|---|---|---|
| Tramo exclusivo | 113 → 82 s | 45,6 → 24,4 % | 30,5 → 7,5 % |
| Tronco compartido | 124 → 112 s | 16,0 → 15,1 % | 11,0 → 9,6 % |

Línea 39 (base → oráculo ramal): MAE 86 → 82 s; bondis fantasma 30,4 → 11,3 %; sin aviso firme 24,6 → 5,0 % (en su tramo exclusivo, 42,1 → 5,3 %). La ganancia es de confiabilidad más que de precisión.

- **Mejoran claramente:** 42 (MAE 164 → 103 s), 106 (115 → 80 s), 132 (117 → 75 s; bondis fantasma 25,4 → 7,1 %) y 168 (117 → 97 s).
- **No mejoran:** 26, 92, 108 y 124 (un solo recorrido por sentido; no hay ramal que restringir) y, en el MAE, 107, 151 y 50.

**Lectura:** conocer solo el sentido no aporta (con contrato 2.1 el sentido ya sale bien). Conocer el ramal aporta por sacar de la lista coches de otro ramal, sobre todo en tramo exclusivo; no por afinar la ETA.

**Salvedades:**
- Es un techo: supone el ramal siempre correcto; cualquier error del ramal de CuandoSubo lo reduce.
- Vara anterior a la corrección de §5: las bondis fantasma absolutas están infladas (por igual en las tres variantes). La bondi no anunciado no cuenta los coches sin ping vigente en t.
- Con el oráculo, casi todo lo que queda en "puede venir" son coches sin viaje ex post; su tasa de bondis fantasma (~96 %) no es comparable con la de base.
- La bondi no anunciado de 17 % no cambia con el oráculo; sus causas están en «Causas de bondi no anunciado (2026-11-15)».
- En la línea 151, tramo exclusivo, el MAE de la banda (225 → 862 s) sale de muy pocos instantes y no se interpreta.

### v3: escalado a 48 líneas (2026-11-15)

Modelo por tramos con `--loss l1 --stops-feature`, LR 2e-3, 12 épocas, semillas 0 y 1. Train: 48 líneas (12 de producción + 36 nuevas), 30.979.763 filas train y 6.619.478 val (`data/ml/v3_sub`). Control fuera de train: 12 líneas (1, 12, 15, 21, 64, 65, 68, 87, 100, 109, 128, 181). Tiempo: ~5,4 min por época en GPU (~65 min por semilla completa; la semilla 0 se reanudó en la época 7 y las 6 épocas restantes tardaron 32,5 min). Val MAE: s0 82,3 s, s1 82,2 s. Eval `data/ml/v3/eval` (15.000 filas por bucket de ETA y por conjunto, asignación geo3); cada celda es la media de las semillas 0 y 1. Tabla completa, MAE por banda de ETA y desglose por línea: `data/ml/v3_sub/runs/comparacion.md`.

Banda de ETA real 3–7 min. MAE (s) y % de casos en que el coche llega antes de lo anunciado en más de 60 s:

| Conjunto | n | v3 (48 líneas, paradas) | v2c_l1 | v2c_l1_paradas |
|---|---|---|---|---|
| seen, 12 líneas de producción | 3.915 | 55,9 s (llega antes 16,2 %) | 56,1 s (16,8 %) | 56,0 s (15,8 %) |
| seen, 36 líneas nuevas | 9.483 | 56,2 s (13,8 %) | no aplica | no aplica |
| seen, 48 líneas de train | 13.398 | 56,1 s (14,5 %) | no aplica | no aplica |
| heldout, 3 de control (12, 15, 128) | 3.442 | 66,9 s (11,8 %) | 90,2 s (18,5 %) | 84,0 s (15,5 %) |
| heldout, 12 de control (solo v3) | 13.292 | 74,1 s (17,1 %) | no aplica | no aplica |

En las 12 líneas de producción, el llega después >60 s es 20,1 % (v3), 19,8 % (v2c_l1) y 19,9 % (v2c_l1_paradas). En las 3 de control comparables, v3 reduce el MAE de 90,2 a 66,9 s con llega después >60 s en 33,3 % (v2c_l1: 33,5 %).

**Lectura:** escalar no empeora las líneas de producción (55,9 contra 56,1 s); las 36 líneas nuevas quedan al nivel de las viejas (56,2 s); la generalización a líneas no vistas mejora mucho (90 → 67 s en las 3 comparables).

**Líneas atípicas (seen, banda 3–7 min):** 61 (MAE 133,3 s, n = 82) y 88 (91,8 s, n = 180; start_unknown 79 %). No habilitadas en la app (decisión del usuario, §6.1).

**Vara de producto de v3 (2026-11-15; `data/ml/replay/V3_PRODUCCION.md`).** Replay con pin nuevo (contrato 2.2), la corrección de hora de CABA y la vara anterior a la corrección de §5, mismos 10 días que el oráculo de ramal. 12 líneas de producción, v2c → v3, banda 3–7 min: MAE 107 → 107 s, llega antes >60 s 18,4 → 17,0 %, llega después >60 s 23,1 → 24,5 %; bondis fantasma 24,0 %, bondi no anunciado 17,0 % y sin aviso firme 13,7 % idénticos (no dependen del modelo). 34 líneas nuevas (v3): MAE 124 s agregado (mediana por línea 105 s); claramente peor que la mediana: 188 (455 s), 29, 197, 98, 194, 28, 7 y 180. Decisión del usuario (2026-11-16): siguen habilitadas en la app con aviso de calidad baja (`quality: "baja"` + `qualityNote` en `proyectoconsola/public/config/prediccion.json`, commit e487541; solo presentación, no cambia el cálculo). 61 y 88 (no habilitadas): 97 y 112 s, dentro de la dispersión; el MAE alto de la vara del modelo viene de muestras chicas.

**Validación del dataset v3** (4.732.764 viajes, 147.680.460 filas; ninguna línea sin filas). Líneas con `start_unknown` alto: 42 (41 %), 28 (35 %), 74 (77 %), 88 (79 %), 102 (56 %), 118 (49 %), 143 (98 %), 194 (59 %), 15 (48 %).

### v4: todas las líneas AMBA < 200 (2026-11-21)

Receta de producción sin cambios (geo2/geo3, K = 32, por tramos `--loss l1 --stops-feature`, LR 2e-3, 12 épocas, OneCycle, batch 1024; train 2026-07-20 → 09-14, val 09-15 → 10-14 con muestra del 40 %). Lanzador `prediccion/scripts/run_v4.py`, informe `data/ml/v4_sub/runs/INFORME.md`.

- **Líneas:** las 129 líneas AMBA < 200 con shapes en `line_shapes` y sufijo en `LABEL_LINE_MAP`. Criterio mínimo de datos (≥ 12 viajes con forma por día y ≥ 1.000 filas de val): lo cumplen las 129. La 148 tiene sufijo pero no shapes; otras 147 líneas < 200 no tienen shapes.
- **Dataset:** `data/ml/v4`, 71 días (2026-07-20 → 10-14), 119 min con 3 workers (límite de RAM). `v4_sub` (129 líneas): 82.258.188 filas train, 17.797.165 val. `v4_ctrl` (117, sin las 12 de control de v3): 73.313.316 / 15.848.181.
- **Entrenamiento (GPU):** ~14,5 min por época. Run full, semilla 1: 175 min, val MAE 80,5 s. Run control, semilla 0: 156 min, val MAE 81,0 s.

**No regresión en las 46 líneas habilitadas con v3** (eval congelado `data/ml/v3/eval/eval_seen.parquet`, mismas filas para ambos modelos, banda 3–7 min, n = 13.136). Criterio: MAE agregado ≤ +1 s y ninguna línea con n ≥ 100 peor en más de 5 s.

| Modelo | MAE | P90 | Llega antes > 60 s | Llega después > 60 s |
|---|---|---|---|---|
| v4 full s1 (`path_v4_l1_s1`) | 55,5 s | 117,4 s | 14,5 % | 20,8 % |
| v3 s1 (`path_v3_l1_s1`) | 55,1 s | 115,6 s | 14,6 % | 20,5 % |
| v3 s0 (ruido entre semillas) | 55,2 s | 116,8 s | 14,3 % | 20,9 % |

- Diferencia agregada +0,38 s: cumple.
- Por línea, ninguna falla. Peor: 194 (+3,8 s), 25 (+2,9 s), 4 (+2,7 s), 197 (+2,6 s). Mejor: 20 (−4,4 s), 26 (−2,1 s; n = 42, informativa), 110 (−2,0 s).
- 61 y 88 (no habilitadas): 131,6 y 95,3 s, contra 132,8 y 94,2 s con v3.

**Generalización** (eval congelado `data/ml/v3/eval/eval_heldout.parquet`, banda 3–7 min). El run control no vio las 12 líneas de control de v3; el run full sí las vio y no mide generalización.

| Conjunto | n | v4 control s0 (117 líneas) | v3 (48 líneas, media s0/s1) | v4 full s1 (las vio) |
|---|---|---|---|---|
| 12 de control | 13.292 | 65,6 s (llega antes 15,9 %) | 74,1 s (17,1 %) | 54,4 s (14,2 %) |
| 3 de control (12, 15, 128) | 3.442 | 64,7 s (12,8 %) | 66,9 s (11,8 %) | 54,8 s (15,0 %) |

Pasar de 48 a 117 líneas de train mejora la generalización a líneas no vistas en 8,5 s (12 de control).

**Habilitación de líneas nuevas** (eval congelado de v4, `data/ml/v4/eval`, seen, run full, banda 3–7 min). Criterio: n ≥ 100 y MAE ≤ 1,3 × la mediana por línea de las 46 habilitadas en este eval (54,7 s → umbral 71,1 s). Pasan 72 (lista en §6.1); MAE entre 44,6 s (179) y 67,1 s (la 8, la más alta, con n = 595). No pasan: 49, 97, 119, 153, 154, 163, 185, 193 por n; 164 por MAE (72,4 s). Tabla por línea en `data/ml/v4_sub/runs/no_regresion.md`.

**Publicación:** decisión automática del lanzador (`decision.json`, `publish: true`), tarea delegada por el usuario el 2026-11-21. Commit 576aeb5 de proyectoconsola; `npm test` 113/113 (incluye la paridad) y `test/e2e/prediccion.spec.js` 60/60. Verificado el 2026-11-22: Vercel sirve `activeModel: path_v4_l1_s1` con 118 líneas habilitadas.

**Vara de producto de v4 (2026-11-22; `data/ml/replay/V4_PRODUCCION.md`, crudos y scripts en `data/ml/replay/v4prod/`).** Replay `base`, regla `trailing_run`, vara vigente (§5), mismos 10 días que `V3_PRODUCCION.md`, 40 paradas por línea (la 154 tiene 18), 127 líneas (las 118 habilitadas y las 9 sin habilitar). v3 en las 46 líneas: las 12 viejas de `data/ml/replay/vara/run_base_xp`, las otras 34 corridas de nuevo; comparación pareada en los mismos (línea, día, parada, t), verdad idéntica. 6,0 h de pared en prioridad Idle con 8 núcleos.

| 46 líneas habilitadas con v3 | v3 | v4 |
|---|---|---|
| MAE próximo coche 3–7 min | 121,0 s | 119,6 s |
| Llega antes / después > 60 s | 17,6 / 23,8 % | 17,5 / 23,8 % |
| Bondis fantasma | 21,4 % | 21,5 % |
| Bondi no anunciado | 10,2 % | 10,1 % |
| Sin aviso firme (problema de la app) | 11,5 % | 11,5 % |

- v4 mejora o iguala en 37 de las 46 líneas; mediana de la diferencia por línea −0,9 s (rango −10,9 a +1,3 s); la 39 pasa de 89 a 78 s. Las 12 viejas: 97 → 94,6 s.

v4 por grupo (promedio ponderado por n de la banda):

| Grupo | MAE | Llega antes | Llega después | Bondis fantasma | Bondi no anunciado | Sin aviso firme |
|---|---|---|---|---|---|---|
| 12 viejas | 94 s | 14,3 % | 26,2 % | 16,3 % | 8,6 % | 9,7 % |
| 34 de v3 | 129 s | 18,7 % | 22,9 % | 21,0 % | 9,2 % | 12,1 % |
| 72 nuevas | 119 s | 17,5 % | 23,0 % | 19,2 % | 8,7 % | 12,1 % |
| 118 habilitadas | 119 s | 17,5 % | 23,3 % | 19,4 % | 8,8 % | 11,9 % |

- Varias líneas nuevas pasan la vara del modelo y en el replay tienen un MAE del próximo coche de 2 a 6 veces mayor: 8 (464 s; 67 s en la vara del modelo), 45 (380 s), 80 (376 s), 182 (323 s), 145 (319 s). La diferencia viene de qué coche se anuncia como próximo (ramal o sentido desconocido), no del ETA por coche.
- Umbral de avisos con el criterio de v3 (mediana + 1,5 × MAD × 1,4826 sobre las 72 nuevas; marca si supera el MAE o 2 o más de las 6 métricas): MAE 136 s, llega antes 25,8 %, llega después 28,9 %, bondis fantasma 46,0 %, bondi no anunciado 15,1 %, sin aviso firme 30,3 %. Superan: 8, 12, 15, 21, 45, 55, 57, 68, 80, 86, 95, 96, 100, 136, 145, 152, 158, 159, 160, 166, 178, 182, 195 (18 por MAE; 12, 68, 86, 152 y 158 por 2 o más métricas, marginales). Con la mediana de las 118 se agrega la 60.
- Avisos vigentes medidos con v4: 28, 29, 98, 180, 188, 194 y 197 siguen sobre el umbral; la 7 solo por sin aviso firme. Con los umbrales de las 34 de v3 también superarían 34, 102 y 118.

**Líneas no habilitadas por muestra chica y la 164** (`data/ml/v4_eval_ext/`: eval ampliado de 323.245 filas de los 25 días de val de `data/ml/v4/daily`, banda 3–7 min, IC por bootstrap por cluster de día, línea, recorrido y ventana de 30 min; el eval congelado no se modifica). Vara del modelo: 49 (44,5 s), 153 (45,1 s), 154 (47,2 s), 185 (47,6 s), 119 (49,1 s), 97 (49,9 s), 193 (53,4 s), 163 (54,6 s), 164 (67,6 s, IC 66,2–69,0); todas con n ≥ 13.748 y bajo el umbral de 71,1 s. Replay: las 8 primeras dan MAE del próximo coche de 58 a 82 s, bondis fantasma 5–26 %, bondi no anunciado 2–13 %, dentro de las mejores habilitadas. La 164: MAE 404 s, llega antes 37,9 %, bondis fantasma 58 % (start_unknown 74 %).

### Descomposición del error del próximo coche, v4 (2026-11-22)

Replay de v4 (RESULTADOS.md «v4»), 126 líneas habilitadas, banda 3–7 min. Fuente: `data/ml/replay/v4prod/DESCOMPOSICION.md` (`data/ml/replay/porcoche/descomposicion.py`, `descomposicion_md.py`; por línea en `v4prod/descomposicion_lineas.csv`). Casos excluyentes por el estado del 1.º anunciado; suman el MAE.

| Vara | MAE |
|---|---|
| Modelo (eval congelado, media por línea) | 53,9 s |
| Por coche en el replay (2,13 M coches) | 54,8 s |
| Próximo coche anunciado (1.193.075 instantes; 2,9 % sin anuncio fuera) | 116,9 s |

| Caso | % de los instantes | MAE | Aporte |
|---|---|---|---|
| (a) El 1.º anunciado es el primero en llegar | 78,3 | 49 s | 38,7 s |
| (b) El 1.º ya había pasado entre su último ping y t | 5,5 | 277 s | 15,1 s |
| (c) El 1.º es bondi fantasma | 5,2 | 563 s | 29,3 s |
| (d) Otro coche listado llega primero | 7,9 | 233 s | 18,4 s |
| (e) Llega primero un bondi no anunciado | 3,1 | 484 s | 14,9 s |
| (f) El 1.º no es verificable | 0,1 | 649 s | 0,4 s |

- El error por coche es igual a la vara del modelo (cociente 1,02, también en las 25 peores líneas); la diferencia hasta 117 s es qué coche se anuncia primero.
- Por línea: MAE del próximo coche 58–567 s (mediana 83 s); cociente contra la vara del modelo 1,1–10,8 (mediana 1,6).
- Por cantidad de shapes de la línea (`line_shapes`): 1–2 shapes, 43 líneas, 74 s (aporte c + d 10 s); 3–4, 43 líneas, 112 s (42 s); 5–6, 18 líneas, 157 s (79 s); ≥ 7, 22 líneas, 189 s (116 s). Spearman de la cantidad de ramales con el aporte c + d: +0,74; con el error por coche: −0,17.
- Peores (aportes c / d / e en s): 188 567 s (320 / 190 / 25), 8 464 s (337 / 45 / 26), 45 380 s (73 / 181 / 85), 80 376 s (154 / 48 / 133), 29 328 s, 182 323 s, 145 319 s. Con 2 ramales y MAE alto: 45, 95 (por d), 166 (por c), 80 (por e); causa no medida.
- La 8 tiene 6 ramales (11 shapes) en `line_shapes`; el usuario indica 10–12 ramales reales: posibles recorridos faltantes en OSM, no verificado.
- Causa del bondi fantasma solo aproximada en las 12 líneas viejas (clasificación de `FALSAS_ALARMAS.md`, hecha con v3 y la vara anterior): otro ramal 36 %, coche sin viaje o en cabecera 11 %, sentido contrario 11 %, viaje termina antes de la parada 9 %, shape sin la parada 7 %.

### Primer arribo anunciado dentro de ±2 min y caso (d) (2026-11-27)

Medido sobre el replay de v4 (`data/ml/replay/v4prod/v4/`, 126 líneas, 10 días, 40 paradas por línea, vara corregida; sin volver a predecir). Detalle y tabla por línea: `data/ml/replay/v4prod/DENTRO_2MIN.md`. Métrica nueva `metrics.within_tol`: % de instantes en que el primer arribo anunciado (`ann0_any_s`) cae dentro de ±tol del primer paso real de cualquier coche que sirve la parada (la verdad de `next_bus`, sin los instantes con paso previo no verificable), sobre los instantes con anuncio.

| Banda de ETA real | Grupo (shapes del export v4) | ±60 s | ±120 s | ±180 s |
|---|---|---|---|---|
| 3–7 min | Todas (126 líneas) | 59,4 % | **81,5 %** | 87,1 % |
| 3–7 min | 1–2 shapes (43 líneas) | 63,3 % | 85,8 % | 91,0 % |
| 3–7 min | 3–4 (43) | 59,4 % | 81,4 % | 86,9 % |
| 3–7 min | 5–6 (18) | 56,2 % | 78,0 % | 84,0 % |
| 3–7 min | ≥ 7 (22) | 53,7 % | 75,1 % | 81,5 % |
| 0–15 min | Todas | 62,3 % | 81,1 % | 87,1 % |
| 0–15 min | 1–2 / 3–4 / 5–6 / ≥ 7 | 65,8 / 63,0 / 58,9 / 56,2 % | 85,7 / 81,5 / 77,3 / 73,9 % | 91,5 / 87,4 / 83,6 / 80,5 % |

Si el instante sin anuncio cuenta como falla, ±120 s en 3–7 min baja a 79,1 %.

Caso (d) de la descomposición (otro coche listado, 2.º–5.º, llega primero; 94.372 instantes, 7,9 % de los instantes con anuncio): |error| mediano 61 s, < 120 s en el 70,4 % (en (a), mediana 39 s y 93,6 %). Separación entre el paso real del 1.º anunciado y el del primero que llega:

| Separación | % de (d) | % con error < 120 s |
|---|---|---|
| ≤ 60 s | 51,8 | 93,9 |
| 60–120 s | 15,5 | 89,5 |
| 120–300 s | 8,0 | 56,3 |
| 300–600 s | 6,3 | 17,7 |
| > 600 s | 18,3 | 12,2 |

- El 62,6 % de (d) son coches amontonados con error chico (separación ≤ 120 s y error < 120 s); el 67,3 % tiene separación ≤ 120 s. Inversiones grandes (el 1.º anunciado pasa más de 2 min después del primero real): 32,7 % de (d): 24,6 % a más de 5 min y 18,3 % a más de 10 min.
- La métrica ±2 min baja con la cantidad de shapes igual que el MAE del próximo coche: 85,8 % con 1–2 shapes contra 75,1 % con ≥ 7.
- Salvedades: la agrupación «amontonado» es por separación entre pasos reales, no distingue coches físicamente juntos de un orden mal estimado por poco; las 40 paradas por línea son una muestra.

### Ruido de la verdad, error por tramo y feriados (2026-11-23)

Modelo `path_v4_l1_s1`, eval congelado `data/ml/v4/eval/eval_seen.parquet` (MAE 3–7 min 56,0 s). Fuente: `data/ml/ruido_tramos_feriados/INFORME.md` (scripts en `scripts/`).

**Ruido de la verdad.** El objetivo del dataset v4 es un ping real (`targets=any`), sin interpolar: el eval no tiene ruido de interpolación. El cruce del replay sí interpola (`replay/core.py::crossings_v2`). Medido con cadenas de pings de `traj_flat` (16 días, 21 M evaluaciones, saltos de 2 a 8 intervalos; espaciado real mediana 60 s, media 70,7 s) y extrapolado a un intervalo por ajuste log-log (no validable): MAE 7,2 s (objetivo uniforme entre pings) a 14,9 s (coche detenido en el objetivo). Por velocidad: < 1,5 m/s 10,9 / 23,7 s; ≥ 8 m/s 3,9 / 7,9 s. Paradas lejanas (≥ 1,5 km) no empeoran la interpolación a igual velocidad (+0,7 a +1,4 s). Aporte al MAE del modelo: 0,7–2,4 s de 56 s (1–4 %). El sello por lote de CABA no se mide sin verdad de campo (un retraso uniforme 0–60 s independiente por ping agregaría ~3,7 s; hipótesis). El error del modelo no es ruido de la verdad.

**Error por distancia desde el inicio del shape** (banda 3–7 min, sin 236 filas con velocidad implícita > 25 m/s): 0–300 m 70,0 s (sesgo +18,9 s); 300–600 m 59,4 s; 600–1000 m 51,8 s; 1–2 km 55,9 s; 2–5 km 54,9 s; > 5 km 55,0 s. `start_unknown`: 60,1 contra 53,9 s. Primer minuto del viaje: 71,1 s. Los primeros 600 m son el 4,7 % de las filas; con el error del resto el MAE 3–7 min baja 0,3 s (emparejado por ETA y distancia): un modelo específico de cabecera no se justifica. Coche detenido en cabecera (derivado de la trayectoria): 0,3 % del eval; 2–3 pings detenido: 86,9 s en 3–7 min.

**Feriados.** En el rango de datos: 2026-08-17 (train) y 2026-10-12 (val), ambos lunes, con volumen de domingo (~0,8 M filas contra ~2,2 M). 100.000 filas por día en los 71 días, banda 3–7 min, IC95 por bootstrap por cluster:

| Día | MAE | Sesgo (real − predicho) | Llega antes > 60 s |
|---|---|---|---|
| 12-oct feriado (val) | 58,5 s | −28,7 s | 28,1 % |
| Lunes no feriados (val) | 53,3 s | +4,8 s | 14,7 % |
| Domingos (val) | 44,9 s | +8,4 s | 9,8 % |
| 17-ago feriado (train) | 57,3 s | −28,0 s | 27,6 % |
| 12-oct con `dow` = domingo en la entrada (sin reentrenar) | 43,6 s | +6,9 s | 10,0 % |

- Diferencia 12-oct contra lunes +5,2 s (IC95 4,2–6,4); sesgo −33,5 s (IC95 −35,0 a −32,0); sd entre días hábiles de val 1,4 s. En feriado el coche llega antes de lo anunciado el doble de veces. El 17-ago visto en train da el mismo error: el modelo no aprende el feriado con `dow` = lunes.
- Arreglo medido: tratar el feriado como domingo en `dow` de la entrada. La app (`proyectoconsola/lib/eta_predict.js` / `prediccion.js`) calcula `dow` por calendario, sin feriados. Pendiente §11, ítem 13.

### Historial para "coche de adelante": 20 min contra 60 min o el día (2026-11-23): sin valor

Replay `base`, `path_v4_l1_s1`, regla `trailing_run`, vara vigente (§5), 10 días de `V3_PRODUCCION.md`, 40 paradas por línea, subconjunto de 23 de las 126 líneas habilitadas estratificado por frecuencia (incluye las de muy baja frecuencia 62, 93, 136, 154, 163, 185; sin las de más de ~70 coches por día). Solo cambia la ventana de pings de los otros coches que usa `last_bus` (`time_since_last_bus_norm`, `last_bus_found`); la de sentido queda en 900 s. Fuente: `data/ml/replay/HISTORIAL_COCHE_ADELANTE.md` (`prediccion/replay/historial_ca.py`, flag `others_windows` de `core.evaluate_line`).

| Ventana | MAE próximo coche 3–7 min | Llega antes > 60 s | Llega después > 60 s | MAE por coche | `last_bus_found` = 0 |
|---|---|---|---|---|---|
| 20 min (servicio) | 82,80 s | 14,15 % | 24,93 % | 55,12 s | 8,6 % |
| 60 min | 82,79 s | 14,26 % | 24,84 % | 55,15 s | 2,7 % |
| Día completo, regla de la app | 82,76 s | 14,74 % | 24,34 % | 55,34 s | 14,8 % |
| Día completo por viaje (≈ entrenamiento) | 82,81 s | 14,24 % | 24,88 % | 55,14 s | 3,7 % |

- Bondis fantasma y bondi no anunciado iguales en las cuatro (13,8 % y 11,5 %). Por grupo de frecuencia el MAE cambia ≤ 0,1 s; en frecuencia muy baja `last_bus_found` = 0 baja de 33,9 a 13,0 % con 60 min y llega antes sube 0,4 pp.
- Con el día completo la regla de la app toma el primer cruce del día (artefacto): llega antes +0,59 pp.
- Conclusión: el servicio guarda 20 min; más historial no mejora la predicción.

### Coche que ya pasó: bajarlo o sacarlo de la lista (2026-11-23)

Recalculado sobre el replay de v4 (RESULTADOS.md «v4»; sin correr el modelo), 126 líneas, 10 días, vara vigente. P(ya pasó) = frecuencia empírica de `past` por ETA anunciado (10 bins) y edad del último ping (5 bins); 0 con ETA > 300 s; validación cruzada por días (2 pliegues de 5 días). P máxima observada 0,74. Variantes: «baja» (el coche pasa al final de la lista) y «saca». Fuente: `data/ml/replay/v4prod/YA_PASO.md` (scripts en `v4prod/yapaso/`).

| Variante | MAE próximo coche 3–7 min | MAE 0–3 min | MAE 0–15 min | Bondi no anunciado | Coches movidos (% que ya había pasado) |
|---|---|---|---|---|---|
| Base | 116,9 s | 71,9 s | 123,3 s | 9,83 % | 0 |
| Regla de la app (ETA del último ping consumido), baja | 106,0 s | 215,9 s | 167,0 s | 9,83 % | 988.940 (25 %) |
| Regla de la app, saca | 105,4 s | 219,9 s | 167,2 s | 19,66 % | 988.940 (25 %) |
| P > 0,5, baja | 113,6 s | 74,3 s | 120,9 s | 9,83 % | 123.605 (66 %) |
| P > 0,7, baja | 115,5 s | 72,6 s | 122,1 s | 9,83 % | 46.889 (70 %) |

- La regla de la app mueve sobre todo coches que no pasaron (75 %; el 58 % pasa en ≤ 10 min): mejora la banda 3–7 min y empeora 0–3 y 0–15 min. Vale solo como texto («llegando o recién pasó», §6.1), no para reordenar.
- P > 0,5 con «baja»: −3,3 s en 3–7 min y −2,4 s en 0–15 min; mejora 117 de 126 líneas; el aporte del caso (b) baja de 15,1 a 10,7 s. «Saca» gana 0,2–0,6 s más a costa de bondi no anunciado.
- No portado a la app.

### ETA de CuandoSubo contra el modelo (2026-11-22)

Datos del grabador de CuandoSubo (`grabador_cuandosubo/`, estado en `grabador_cuandosubo/ESTADO_Y_PLAN_EXPERIMENTO.md`): panel de 18 paradas (3 por línea: 39, 26, 42, 92, 168, 152), cada una consultada cada ~4,5 min. 8 días completos (2026-11-14 → 11-21), 06–23 h. La 26 se excluye: CuandoSubo no le asigna coches en sus paradas (solo horario). Las otras 113 líneas habilitadas no tienen arribos grabados. Paradas OBA → OSM: 15, todas a ≤ 17 m y en el sentido del headsign. Verdad: cruce firme de la vara vigente (§5), mismo id de coche en las dos fuentes. Modelo: `path_v4_l1_s1`, replay `base` sin el parche de ramal de CuandoSubo, en los mismos (parada, t) de cada consulta. ETA de CuandoSubo = `max(0, pred_arr − t)`, coches de la línea por label. Corrimiento de la hora de CABA 60 s. Fuente: `data/ml/replay/cuandosubo/COMPARACION_CUANDOSUBO.md` (`prediccion/replay/cuandosubo_cmp.py`, `cuandosubo_report.py`).

Banda de ETA real 3–7 min:

| Métrica | CuandoSubo | Modelo |
|---|---|---|
| MAE por coche, mismos coches (n = 21.101) | 78 s | 50 s |
| Llega antes / después > 60 s, mismos coches | 18,3 / 33,9 % | 16,5 / 16,1 % |
| MAE del próximo coche anunciado (7.624 instantes) | 110 s | 99 s |
| Llega antes / después > 60 s, próximo coche | 25,4 / 29,3 % | 12,9 / 29,1 % |
| Bondis fantasma | 20,0 % | 3,5 % |
| Bondi no anunciado (pasan en ≤ 10 min, n = 63.569) | 19,6 % | 10,5 % |

- Por coche, el modelo gana en las 5 líneas (CuandoSubo / modelo: 39 71/55 s, 42 76/52, 92 84/59, 152 76/47, 168 105/52) y en 13 de las 15 paradas. CuandoSubo gana en la parada inicial del 39 (Ciudadela 1165: 62 contra 67 s); en la final del 42 empatan (45 s).
- Próximo coche: CuandoSubo tiene menor MAE en el 39 (70 contra 85 s) y en el 152 (70 contra 86 s).
- Bondis fantasma con denominadores distintos: CuandoSubo lista todos los coches que OBA ve en ~35 min (213.618 entradas); la app, hasta 5 por instante (120.941). El orden entre fuentes es firme; el valor absoluto de CuandoSubo depende del conteo.
- Sensibilidad de CuandoSubo al corrimiento de la hora de CABA (por coche): 0 s → MAE 104 s; 60 s → 78 s; 120 s → 83 s. El mínimo con 60 s coincide con `CABA_TS_OFFSET_S`; no reemplaza la verdad de campo. La ventaja del modelo se mantiene con los tres valores.
- 40 min de pared con 2 workers en Idle.

### v3full: train con todo el período (2026-11-15)

Único cambio respecto de v3: `--train-start` 2026-03-28 en lugar de 2026-07-20 (ambos hasta 2026-09-14). Train: 98,2 M filas (158 días) contra 31,0 M (46 días); val idéntica (6.619.478 filas). Una semilla (s0), ~23 min por época con contención de CPU (285,6 min en total, contra ~65 min por semilla de v3: 3,2× el costo; val MAE 81,2 s). Eval `data/ml/v3/eval` (asignación geo3). Tabla completa, MAE por banda y desglose por línea: `data/ml/v3full_sub/runs/comparacion.md`.

Banda de ETA real 3–7 min, v3full_s0 contra v3_s0. MAE (s) y % de casos en que el coche llega antes de lo anunciado en más de 60 s:

| Conjunto | n | v3full_s0 | v3_s0 |
|---|---|---|---|
| seen, 12 líneas de producción | 3.915 | 54,9 s (llega antes 15,2 %) | 56,1 s (16,0 %) |
| seen, 36 líneas nuevas | 9.483 | 55,5 s | 56,2 s |
| heldout, 3 de control (12, 15, 128) | 3.442 | 71,1 s | 66,4 s |
| heldout, 12 de control | 13.292 | 75,5 s | 73,8 s |

Línea 88 (seen): 73,9 contra 89,3 s.

**Lectura:** la ganancia en líneas vistas es ~1 s, apenas sobre el ruido entre semillas de v3 (≤ 0,4 s). La generalización a líneas no vistas empeora (control 3: +4,7 s; control 12: +1,7 s). Con 3,2× el costo de entrenamiento, v3full no reemplaza a v3 en producción. Referencia de producto: el replay (`data/ml/replay/V3_PRODUCCION.md`) mostró que las métricas de producto (bondis fantasma, bondi no anunciado) las domina la asignación, no el modelo.

### Causas de bondi no anunciado (2026-11-15)

Replay `base` (regla de sentido anterior: ≥ 80 % de los pings de la ventana de 15 min a ≤ 45 m del shape), 6 días (15, 17, 19, 20 de sep., 4 y 6 de oct.), 12 líneas, 40 paradas por línea: 427.207 coches que pasan en ≤ 10 min, bondi no anunciado 16,4 %. Vara anterior a la corrección de §5. Fuente: `data/ml/replay/OMISIONES.md`.

| Causa (coche con ping vigente que pasa y no está listado) | % de las bondis no anunciados |
|---|---|
| A. Sentido «incoherente»: viaje iniciado hace < 15 min (la ventana incluye cabecera o viaje anterior) | 33,0 |
| B. Sentido «incoherente»: el coche salió del shape (> 45 m) en parte de la ventana y volvió | 20,7 |
| C. Sentido «incoherente»: retroceso u otro | 4,9 |
| G. Cortado por el tope de 5 coches de la lista | 19,4 |
| F. Coche sobre otro shape de la línea que se une al de la parada después | 10,8 |
| E. Coche a > 45 m de todo shape (desvío, cabecera, otra calle) | 8,6 |
| D. Idem E, en la cabecera antes del inicio del shape | 2,6 |

Sin ping vigente: 0,93 % adicional de los que pasan. A + B + C (58,5 %) los ataca la regla de sentido por racha final (subsección siguiente); el oráculo de ramal no cambia la bondi no anunciado porque solo resta candidatos.

### Regla de sentido por racha final (2026-11-16)

Barrido de `direction_from_history` en el replay `base`, modelo `path_v3_l1_s1`, 12 líneas, 10 días de `V3_PRODUCCION.md`; media de 10 días; diferencia pareada día por día. Vara anterior a la corrección de §5. Fuente: `data/ml/replay/BARRIDO_SENTIDO.md`. Regla adoptada (contrato 2.3, §4.5): racha final de pings consecutivos a ≤ 45 m, k = 2 pings mínimo, avance neto ≥ 40 m, fracción de avance ≥ 0,6; sin `MIN_NEAR_FRAC`.

| | ≥ 80 % de la ventana | racha final k = 2, 40 m |
|---|---|---|
| Bondi no anunciado ≤ 10 min | 16,5 % | 8,7 % |
| Bondi no anunciado, ETA real 3–7 min | 16,1 % | 7,9 % |
| Bondi no anunciado del primer coche | 12,7 % | 4,4 % |
| Sin aviso firme | 13,9 % | 10,1 % |
| MAE próximo coche 3–7 min | 107 s | 98 s |
| Llega antes de lo anunciado > 60 s | 17,0 % | 14,4 % |
| Llega después de lo anunciado > 60 s | 24,3 % | 26,2 % |
| Bondis fantasma | 24,4 % | 24,9 % |

- Parámetros: avance 20, 40 u 80 m da lo mismo (≤ 0,1 pp de bondi no anunciado); k = 3 o 4 empeora 0,1 pp; fracción de avance 0,5 o 0,75 mueve ± 0,2 pp.
- Por línea: la bondi no anunciado baja en las 12 (107: 32,8 → 10,3 %). El MAE empeora en 42 (165 → 195 s) y 106 (115 → 155 s).
- Curva de arranque (historial recortado a N pings solo en la regla de sentido), bondi no anunciado regla anterior / racha final: 1 ping 23,0 / 23,0 %; 2 pings 9,7 / 9,7 %; 3 pings 9,9 / 8,6 %; 5 pings 11,3 / 8,8 %; 15 min 17,0 / 9,3 %. Con 1 ping, para toda regla: bondis fantasma 35,1 %, MAE 3–7 min 230 s, llega antes > 60 s 28,7 %. Con 2 pings el MAE es 99 s.

### Causas de bondis fantasma (2026-11-16)

Replay `base`, modelo `path_v3_l1_s1`, regla de racha final, 12 líneas, 10 días, 1.933.795 coches listados; bondi fantasma = listado que no pasa en 40 min: 24,5 % (vara anterior). Fuente: `data/ml/replay/FALSAS_ALARMAS.md`. Clasificación jerárquica (una causa por caso):

| Causa | % de las bondis fantasma | % en ETA anunciado 3–7 min |
|---|---|---|
| X0 ETA anunciado > 40 min (fuera del horizonte) | 18,4 | 0 |
| X2/X3/X4 artefactos de la vara (hueco de GPS, parada al final del shape, cruces no consecutivos) | 12,2 | 21,5 |
| X2d pasa por la calle de la parada con un recorrido que no la tiene (no para ahí: bondi fantasma real) | 4,0 | 7,0 |
| P ya había cruzado antes de t | 7,0 | 0,2 |
| X1 pasa después de 40 min, mismo viaje | 4,5 | 1,5 |
| R1 otro ramal: diverge del tronco compartido (96 % en «puede venir») | 32,1 | 41,3 |
| S sentido contrario | 4,9 | 7,1 |
| C coche sin viaje, detenido o en cabecera | 5,1 | 7,4 |
| T el viaje termina antes de la parada | 6,5 | 7,3 |
| Desvío, hueco de GPS, otro | 5,4 | 6,7 |

Las causas X0, X1, X2 (salvo X2d), X3, X4 y P son artefactos de la vara anterior y se corrigieron en §5; X2d es bondi fantasma real. R1 es la causa real dominante; solo la resuelve conocer el ramal (oráculo: 24,5 → 17,4 % global, 14,6 → 6,7 % en 3–7 min).

### Parche de ramal de CuandoSubo en el replay (2026-11-16)

Variante `cs` del replay: reproduce el parche de producción (§6.1) con el `route_id` grabado por coche, traducido con la copia de `ROUTE_AGENCY_MAP` del 2026-11-13, la única que resuelve los días del replay, y solo desde 2026-09-23. 6 días (23, 24, 25, 26 de sep., 2 y 3 de oct.), 11 líneas (la 26 sin datos esos días), modelo `path_v3_l1_s1`, vara corregida (§5). Fuente: `data/ml/replay/FILTRO_RAMAL_CS.md`.

| | base | cs (parche) | oráculo de ramal |
|---|---|---|---|
| Bondis fantasma (todo ETA / 3–7 min) | 18,2 / 14,0 % | 11,9 / 8,8 % | 8,3 / 4,8 % |
| Sin aviso firme | 10,0 % | 4,4 % | 2,9 % |
| MAE próximo coche 3–7 min | 107 s | 94 s | 87 s |
| Bondi no anunciado ≤ 10 min | 10,2 % | 10,1 % | 9,4 % |
| Llega antes / después > 60 s | 14,4 / 28,8 % | 15,3 / 26,8 % | 15,1 / 26,1 % |

- Cobertura: el `route_id` resuelve a una ruta en el 75,3 % de los (t, coche); está en la tabla en el 60,4 %; el filtro se aplica en el 56,6 %. La 124 no tiene `route_id` en el feed esos días; en la 151 resuelve a rutas de la línea 65, fuera de la tabla.
- Acierto: la restricción contiene el recorrido real del viaje en el 91,3 % de los casos.
- Efecto del parche (cs − base, mismos 6 días): bondis fantasma −6,3 pp, MAE −13 s, bondi no anunciado −0,1 pp, llega antes de lo anunciado +0,8 pp (los 6 días).
- Por línea: mejoran mucho la 39 y la 168 en bondis fantasma; la 42 en MAE (228 → 133 s con la vara anterior). En la 42 el ramal informado no coincide con el real en el 57 % de los casos, pero la 42A y la 42B comparten casi todo el recorrido y el resultado mejora igual.

### Error de ETA por coche contra «próximo coche» (2026-11-16)

Replay `base`, modelo `path_v3_l1_s1`, regla `trailing_run`, vara vigente (§5), 10 días, 12 líneas, 1.481.138 coches listados con paso. Error por coche = ETA anunciado − tiempo real hasta el paso del mismo coche. Fuente: `data/ml/replay/ERROR_POR_COCHE.md` (`data/ml/replay/porcoche/calcula.py` y `genera_md.py`).

Error por coche, banda de ETA real 3–7 min: MAE 54 s (P90 114 s; llega antes > 60 s 19,2 %, llega después > 60 s 15,5 %), igual a la vara del modelo (~55 s). Por grupo: «Viene» 54 s, «Puede venir» 57 s, «Sentido sin confirmar» 82 s. Por edad del ping: 0–30 s ~52 s, > 120 s ~109 s (3,7 % de los casos). Por horizonte: 0–3 min 33 s, 7–15 min 89 s.

Descomposición del MAE del próximo coche anunciado (97 s; 2,3 % de los instantes sin anuncio quedan fuera):

| Caso | % de los instantes | MAE | Aporte |
|---|---|---|---|
| El 1.º anunciado es el primero en llegar | 74,9 | 49 s | 36 s |
| El 1.º anunciado ya había pasado entre su último ping y t | 7,0 | 275 s | 19 s |
| El 1.º anunciado es bondi fantasma | 6,0 | 336 s | 20 s |
| Otro coche listado (2.º–5.º) llega primero; el 1.º llega después | 9,5 | 115 s | 11 s |
| Llega primero un bondi no anunciado; el 1.º llega después | 2,6 | 392 s | 10 s |

**Lectura:** el modelo rinde en producción lo mismo que en la vara; la diferencia entre ~55 s y ~97 s viene de qué coche se anuncia como próximo. El caso «ya había pasado» (coche que cruzó la parada después de su último ping y sigue listado hasta que llega el ping siguiente) es el 60 % de los primeros anunciados que no pasan y se puede detectar con la edad del ping y el ETA (§11).

### Consistencia temporal del ETA (2026-11-17)

Replay `base`, modelo `path_v3_l1_s1`, regla `trailing_run`, vara vigente (§5). Muestra aleatoria (semilla 20261116): 12 líneas, 12 días entre 2026-09-15 y 10-14 (4 de fin de semana), hasta 150 paradas por línea (1.488), ventana de 2 h por (línea, día) entre las 6 y las 21 h, consultas cada 60 s, lista de 5 coches como la app. 710 k secuencias (coche, parada); 1,37 M pasos entre consultas consecutivas con anuncio de 3–7 min. Fuente: `data/ml/replay/CONSISTENCIA_ETA.md` (`prediccion/replay/consistencia.py`, `consistencia_verdad.py`, `report_consistencia.py`).

Cambio del anuncio entre consultas separadas 60 s (ideal −60 s), anuncio 3–7 min:

| Métrica | Valor |
|---|---|
| Cambio mediano | −56 s (P5 −129, P95 +1) |
| El anuncio sube | 5,6 % de los pasos |
| Sube > 60 s | 0,7 % (por día 0,3–1,1 %; por línea 0,2–1,8 %, la mayor la 42) |
| Secuencias con alguna subida > 60 s | 2,1 % |
| Baja más de 60 s más que el reloj | 6,5 % |

Resultado final según el paso (llega antes / después de lo anunciado > 60 s): sube > 60 s 4,6 / 81,2 %; baja normal 14,3 / 22,3 %; baja más de 60 s más que el reloj 60,3 / 8,5 %. Por grupo, sube > 60 s: «Viene» 0,4 %, «Puede venir» 1,8 %, «Sentido sin confirmar» 6,2 %. Los saltos se concentran en los pasos con ping nuevo (|Δ + 60| mediana 26 s contra 12 s sin ping nuevo).

**Lectura:** el anuncio casi nunca sube; cuando sube, el coche llega después de lo anunciado (el anuncio anterior era corto). Las bajadas más rápidas que el reloj terminan en llegada antes de lo anunciado. No hace falta suavizar el anuncio en «Viene».

### Objetivos de entrenamiento en paradas reales (2026-11-17): descartado

Un solo cambio contra `v2c_l1_paradas` (12 líneas, `--loss l1 --stops-feature`, LR 2e-3, 12 épocas, semillas 0 y 1): los T de cada par se muestrean solo en paradas de la lista del propio recorrido (pertenencia a la relación OSM); etiqueta = paso interpolado entre los dos pings que encierran la parada (error de interpolación P50 17 s, P90 42 s). Datos `data/ml/v2c_stops`, `data/ml/v2c_stops_sub` (9,28 M pares de train, 99 % de la base); los viajes difieren de v2c en 0,40 % (días de inicio de bloque sin carry en el build de v2c; `data/ml/v2c_stops/validation/diagnostico_viajes.md`). Eval nuevo de T en paradas: `data/ml/v2c_stops/eval`. Fuente: `data/ml/v2c_stops_sub/runs/comparacion.md`.

Banda de ETA real 3–7 min, media de 2 semillas (MAE; % llega antes / después de lo anunciado > 60 s):

| Vara | Conjunto | base | T en paradas | Dif. entre semillas |
|---|---|---|---|---|
| T en paradas | seen | 53,4 s (16,1 / 17,9 %) | 52,9 s (14,1 / 19,6 %) | 0,8 s |
| T en paradas | heldout (12, 15, 128) | 80,8 s (17,0 / 33,6 %) | 85,5 s (15,6 / 38,1 %) | 2,2 s |
| T cualquiera | seen | 55,7 s (14,9 / 21,3 %) | 56,8 s (13,1 / 23,7 %) | — |
| T cualquiera | heldout | 82,3 s (15,3 / 36,8 %) | 87,8 s (14,5 / 40,5 %) | 4,0 s |

**Lectura:** en líneas vistas, sobre paradas, la mejora es 0,4 s (dentro de la diferencia entre semillas); baja «llega antes» 2 pp y sube «llega después» 1,7 pp: corre el anuncio, no lo mejora. Mejora solo a 0–2 min (−4,3 s), fuera del horizonte que importa. En líneas no vistas empeora 4,7 s (más que la diferencia entre semillas) y en la vara de T cualquiera empeora en los dos conjuntos. Se descarta: el modelo de producción sigue entrenando con T en puntos cualquiera del camino.

### Feature de tránsito actual por tramo (2026-11-16)

Comparación `v2c_l1_paradas` (base) contra la misma receta más `--traffic-feature`, un solo cambio, 12 líneas de producción, semillas 0 y 1, mismo eval (`data/ml/v2c/eval`). Fuente: `data/ml/v2c_sub/runs_traffic/comparacion.md`. Definición de la feature: `prediccion/v2/traffic/feature.py`. Banda de ETA real 3–7 min, MAE medio de las semillas:

| Conjunto | base | + tránsito | diferencia |
|---|---|---|---|
| seen | 55,7 s | 54,7 s | -1,0 s |
| heldout | 82,3 s | 80,2 s | -2,1 s |

Cobertura de la feature (tramos de 250 m del camino con algún coche de la flota en las 2 ventanas previas): 93–95 %.

**Lectura:** la ganancia es de ~1–2 s, coherente con el techo de 2026-11-12 (`data/ml/v2/diag/TECHO_TRANSITO.md`). No se porta a la app por ahora: requeriría que la app mantenga historial de la flota completa de la línea para calcular la feature.

Definición (variante por el camino que le queda al coche: celdas que atraviesa el recorrido entre P y T):
- **Tabla construida (2026-11-11):** `data/ml/v2/traffic/daily/YYYY-MM-DD.parquet` (sparse: `window`, `cell`, `speed_mps`, `n`, `n_stopped`; celdas de `CityGridEncoder`, solo las 2465 por donde pasan recorridos de las 60 líneas de `lines.json`, ventana de 2 min en hora de BA, sin coches de depósito, velocidad por desplazamiento entre pings, toda la flota). Medido: ~1 M filas y ~3,3 MB por día, **531 MB los 183 días** (con ventana de 1 min serían ~1 GB); ~1.700 celdas ocupadas por ventana (mediana); ~15-25 s de CPU por día, 24 min con 3 workers. Comando: `python -m prediccion.v2.traffic.build --days 2026-03-28:2026-10-14 --window-min 2 --workers 3` (parámetros en `data/ml/v2/traffic/meta.json`). Integrada al modelo como `--traffic-feature` (abajo).
- **Feature `--traffic-feature`.** Entrada por tramo de 250 m del camino P->T, análoga a `--stops-feature`: 4 columnas de la celda de 500 m (la de `CityGridEncoder`) que contiene el punto medio del tramo. Definición única y contrato pipeline/app en el docstring de `prediccion/v2/traffic/feature.py`; resumen:
  - *Tabla:* la de `data/ml/v2/traffic` (toda la flota de la grilla, sin depósito; velocidad por desplazamiento de cada par de pings consecutivos, 10 s <= dt <= 150 s, asignada al segundo ping; ventana de 2 min en hora de BA). La app la arma con el snapshot protobuf actual contra el anterior (cada snapshot agrega sus pares; caché de ~6 min). El tiempo es el `ts` del pipeline (estampado por lote de CABA, no hora GPS), el mismo de `ts_p` / `ts_ping`.
  - *Causalidad:* con t0 = ts del ping de P y w0 la ventana que lo contiene, solo se usan las ventanas completas w0-1 y w0-2 (terminan en o antes de t0); nunca w0 ni posteriores.
  - *Entradas por tramo* (con N = coches de las dos ventanas, NS = quietos, v = velocidad media ponderada por coches en movimiento): `hay_dato` (N > 0), `v / 15 m/s` topeada a [0, 2], `log1p(N) / log1p(16)` topeada a 1,5, `NS / N`. Sin dato: las 4 en 0 (la máscara es `hay_dato`); celda fuera de la tabla o ventana fuera de rango = sin dato. No se inventa velocidad.
  - *Código:* tabla densa `data/ml/v2c_sub/traffic_dense.npz` (`python -m prediccion.v2.traffic.feature --out ...`; ventanas x 657 celdas de los shapes de las 15 líneas, 2026-07-19 -> 2026-10-14), entrenamiento `train_path --traffic-feature [--traffic-table ...]`, lanzador `prediccion/scripts/run_traffic.py` (`comparacion.md` en `data/ml/v2c_sub/runs_traffic/`). Tests: `prediccion/tests/test_traffic_feature.py`.
  - *Cobertura medida sobre el eval v2c* (tramos del camino con algún coche de la flota en las 2 ventanas previas, banda 3-7 min): seen 93,0 %, heldout 95,2 %.


### Factor de anuncio (2026-11-16): sin valor, no se usa

**Qué es:** un parámetro de la app que muestra un ETA más corto que el predicho, ETA mostrado = ETA predicho × (1 − a), para que menos colectivos lleguen antes de lo anunciado. No agrega información ni mejora la predicción: solo corre el anuncio, cambiando "llega antes" por "llega después" (el MAE no cambia).

**Evaluación del usuario (2026-11-16):** no sirve para nada y no representa una mejora; es un ajuste fino irrelevante de producción. No se aplica (a = 0) y no se considera una vía de mejora del producto. Lo que mejora el producto es mejorar la predicción o la asignación de coches.

Medido: Replay de producto (`prediccion/replay/`, variante `base`), modelo `path_v3_l1_s1`, regla de sentido racha final (`trailing_run`, §4.5), 12 líneas de producción, 10 días, 40 paradas por línea, instantes cada 10 min de 6 a 23 h. El factor es creciente: el orden de los coches y la lista anunciada no cambian; bondis fantasma y bondi no anunciado no dependen de `a`. Fuente: `data/ml/replay/FACTOR_ANUNCIO.md`.

Banda de ETA real 3–7 min (media de 10 días; llega antes / después = error > 60 s respecto de lo anunciado):

| a | MAE (s) | llega antes de lo anunciado % | llega después de lo anunciado % | espera extra media (s) |
|---|---|---|---|---|
| 0 | 98 | 14,4 | 26,2 | 91 |
| 0,05 | 97 | 10,0 | 31,1 | 89 |
| **0,08** | **98** | **8,0** | **34,8** | **90** |
| 0,10 | 98 | 6,9 | 37,5 | 90 |
| 0,15 | 102 | 4,9 | 45,5 | 93 |

- **a = 0,08 minimiza 2·antes + después** (50,8 contra 54,9 con a = 0): llega antes −6,35 pp (mejora los 10 días), llega después +8,62 pp (empeora los 10 días); MAE, espera extra y P90 sin cambio. Con a ≥ 0,12 sube el MAE.
- Fuera de la banda: 0–3 min MAE 43 → 40 s; 7–15 min MAE 198 → 209 s y llega después 47,9 → 64,0 %.
- Descartado: descuento fijo en segundos (−20 s: MAE 102 s, llega antes 9,7 %, llega después 34,8 %; −30 s: MAE 106 s, 8,1 %, 40,1 %; peor que proporcional a igual llega antes, castiga ETA cortos). Descartado: tope en segundos (a = 0,10 con tope 30 s: MAE 102 s, 8,1 %, 36,8 %). Descartado: factor por banda de ETA anunciada (0,08 / 0,08 / 0,05 por <3 / 3–7 / ≥7 min: 3–7 min igual o apenas peor, 7–15 min llega después 64,0 → 58,1 %); ganancia marginal por un parámetro extra.
- Salvedad: el óptimo depende de `CABA_TS_OFFSET_S` = 60 s, que no tiene verdad de campo; un error en ese corrimiento mueve en bloque llega antes / después y por lo tanto el `a` óptimo.
- Estado: no aplicado en producción (§6.1); descartado como mejora (evaluación del usuario, arriba).

### Regla de coche detenido (2026-11-16): descartada

Medido: regla causal que marca un coche como `detenido` si en los últimos 5 min su racha final sobre el shape avanzó < 50 m. Replay de producto (`prediccion/replay/`, variante `base`), modelo `path_v3_l1_s1`, regla de sentido racha final (`trailing_run`, §4.5), 12 líneas de producción, 10 días, 40 paradas por línea, instantes cada 10 min de 6 a 23 h. Vara corregida (`prediccion/replay/metrics.py` con `corrected=True`). Fuente: `data/ml/replay/COCHE_DETENIDO.md`.

Variantes (ventana 5 min, avance 50 m; diferencia pareada contra base, 10 días):
- **(a) Descartar el coche:** bondis fantasma −0,7 pp, pero bondi no anunciado +0,5 pp (10 de 10 días). Del total marcado, 10,5 % pasa en ≤ 10 min y 44,5 % pasa en 40 min (cabecera que sale, pausa larga, semáforo, fila).
- **(b2) Bajarlo a "sentido sin confirmar" al final de la lista** (ETA sin cambio): bondis fantasma −0,32 pp (de 14,7 %), MAE del próximo coche 3–7 min −2,4 s, bondi no anunciado −0,05 pp, sin aviso firme +0,16 pp, llega antes >60 s +0,08 pp. En la línea 42: MAE 196 → 170 s, bondis fantasma 30,7 → 28,3 %, causa C 10,2 → 6,9 pp. Las demás líneas casi sin cambio.

Decisión: **descartada por el usuario (2026-11-16).** Ganancia chica en el agregado y regla demasiado específica (feature engineering ad hoc para un caso concentrado en la 42). No se implementa en pipeline ni app.

## Registros de error

**Registro de error (hasta 2026-11-13).** La pinball usaba q 0,5 → 0,8 bajo 1 km (castiga que el colectivo llegue después de lo anunciado) y la vara rotulaba "subest. >60 s (el usuario pierde el colectivo)" a las filas donde el colectivo llega después. Definición correcta: pérdida L1 simétrica; el error grave es "llega antes de lo anunciado". Afecta a:
- Modelos entrenados con esa pinball: todos los A3 y por tramos de `data/ml/models/`, `data/ml/v2/models_e2_geo/`, `data/ml/v2_39_k32/`, `data/ml/v2_39_k32_geo/`, `data/ml/v2_39_k64/`, `data/ml/v2_sub/conf/{a3_*,path_*}` y `data/ml/v2b_sub/runs/{a3_*,path_*}` (las corridas E0/E1/E2 de §6.4 y las de la sección Resultados).
- Tablas de evaluación de todos los modelos (también A0 y A1) en `data/ml/*/eval*` y las tablas de la sección Resultados: la columna "subest. >60 s" equivale a "llega después de lo anunciado > 60 s" y la columna "sobreest. >60 s" a "llega antes de lo anunciado > 60 s". En la sección Resultados las columnas anteriores a 2026-11-13 se rotulan con la definición correcta.
- Las evaluaciones generadas desde 2026-11-13 traen las columnas "llega antes >60 s", "llega después >60 s" y "espera extra media" (claves JSON `pct_llega_antes_60s`, `pct_llega_despues_60s`, `espera_extra_media_s`; `pct_over_60s` y `pct_under_60s` son sus alias históricos).

**Registro de error (2026-11-13): tolerancia de 150 m y calle paralela.** La máscara de pings válidos (`valid` de `geometry_for_trip`), el filtro de `project_trip` y el criterio de ajuste del segmentador admitían como válido un ping a hasta 150 m del recorrido, que incluye el recorrido de la calle paralela (~100–130 m) y el sentido opuesto del mismo ramal. Medido (`data/ml/v2b/diag/asignacion/ASIGNACION_RECORRIDO.md`): 3,76 % de las filas de `v2b` son sucias (P o F a 45–150 m del recorrido, o con otro recorrido ≥ 10 m más cerca), con ~2 × el MAE de las limpias (banda 3–7 min, seen: 85 contra 53 s; heldout 158 contra 79 s); limpiarlas bajaría el MAE global 3,9–4,5 % y en la banda 3–7 min 2,2–3,4 %. Afecta a los datasets `data/ml/v2/`, `v2b/`, `v2_sub/`, `v2b_sub/`, `v2_39_k32/`, `v2_39_k32_geo/`, `v2_39_k64/` y a todos los modelos y evaluaciones entrenados o construidos sobre ellos: `data/ml/v2/models_e2_geo/`, `data/ml/v2_sub/` (`models*`, `conf/`), `data/ml/v2b_sub/` (`runs/`, `runs_l1/`, `runs_band/`), los eval `data/ml/v2/eval`, `data/ml/v2_sub/eval` y `data/ml/v2b/eval`, y los exportes `data/ml/export/path_v2b_s0` y `path_v2b_pinv_s0`. Corrección: §4.5 (`--assign geo3`, dataset `data/ml/v2c`). Los números de la sección Resultados anteriores a esta fecha siguen siendo válidos como comparación entre sí.

**Registro de error (2026-11-14): suspensión de la PC durante el entrenamiento v3.** La PC entró en suspensión por inactividad a las 19:39 (el bloqueo de suspensión lanzado desde PowerShell fue inefectivo) y `train_path` quedó colgado tras reanudar la PC, en la época 6 de la semilla 0. Se perdieron ~15 h. Se reanudó el 2026-11-15 a las 10:27 con `--resume`; los resultados no se ven afectados.

**Registro de cambio (2026-11-16): regla de sentido por historial.** Hasta esa fecha `direction_from_history` exigía ≥ 80 % de los pings de la ventana de 15 min a ≤ T (`MIN_NEAR_FRAC`); un coche recién salido de cabecera con pings viejos fuera del shape salía `sentido_incoherente`. Regla vigente: racha final (arriba); se eliminan `MIN_NEAR_FRAC` y `manifest.assignment.min_near_frac` y se agrega `direction_rule`. Contrato 2.3. La función no interviene en el armado del dataset ni en el entrenamiento (solo la usan `path_reference.py` y el replay): `path_v3_l1_s1` no se reentrena, el ONNX y `lines/` no cambian; solo se reexporta el manifest.

**Registro de error (2026-11-16): definición de bondi fantasma de la vara de producto.** Hasta esa fecha el replay contaba como bondi fantasma a coches con ETA anunciado > 40 min, con la parada en el último tramo del shape, con el paso dentro de un hueco de GPS, entre pings no consecutivos o que ya habían cruzado segundos antes (`FALSAS_ALARMAS.md`: 37,6 % de las bondis fantasma eran artefactos de esos tipos; con la corrección, 43,9 % dejan de serlo). Afecta a `V3_PRODUCCION.md`, `ORACULO_RAMAL.md`, `OMISIONES.md`, `BARRIDO_SENTIDO.md`, `FACTOR_ANUNCIO.md` y `FALSAS_ALARMAS.md` y a las tablas de la sección Resultados que citan bondis fantasma, bondi no anunciado o sin aviso firme del replay: siguen válidos como comparaciones relativas entre variantes; sus bondis fantasma absolutas están infladas (≈ 24,5 contra ≈ 17,1 % con la vara vigente), la bondi no anunciado y el sin aviso firme absolutos algo subestimados (≈ 9,3 contra 9,5 %; 10,0 contra 11,2 %). MAE y llega antes / después no cambian materialmente.

**Registro de error (2026-11-16): asociación parada↔recorrido por geometría en la vara corregida.** Error en la primera versión de la vara corregida (retirada el mismo día): contaba como recorridos que sirven la parada también a los shapes del mismo sentido a ≤ 45 m. Definición correcta: sirven la parada solo los recorridos que la tienen en su lista; un recorrido que no la tiene no para ahí (a OSM le pueden faltar paradas, pero una parada presente y no compartida es correcta). Inflaba los pasos (+1,3 %) y la bondi no anunciado (11,3 contra 10,7 %), y desinflaba las bondis fantasma (14,2 contra 14,7 %; 3–7 min: 9,3 contra 9,9 %). Retirada el mismo día. Afectó a `VARA_CORREGIDA.md`, `FILTRO_RAMAL_CS.md`, `COCHE_DETENIDO.md` y `FALSAS_ALARMAS.md` (X2d como artefacto, con una propuesta de asociar parada y recorrido por geometría en el pipeline de paradas: retirada); se retiró también la lectura «dato incompleto de `ramales[].stops`». Las cifras publicadas de esa versión contaban además dos veces el 2026-10-04. Detalle: `VARA_CORREGIDA.md`, registro de error.

## Pendientes cerrados

- **Consistencia temporal del ETA (ex 11.1).** Hecho (2026-11-17, la sección Resultados): sube > 60 s en el 0,7 % de los pasos (anuncio 3–7 min); no hace falta suavizar.
- **Objetivos de entrenamiento en paradas reales (ex 11.2).** Descartado (2026-11-17, la sección Resultados): sin mejora en líneas vistas (0,4 s, dentro del ruido) y peor en no vistas (+4,7 s).
- **Cabecera y coche detenido (ex 11.5).** Refutado como prioridad (2026-11-23, RESULTADOS.md «Ruido de la verdad, error por tramo y feriados»): los primeros 600 m pesan 0,3 s del MAE 3–7 min; un modelo de cabecera no se justifica. La regla de coche detenido está descartada (la sección Resultados); el coche detenido como variable de asignación pasa al ítem 3. Medición previa: cabecera 143 s contra 105 s del resto; detenido 120 contra 109 s (RESULTADOS.md «Paso 6.2.1»).
- **Paso de coches de un recorrido sin la parada por un tronco compartido (ex 11.9).** Hecho (2026-11-16, §5, «Recorrido real»): la verdad del replay usa el recorrido ex post del coche.
- **Vara de producto de v4 y avisos de calidad en las líneas nuevas (ex 11.12).** Hecho (2026-11-22, §6.1 y la sección Resultados): 8 líneas habilitadas (commit 0f688b1) y 22 avisos (commit 96fd195). Las 72 líneas habilitadas con v4 habían pasado solo la vara del modelo; los 8 avisos de calidad baja vigentes salieron de la vara de producto.
- **Feriado tratado como domingo en la entrada del modelo (ex 11.13).** Hecho (2026-11-23): la app pasa `dow` = domingo en feriados nacionales, trasladables y puentes (fuente ArgentinaDatos vía `api/feriados.js`, ver CLAUDE.md de proyectoconsola). El dataset de entrenamiento todavía los tiene con su día de semana.
- **Historial de más de 20 min para «coche de adelante» (ex 11.14).** Descartado (2026-11-23, la sección Resultados): sin mejora.
