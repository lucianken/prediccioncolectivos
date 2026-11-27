# Recorridos nuevos de la línea 42: qué ve la predicción (2026-11-27)

Prueba de diagnóstico. No se instaló nada en la app, no se tocó `proyectoconsola/` (solo lectura) ni `prediccion/replay/pinned/`, y `data/ml/export/path_v4_l1_s1/` quedó intacto. Scripts en `experiments/recorridos_nuevos_42/`; salidas intermedias en `data/ml/replay/recorridos_nuevos_42/`.

## 1. Resumen

- **Hipótesis confirmada.** En los tramos nuevos de la 42 la predicción de producción (bundle `path_v4_l1_s1`) no lista ningún coche en 9 de las 15 paradas nuevas, y en las otras 6 lista coches que mayormente no pasan. Con los recorridos y paradas actuales (bundle reexportado) la lista se llena y el error baja a nivel del resto de la línea. Detalle en §4.
- El cambio de recorrido de los coches fue en la madrugada del 2026-11-25 (entre las 01:09 y las 01:35). Desde entonces ~10 % de los pings en movimiento van por el recorrido nuevo y ~0 % por el viejo (§3).
- El modelo no tiene parámetros por shape: el reexport sin reentrenar funciona (§5). El ONNX es byte a byte el mismo; cambian las tablas de shapes (`lines/*.json`).
- Otras líneas con cambio de geometría o paradas: 84, 7, 106 (km nuevos), 102, 34, 47, 132 y 6 más con una parada distinta (§2.3).

## 2. Diferencias entre el export de v4 y los `line_shapes` del 2026-11-26

Viejo = `data/ml/export/path_v4_l1_s1/lines/` (geometría y `stops_m`; las coordenadas de las paradas viejas salen de `proyectoconsola` en el commit fec1e65, el último previo a c2bb8ec, y reproducen el mismo recorrido del export). Nuevo = `proyectoconsola/data/line_shapes/` actual. Script `diff_shapes.py`; resultado completo `diff_lineas.json` y `diff_42.json`.

Definiciones. «Km nuevo > 45 m»: longitud de los recorridos nuevos que queda a más de T = 45 m de todos los recorridos viejos de la línea (polilíneas densificadas a 10 m contra 5 m). «Parada nueva»: sin parada vieja de la línea a ≤ 25 m. «Parada desaparecida»: sin parada nueva a ≤ 25 m.

### 2.1 Línea 42

Los 6 shapeIds son los mismos (3464362, 3464448, 3464655, 20138153, 20131886, 20139530), con los mismos ramales (A, B, C × ida/vuelta) y nombres. Lo que cambió es el tramo central.

| shapeId | ramal y sentido | km nuevo > 45 m del viejo | paradas viejo → nuevo |
|---|---|---|---|
| 3464362 | A Ciudad Universitaria → Pompeya | 2,49 | 61 → 57 |
| 20138153 | B Ciudad Universitaria → Pompeya | 2,49 | 57 → 53 |
| 20139530 | C Parque de los Niños → Pompeya | 2,49 | 57 → 53 |
| 3464448 | A Pompeya → Ciudad Universitaria | 2,06 (2,29 contra su propio viejo) | 48 → 47 |
| 3464655 | B Pompeya → Ciudad Universitaria | 2,06 (2,29) | 41 → 40 |
| 20131886 | C Pompeya → Parque de los Niños | 2,06 (2,29) | 47 → 46 |
| **suma de los 6 shapes** | | **13,67** | |

Son ~2,1–2,5 km por recorrido, la misma desviación repetida en cada ramal (la suma cuenta el mismo tramo una vez por shape). Además, 8,9 km (suma de los 6) del recorrido viejo ya no tienen recorrido nuevo a ≤ 45 m.

Dónde (centro del desvío, entre Juan B. Justo / Warnes y Rivadavia / Acoyte, Villa Crespo – Caballito):
- Sentido a Pompeya (hacia el sur): el viejo iba por Warnes – Muñecas – Olaya – Acoyte (paradas desaparecidas: Warnes y Juan B. Justo, Muñecas y Humboldt, Olaya y Tres Arroyos, Olaya y Luis Viale, Plaza Nazar, Olaya y Ángel Gallardo, Acoyte y Vallese, Sanatorio Méndez, Neuquén - Aráoz Alfaro, Acoyte y Rivadavia). El nuevo va por Honorio Pueyrredón – Galicia – Ampère – Aranguren – Neuquén e Hidalgo (lat −34,597 a −34,616; lon −58,455 a −58,439).
- Sentido a Ciudad Universitaria: el viejo volvía por Acoyte – Muñecas; el nuevo por Nicolás Vila – Aranguren – Gallardo e Hidalgo – Gallardo y Virasoro – Galicia – Belaustegui – Dorrego (lat −34,616 a −34,596).
- Más una parada en Parque de la Innovación - Monumental (movida 20 m, sin desvío).

Paradas (por ubicación, de las 107 nuevas de la línea contra 112 viejas):

| | n | detalle |
|---|---|---|
| nuevas | 15 | 9 a > 45 m de todo recorrido viejo (Galicia ×2, Belaustegui, Ampère, Aranguren, Neuquén e Hidalgo, Gallardo e Hidalgo, Gallardo y Virasoro, Avenida Dorrego; perp. al viejo 91–311 m) y 6 a ≤ 45 m (Honorio Pueyrredón 39 m, Dorrego y Rosas 18 m, Aranguren, Avenida Rivadavia, Nicolás Vila, Parque de la Innovación) |
| desaparecidas | 20 | las de Acoyte, Olaya, Muñecas y Warnes listadas arriba, más Av. Avellaneda, Acoyte y Ghandi, Acoyte y Apolinario Figueroa, Muñecas y Gurruchaga, Muñecas y Dorrego |

### 2.2 Qué pasa con ellas en el modelo viejo

- Las 9 paradas a > 45 m no pueden predecirse: `snap_to_route` a T = 45 m no engancha, y no están en ninguna lista `stops_m` del bundle viejo.
- Las 6 a ≤ 45 m enganchan con el punto del usuario (geométricamente), pero el bundle viejo no las asocia a ningún ramal por nombre.

### 2.3 Todas las líneas del modelo (129)

Solo se muestran las que cambiaron (geometría, shapes o paradas); las otras 115 son idénticas en geometría y a lo sumo 1 parada.

| línea | km nuevo > 45 m (suma de shapes) | km viejo sin cobertura nueva | shapes que salen | paradas nuevas / desaparecidas | paradas nuevas a > 45 m |
|---|---|---|---|---|---|
| 42 | 13,67 | 8,91 | 0 | 15 / 20 | 9 |
| 84 | 4,53 | 0,00 | 0 | 0 / 0 | 0 |
| 7 | 4,14 | 0,00 | 0 | 12 / 0 | 12 |
| 106 | 2,25 | 1,72 | 0 | 5 / 3 | 4 |
| 102 | 0,05 | 0,00 | 0 | 13 / 0 | 1 |
| 34 | 0,00 | 2,06 | 0 | 1 / 1 | 0 |
| 132 | 0,00 | 0,74 | 2 | 0 / 2 | 0 |
| 47 | 0,00 | 0,00 | 4 | 0 / 0 | 0 |
| 39, 50, 76, 109, 115, 151 | 0,00 | 0,00 | 0 | 1 / 1 (o 1 / 0) | 0 |

Lectura: la 42 es la que más cambia, seguida de 84, 7 y 106. En 7, 84 y 106 los coches probablemente ya van por el recorrido nuevo o lo harán: tienen el mismo problema que la 42 (en 7 hay 12 paradas nuevas a > 45 m del viejo; en 84 hay 4,5 km nuevos pero ninguna parada nueva). La 102 agrega 13 paradas sin cambiar el trazado. En 47 y 132 salen shapes que ya no están en `line_shapes` (el modelo los conserva en el checkpoint, el reexport los omite). No se verificó con pings si los coches de esas líneas ya recorren los tramos nuevos.

## 3. ¿Los coches hacen el recorrido nuevo?

Pings de la 42 en movimiento (velocidad ≥ 2 m/s), clasificados por distancia a la unión de los recorridos viejos y de los nuevos (T = 45 m). Script `pings_recorrido.py`; `pings_dias.csv`, `pings_horas.csv`, `pings_tramos.csv`. Días: 17, 18, 19, 20 y 24/11 (el 23/11 es feriado y se excluye; 14–16/11 no usados) contra 25, 26 y 27/11 (parcial, hasta ~14:30). Las grabaciones del 25/11 tienen huecos (sin pings 03–09 h y 20–22 h).

| día | pings en mov. | solo recorrido nuevo | solo recorrido viejo | ambos | ninguno | zona del desvío: solo nuevo / solo viejo | coches con ≥ 1 ping solo-nuevo / solo-viejo |
|---|---|---|---|---|---|---|---|
| 17/11 | 17 783 | 0,01 % | 7,46 % | 89,2 % | 3,3 % | 0,0 % / 40,4 % | 1 / 46 |
| 18/11 | 18 273 | 0,02 % | 7,31 % | 88,2 % | 4,5 % | 0,1 % / 39,9 % | 3 / 46 |
| 19/11 | 18 385 | 0,01 % | 7,51 % | 89,0 % | 3,4 % | 0,0 % / 40,2 % | 1 / 47 |
| 20/11 | 17 419 | 0,00 % | 7,34 % | 89,4 % | 3,3 % | 0,0 % / 40,0 % | 0 / 46 |
| 24/11 | 17 852 | 0,02 % | 7,55 % | 88,9 % | 3,5 % | 0,1 % / 40,3 % | 4 / 46 |
| **25/11** | 6 945 | **10,0 %** | 0,09 % | 85,9 % | 4,0 % | 53,3 % / 0,5 % | 45 / 2 |
| **26/11** | 18 485 | **9,8 %** | 0,01 % | 86,2 % | 4,0 % | 52,8 % / 0,0 % | 46 / 1 |
| **27/11** (parcial) | 10 722 | **9,8 %** | 0,00 % | 86,4 % | 3,9 % | 52,6 % / 0,0 % | 45 / 0 |

(«Zona del desvío»: pings en la caja lat −34,622 a −34,594, lon −58,458 a −58,434.)

- Cambio de recorrido: el 25/11 el último ping solo-viejo es a las 01:09 y el primero solo-nuevo a las 01:35 (hora local). Antes del 25/11 los pings solo-nuevo son 0–4 por día (ruido de GPS en calles paralelas); desde el 25/11, los solo-viejo son 6, 1 y 0.
- Los coches cumplen: ~100 % de los coches circulan por el recorrido nuevo desde el 25/11. La parte «ninguno» (~3–4 %, depósitos y cabeceras) no cambia entre períodos.
- Tramos por cantidad de pings solo-nuevo desde el 25/11: Galicia 653, Honorio Pueyrredón 523, Ángel Gallardo y Virasoro 494, Aranguren 381, Belaustegui 365, Ampère 335, Avenida Dorrego 323, Neuquén e Hidalgo 273 (por parada nueva más cercana). En el período previo, los solo-viejo se reparten entre Olaya y Gallardo (931), Muñecas y Gurruchaga (792), Acoyte y Apolinario Figueroa (696), Juan B. Justo (661), etc.

## 4. Replay de producción (`base`), viejo contra reexportado

### 4.1 Diseño

Script `replay42.py` (usa la lógica del replay de `HEAD`, copia en `core_head.py`, con dos cambios mínimos: la verdad se calcula con otro bundle y el punto del usuario se resuelve por separado). Variante `base`, regla de sentido `trailing_run`, vara corregida, instantes cada 10 min entre 06 y 23 h.
- **Verdad (igual para los dos):** bundle reexportado (recorridos nuevos), paradas de `line_shapes` actuales (ramales que las tienen por nombre) y viajes ex post con los `line_shapes` actuales. Cruce firme interpolado entre pings consecutivos compatibles con el recorrido nuevo.
- **Paradas (55):** las 15 nuevas (9 `nueva_fuera` a > 45 m del viejo, 6 `nueva_cerca`) y 40 de las 112 del resto (muestra aleatoria fija, semilla 0).
- **Bundle viejo:** `nueva_*`: punto resuelto como la app con GPS/mapa (`snap_to_route` a ≤ 45 m, `user_kind=punto`); si no engancha, no se puede predecir (ningún coche). `resto`: por nombre de ramal, como en producción.
- **Bundle reexportado:** todas por nombre de ramal.
- **Instantes:** solo los de horas con ≥ 1000 pings de la 42 (también en la hora t + 40 min), para no confundir huecos de la grabación con fallas. Instantes de tramo nuevo desde el 25/11: 28 (25/11), 103 (26/11), 50 (27/11) por parada.
- **Intervalos:** bootstrap por cluster (parada × ventana de 30 min × día), 300 réplicas, IC 95 %. Con 3 días (2 parciales), los IC miden poco más que el muestreo dentro de esos días: no hay variación entre días hábiles ni entre semanas.

### 4.2 Desde el 25/11 (recorrido nuevo en la calle)

| grupo | bundle | coches listados por instante | % instantes sin ningún coche listado (pasa uno en ≤ 10 min) | bondi no anunciado % | bondi fantasma % | MAE próximo coche 3–7 min (n) |
|---|---|---|---|---|---|---|
| tramo nuevo (15 paradas) | viejo | 1,99 [1,83–2,17] | **60,3 [57,0–63,5]** | **76,0 [73,2–78,8]** | 50,6 [47,1–54,1] | 177 s [133–227] (806) |
| | reexport | 4,99 [4,99–5,00] | 0,0 | 1,0 [0,7–1,3] | 8,3 [7,4–9,2] | 91 s [74–112] (806) |
| a > 45 m del viejo (9) | viejo | **0,00** | **100,0** | **100,0** | sin coches listados | sin anuncio en 467 de 467 |
| | reexport | 4,99 | 0,0 | 1,0 [0,6–1,4] | 5,9 [4,9–6,9] | 60 s [55–65] (467) |
| a ≤ 45 m del viejo (6) | viejo | 4,98 | 0,0 | 37,2 [32,3–41,8] | 50,6 [47,3–53,4] | 177 s [140–229] (339) |
| | reexport | 4,99 | 0,0 | 1,1 [0,6–1,6] | 12,0 [10,1–14,0] | 133 s [97–183] (339) |
| resto de la línea (40) | viejo | 4,31 [4,25–4,36] | 2,0 [1,6–2,5] | 14,1 [13,3–15,1] | 14,7 [13,9–15,5] | 225 s [193–254] (2183) |
| | reexport | 4,31 [4,25–4,36] | 2,0 [1,6–2,5] | 8,6 [8,0–9,3] | 12,6 [11,8–13,3] | 199 s [167–232] (2183) |

Instantes con paso ≤ 10 min (denominador del «sin ningún coche»): 2214 en tramo nuevo (1335 en las 9 paradas lejanas), 5829 en el resto. Coches que pasan en ≤ 10 min (denominador de bondi no anunciado): 4914 en tramo nuevo, 12 817 en el resto. Coches listados evaluados (bondi fantasma): 5292 viejo y 13 324 reexport en tramo nuevo.

Por parada (instantes con paso ≤ 10 min, 3 días):

| parada | clase | perp. al viejo (m) | inst. paso ≤ 10 | viejo: coches/inst, sin lista % | reexport: coches/inst, sin lista % |
|---|---|---|---|---|---|
| Aranguren (nuevo, -58,4383) | cerca | 0 | 163 | 5,00 / 0 | 4,99 / 0 |
| Avenida Rivadavia | cerca | 2 | 140 | 5,00 / 0 | 4,99 / 0 |
| Dorrego y Rosas | cerca | 18 | 152 | 4,94 / 0 | 5,00 / 0 |
| Honorio Pueyrredón | cerca | 39 | 141 | 4,96 / 0 | 4,96 / 0 |
| Nicolás Vila | cerca | 0 | 163 | 5,00 / 0 | 4,99 / 0 |
| Parque de la Innovación - Monumental | cerca | 1 | 120 | 5,00 / 0 | 5,00 / 0 |
| Ampère | lejos | 218 | 140 | 0,00 / **100** | 4,98 / 0 |
| Aranguren (nuevo, -58,4411) | lejos | 261 | 135 | 0,00 / **100** | 4,99 / 0 |
| Avenida Dorrego | lejos | 311 | 155 | 0,00 / **100** | 5,00 / 0 |
| Belaustegui | lejos | 216 | 156 | 0,00 / **100** | 5,00 / 0 |
| Galicia (×2) | lejos | 217–218 | 137 / 156 | 0,00 / **100** | 4,97–5,00 / 0 |
| Gallardo e Hidalgo | lejos | 91 | 161 | 0,00 / **100** | 5,00 / 0 |
| Neuquén e Hidalgo | lejos | 173 | 140 | 0,00 / **100** | 4,99 / 0 |
| Ángel Gallardo y Virasoro | lejos | 137 | 155 | 0,00 / **100** | 5,00 / 0 |

Por día, % de instantes sin ningún coche listado con paso ≤ 10 min (15 paradas nuevas): viejo 59 / 60 / 61 % (25, 26, 27/11); reexport 0 / 0 / 0 %.

### 4.3 Control: 17–24/11 (los coches van por el recorrido viejo)

Solo las 40 paradas del `resto`; en las paradas nuevas la verdad de esos días no vale (el cruce se interpola entre los pings compatibles a ambos lados del desvío, de modo que el «paso» por una parada que el coche no recorre es un artefacto).

| bundle | instantes | coches/inst | sin lista % | bondi no anunciado % | bondi fantasma % | MAE 3–7 min (n) | llega antes > 60 s % |
|---|---|---|---|---|---|---|---|
| viejo | 20 200 | 4,32 | 2,2 [1,9–2,4] | 7,7 [7,4–8,1] | 13,5 [13,1–14,0] | 180 s [163–199] (6049) | 15,3 |
| reexport | 20 200 | 4,31 | 2,2 [1,9–2,4] | 12,6 [12,1–13,0] | 16,9 [16,4–17,3] | 209 s [192–229] (6049) | 16,5 |

El viejo funciona con el recorrido viejo (bondi no anunciado 7,7 %, fantasma 13,5 %); el reexportado es peor en esos días (+5 pp no anunciado, +29 s) porque los coches que van por Acoyte quedan a > 45 m de sus recorridos. Es el costo simétrico del reexport en la ventana previa al cambio.

## 5. Reexport sin reentrenar

### 5.1 Cómo trata el modelo los shapeIds

`PathETAModel` no tiene embedding por shape ni índice «desconocido»: el tiempo de cada tramo de 250 m sale de (a) el embedding del lugar (celda de 500 m del `CityGridEncoder`, compartido por todas las líneas), (b) el embedding de la línea, (c) hora y día, (d) cantidad de paradas y distancia a la próxima en el tramo (`stops_feature`), y (e) el estado del coche. El shape solo indexa tablas estáticas del checkpoint, que son buffers y no pesos: `seg_lat`/`seg_lon` (puntos medios de las celdas de 250 m), `shape_off` y `stop_key`. Por eso un shapeId nuevo, o con otra geometría, funciona si se reconstruyen esas tablas.

### 5.2 Qué falla con el script actual

`export_path_onnx.py` verifica que la geometría y las paradas de `line_shapes` coincidan con los buffers del checkpoint y aborta (`SystemExit: ... cambió el recorrido desde el entrenamiento; reentrenar o usar el shapes-dir original`); y descarta los shapeIds que no están en el checkpoint. La verificación es una salvaguarda correcta contra desfase entre entrenamiento y servicio, no un límite del modelo.

### 5.3 Lo que se hizo

`reexport.py` reconstruye los 4 buffers desde los `line_shapes` actuales (shapes que ya no están, 6, se conservan en la tabla y no se exportan; shapeIds nuevos se agregarían: no hay), guarda un checkpoint temporal (en `cache/`, no versionado) y llama a `export_path_onnx.export`, con sus verificaciones de geometría, paradas y ONNX contra PyTorch (error máximo 0,0015 s). Resultado: `data/ml/export/path_v4_l1_s1_shapes20261126/` (17 MB, no versionado). `path_eta.onnx` tiene el mismo sha256 que el de v4; 646 shapes (el viejo tiene 652), de los cuales 81 cambian geometría o paradas; 33 051 paradas (33 362 antes).

Nota: `manifest.checkpoint.path` apunta al checkpoint original y agrega `nota` con el origen de las tablas.

### 5.4 Qué hace falta para producción

1. Copiar el directorio a `proyectoconsola/public/models/` y apuntar la app a él (fuera del alcance de esta prueba).
2. Un paso de reexport cada vez que cambien los `line_shapes` (hoy manual); el modelo no necesita reentrenarse.
3. Vara de modelo con geometría nueva: el eval congelado (`eval_seen`, validación 15/09–14/10, antes del cambio) mide distancias a lo largo del recorrido viejo; no se puede usar con la geometría nueva (ver 5.5).

### 5.5 Vara del modelo de la 42 (`prediccion.eval`, `eval_seen`, n = 1169)

| banda de ETA real | checkpoint original: MAE / llega antes > 60 s | tablas nuevas: MAE / llega antes > 60 s |
|---|---|---|
| 3–7 min (principal) | 59,2 s / 16,2 % | 68,8 s / 17,0 % |
| 0–2 | 20,7 / 5,6 | 27,5 / 10,2 |
| 4–6 | 62,2 / 16,5 | 71,0 / 17,4 |
| 10–15 | 126,9 / 34,1 | 126,0 / 31,4 |
| global | 119,0 / 24,9 | 126,7 / 26,0 |

El empeoramiento de la fila «tablas nuevas» es esperable y no es una medida válida: las filas del eval (`dist_along_m`, `dist_remaining_m`) están medidas a lo largo del recorrido viejo, y al leerlas sobre las celdas del recorrido nuevo (que desplazan las posiciones después del desvío) se predice otro tramo de calle. Es un desajuste de las filas, no del modelo. Resultados en `eval/`.

## 6. Lectura y salvedades

- **Hipótesis:** se confirma en producción para las paradas nuevas a > 45 m (9 de 15): 0 coches listados, 100 % de los instantes sin ningún coche cuando pasa uno, 100 % de los coches que pasan no anunciados. En las 6 paradas que sí enganchan (≤ 45 m) se listan coches (4,98 por instante), pero con `user_kind=punto` (sin ramal por nombre): 50,6 % de bondis fantasma y 37 % de bondi no anunciado.
- **Mejora del reexport** sobre el mismo período y verdad (tramo nuevo): sin coche listado 60,3 → 0 %, bondi no anunciado 76,0 → 1,0 %, bondi fantasma 50,6 → 8,3 %, MAE 3–7 min 177 → 91 s. En el resto de la línea también mejora (bondi no anunciado 14,1 → 8,6 %, MAE 225 → 199 s), porque los coches que corren por el desvío dejan de ser invisibles en las paradas de aguas abajo.
- **Peor que el viejo antes del 25/11**: el reexport no es retrocompatible con coches que van por el recorrido viejo (§4.3); hay que activarlo cuando el recorrido nuevo es el vigente.
- **MAE 3–7 min de la 42**: ~199–225 s en `resto` contra ~97 s del conjunto de 12 líneas de la vara de producto de referencia (ARQUITECTURA §6.1): la 42 anda mal en general, no solo en el desvío. El MAE de `a ≤ 45 m` (133 s) con n = 339 instantes y 60 s en las 9 paradas lejanas (n = 467) no se pueden comparar finamente entre sí.
- **Salvedades:**
  - Solo 3 días con recorrido nuevo (25/11 con huecos, 26/11, 27/11 hasta ~14:30), 28 + 103 + 50 instantes por parada. IC por cluster (parada × 30 min), no por día; no hay variación entre días hábiles ni entre semanas. No sacar conclusiones finas sobre las cifras de MAE.
  - Los instantes se limitan a horas con ≥ 1000 pings de la 42: la mañana del 25/11 y la noche del 27/11 quedan fuera.
  - La verdad usa el recorrido nuevo para definir el paso (cruce interpolado entre pings consecutivos compatibles con él). En las paradas de 6 a ≤ 45 m con el bundle viejo, el ramal asignado al viaje ex post (segmentador con los `line_shapes` actuales) puede diferir del que vería un coche en producción.
  - Con el bundle viejo, `nueva_cerca` se resuelve como `punto` con el snap a 45 m: es la lectura del enunciado (el mapa/GPS). La app real puede mostrar la parada de otra manera; el 100 % en las lejanas no depende de esa elección (no enganchan en ningún caso).
  - La verificación contra la conducta del usuario (qué ve exactamente en producción) no se hizo: es una réplica con la lógica fijada, con los pings de grabación.
  - Sello de CABA: el ts es de lote, no hora GPS (memoria del proyecto); el ETA anunciado usa el descuento de 60 s de producción (`ann0` en la métrica de MAE: hora común).
  - Los cambios de las demás líneas (§2.3) no se validaron con pings ni replay.

## 7. Archivos

- `experiments/recorridos_nuevos_42/`: `diff_shapes.py`, `pings42.py`, `pings_recorrido.py`, `reexport.py`, `replay42.py`, `core_head.py` (copia de `prediccion/replay/core.py` en `HEAD`), `metricas42.py`, `tablas42.py`.
- Resultados versionados en `data/ml/replay/recorridos_nuevos_42/`: `diff_lineas.json`, `diff_42.json`, `pings_dias.csv`, `pings_horas.csv`, `pings_tramos.csv`, `metricas.json`, `metricas.txt`, `tablas.md`, `eval/`.
- No versionados: `cache/` (pings y checkpoint temporal), `run/` (parquet del replay), `data/ml/export/path_v4_l1_s1_shapes20261126/` (17 MB).
