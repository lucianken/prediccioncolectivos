# Diagnóstico: ¿por qué el A3 no aprendió lo que sabe la tabla A1? (línea 39)

Fecha: 2026-11-11. Scripts: `prediccion/v2/diag/` (`common.py`, `d1_train_vs_val.py`, `d2_breakdown.py`, `d3_extract_hist.py`, `d3_leak.py`). Solo inferencia y
estadística sobre modelos ya entrenados; no se entrenó nada ni se tocó modelo, pipeline o datos. Tablas completas: `d1_tables.md`, `d2_tables.md`, `d3_tables.md`;
crudos: `d1_results.json`, `d2_results.json`, `d3_results.json` (misma carpeta).

Modelos: A1 `a1_v1794415690.pkl` (entrenada con el train v2 completo, que incluye estas filas de train: en train es "en muestra"); A3-K32 `v2_39_k32/models/eta_a3_best.pt`
(época 16); A3-K64 `v2_39_k64/models/e1_k64.pt`. Reproducen exactamente los MAE ya publicados en `eval_seen --lines 39` (A1 96,7 / A3-K32 105,6 / A3-K64 106,7 s).

## Resumen

1. **El A3 pierde contra A1 también en entrenamiento** (MAE 104,4 vs 99,3 s en 100 k filas de train; en eval 105,6 vs 96,7). Entre train y eval el A3 casi no cambia
   (104,4 -> 105,6). **No es sobreajuste: no logra representar la función** con las entradas que tiene.
2. **La causa que mejor apoyan los datos es H-identidad, sobre todo el sentido (ida/vuelta)**: el A3 no recibe `shape_id` ni sentido y la posición le llega solo como fracción del
   recorrido (dos recorridos de sentido opuesto a igual fracción están a una mediana de 6,3 km). Evidencia fuerte pero indirecta (§D2).
3. **H-representación (no puede dibujar los escalones): no apoyada.** El A3 reproduce la forma del perfil de velocidad (correlación 0,885 vs 0,94 de A1; misma amplitud).
4. **H-pérdida: real pero menor.** Explica el sesgo +30 s en 0-5 min, pero a < 500 m la brecha de MAE es de 3,6 s y aporta ~0,5 s de los ~5 s de brecha global (train); el 81 % (train)
   / 87 % (eval) del exceso está a más de 2 km, donde q = 0,5.
5. **Fuga por el shape ex post (D3): existe, pero es chica.** Es el shape del viaje completo para A1 y A3. 77,6 % de las filas de eval tienen a P en un tramo ambiguo
   (>= 2 recorridos compatibles con los pings hasta P). Sin fuga, A1 pasa de 96,7 a **97,6 s** (promedio de candidatos) o **100,5 s** (el de mejor ajuste hasta P), contra A3 105,3 / 106,6 s
   (misma sustitución, aproximada). La brecha A3-A1 baja de 8,9 s a **7,7 s** (promedio) o **6,1 s** (mejor ajuste): la fuga explica entre ~10 % y ~30 % de la ventaja de A1. Y en las filas **no ambiguas** (shape
   sin duda) A1 gana por 8,9 s: la ventaja no depende de la fuga.

## D1: ¿generaliza mal o no logra representar?

Muestra de train: 100 000 filas de `v2_39_k32/training/eta_train.parquet` (4,1 M filas), mismo filtro que la vara, 25 k por bucket de ETA real como eval_seen. Comparado con
`eval_seen` filtrado a la 39 (n = 3770).

| MAE global (s) | A1 | A3-K32 | A3-K64 |
|---|---:|---:|---:|
| train (muestra, 100 k) | **99,3** | 104,4 | 107,1 |
| eval_seen 39 (3770) | **96,7** | 105,6 | 106,7 |

Por bucket de ETA real (MAE s; sesgo s entre paréntesis cuando importa):

| ETA real | A1 train | A3-K32 train | A1 eval | A3-K32 eval |
|---|---|---|---|---|
| 0-5 min | 35,5 (-2,6) | 43,6 (+28,8) | 36,1 (-4,8) | 46,2 (+29,7) |
| 5-10 min | 70,2 | **66,7** | 72,0 | **68,5** |
| 10-20 min | 105,1 | 111,8 | 100,8 | 108,6 |
| 20+ min | 186,5 | 195,6 | 159,7 | 179,3 |

Por distancia (MAE, train, A1 vs A3-K32): <500 m 49,9 vs 53,5; 0,5-2 km 71,4 vs 72,7; 2-5 km 98,8 vs 106,4; 5+ km 176,1 vs 185,5. Mismo patrón en eval. P50, P90, sesgo y % de subestimaciones > 60 s
en `d1_tables.md`.

**Lectura:** el orden A1 < A3 se repite en train y en eval. El A3 casi no cambia de train a eval (+1,2 s) y A1 mejora (-2,6 s). Un modelo sobreajustado tendría un train mucho mejor que el eval; este
no. Con 4 M de filas de train el A3 no alcanza a la tabla: **no logra representar** lo que la tabla sabe.

### El "MAE train 48 s > val 41 s" del log no es MAE

El `train_mae_s`/`val_mae_s` del log de `train_phase3` es **la pérdida pinball** (q 0,5 -> 0,8 bajo 1 km), no el MAE: con q = 0,5 vale la mitad del MAE. Recalculada sobre muestras naturales (sin estratificar, como
el log) con el A3-K32 época 16:

| | train (315 k filas) | val (300 k filas) |
|---|---:|---:|
| pinball, dropout activo (como el train del log) | **48,1** | 44,9 |
| pinball, modo eval (como el val del log) | 43,0 | **40,4** |
| MAE real, modo eval | 88,0 | 83,2 |
| MAE real, dropout activo | 97,9 | 92,1 |
| log de entrenamiento (época 16) | 47,8 | 41,0 |

Se reproduce el log. Los ~7 s de diferencia se descomponen en:
- **Dropout: ~5 s** (48,1 -> 43,0 en train). El valor de train del log se mide con dropout 0,1 activo y el de val sin él. Es la causa principal.
- **Período de validación más fácil: ~2,7 s** (43,0 -> 40,4, ambos en modo eval). No es la mezcla de distancias (casi idéntica: <500 m 22 %, 0,5-2 km 41-42 %, 2-5 km 19 %, 5+ km 17-18 %), sino el período: ETA medio 664 s en val
  vs 708 s en train. **A1 muestra el mismo salto** (MAE 82,3 en train natural -> 76,1 en val, pinball 42,6 -> 39,4) siendo una tabla sin dropout, así que es el período y no el modelo. Pinball por mes del A3: abril 45,4 (el peor), septiembre 38,6-39,4.
- Comparación limpia (MAE en modo eval, misma muestra natural): **A1 82,3 / A3 88,0 en train y 76,1 / 83,2 en val** (A1 gana por 5,8 y 7,1 s). Para comparar modelos hay que usar MAE en modo eval, nunca el número del log.

## D2: ¿dónde pierde el A3?

(Δ = MAE A3 - MAE A1; ep = error estándar del Δ pareado.)

### Concentración: la ventaja de A1 es pareja, con algunos núcleos

| Corte (train 100 k) | Δ por grupo | Comentario |
|---|---|---|
| shape_id (6) | 382202 (39A ida) +0,3; 382208 +4,5; 382209 +5,0; 382211 +5,8; 382210 +7,0; 382203 +7,2 | A1 gana en 5 de 6; el 39A ida empata |
| sentido | ida +4,2; vuelta +6,1 | vuelta aporta 59 % del exceso (60 % en eval) |
| franja | pico mañana **-1,7** (A3 gana); valle +5,7; pico tarde +8,5; noche +6,9 | A3 solo empata en pico mañana |
| tramo del coche (1 km) | de -6,1 (km 3) a +13,9 (km 9); picos km 1 (+11,4) y km 8-9 (+14) | A1 mejor en 14 de 17 tramos |
| tramo del objetivo | de -2,7 a +11,6, creciente hacia el final del recorrido (km 15-16: +10 a +12) | |
| distancia restante | <500 m +3,6; 0,5-2 km +1,3; 2-5 km +7,5; 5+ km +9,3 | 81 % del exceso a > 2 km |
| zona (hermanos del mismo sentido) | compartido +4,5; separado >150 m +6,8 | 25 % de las posiciones en zona separada |

En eval (n = 3770, ep de 2 a 6 s por tramo) sale lo mismo con más ruido: 382203 +14,3, 382210 +11,6; noche +12,5, pico tarde +12,3, valle +10,8, pico mañana -1,1; 5+ km +20,7 (60 % del exceso).
Por celdas (shape x km del coche, >= 20 filas): A1 es mejor en 84 de 100 celdas en train (57 de 78 en eval); el 20 % de celdas con más exceso concentra 53 % (train) / 57 % (eval) de la ventaja.
**Pareja a lo largo de todo el recorrido, con algo de concentración en los km 1-2 y 8-9 y en 382203 / 382210; no localizada en pocos tramos.**
Gráficos: `d2_mae_por_tramo_train.png` (MAE por tramo de 1 km, un panel por recorrido), `d2_mae_por_tramo_agregado.png`.

### H-representación: el A3 NO aplana los picos

Con consultas de 1-3 km (fuera de la zona q > 0,5), velocidad implícita Σdist/Σeta por tramo de 1 km: `d2_velocidad_implicita.png`.

| Promedio de los 6 recorridos | A1 | A3-K32 |
|---|---:|---:|
| correlación del perfil con el observado | 0,94 | 0,885 |
| desvío del perfil / desvío observado (1 = sin aplanar) | 0,81 | 0,79 |
| RMSE del perfil sin nivel (km/h) | 0,67 | 0,89 |

El A3 reproduce la forma (valles en km 4 y 10 de la ida, subida al final de la vuelta) con la misma amplitud que A1 (ambos algo por debajo de lo observado). Lo que falla son **desplazamientos y errores de nivel**: en las
idas, desde el km 12 el A3 sube a 16 km/h cuando lo observado y A1 dan 14-15; en las vueltas el final queda por debajo (16-17 vs 19). Otra medida: contra un baseline "plano" (velocidad por recorrido y hora, sin
posición; MAE 129,0), el A3 captura 83 % (train) / 72 % (eval) de lo que gana A1 (MAE A1 99,3; A3 104,4). `d2_captura_perfil.png`. **Evidencia en contra de "no puede representar escalones"; a favor de "le falta información o se confunde de lugar".**

### H-identidad: lo que mejor encaja

- **El A3 no ve el sentido ni el `shape_id`.** La posición entra como `dist_along_norm` y `dist_remaining_norm` (metros / largo del recorrido). A igual fracción, dos recorridos del mismo sentido están a una mediana de 129 m
  (P90 862 m): ruido moderado. A igual fracción, uno de ida y uno de vuelta están a una mediana de **6,3 km** (P90 9,9 km): lugares distintos.
- **Estructura de la velocidad** (R² de log-velocidad, consultas 1-3 km): fracción 0,123; fracción x sentido 0,197; shape x tramo 0,217; fracción x sentido x franja 0,372. Agregar el sentido sube el R² de 0,123 a 0,197 (+60 %): información que una red ciega al sentido
  no puede usar salvo que la infiera.
- **Ablación en A1** (inferencia): consultar a A1 con otro recorrido a igual fracción empeora el MAE de 99,3 a 113,9 s (mismo sentido) y a 154,1 s (sentido opuesto). Una tabla ciega a la identidad perdería más que el A3 (104,4), porque el A3 compensa con velocidad
  reciente, hora y trayectoria, pero el margen entre "con" y "sin" identidad (>= 14 s) es mayor que la brecha A3-A1 (5-9 s).
- **El error de nivel del A3 se anticorrelaciona entre ida y vuelta** a igual fracción: correlación de log(v_modelo/v_obs) entre sentidos = **-0,60 para A3 vs -0,02 para A1**. El A3 se equivoca para un lado como acierta en el otro: típico de un perfil promedio de dos lugares distintos. El
  sesgo firmado también difiere por sentido solo en A3 (ida -36 s, vuelta -6,5 s; A1 -31 / -27).
- La concentración por recorrido/sentido es débil (Δ de +0,3 a +7,2), por lo que H-identidad se apoya sobre todo en la anticorrelación y en la estructura, no en un recorrido aislado.

Límite: la anticorrelación es un indicio fuerte, no una prueba (no hubo intervención). La identidad tampoco explica todo: la brecha en tramos "compartidos" (+4,5 s) es la mayor parte del total.

### H-pérdida: efecto real, chico en el MAE global

Cobertura del A3 (fracción de casos con real <= pred), train: <250 m 0,80 (q objetivo ~0,76); 250-500 m 0,71 (0,69); 0,5-1 km 0,53 (0,57); 1-2 km 0,44; >2 km 0,46. El A3 hace lo que la pérdida le pide; A1 cubre solo 0,17-0,41 a < 500 m. De ahí
el sesgo +29,7 s en 0-5 min y las subestimaciones > 60 s en 6-9 % vs 17 % de A1 a < 500 m: un trueque deliberado. Costo en MAE: a < 500 m la brecha es de 3,6 s; recentrando la mediana del A3 el MAE a < 250 m baja de 46,8 a 40,7 s (A1: 46,6) y a 250-500 m de 56,5 a
50,7 (A1: 51,4). Pero el exceso total del A3 en train es 5,1 s de MAE global y solo 0,47 s sale de < 500 m. **La pinball explica la brecha en 0-5 min (46,2 vs 36,1 en eval; condicionar por ETA real corto exagera la diferencia de sesgo), no la de > 2 km**, donde está casi todo.

## D3: fuga por el shape ex post

Detalle y tablas completas en `d3_tables.md`; gráfico `d3_fuga.png`. El eval parquet no guarda posiciones, así que `d3_extract_hist.py` re-corre (solo lectura) las mismas funciones del pipeline (`read_day`, `segment_vehicles`, `geometry_for_trip`) sobre los 30
días de validación y recupera los pings de cada viaje hasta P (3768 de 3770 filas emparejadas por `ts_p`, `shape_id`, `dist_along_m`).

**1. ¿Qué shape se usa?** El del viaje completo, ex post. `process_day -> geometry_for_trip -> best_shape_for_trip(lats, lons, ...)` con todos los puntos del viaje (también los posteriores a P). Con ese shape se calculan `dist_along_m`, `dist_remaining_m`,
`dist_along_norm` (÷ largo del shape) y la trayectoria. A1 recibe `ramal_id` = ese shape_id y toda su tabla está indexada por él. A3 no recibe el id, pero `dist_remaining_norm` / `dist_along_norm` se normalizan por el largo de ese shape y `schedule_dev_norm` busca las
medianas por `ramal_id`. (El segmentador geométrico también corta viajes usando los shapes: fuga menor y común a todos.)

**2. Ambigüedad de P.** Candidato = shape con perp < 30 m en los últimos 5 pings hasta P y avance hacia adelante (misma `_forward_fraction` del proyector, últimos 10 pings).

| candidatos compatibles con P | filas | % |
|---|---:|---:|
| 0 | 213 | 5,6 |
| 1 | 633 | 16,8 |
| 2 | 497 | 13,2 |
| 3 | 2316 | 61,4 |
| 4-6 | 111 | 2,9 |

**77,6 % de las filas tienen P ambiguo** (>= 2 candidatos); casi todas son de 3 candidatos, es decir, los tres ramales (39A/B/C) del mismo sentido, que comparten troncal. Sensibilidad: 81,9 % con N = 3 pings, 69,9 % con N = 10, 68,7 % con perp < 15 m, 79,7 % con perp < 50 m.
El shape ex post está entre los candidatos en 94,3 % de las filas (el resto: GPS fuera de 30 m en la ventana). De las ambiguas, 11,3 % se resuelven por la parada objetivo (solo un candidato contiene a T).

**3. Error por clase (con el shape ex post)**

| clase | n | MAE A1 | MAE A3 | Δ (A3-A1) | ep |
|---|---:|---:|---:|---:|---:|
| no ambiguo (0-1 candidatos) | 844 | 103,9 | 112,7 | +8,9 | 2,5 |
| ambiguo, T todavía compartido | 2156 | 90,9 | 98,8 | +7,9 | 1,6 |
| ambiguo, T tras la divergencia | 768 | 105,2 | 117,0 | +11,8 | 2,9 |
| total | 3770 | 96,7 | 105,6 | +8,9 | 1,2 |

La ventaja de A1 es la misma en filas no ambiguas (+8,9) que en las ambiguas (+7,9 a +11,8); controlando por distancia (<2 km +1,5/+2,7; 2-5 km +10,9/+8,1; 5+ km +20,1/+20,8, no ambiguo/ambiguo) tampoco aparece una diferencia. Las filas "T tras la divergencia" son
las peores en ambos (el ETA hasta un punto después de bifurcar es más incierto) y donde más gana A1.
**La ventaja de A1 no está concentrada en las filas donde el shape es ambiguo.**

**4. Modelos sin fuga (diagnóstico)** — A1 consultado con cada candidato compatible con los pings hasta P que además contiene a T (el usuario elige una parada, que pertenece a ciertos ramales), y se promedia o se toma el de mejor ajuste hasta P (menor perp mediano). A3 con la misma
sustitución, aproximada (se recalculan posición, distancia restante, normalización y la columna de distancia de la trayectoria; el resto igual).

| MAE (s) | n | A1 ex post | A1 sin fuga (prom.) | A1 sin fuga (mejor ajuste) | A3 ex post | A3 sin fuga (prom.) | A3 sin fuga (mejor ajuste) |
|---|---:|---:|---:|---:|---:|---:|---:|
| todas | 3770 | 96,7 | 97,6 | 100,5 | 105,6 | 105,3 | 106,6 |
| >= 2 candidatos con P y T | 2593 | 94,8 | 96,0 | 100,2 | 103,1 | 102,7 | 104,6 |
| resto | 1177 | 101,1 | 101,1 | 101,1 | 111,0 | 111,0 | 111,0 |
| ambiguo, T compartido | 2156 | 90,9 | 91,7 | 95,8 | 98,8 | 97,9 | 99,8 |
| ambiguo, T tras la divergencia | 768 | 105,2 | 107,5 | 109,9 | 117,0 | 118,2 | 119,3 |

Brecha A3-A1 sobre todas las filas: 8,9 s (ex post) -> 8,0 s (A1 sin fuga contra A3 ex post) -> 7,7 s (ambos sin fuga, promedio; ep 1,2) -> 6,1 s (ambos con el mejor ajuste). A1 pierde 0,9 s promediando y 3,8 s eligiendo un único shape por ajuste; A3 pierde ~0 y 1,0 s.
**La fuga existe y favorece a A1, pero explica ~1 s a ~3 s de los 8,9 s: queda una ventaja de A1 de 6 a 8 s sin información del futuro** (el promedio es, además, la variante más favorable a un sistema real que consulte la tabla con todos los ramales compatibles).
Límites: (i) la sustitución de A3 es aproximada; (ii) los candidatos usan la parada objetivo T: sin ese dato (solo pings) la fuga sería mayor; (iii) con el "mejor ajuste" en tramo compartido la elección es arbitraria, como en el pipeline.

## Conclusión: qué apoyan los datos

| Hipótesis | Veredicto | Fuerza | Evidencia clave |
|---|---|---|---|
| Sobreajuste | no | fuerte | A3 pierde también en train; train 104,4 ~ eval 105,6 |
| H-identidad (sentido/recorrido) | **apoyada** | moderada-fuerte (indirecta) | anticorrelación ida/vuelta -0,60 vs -0,02; el sentido suma 60 % de R²; la misma fracción son lugares a 6,3 km entre sentidos; vuelta aporta 59 % del exceso |
| H-representación (escalones) | **no apoyada** | moderada | el A3 sigue el perfil (corr 0,885; amplitud 0,79 vs 0,81) y captura 72-83 % de la ganancia posicional |
| H-pérdida | **real pero menor** | fuerte para 0-5 min, débil para el total | cobertura 0,80 a < 250 m; ~0,5 s de ~5 s de brecha global (train) |
| Fuga por shape ex post | **existe, chica** | moderada | A1 97,6-100,5 s sin fuga vs 96,7; brecha 8,9 -> 6,1-7,7 s; A1 gana igual en filas no ambiguas (+8,9 s) |

Parte de la brecha restante puede ser simplemente la menor resolución por celda que aprende una red frente a una tabla exacta (500 m x hora x día, 4 M de filas); estos diagnósticos no la separan de la identidad (ver experimento).

## Experimento propuesto (no se corrió)

**A3 con identidad explícita, pero causal.** Mismo A3-K32 (mismos datos, pares, época y semilla) agregando (a) un embedding del **sentido** (2 valores; se infiere online con pocos pings por la fracción de avance, ambiguo solo en las cabeceras) y (b) la distancia
recorrida en metros además de la fracción. Variante (c): embedding de shape_id inferido **solo con los pings hasta P** (mejor ajuste causal, con ruido en el troncal compartido), para entrenar con el mismo ruido que habrá en producción y no con el shape ex post. Control: sentido barajado entre filas.
Pronóstico si H-identidad es la causa principal: el MAE (eval y muestra de train) baja sobre todo a 2+ km, la anticorrelación ida/vuelta del error de nivel pasa de -0,60 a ~0 y el control vuelve al valor actual; (c) debería quedar entre (a) y el A3 actual. Si el MAE no se mueve, la causa es capacidad/optimización
y el siguiente paso sería codificar la posición por tramos (embedding por bucket de 500 m). Costo estimado ~20 min por corrida en la 3080 (K=32, solo la 39). Para H-pérdida, la corrida barata es el mismo A3 con q = 0,5 fijo a < 1 km: el sesgo de 0-5 min debería caer a ~0 sin mover el resto.
Observación para el diseño de A1 en producción: consultar la tabla con todos los ramales compatibles y promediar cuesta ~1 s de MAE frente al ex post; elegir un solo ramal por mejor ajuste cuesta ~4 s.

## Archivos

- Gráficos: `d2_mae_por_tramo_train.png`, `d2_mae_por_tramo_agregado.png`, `d2_velocidad_implicita.png`, `d2_captura_perfil.png`, `d3_fuga.png`.
- Tablas: `d1_tables.md`, `d2_tables.md`, `d3_tables.md`; crudos `d1_results.json`, `d2_results.json`, `d3_results.json`. Los parquets de muestra, `pred_*.npz` y `eval_hist_39.pkl` quedan en esta carpeta y no se versionan.
