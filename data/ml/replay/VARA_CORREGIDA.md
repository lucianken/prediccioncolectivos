# Vara de producto corregida: definición, y resultados anterior contra corregida

Medido el 2026-11-16 (recalculado ese mismo día con la verdad por recorrido ex post; ver el registro al final) con `prediccion/replay/` (`core.py`: verdad corregida; `metrics.py`: métricas con `corrected=True`; `report_vara.py`: estas tablas). Modelo de producción `data/ml/export/path_v3_l1_s1`, lógica de la app fijada en `prediccion/replay/pinned/` (regla de sentido de racha final vigente; no se tocó `pinned/`, `prediccion/v2/geo_assign.py` ni proyectoconsola). 12 líneas, 40 paradas por línea, instantes cada 10 min de 6 a 23 h, los 10 días de `V3_PRODUCCION.md` (15–20 sep., 3, 4, 6, 8 oct.; la línea 26 solo 15–17 sep.), variante `base`. Una sola corrida produce las dos definiciones (columnas `tp_s` anterior, `tp2_s` corregida), así que la comparación es pareada fila por fila. Datos: `data/ml/replay/vara/run_base_xp` (9 días) y `run_cs_xp` (se usa el 3 de octubre, variante `base`); tablas: `data/ml/replay/vara/tablas_vara.md` (antes / después de cada corrección: `vara/antes_despues.md`). Los `*_xp` son los crudos originales (`run_base`, `run_cs`; `*_sg` = verdad sin filtro por recorrido) con la verdad corregida recalculada desde los pings crudos y la segmentación ex post (`vara/recalcula_verdad.py`, sin volver a predecir: las predicciones son las mismas). Tests de comportamiento: `prediccion/tests/test_replay.py`.

Las filas «anterior» reproducen `BARRIDO_SENTIDO.md` (regla k=2/40 m: MAE 98 s, llega antes 14,4 %, llega después 26,2 %, falsas alarmas 24,9 %, omisión 8,7 %, «viene» vacío 10,1 %; acá 98 s, 14,4 %, 26,4 %, 24,5 %, 9,3 %, 10,0 %).

## Definición vigente (spec)

La verdad de un (parada, coche, t) es el próximo cruce firme de la parada en (t, t + 40 min]. **Recorridos que sirven la parada = solo los que la tienen en su lista (`ramales[].stops` de su relación).** Si una parada está en la lista de un recorrido y no en la de otro, el otro no para ahí: no se asocia por geometría ni por cercanía. A OSM le pueden faltar paradas, pero eso no convierte en omisión a un coche cuyo recorrido no la tiene. **Un cruce cuenta solo si el recorrido ex post del viaje del coche en ese tramo (segmentador geo2 + asignación geo3, el mismo de la variante oráculo `ramal`) tiene la parada en su lista** (punto 7). Cambios respecto de la definición anterior (cruce estricto entre dos pings consecutivos compatibles, a lo sumo 10 min y 5 km de distancia):

1. **Horizonte (X0).** Una falsa alarma solo se cuenta si el ETA anunciado (`eta0`, hora común) es ≤ 40 min. Los listados con ETA > 40 min salen del denominador y se informan aparte. Se eligió esto y no ampliar el horizonte porque el usuario no decide con coches a más de 40 min y un horizonte variable (ETA + 10 min) deja de ser comparable entre variantes.
2. **Cruce entre pings compatibles no consecutivos (X2b, X2c, X4).** Se saltean los pings no compatibles con el shape: cruce = par consecutivo entre los compatibles con d0 ≤ d_parada < d1, separados ≤ 10 min, con avance plausible (≤ 25 m/s de media + 50 m). Reemplaza el tope fijo de 5 km por una velocidad.
3. **Final del shape (X3).** d_efectiva = min(d_parada, largo − 50 m): una parada en el último tramo se cruza al llegar a 50 m del final.
4. **Huecos de GPS (X2a, G).** Un par de pings compatibles ADYACENTES en la serie grabada (el coche no transmitió nada entre ellos), separados 10–40 min, con avance plausible, que encierra la parada y cuyo intervalo se solapa con (t, t + 40 min], es paso «no verificable»: el coche listado sale del denominador de falsas alarmas y el instante sale del MAE / llega antes / «viene» vacío cuando ese paso pudo ocurrir antes del próximo paso firme (`unv_first_s`). No se interpola su hora. Un coche que transmitió fuera del shape durante el hueco no cuenta como paso. Huecos > 40 min no se verifican y la falsa alarma se mantiene (unos 6 600 casos de X2a, huecos de ~42 min).
5. **«Ya pasó» (P).** Cruce firme entre el último ping (≤ t) del coche y t, a ≤ 10 min de t: el coche listado no es falsa alarma; es un coche que llegó antes de lo anunciado (la app no podía saberlo). Entra al denominador como acierto y se informa su cantidad.
6. **Omisión y paso real.** Se aplican las mismas correcciones: pasos de la verdad corregida (incluye pasos finales y entre pings no consecutivos); los pasos no verificables no cuentan; el MAE y el «llega antes / después» usan el próximo paso firme.
7. **Recorrido ex post del cruce (`core._expost_filter`).** El viaje ex post del coche que cubre el tramo entre los dos pings que encierran el cruce (el de mayor solapamiento; `Veh.trip_shape_between`) define el recorrido. Si ese recorrido tiene la parada en `Stop.serving` (su lista): el cruce cuenta. Si no la tiene: el cruce se descarta (no es paso; si la app lo listó, es falsa alarma real; si no, no es omisión). Si no hay viaje con recorrido asignado en el tramo: el cruce firme pasa a «no verificable» (mismo tratamiento que un hueco de GPS: sale del denominador de falsas alarmas y del MAE / llega antes / «viene» vacío cuando pudo ocurrir antes del próximo paso firme; no cuenta como paso ni como omisión); no se inventa el recorrido. Los huecos de GPS (punto 4) pasan por el mismo filtro (se descartan si el recorrido no tiene la parada). Es información ex post usada solo como verdad de la medición; la lógica de la app (`pinned/`) y la lista de paradas no cambian. Aplica a los coches de corridas con viajes ex post calculados (`run.load_day` los calcula siempre; `Veh.expost`); un `Veh` sin viajes ni `expost` conserva el cruce por compatibilidad de shape (solo tests / usos sin segmentación). La definición anterior (`tp_s`) no se toca.

Código: `core.crossings_v2`, `core.merge_crossings` (une cruces a ≤ 30 s de dos shapes que sirven la parada: el mismo paso), `core.truth_at`, `metrics.false_alarms/omissions/next_bus/seguro_vacio(corrected=True)`. `metrics.summarize(..., ann0=True)` mide el ETA en la hora común (el predeterminado sigue siendo el ETA con el descuento de 60 s). Columnas de los crudos: `tp_s` (anterior), `tp2_s`, `unv`, `past` (corregida).

**Casos sin viaje ex post (tratamiento del punto 7)**, 40 paradas por línea; contadores en `vara/run_*_xp/{día}_{línea}.truth_stats.json`:

| concepto | 10 días base | 6 días (cs) |
|---|---|---|
| cruces firmes (por parada y coche, tras unir shapes) | 897 137 | 502 499 |
| descartados: el recorrido ex post no tiene la parada | 37 596 (4,19 %) | 20 693 (4,12 %) |
| firmes sin viaje ex post con recorrido en el tramo → no verificable | 3 186 (0,36 %) | 2 255 (0,45 %) |
| huecos de GPS (10–40 min) | 18 283 | 11 062 |
| huecos descartados por recorrido sin la parada | 1 521 | 772 |
| huecos sin viaje ex post (siguen no verificables) | 250 | 373 |
| coches del día sin ningún viaje ex post / coches | 212 / 6 961 | 160 / 4 374 |

## Resultados: anterior contra corregida

`base`, 10 días, 12 líneas. «Llega antes / después» = el próximo coche llega más de 60 s antes / después de lo anunciado (ETA en hora común), banda de tiempo real 3–7 min.

Días: 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18, 2026-09-19, 2026-09-20, 2026-10-03, 2026-10-04, 2026-10-06, 2026-10-08. Líneas: 26, 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168.

### Global

| métrica | anterior | corregida |
|---|---|---|
| Coches listados (los 5 mostrados) | 1933795 | 1933795 |
| Falsas alarmas %, todo ETA anunciado | 24.5 | 17.1 |
| Falsas alarmas %, ETA anunciado 3–7 min | 14.6 | 12.7 |
|   «viene» (seguro) % | 14.1 | 5.7 |
|   «puede venir» % | 59.7 | 56.7 |
|   «sentido sin confirmar» (provisional) % | 53.4 | 48.8 |
| Omisión ≤10 min % | 9.3 | 9.5 |
|   n coches que pasan en ≤10 min con ping vigente | 755260 | 766262 |
| «Viene» vacío % | 10.0 | 9.8 |
|   n instantes con paso ≤10 min | 353337 | 353875 |
| MAE próximo coche, banda 3–7 min (s) | 98 | 97 |
|   n instantes en la banda | 128566 | 128757 |
| Llega antes >60 s % (banda 3–7) | 14.4 | 14.4 |
| Llega después >60 s % (banda 3–7) | 26.4 | 26.3 |
| Sin anuncio % (banda 3–7) | 2.5 | 2.3 |
| MAE solo «viene», banda 3–7 (s) | 97 | 96 |
|   llega antes / después >60 s % (solo «viene») | 14.3 / 25.4 | 14.5 / 25.1 |

Lo que la vara corregida deja afuera o reclasifica (no es lo mismo que «falsa alarma resuelta»):

| concepto | n |
|---|---|
| listados con ETA anunciado > 40 min (fuera del horizonte; no entran en el denominador) | 93296 |
| listados «no verificables» (par de pings con hueco de 10–40 min que encierra la parada; no entran) | 19856 |
| listados que ya habían pasado entre su último ping y t (llega antes; no es falsa alarma, entran en el denominador) | 35099 |
| listados evaluados (denominador de la falsa alarma corregida) | 1820643 |
| instantes en la banda 3–7 min excluidos por paso previo no verificable | 1467 |
| instantes con paso ≤10 min excluidos del «viene» vacío por lo mismo | 4044 |

### Por línea

| línea | listados | falsas alarmas % ant → corr | FA 3–7 min % ant → corr | omisión % ant → corr | «viene» vacío % ant → corr | MAE 3–7 (s) ant → corr | llega antes % ant → corr | llega después % ant → corr |
|---|---|---|---|---|---|---|---|---|
| 26 | 42306 | 7.0 → 2.6 | 4.2 → 2.4 | 5.7 → 5.9 | 2.6 → 2.0 | 76 → 76 | 12.2 → 12.3 | 28.9 → 28.7 |
| 39 | 189045 | 31.5 → 29.8 | 18.9 → 20.9 | 7.0 → 6.5 | 23.2 → 22.6 | 88 → 89 | 10.8 → 10.2 | 29.3 → 30.8 |
| 42 | 176034 | 38.8 → 32.2 | 33.3 → 28.9 | 7.5 → 8.6 | 12.0 → 12.5 | 195 → 190 | 17.0 → 16.7 | 32.2 → 33.2 |
| 50 | 160942 | 32.3 → 24.9 | 15.7 → 14.2 | 5.7 → 6.7 | 14.4 → 12.9 | 79 → 79 | 15.9 → 16.4 | 23.0 → 23.2 |
| 92 | 187319 | 14.2 → 6.7 | 4.6 → 2.7 | 4.7 → 4.9 | 3.0 → 2.8 | 67 → 67 | 13.8 → 14.2 | 20.8 → 20.5 |
| 106 | 197402 | 22.4 → 14.2 | 13.9 → 11.0 | 15.1 → 15.7 | 5.6 → 5.4 | 155 → 148 | 14.8 → 14.8 | 30.4 → 29.5 |
| 107 | 131301 | 18.3 → 9.0 | 14.3 → 12.3 | 10.3 → 10.4 | 12.3 → 11.9 | 106 → 106 | 21.1 → 21.0 | 21.9 → 22.0 |
| 108 | 164417 | 24.5 → 11.7 | 11.9 → 8.5 | 6.6 → 6.6 | 3.8 → 3.6 | 75 → 74 | 13.9 → 13.7 | 23.7 → 23.9 |
| 124 | 165783 | 11.1 → 4.3 | 4.8 → 2.7 | 3.9 → 4.0 | 2.8 → 2.6 | 75 → 72 | 13.0 → 13.0 | 22.9 → 21.9 |
| 132 | 185838 | 25.0 → 20.8 | 18.4 → 16.9 | 13.0 → 13.1 | 16.0 → 15.7 | 84 → 83 | 11.2 → 11.3 | 31.1 → 30.8 |
| 151 | 157139 | 12.4 → 7.5 | 5.5 → 4.2 | 12.8 → 12.8 | 8.7 → 7.9 | 84 → 83 | 13.5 → 13.6 | 30.6 → 30.1 |
| 168 | 176269 | 40.8 → 26.7 | 18.1 → 13.5 | 7.0 → 7.2 | 10.1 → 12.1 | 95 → 94 | 16.3 → 16.4 | 23.0 → 22.6 |

### Falsa alarma por ETA anunciado

| ETA anunciado (min) | listados | FA anterior % | listados evaluados | FA corregida % | ya pasó % | no verificable % |
|---|---|---|---|---|---|---|
| 0-2 | 219376 | 31.5 | 213180 | 12.9 | 15.8 | 2.8 |
| 2-3 | 87048 | 11.4 | 86267 | 9.2 | 0.3 | 0.9 |
| 3-5 | 175560 | 13.2 | 173972 | 11.2 | 0.0 | 0.9 |
| 5-7 | 171784 | 16.0 | 170377 | 14.2 | 0.0 | 0.8 |
| 7-10 | 236004 | 18.9 | 233948 | 17.0 | 0.0 | 0.9 |
| 10-20 | 549361 | 19.4 | 544262 | 17.2 | 0.0 | 0.9 |
| 20-40 | 401366 | 26.4 | 398637 | 24.5 | 0.0 | 0.7 |
| >40 | 93296 | 93.5 | 0 | — | 0.0 | 0.0 |

### Qué le pasa a cada causa de FALSAS_ALARMAS

| causa (FALSAS_ALARMAS) | FA anteriores | fuera del horizonte | pasa (cruce firme) | no verificable | ya pasó | sigue falsa alarma | % que sale de las FA |
|---|---|---|---|---|---|---|---|
| X0 | 87276 | 87276 | 0 | 0 | 0 | 0 | 100 |
| X3 | 14131 | 0 | 9230 | 625 | 45 | 4231 | 70 |
| X2a | 21654 | 0 | 0 | 14233 | 0 | 7421 | 66 |
| X2b | 1844 | 0 | 214 | 11 | 6 | 1613 | 13 |
| X2c | 10101 | 0 | 3772 | 63 | 49 | 6217 | 38 |
| X2d | 19089 | 0 | 305 | 120 | 2118 | 16546 | 13 |
| X1 | 21549 | 0 | 0 | 1 | 0 | 21548 | 0 |
| X4 | 9944 | 0 | 9093 | 31 | 6 | 814 | 92 |
| P | 33059 | 0 | 9 | 139 | 32583 | 328 | 99 |
| S | 23117 | 0 | 344 | 34 | 0 | 22739 | 2 |
| R1 | 152202 | 0 | 0 | 8 | 0 | 152194 | 0 |
| T1 | 23448 | 0 | 52 | 49 | 13 | 23334 | 0 |
| T2 | 7687 | 0 | 2 | 22 | 0 | 7663 | 0 |
| C | 24232 | 0 | 0 | 45 | 0 | 24187 | 0 |
| G | 6458 | 0 | 348 | 3304 | 23 | 2783 | 57 |
| D | 14447 | 0 | 7407 | 75 | 97 | 6868 | 52 |
| O | 4047 | 0 | 1137 | 20 | 130 | 2760 | 32 |
| **total** | 474285 | 87276 | 31913 | 18780 | 35070 | 301246 | 36.5 |

(Filas de FALSAS_ALARMAS sin par en esta corrida: 0 de 474285.)

## Lectura

1. **La falsa alarma baja de 24,5 a 17,1 %** (en la banda de ETA anunciado 3–7 min, de 14,6 a 12,7 %). De 474 285 falsas alarmas anteriores, 36,5 % dejan de serlo: 18,4 % por ETA > 40 min (fuera del horizonte), 6,7 % porque el coche sí pasa con la verdad corregida, 7,4 % porque ya había pasado segundos antes de t (llega antes) y 4,0 % no verificables.
2. **Las falsas alarmas que quedan (17,1 %) son reales:** R1 (152 194) y S (22 739) de 301 246, más T1, T2, C, X1, D y X2d. R1 ya no «pasa» nunca (antes 20 %: eran coches de recorridos sin la parada). X2d (coche que pasa por la calle de la parada con un recorrido que no la tiene en su lista) sigue siendo falsa alarma en 87 % de los casos: no para ahí. X0, P y X4 casi desaparecen (100, 99 y 92 %), X3 70 %, X2a 66 % (el resto son huecos > 40 min), X2c 38 %. El oráculo de ramal sigue siendo la palanca de R1 (`FILTRO_RAMAL_CS.md`).
3. **La omisión es 9,5 % y el «viene» vacío 9,8 %** (anterior 9,3 y 10,0 %): 766 262 coches pasan en ≤ 10 min con ping vigente (800 465 antes de descartar los coches que no paran en la parada: −4,3 %). Finales de shape y cruces entre pings no consecutivos suman pasos; los coches que no paran ahí ya no cuentan.
4. **MAE, llega antes y llega después casi no se mueven** (98 → 97 s; 14,4 → 14,4 %; 26,4 → 26,3 %). Se excluyen 1 467 instantes de la banda 3–7 min por paso previo no verificable. Por línea el MAE se mueve ≤ 7 s (106: 155 → 148 s).
5. **Por grupo:** «viene» 14,1 → 5,7 % de falsas alarmas; «puede venir» 59,7 → 56,7 %; «sentido sin confirmar» 53,4 → 48,8 %. Por línea, las peores: 42 (32,2 %), 39 (29,8 %), 168 (26,7 %) y 50 (24,9 %).

## Salvedades

- Una corrida por modelo; 40 paradas por línea; el ex post (segmentador geo2 + geo3) puede ser ambiguo en terminales y calles compartidas: un recorrido ex post equivocado descarta o conserva un cruce de más (el 0,4 % sin viaje ex post se excluye en vez de asignarlo).
- `metrics.py` con `corrected=True` lo usan otros análisis (`COCHE_DETENIDO.md`, consistencia del ETA). Desde el 2026-11-16 la verdad no incluye shapes por geometría (las claves `omision_sin_extra_pct` y `n_extra` de `omissions` y la columna `extra` de las filas ya no existen) y exige que el recorrido ex post del coche tenga la parada en su lista. Las firmas de `core._passes` / `core.truth_at` / `core.evaluate_line` conservan sus argumentos (`_passes` y `evaluate_line` aceptan `stats` / `truth_stats` opcionales); `run.load_day` calcula siempre los viajes ex post (`with_trips` se ignora), así que `consistencia.py` y `detenido/extrae.py` usan la verdad por recorrido sin cambios de código, pero tardan lo que tarda la segmentación (~1 min por día y línea).

## Registro de error (2026-11-16): asociación parada↔recorrido por geometría

La primera versión de la vara corregida (2026-11-16) contaba también como recorridos que sirven la parada a los shapes del mismo sentido a ≤ 45 m de ella (`core.geo_serving`, columna `extra`; causa X2d de `FALSAS_ALARMAS.md`). Era incorrecto: que una parada esté en la lista de un recorrido y no en la de otro significa que el otro no para ahí. Contaba como paso real a coches que pasan por la calle sin parar, y los medía como omisión si la app no los listaba. Efecto, 10 días, 12 líneas, base, mismas filas (con geometría contra sin geometría):

| métrica | con geometría (retirada) | sin geometría (vigente) |
|---|---|---|
| coches que pasan en ≤ 10 min con ping vigente | 810 844 | 800 465 |
| omisión ≤ 10 min % | 11,3 | 10,7 |
| «viene» vacío % | 11,5 | 11,2 |
| falsas alarmas % (todo ETA / 3–7 min) | 14,2 / 9,3 | 14,7 / 9,9 |
| falsas alarmas % «puede venir» / «sentido sin confirmar» | 43,8 / 40,6 | 46,6 / 41,3 |
| X2d: falsas alarmas anteriores que pasan (de 19 089) | 10 708 | 2 470 |
| X2c: falsas alarmas anteriores que pasan (de 10 101) | 5 685 | 3 972 |
| falsas alarmas anteriores que dejan de serlo, total (de 474 285) | 46,1 % | 43,9 % |

La versión con geometría inflaba pasos (+1,3 %) y omisión (+0,6 pp) y desinflaba falsas alarmas (−0,5 pp; −0,6 pp en 3–7 min). Afectó a: `VARA_CORREGIDA.md` (tablas, lectura y la fracción «sin los pasos por shapes no asociados por nombre»), `FILTRO_RAMAL_CS.md` (columnas base / cs / oráculo y el análisis de omisión por recorrido), `COCHE_DETENIDO.md` (columna `extra` y niveles absolutos), `FALSAS_ALARMAS.md` (X2d clasificada como artefacto de la vara, con una propuesta de asociar por geometría: retirada) y `ARQUITECTURA.md` §5. También se retiró la interpretación «el 6,7 % de los pasos son de un recorrido que `ramales[].stops` no asocia por nombre: dato incompleto de stops»: esos coches no paran ahí.

Corrección adicional en la misma tabla: las cifras publicadas (2 093 900 coches listados) contaban dos veces el 2026-10-04, presente en `run_base` y en `run_cs`. Las de acá cuentan cada (línea, día, parada, t, coche) una vez (1 933 795 listados, igual que `FALSAS_ALARMAS.md`); `report_vara.load` lo hace. Publicado contra corregido sin duplicar: falsas alarmas 25,0 → 24,5 % (anterior) y 14,3 → 14,2 % (corregida con geometría); omisión 9,1 → 9,3 % y 11,1 → 11,3 %; «viene» vacío 10,2 → 10,0 % y 11,8 → 11,5 %.

## Resultados previos que usaron la definición anterior (hecho fechado 2026-11-16)

`V3_PRODUCCION.md`, `ORACULO_RAMAL.md`, `OMISIONES.md`, `BARRIDO_SENTIDO.md`, `FACTOR_ANUNCIO.md` y `FALSAS_ALARMAS.md` usan la definición anterior de verdad (cruce estricto de 10 min, horizonte 40 min sin tope por ETA anunciado, recorridos asociados por nombre). Siguen siendo válidos como comparaciones relativas (la misma vara para todas las variantes); sus falsas alarmas absolutas están infladas (≈ 24,5 contra ≈ 17,1 % corregido; ≈ 14,6 contra 12,7 % en 3–7 min); su omisión y «viene» vacío absolutos casi coinciden con los corregidos (≈ 9,3 contra 9,5 %; 10,0 contra 9,8 %).

## Registro de cambio (2026-11-16): verdad por recorrido ex post del coche

La verdad corregida contaba como paso a un coche cuyo recorrido NO tiene la parada en su lista si su GPS iba compatible con un shape que sí la sirve (tronco compartido; ej.: «Santa Fe y Salguero» está en R1 y R2 de la 39, no en R3, y un coche de R3 por Santa Fe contaba): 4,2 % de los cruces (37 596 de 897 137, 10 días). Desde ahora un cruce cuenta solo si el recorrido ex post del viaje del coche tiene la parada en su lista (definición, punto 7). Mismas filas y predicciones; cambia solo la verdad. 10 días, 12 líneas, base:

| métrica | corregida anterior (sin filtro por recorrido) | corregida vigente |
|---|---|---|
| falsas alarmas % (todo ETA / 3–7 min) | 14,7 / 9,9 | 17,1 / 12,7 |
| falsas alarmas % «viene» / «puede venir» / «sentido sin confirmar» | 5,6 / 46,6 / 41,3 | 5,7 / 56,7 / 48,8 |
| omisión ≤ 10 min % | 10,7 | 9,5 |
| coches que pasan en ≤ 10 min con ping vigente | 800 465 | 766 262 |
| «viene» vacío % | 11,2 | 9,8 |
| MAE 3–7 min (s) | 99 | 97 |
| llega antes / después >60 s % (3–7) | 15,6 / 25,5 | 14,4 / 26,3 |
| listados no verificables | 19 026 | 19 856 |
| listados «ya pasó» | 35 664 | 35 099 |
| listados evaluados | 1 821 473 | 1 820 643 |

Las falsas alarmas suben (+2,4 pp; +2,8 pp en 3–7 min) porque los coches de recorridos sin la parada que la app lista ya no «pasan»; la omisión baja (−1,2 pp) porque esos coches ya no cuentan como omitidos. Por línea (corregida anterior → vigente): falsas alarmas 39 23,6 → 29,8 %, 132 13,5 → 20,8, 107 5,2 → 9,0, 168 22,3 → 26,7; omisión 107 14,9 → 10,4, 132 15,7 → 13,1, 168 8,9 → 7,2, 39 8,7 → 6,5. La limitación «pasos de coches cuyo recorrido no tiene la parada» queda resuelta; `vara/omision_por_recorrido.py` (que la medía: 4,0 % de los pasos, omisión 35,7 % en base) queda como medición histórica. Afectó a: `VARA_CORREGIDA.md` (tablas y lectura), `FILTRO_RAMAL_CS.md` (tablas base / cs / oráculo), `FALSAS_ALARMAS.md` (R1 y X2d: cambian las cifras de «pasa»; ver la tabla por causa) y las cifras de `COCHE_DETENIDO.md` y de consistencia del ETA que usan `tp2_s` (se recalculan con `recalcula_verdad.py`).
