# Prior de ramal por cabecera (2026-11-27)

Pregunta: el ramal del próximo coche que sale de una cabecera, ¿es predecible con información de tiempo real a nivel línea/cabecera (no por coche)? Medición; no se entrenó ningún modelo del pipeline ni se tocó la app.

## Método
- Líneas con más de un ramal (shapes en `proyectoconsola/data/line_shapes/{N}.json`): 39 (6 shapes, 3 ramales), 42 (6; A, B, C), 50 (4; A, C), 106 (4; A, B), 107 (3; A ida y vuelta, B solo vuelta), 132 (4; A, B), 151 (4; A, B), 168 (4; 168 y 168C).
- Viajes ex post: `data/ml/v4/daily/*.trips.parquet` (shape elegido por geo3 sobre segmentador geo2), ramal = `shortName` del shape. Solo `start_unknown = 0`. `load.py` arma `trips8.parquet` (329 900 viajes de las 8 líneas, 2026-07-20 a 10-14).
- Cabecera = origen del shape (`direction_id` del parquet no es confiable para esto). Se usan las cabeceras donde salen ≥ 2 ramales: 39 Barracas y Chacarita (A, B, C); 42 Ciudad Universitaria (A, B) y Nueva Pompeya (A, B, C); 50 Plaza del Correo y Eva Perón (A, C); 106 Liniers (A, B); 107 Ciudad Universitaria (A, B); 132 Cementerio de Flores y Retiro (A, B); 151 Puente Saavedra (A, B); 168 La Boca (168, 168C). Las cabeceras de un solo ramal (p. ej. 168 San Isidro) son triviales y quedan fuera.
- Salidas ordenadas por `start_ts` dentro de la cabecera, cualquier coche. Un contexto previo solo vale si el despacho está a ≤ 90 min (si no, "sin dato").
- Train 2026-07-20 a 09-14; test 2026-09-15 a 10-14 (fuera de muestra, un modelo por cabecera). Tipo de día: hábil / sábado / domingo (feriados 08-17 y 10-12 como domingo).
- Modelos (suavizado de Dirichlet; hiperparámetros por validación cruzada por bloques de días dentro del train):
  - base freq: ramal más frecuente de la cabecera en train (acc = ese ramal; logloss = con la distribución de train). base unif: 1/K.
  - (a) P(ramal | hora, tipo de día), con retroceso a tipo de día y a la cabecera.
  - (b) P(ramal | ramales de los 3 despachos anteriores de la cabecera), con retroceso 3 → 2 → 1 → marginal.
  - (c) producto de expertos de (a) y (b) con pesos ajustados en predicciones fuera de bolsa del train. cq = (c) + experto de los últimos 6 despachos ("cuotas"; en todas las cabeceras salvo 151 su peso salió negativo, es decir, un ramal recién despachado más veces es menos probable).
- Scripts: `load.py`, `prior.py` (modelos y métricas; salida `result.pkl`, `por_grupo.csv`), `analisis.py` (calibración, producto, CuandoSubo; salida cruda `analisis_out.txt`). Correr desde `prediccion colectivos` con Python313. Tarda segundos.

## Resultados en test (accuracy / logloss, todas las cabeceras multi-ramal de la línea juntas; menor logloss es mejor)

| Línea | n | unif | freq | (a) hora × día | (b) secuencia | (c) a+b | cq |
|---|---|---|---|---|---|---|---|
| 39 | 16317 | 0.289 / 1.099 | 0.372 / 1.093 | 0.389 / 1.055 | 0.668 / 0.776 | 0.685 / 0.723 | **0.699 / 0.712** |
| 42 | 5540 | 0.503 / 0.997 | 0.503 / 0.935 | 0.540 / 0.833 | 0.569 / 0.888 | **0.593 / 0.822** | 0.587 / 0.831 |
| 50 | 9433 | 0.717 / 0.693 | 0.717 / 0.596 | 0.716 / 0.582 | 0.717 / 0.540 | 0.721 / 0.531 | **0.743 / 0.517** |
| 106 | 10370 | 0.603 / 0.693 | 0.603 / 0.672 | 0.603 / 0.666 | 0.651 / 0.635 | 0.642 / 0.630 | **0.659 / 0.616** |
| 107 | 3157 | 0.688 / 0.693 | 0.688 / 0.621 | 0.687 / 0.625 | 0.688 / 0.583 | 0.688 / 0.584 | 0.692 / 0.581 |
| 132 | 17403 | 0.569 / 0.693 | 0.569 / 0.683 | 0.571 / 0.677 | 0.666 / 0.614 | 0.682 / 0.608 | **0.689 / 0.598** |
| 151 | 5360 | 0.127 / 0.693 | 0.873 / 0.398 | 0.873 / 0.401 | 0.873 / 0.396 | 0.873 / 0.398 | 0.873 / 0.396 |
| 168 | 4680 | 0.461 / 0.693 | 0.539 / 0.690 | 0.608 / 0.644 | 0.675 / 0.604 | **0.733 / 0.570** | 0.723 / 0.564 |

Lectura:
- (a) hora × tipo de día casi no le gana a la base: 39 +1.7 pp de accuracy y −0.04 de logloss; 106, 107, 132, 151 y 50, nada. Única excepción real: 42 (acc 0.540 contra 0.503, logloss 0.833 contra 0.935), por servicios que solo corren en ciertas horas: en Nueva Pompeya de noche 42C no sale nunca (P 0.00, real 0.00), 42B casi no (0.07 contra real 0.08) y 42A sale el 92 %.
- (b) secuencia es lo que mueve la aguja en 39 (acc 0.372 → 0.668, logloss 1.093 → 0.776), 132 (0.569 → 0.666), 168 (0.539 → 0.675), 106 (0.603 → 0.651) y 50 (logloss 0.596 → 0.540 con acc igual). En 107, 151 y 42 el aporte es chico.
- El patrón de la 39 es una rotación casi fija. P(siguiente | anterior) para Barracas: tras A sale B (58 %) o C (32 %); tras B sale C (78 %); tras C sale A (52 %) o B (42 %). Repetir el mismo ramal es raro (5–10 %). Chacarita idéntico (A→B 57 %, B→C 70 %, C→A 52 %). Despacho mediano cada 3–4 min.
- (c) suma a (b) en 39, 168, 132, 42; cq suma un poco más con las cuotas (39 0.712, 50 0.517, 106 0.616, 132 0.598). Con 151 (87 % B) nada le gana a la base: no hay incertidumbre que reducir.
- Donde la mezcla de ramales es casi pareja (39, 168) la base freq no mejora a uniforme (logloss 1.093 contra 1.099; 0.690 contra 0.693) y es donde la secuencia más aporta.

## Calibración (modelo cq, test, deciles de P predicha por par viaje-ramal)
| P media | real (todas las líneas) | P media | real (39) | P media | real (168) |
|---|---|---|---|---|---|
| 0.04 | 0.05 | 0.02 | 0.03 | 0.09 | 0.16 |
| 0.12 | 0.13 | 0.04 | 0.05 | 0.20 | 0.22 |
| 0.20 | 0.19 | 0.07 | 0.07 | 0.30 | 0.22 |
| 0.29 | 0.29 | 0.11 | 0.12 | 0.38 | 0.31 |
| 0.38 | 0.37 | 0.16 | 0.15 | 0.46 | 0.48 |
| 0.47 | 0.47 | 0.25 | 0.31 | 0.54 | 0.52 |
| 0.57 | 0.58 | 0.42 | 0.43 | 0.62 | 0.69 |
| 0.67 | 0.66 | 0.62 | 0.57 | 0.71 | 0.78 |
| 0.76 | 0.78 | 0.76 | 0.75 | 0.80 | 0.78 |
| 0.88 | 0.87 | 0.88 | 0.86 | 0.92 | 0.85 |

ECE: todas 0.009, 39 0.019, 168 0.050 (n por línea más chico, 4680 viajes). La calibración global es muy buena. Dentro de la 39 y la 168 es razonable. La base freq también tiene ECE 0.010, porque calibrada no es informativa: lo valioso es la resolución (cuántas P alejadas de la mezcla).

Resolución: viajes en los que el prior da P(ramal más probable) ≥ 0.8 (y acierto real): 39 35 % de los viajes (0.853), 50 41 % (0.891), 168 31 % (0.829), 107 29 % (0.893), 151 58 % (0.889), 42 18 % (0.893), 132 15 % (0.827), 106 4 % (0.927). Con ≥ 0.6: 39 79 % (0.753), 50 78 % (0.789), 168 75 % (0.782), 132 70 % (0.745), 107 77 % (0.723), 106 65 % (0.716), 42 45 % (0.700).

## Traducción a producto
P(pasa por la parada del tramo exclusivo de R) para un coche de ramal desconocido que acaba de salir = P(ramal = R). Fuente: tabla "Traducción a producto" de `analisis_out.txt` (días hábiles de test). Ejemplos:
- 39, Chacarita, pico 7–9: el prior de hora da 0.33 / 0.33 / 0.34 (A/B/C), real 0.35 / 0.32 / 0.33. Sin secuencia, la 39 es 1/3 para cada una y no se gana nada.
- 39, con secuencia (cq): 35 % de las salidas tienen un ramal con P ≥ 0.8 y acierta el 85 %; el 79 % tiene P ≥ 0.6 y acierta el 75 %.
- 42 Nueva Pompeya, noche 21–23 hábil: P(42A) 0.93 (real 0.92), P(42B) 0.07 (0.08), P(42C) 0.00 (0.00). Esto sí sirve solo con hora × día.
- 151, Puente Saavedra: P(151A) 0.20 (pico) contra real 0.12 (n 1013) y 0.21 contra 0.13 (valle): el prior sobreestima 151A en test (cambio de mezcla entre train y test; 151A pesa 12–13 % en test y 20 % en train).
- 168 La Boca, noche: P(168) 0.75 contra real 0.61 (n 155): muestras chicas, diferencias de hasta 14 pp.

## Validación con la verdad de CuandoSubo (2026-09-23 a 10-03, `route_id_diag` → `ROUTE_AGENCY_MAP` del 2026-11-13 → `ramal_cuandosubo.json` → shape → ramal)
Las predicciones de test (con contexto de la etiqueta ex post) puntuadas contra el ramal de CuandoSubo, solo en viajes con `route_id` y ramal único resuelto:

| Línea | n con CS | Acuerdo ex post–CS | cq acc contra CS (contra ex post) | freq acc contra CS |
|---|---|---|---|---|
| 39 (Barracas + Chacarita) | 2444 | 0.94 | 0.665 (0.687) logloss 0.791 | 0.399 |
| 168 La Boca | 976 | 0.92 | 0.731 (0.752) logloss 0.559 | 0.551 |
| 132 Flores / Retiro | 1322 / 1028 | 0.94 / 0.91 | 0.684 / 0.623 | 0.542 / 0.557 |
| 107 CU | 343 | 0.97 | 0.691 | 0.685 |

Detalle 39 (acc / logloss contra CS): unif 0.226 / 1.099, freq 0.399 / 1.083, (a) 0.347 / 1.079, (b) 0.655 / 0.812, (c) 0.658 / 0.786, cq 0.665 / 0.791. 168: freq 0.551 / 0.688, (a) 0.629 / 0.650, (b) 0.681 / 0.621, (c) 0.741 / 0.578, cq 0.731 / 0.559.
La ganancia de la secuencia se mantiene con una etiqueta independiente del pipeline (caída de 2 pp en acc respecto de ex post). No es un artefacto del segmentador ni de geo3.
50, 106 y 42 no son interpretables con CuandoSubo: la tabla de `ramal_cuandosubo.json` solo resuelve un ramal de cada una (la freq "acierta" 0.99–1.0 por selección de muestra). 151 no tiene viajes con ramal único resuelto en esos días.

## Salvedades
- El contexto del prior (ramales de los despachos anteriores) son etiquetas ex post. En tiempo real, el ramal de un coche que salió hace 3–4 min también es desconocido hasta que pasa por un tramo exclusivo o llega el dato de CuandoSubo. Habría que encadenarlo: un coche adelante que se resuelve informa al de atrás. Esto no se midió. Por eso el resultado es el techo con contexto conocido, no un desempeño en producción.
- Los despachos con `start_unknown = 1` quedan fuera de la secuencia: en 42 (39 % desconocido) y 151 (23 %) la cadena tiene huecos (tratados como "sin dato" cuando el hueco > 90 min; huecos cortos no se detectan, el despacho anterior pasa a ser el siguiente conocido).
- 39: la etiqueta ex post del ramal A es la menos confiable (A no tiene tramo exclusivo, 74 % de acuerdo con CS en ese ramal según `ramal_persistencia_39`); acá el acuerdo global ex post–CS es 0.94 en 3 días de verificación nuevos.
- En 107 el ramal B solo existe en un sentido; en 168 la cabecera de Puente Saavedra y la de San Isidro tienen un solo ramal (trivial). La "cabecera" es el origen del shape; coches con ramal conocido por cabecera distinta no están en la medición.
- Test de 30 días con feriado del 10-12 tratado como domingo; no hay ajuste fino de feriados ni de cambios de servicio. 151 muestra deriva train → test.
- Las medias por franja con n < 300 (noches) son ruidosas.

## Conclusión
Con el contexto de los despachos anteriores conocido, sí hay información útil: la 39 pasa de 0.37 a 0.70 de acierto (el patrón es una rotación A→B→C), la 168 de 0.54 a 0.72, la 132 de 0.57 a 0.69; los priors de hora × día solo importan en la 42. Está bien calibrado (ECE 0.009) y es utilizable como entrada de P(el coche pasa por la parada), con la condición de resolver el contexto en tiempo real (no medido).



---

## Segunda ronda (v3), 2026-11-27

Misma medición sobre las 48 líneas de la segunda ronda: las 36 líneas nuevas de train de `data/ml/v3/lines.json` (`new_lines`) y las 12 de control (`heldout`, marcadas con `*`). Las 12 originales de train de v3 (de las que 8 ya se midieron arriba) quedan fuera. Medición; no se tocó pipeline, app ni ARQUITECTURA.

### Método
- Idéntico al de la primera ronda: cabecera = origen del shape (`line_shapes/{N}.json`), ramal = `shortName` sin espacios, `start_unknown = 0`, cabeceras con ≥ 2 ramales observados, train 2026-07-20 a 09-14, test 09-15 a 10-14, mismos modelos e hiperparámetros por validación cruzada (`prior.py` importado tal cual). Viajes de `data/ml/v4/daily/` (v4 tiene las 48 líneas): 1 509 884 viajes, 1 160 188 con `start_unknown = 0`, 399 356 en test.
- Script nuevo: `ronda2.py` (arma `trips48.parquet`, corre todo, deja `result48.pkl`, `ronda2_out.txt`, `ronda2_lineas.csv`, `ronda2_cs.csv`). Correr desde `prediccion colectivos` con Python313.
- Se evaluaron las 62 cabeceras multi-ramal (todas pasan el mínimo de 150 viajes de train y 100 de test; no se omitió ninguna).
- Peso del problema = % de los despachos de test de la línea que salen de una cabecera multi-ramal. En el resto (cabeceras con un solo ramal) el ramal sale directo de la cabecera.

### Estructura y peso del problema
- 29 de las 48 líneas tienen al menos una cabecera multi-ramal (23 de las 36 nuevas, 6 de las 12 de control). Las otras 19 no tienen problema de ramal en cabecera: 1, 25, 41, 44, 65, 74, 76, 84, 102, 109, 123, 128, 184 tienen un solo ramal; 61, 87, 115, 118, 143 tienen 2 ramales pero cada uno sale de una cabecera distinta; 68 tiene 2 en el shape pero el ex post solo ve 1.
- Esas 29 líneas concentran 226 731 de los 399 356 despachos de test de las 48 (56,8 %). Pesos por línea en la tabla siguiente.
- Shapes / ramales y cabeceras multi-ramal (entre paréntesis, ramales que salen de ella): 4 (4/2; Lomas del Mirador 2), 7 (4/2; Retiro 2), 9 (6/3; Retiro 3, Villa Caraza 3), 20 (4/2; Cruce de Lomas, Retiro), 28 (18/9; Barrio Hernández 2, Ciudad Universitaria 4, La Noria 5, Retiro 4), 29 (6/4; La Boca, Olivos, Parque Sarmiento, 2 c/u), 33 (10/5; Ciudad Universitaria 4, San José 4), 34 (4/2; Liniers), 46 (4/2; La Boca, San Justo), 47 (4/2; Autódromo, Chacarita), 62 (2/2; Constitución), 85 (6/3; Balneario Quilmes 3, Ciudadela Norte 3), 88 (6/3; Once 2), 98 (14/7; Once 7, Quilmes 2, Villa España 2, Wilde 3), 110 (4/2; Facultad de Derecho, Villa Martelli), 113 (4/2; Barrancas de Belgrano, San Justo), 114 (6/3; Barrancas de Belgrano, Puente La Noria), 127 (4/2; San Cristóbal, Villa Hidalgo), 169 (6/3; Congreso y Cabildo, Remedios de Escalada), 180 (14/7; Caballito 4, Kilómetro 29 6, Puerto Madero 2), 188 (8/4; Cruce de Lomas 4, Plaza Italia 3), 194 (6/3; Once 3), 197 (16/8; Once 3, Retiro 4, Rotonda de Alpargatas 3, "Rotonda de Apargatas" 2), 12* (4/2; Palermo, Puente Pueyrredón), 15* (8/4; Benavidez 2, Pacheco 2, Puente Alsina 4), 21* (16/8; Fábrica Ford 3, La Noria 4, Liniers 4, Tigre 3), 64* (3/2; Barrancas de Belgrano), 100* (6/3; Lanús, Retiro), 181* (4/2; Boedo, Ramos Mejía).
- En la 197 el origen del shape tiene una errata en el dato ("Apargatas") que parte la cabecera de Rotonda de Alpargatas en dos; se dejó tal cual (misma definición de cabecera).

### Resultados en test (cq contra freq; accuracy / logloss), ordenado por Δlogloss × peso
Δll = logloss(freq) − logloss(cq) (positivo = cq mejor). Peso = % de despachos de test de la línea en cabecera multi-ramal. n = despachos de test en cabeceras multi-ramal. ECE de cq (entre paréntesis el de freq); P≥0,8 = % de despachos con P(ramal más probable) ≥ 0,8 y su acierto.

| Línea | n test | peso | freq acc / ll | (a) | (b) | (c) | cq | Δll cq vs freq | Δll × peso | ECE cq (freq) | P≥0,8: % / acierto |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 33 | 6879 | 63 % | 0.362 / 1.298 | 0.394 / 1.245 | 0.678 / 0.855 | 0.699 / 0.823 | 0.709 / 0.799 | +0.499 | +0.316 | 0.016 (0.003) | 45 % / 0.865 |
| 110 | 9704 | 100 % | 0.506 / 0.693 | 0.521 / 0.681 | 0.818 / 0.431 | 0.822 / 0.421 | 0.822 / 0.423 | +0.270 | +0.270 | 0.015 (0.004) | 83 % / 0.874 |
| 181* | 6483 | 100 % | 0.506 / 0.693 | 0.518 / 0.687 | 0.837 / 0.430 | 0.837 / 0.424 | 0.837 / 0.424 | +0.269 | +0.269 | 0.034 (0.004) | 83 % / 0.881 |
| 85 | 8449 | 100 % | 0.468 / 1.058 | 0.474 / 1.040 | 0.588 / 0.827 | 0.615 / 0.811 | 0.625 / 0.793 | +0.264 | +0.264 | 0.012 (0.005) | 20 % / 0.873 |
| 180 | 11231 | 84 % | 0.325 / 1.452 | 0.383 / 1.295 | 0.437 / 1.277 | 0.462 / 1.200 | 0.487 / 1.172 | +0.280 | +0.235 | 0.007 (0.007) | 10 % / 0.932 |
| 98 | 19746 | 100 % | 0.447 / 1.224 | 0.460 / 1.193 | 0.572 / 1.046 | 0.583 / 1.023 | 0.600 / 0.993 | +0.232 | +0.232 | 0.005 (0.002) | 29 % / 0.923 |
| 188 | 8538 | 92 % | 0.423 / 1.226 | 0.481 / 1.132 | 0.493 / 1.077 | 0.519 / 1.021 | 0.557 / 0.985 | +0.241 | +0.220 | 0.008 (0.003) | 6 % / 0.851 |
| 9 | 8875 | 100 % | 0.528 / 0.812 | 0.542 / 0.752 | 0.739 / 0.640 | 0.740 / 0.619 | 0.739 / 0.593 | +0.219 | +0.219 | 0.018 (0.010) | 41 % / 0.858 |
| 20 | 4926 | 100 % | 0.590 / 0.674 | 0.599 / 0.622 | 0.758 / 0.520 | 0.792 / 0.485 | 0.798 / 0.476 | +0.198 | +0.198 | 0.032 (0.011) | 56 % / 0.867 |
| 113 | 7007 | 100 % | 0.630 / 0.659 | 0.639 / 0.636 | 0.738 / 0.526 | 0.744 / 0.510 | 0.810 / 0.483 | +0.176 | +0.176 | 0.053 (0.009) | 51 % / 0.886 |
| 169 | 6343 | 100 % | 0.511 / 0.695 | 0.512 / 0.691 | 0.758 / 0.539 | 0.758 / 0.541 | 0.757 / 0.534 | +0.161 | +0.161 | 0.034 (0.022) | 56 % / 0.822 |
| 46 | 4485 | 100 % | 0.532 / 0.691 | 0.582 / 0.671 | 0.701 / 0.581 | 0.721 / 0.560 | 0.723 / 0.558 | +0.132 | +0.132 | 0.020 (0.019) | 27 % / 0.851 |
| 4 | 3303 | 54 % | 0.573 / 0.683 | 0.560 / 0.664 | 0.810 / 0.443 | 0.819 / 0.422 | 0.815 / 0.437 | +0.246 | +0.132 | 0.052 (0.018) | 80 % / 0.885 |
| 28 | 17096 | 77 % | 0.495 / 1.088 | 0.544 / 0.949 | 0.543 / 0.991 | 0.560 / 0.931 | 0.575 / 0.921 | +0.168 | +0.128 | 0.010 (0.005) | 24 % / 0.962 |
| 21* | 21029 | 93 % | 0.372 / 1.218 | 0.407 / 1.135 | 0.453 / 1.166 | 0.476 / 1.105 | 0.482 / 1.083 | +0.135 | +0.125 | 0.007 (0.004) | 3 % / 0.897 |
| 100* | 7009 | 70 % | 0.671 / 0.633 | 0.677 / 0.621 | 0.783 / 0.478 | 0.783 / 0.478 | 0.790 / 0.464 | +0.168 | +0.117 | 0.018 (0.008) | 45 % / 0.908 |
| 127 | 5604 | 100 % | 0.644 / 0.653 | 0.679 / 0.611 | 0.694 / 0.579 | 0.682 / 0.557 | 0.739 / 0.537 | +0.116 | +0.116 | 0.032 (0.029) | 44 % / 0.859 |
| 29 | 9709 | 100 % | 0.793 / 0.493 | 0.792 / 0.456 | 0.783 / 0.414 | 0.795 / 0.389 | 0.815 / 0.383 | +0.110 | +0.110 | 0.011 (0.018) | 61 % / 0.936 |
| 197 | 5478 | 64 % | 0.545 / 0.997 | 0.558 / 0.909 | 0.571 / 0.928 | 0.602 / 0.849 | 0.617 / 0.837 | +0.161 | +0.103 | 0.019 (0.011) | 19 % / 0.859 |
| 15* | 4967 | 100 % | 0.838 / 0.563 | 0.842 / 0.506 | 0.840 / 0.546 | 0.842 / 0.497 | 0.843 / 0.487 | +0.076 | +0.076 | 0.013 (0.012) | 56 % / 0.922 |
| 12* | 16553 | 100 % | 0.893 / 0.341 | 0.893 / 0.292 | 0.893 / 0.336 | 0.893 / 0.287 | 0.893 / 0.276 | +0.065 | +0.065 | 0.011 (0.007) | 78 % / 0.935 |
| 194 | 3655 | 74 % | 0.627 / 0.806 | 0.631 / 0.781 | 0.637 / 0.752 | 0.632 / 0.737 | 0.666 / 0.727 | +0.079 | +0.059 | 0.015 (0.005) | 22 % / 0.837 |
| 62 | 2728 | 100 % | 0.805 / 0.495 | 0.805 / 0.459 | 0.805 / 0.489 | 0.805 / 0.454 | 0.797 / 0.446 | +0.049 | +0.049 | 0.025 (0.022) | 54 % / 0.894 |
| 47 | 3423 | 100 % | 0.902 / 0.322 | 0.901 / 0.308 | 0.902 / 0.306 | 0.903 / 0.291 | 0.903 / 0.292 | +0.029 | +0.029 | 0.025 (0.017) | 92 % / 0.911 |
| 7 | 2549 | 51 % | 0.659 / 0.642 | 0.665 / 0.602 | 0.662 / 0.615 | 0.693 / 0.587 | 0.676 / 0.585 | +0.057 | +0.029 | 0.051 (0.011) | 28 % / 0.833 |
| 114 | 4193 | 80 % | 0.938 / 0.230 | 0.938 / 0.205 | 0.938 / 0.228 | 0.938 / 0.204 | 0.938 / 0.204 | +0.026 | +0.021 | 0.009 (0.004) | 96 % / 0.946 |
| 34 | 9773 | 72 % | 0.814 / 0.480 | 0.817 / 0.466 | 0.814 / 0.475 | 0.814 / 0.461 | 0.821 / 0.456 | +0.024 | +0.018 | 0.017 (0.008) | 67 % / 0.870 |
| 64* | 5382 | 51 % | 0.850 / 0.423 | 0.850 / 0.417 | 0.850 / 0.402 | 0.850 / 0.395 | 0.850 / 0.396 | +0.027 | +0.014 | 0.024 (0.012) | 73 % / 0.900 |
| 88 | 1614 | 100 % | 0.709 / 0.640 | 0.693 / 0.630 | 0.543 / 0.687 | 0.654 / 0.610 | 0.581 / 0.729 | -0.089 | -0.088 | 0.186 (0.132) | 50 % / 0.695 |


Agregado de las 29 líneas (226 731 despachos): accuracy unif 0.503, freq 0.579, (a) 0.598, (b) 0.679, (c) 0.691, cq 0.703; logloss unif 1.006, freq 0.847, (a) 0.794, (b) 0.725, (c) 0.691, cq 0.678.

Lectura:
- cq le gana a freq en 28 de 29 líneas. Δll ≥ 0.05 en 23, Δll ≥ 0.10 en 19 (mediana 0.16); Δacc ≥ 5 pp en 18, ≥ 10 pp en 15. La única línea donde pierde es la 88 (1 618 despachos; cabecera Once con 2 ramales, cq 0.581 / 0.729 contra 0.709 / 0.640 de freq: (b) sobreajusta).
- Las mayores mejoras: 33 (freq 0.362 → cq 0.709; logloss 1.298 → 0.799), 110 y 181* (0.506 → 0.822 y 0.837: rotación casi alternada de dos ramales con mezcla 50/50), 85 (0.468 → 0.625), 9 (0.528 → 0.739), 20 (0.590 → 0.798), 113 (0.630 → 0.810), 169 (0.511 → 0.757), 46 (0.532 → 0.723), 4 (0.573 → 0.815). En líneas con muchos ramales (180, 98, 188, 28, 197, 21*) la ganancia de logloss es grande (0.13–0.28) pero el acierto absoluto queda en 0.48–0.62: son 5–9 ramales y hay pocos P ≥ 0.8 (3–29 % de los despachos).
- Casi no hay ganancia (Δll < 0.05) donde la cabecera ya está dominada por un ramal (freq acc ≥ 0.80): 12*, 34, 47, 62, 64*, 114. No hay incertidumbre que reducir: son multi-ramal pero con problema chico. 15* (freq 0.838) y 7 (0.659) también quedan bajas (Δll 0.076 y 0.057).
- (a) hora × día aporta poco en todas; (b) secuencia explica casi todo el salto (igual que en la primera ronda). cq suma sobre (c) 0.01–0.03 de logloss en la mitad de las líneas.

Top 10 por Δll ponderado (acierto freq → cq): 33 (0.362 → 0.709), 110 (0.506 → 0.822), 181* (0.506 → 0.837), 85 (0.468 → 0.625), 180 (0.325 → 0.487), 98 (0.447 → 0.600), 188 (0.423 → 0.557), 9 (0.528 → 0.739), 20 (0.590 → 0.798), 113 (0.630 → 0.810).

### Calibración (cq, test, deciles de P por par viaje-ramal, 29 líneas)
| P media | real |
|---|---|
| 0.002 | 0.006 |
| 0.03 | 0.04 |
| 0.08 | 0.09 |
| 0.14 | 0.14 |
| 0.20 | 0.21 |
| 0.27 | 0.27 |
| 0.37 | 0.37 |
| 0.55 | 0.55 |
| 0.78 | 0.77 |
| 0.95 | 0.93 |

ECE global 0.006 (nuevas 0.006, control 0.007; freq 0.002). Por línea ECE ≤ 0.035 en 25 de 29; las peores: 88 (0.186, la línea donde cq pierde), 4 (0.052), 113 (0.053), 7 (0.051). Calibración muy buena; ligera sobreconfianza en el decil superior (0.95 prometido, 0.93 real).

Resolución: 43 % de los despachos tienen P(ramal más probable) ≥ 0,8 y aciertan 0.896; 67 % tienen P ≥ 0,6 y aciertan 0.827. Por línea, el acierto con P ≥ 0,8 está entre 0.82 y 0.96 en todas salvo la 88 (0.695).

### Validación contra CuandoSubo
No se puede en esta ronda. `proyectoconsola/public/config/ramal_cuandosubo.json` (tabla `route_id` de CuandoSubo → shape → ramal) solo tiene entradas de las líneas originales (26, 39, 42, 50, 92, 99, 106, 107, 108, 124, 132, 151, 168); ninguna de las 48 líneas de esta ronda está. `ronda2.py` incluye el cruce y sale vacío. Esta ronda se mide solo contra la etiqueta ex post (en la primera ronda el acuerdo ex post–CS era 0.91–0.97 y la ganancia de la secuencia bajaba ~2 pp contra CS).

### Salvedades
- Valen las de la primera ronda: el contexto (ramales de los despachos anteriores) son etiquetas ex post; en producción hay que encadenarlo y eso no se midió. Es el techo con contexto conocido.
- Sin verdad independiente en estas 48 líneas, la calidad de la etiqueta ex post en ramales sin tramo exclusivo es desconocida; en las de muchos ramales (21, 28, 98, 180, 197) shapes casi iguales pueden volver ruidosa la etiqueta, y la accuracy mezcla error de etiqueta con error de predicción.
- Cabeceras con hasta 7 ramales (98 Once): pocas observaciones por combinación de contexto; (b) retrocede a contexto corto.
- Pesos de test calculados sobre despachos con `start_unknown = 0`; líneas con mucho `start_unknown` pueden estar subrepresentadas.

### Conclusión de la segunda ronda
El patrón de la 39, la 168 y la 132 es general: en 28 de las 29 líneas con cabecera multi-ramal la secuencia de despachos mejora el logloss de freq (en 19, más de 0.10) y el acierto sube 5 pp o más en 18; falta ganancia solo donde un ramal ya domina la cabecera. El problema pesa: 57 % de los despachos de estas 48 líneas salen de una cabecera multi-ramal. Calibración muy buena (ECE 0.006). Siguen pendientes la validación independiente y el encadenado en tiempo real.
