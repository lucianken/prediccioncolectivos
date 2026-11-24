# Latencia y fidelidad de posiciones: API CABA vs CuandoSubo (OBA), líneas 39 y 168

Estado al 2026-11-13. Dos capturas simultáneas CABA + OBA (agencias 56 = línea 39, 80 = línea 168):

| captura | inicio - fin (hora local BA) | duración | requests OBA | incidentes WAF | archivos |
|---|---|---|---|---|---|
| 10 min | 2026-11-13 20:45:59 - 20:55:48 | 9.8 min | 40 (+2 de prueba) | 0 | `datos/captura_20261113-204553.ndjson`, `resultados_10min.*`, `resultados_lote_10min.*` |
| 90 min | 2026-11-13 21:14:08 - 22:44:14 | 90.1 min | 360 | 0 | `datos/captura_20261113-211401.ndjson` (+ `.log`), `resultados_90min.*`, `resultados_lote_90min.*` |

Requests a OBA el 2026-11-13: 402 en total (42 + 360), todas 200 con JSON, secuenciales, 1 cada 15 s como máximo; sin pausas por WAF. Reloj local con NTP (`w32tm`): +0.261 s (10 min) y +0.273 s (90 min), corregido en todas las horas locales. Las tablas completas están en los `resultados*.md/json` (salidas de `analisis.py` y `analisis_lote.py`).

## Pregunta

La app de CuandoSubo muestra los colectivos en una posición distinta de la que da la API CABA. ¿Es porque CABA procesa y publica tarde, o la diferencia es la extrapolación de OBA (`tripStatus.position`)? Se separa en: (1) si ambas fuentes dan el mismo fix GPS; (2) qué significa el `timestamp` de cada fuente; (3) retraso de publicación; (4) cadencia; (5) delta y acierto de la extrapolación de OBA; (6) relojes de servidor.

## Método

- CABA: `GET .../colectivos/vehiclePositions` (protobuf GTFS-RT, flota completa), 1 request cada 15 s. Se guardan sólo los coches de 39 y 168 (sufijo de label con `LABEL_LINE_MAP.json` más cualquier id visto en OBA 56/80). `ts` = `entity.vehicle.timestamp`; `server_time` = `header.timestamp`.
- OBA: `GET .../vehicles-for-agency/{56|80}.json`, 1 request cada 15 s alternando agencias (cada agencia cada 30 s), secuencial, sin redirects. `ts` = `lastUpdateTime`, GPS = `location`, extrapolación = `tripStatus.position`. Coches sin `location` se descartan (18 en la corrida de 10 min, 24 en la de 90).
- Shapes: `proyectoconsola/data/line_shapes/{39,168}.json`. Por (coche, trip) se elige el shape de menor distancia perpendicular mediana; proyección en plano local; descartes con perpendicular > 120 m.
- Mismo punto entre fuentes: mismo id y posición a ≤ 2 m, sólo pares inequívocos (un fix CABA y un fix OBA del coche dentro de 2 m entre sí; se excluyen coches detenidos con posiciones repetidas).

## 1. Estampado por lote de la API CABA (hecho medido el 2026-11-13)

`vehicle.timestamp` de CABA no es la hora del GPS: es un estampado por lote. Medido sobre el día 2026-11-12 del grabador CABA (`//192.168.0.18/buffer/grabaciones/2026-11-12.ndjson.gz`, 11.36 M actualizaciones, ~11 000 coches por foto) con `ts_grabador_dist.py` y `ts_grabador_dist2.py`:

- 100 % de los ts son segundos pares; nunca hay milisegundos.
- ~139 valores de ts distintos por foto para ~10 900 coches (p50). El grupo más grande con el mismo ts es el 23 % de la foto (p50) y 90 % (p90).
- ts mod 60 concentrado en los segundos 32-52 del minuto (46, 44, 48, 40, 42, 38, 50: 9-12 % cada uno contra 1.7 % uniforme).
- Paso de ts del mismo coche entre actualizaciones: 60 s en 52.7 %, 62 s 13.7 %, 58 s 4.5 %, 120 s 3.6 %, 30 s 3.4 %.
- Saltos entre ts distintos dentro de una foto: mayormente 2 s (y 26-30 s).
- En el grabador, `t` del frame = max(ts) del frame (`prediccion colectivos/grabador/delta.py:67`), no la hora del poll; por eso "edad = t − ts" no sirve para medir latencia.

Misma firma en la captura de 90 min (sólo líneas 39 y 168, ~118 coches por respuesta, así que los conteos absolutos no son comparables con los del día completo):

| fuente | respuestas | coches/resp (p50) | ts distintos/resp p10 / p50 / p90 | distintos / coches (p50) | mayor grupo con el mismo ts p50 / p90 | puntos únicos | con ms | pares | en seg. 40-59 |
|---|---|---|---|---|---|---|---|---|---|
| CABA | 360 | 118 | 30 / 34 / 38 | 0.283 | 32 % / 39 % | 7838 | 0.0 % | 100 % | 92.9 % |
| OBA | 360 | 77.5 | 37 / 50 / 66 | 0.667 | 10 % / 16 % | 6688 | 7.6 % | 50.7 % | 59.6 % |

Segundos del minuto más frecuentes de CABA: 48 (41.6 %), 50 (27.8 %), 46 (23.1 %); estable en todos los bloques de 10 min (92-95 % en 40-59; 84 % en el primero). La firma de CABA no cambió durante la captura.

## 2. El desfase de ts entre CABA y OBA no es constante

`ts_CABA − ts_OBA` para el mismo punto (87.0 % de los fixes OBA de coches comunes tienen par inequívoco: 5777 de 6638; coches vistos: CABA 133, OBA 161, ambas 131).

**Régimen A (hasta ~21:53; toda la captura de 10 min cae acá).** Δts ≈ 29 s o ≈ 58 s: p10 / p50 / p90 = 27 / 29 / 57-58 s en los dos primeros bloques de 15 min, con la misma distribución en 39 y 168 (n 591 + 520 en el bloque 0, 556 + 455 en el 1). En los bloques de 5 min entre 21:14 y 21:39, 95-98 % de los pares tiene Δts ≥ 20 s. En 10 min: n = 848, p10/p50/p90 = 27 / 29 / 58.

**Cambio de régimen entre ~21:44 y 21:53.** El modo de 58 s desaparece hacia 21:47-21:49 (p90 del bloque 21:49 = 33 s) y el modo de 29 s desaparece en el bloque 21:54.

**Régimen B (desde 21:54).** Δts = −3 / −2 / −1 s (p10 / p50 / p90), 0.0-2.2 % de los pares con Δts ≥ 20 s en cada bloque de 5 min hasta 22:44 (n = 198-329 por bloque). El cambio es simultáneo en 39 y 168.

| bloque de 15 min (desde el inicio) | n (39 / 168 / ambas) | p10 / p50 / p90 (ambas) |
|---|---|---|
| 0-15 | 591 / 520 / 1111 | 27 / 29 / 58 |
| 15-30 | 556 / 455 / 1011 | 27 / 29 / 57 |
| 30-45 | 507 / 448 / 955 | -3 / 27 / 30 |
| 45-60 | 460 / 443 / 903 | -3 / -2 / -1 |
| 60-75 | 533 / 427 / 960 | -3 / -2 / -1 |
| 75-90 | 418 / 320 / 738 | -3 / -2 / -1 |

Histograma por valor (todas, n = 5777): -2 s 25.5 %, -1 s 15.0 %, 28 s 13.7 %, 29 s 11.4 %, -3 s 8.9 %, 27 s 5.0 %, 57 s 3.2 %, 56 s 2.6 %, 58 s 2.1 %. Fuera de 27-31 s y 55-61 s: 57 % (casi todo es el régimen B). Hay además ~100 pares (≈ 1.7 %) con Δts entre -32 y -38 s (CABA 33-38 s antes que OBA).

**Lo que cambia en OBA (no en CABA).** El reparto de segundos del minuto del ts de OBA:

| régimen | puntos únicos | segundos más frecuentes (%) | en seg. 40-59 | retraso de publicación OBA p10 / p50 / p90 | retraso CABA p50 |
|---|---|---|---|---|---|
| A | 3265 | 19, 18, 20, 21, 22, 17 (9-12 % cada uno) | 28.3 % | 72.0 / 89.7 / 119.4 s (n 3105) | 20.0 s |
| B | 3423 | 48, 49, 51, 50, 52 (15 % cada uno), 53 (7 %) | 89.4 % | 36.1 / 51.3 / 66.4 s (n 3422) | 22.1 s |

En el régimen B el ts de OBA queda 1-3 s después del de CABA para el mismo punto y con el mismo reparto de segundos (concentrado en 47-53): OBA pasó a llevar un estampado equivalente al de CABA. En el régimen A estaba concentrado en los segundos 17-22 (≈ ts de CABA − 29 s). En ninguno de los dos regímenes el ts de OBA es una hora de equipo distribuida uniformemente en el minuto (7.6 % de los ts de OBA tienen milisegundos; ~50 % son pares).

Lo que esto cambia de la interpretación previa: no se sostiene que `lastUpdateTime` de OBA sea la hora real del equipo. Que OBA coincida con CABA en B y que en A esté ~29/58 s antes con concentración propia de segundos indica que ambos ts son estampas de procesamiento; la causa del cambio de OBA (~21:53) es desconocida. Sin verdad de campo no se puede decir cuál de los tres (CABA, OBA-A, OBA-B) está más cerca de la hora real del GPS.

Primera recepción del mismo fix (CABA − OBA, n = 5698): p10 / p50 / p90 = -47.8 / -34.7 / -24.2 s. CABA muestra el punto ~25-50 s antes que OBA en toda la captura; es independiente del régimen del ts.

## 3. Mismo fix GPS

- 87.0 % de los fixes de OBA de coches comunes tienen el mismo punto (≤ 2 m) en CABA (5777 de 6638 en 90 min; 848 de 969 en 10 min). Ambos servicios consumen la misma cadena de posiciones.
- Cruce por ts ±1 s (`analisis.py`, sección 1-2): 1047 fixes coinciden en 90 min, casi todos del régimen B (Δts ≤ 1 s); no es una medida de fidelidad.

## 4. Retraso de publicación (primera recepción − ts, corregido por NTP)

Sólo fixes de coches ya vistos y aparecidos después del primer poll. Cota superior con error de hasta +15 s (CABA) y +30 s (OBA) por la resolución de poll.

| fuente | corrida | n | p10 | p50 | p90 |
|---|---|---|---|---|---|
| CABA (39 + 168) | 10 min | 1095 | 22.4 s | 26.2 s | 29.1 s |
| CABA (39 + 168) | 90 min | 7705 | 17.7 s | 21.2 s | 27.0 s |
| OBA (39 + 168) | 10 min (39 / 168) | 452 / 388 | 101 / 86 s | 105 / 90 s | 130 / 115 s |
| OBA (39 + 168) | 90 min | 6527 | 38.3 s | 66.2 s | 108.4 s |

El retraso de OBA cambia con el régimen del ts (sección 2): 89.7 s (A) y 51.3 s (B) de p50. "Retraso respecto del GPS" sólo vale respecto de la base de tiempo elegida; no es retraso respecto de la hora real.

Edad del dato en la respuesta (`server_time − ts`, 90 min): CABA p10 / p50 / p90 = 21 / 54 / 1540 s (n = 42 464); OBA 62 / 279 / 26 449 s (n = 27 807). Las colas son coches detenidos o que dejaron de reportar.

## 5. Cadencia entre fixes consecutivos del mismo coche (90 min)

| fuente | n | p10 | p50 | p90 |
|---|---|---|---|---|
| CABA (39 + 168) | 7705 | 58 s | 60 s | 64 s |
| OBA (39 + 168) | 6527 | 30.6 s | 60 s | 84 s |

Ambas publican ~1 fix por minuto por coche. En OBA aparecen intervalos de ~30 s o ~85 s (re-envíos, resolución de poll de 30 s por agencia).

## 6. Plausibilidad de velocidades con cada base de tiempo

Intervalos entre puntos emparejados consecutivos del mismo coche; distancia idéntica en ambas bases (sobre el shape si ambos puntos proyectan: 5257 intervalos; haversine: 408), sólo cambia el reloj. "Ceros raros" = intervalo con < 1 m entre dos intervalos > 3 m/s. CV = MAD·1.48 / mediana de velocidades en movimiento (≥ 20 m). Jitter = mediana de |Δ ln v| entre intervalos en movimiento consecutivos. Error vs `speed` = |v − speed reportada por CABA| / speed, intervalos con speed > 3 m/s.

| subconjunto | base | intervalos | v > 25 m/s | ceros raros | CV | jitter | error vs `speed` (mediana) | dt p10 / p50 / p90 |
|---|---|---|---|---|---|---|---|---|
| todos | ts OBA | 5665 | 1 | 5 / 2388 | 0.585 | 0.620 | 0.378 | 57 / 60 / 87 s |
| todos | ts CABA | 5665 | 0 | 4 / 2484 | 0.536 | 0.553 | 0.342 | 58 / 60 / 86 s |
| desfasado (A) | ts OBA | 2481 | 0 | 4 / 977 | 0.574 | 0.645 | 0.390 | 56 / 60 / 85 s |
| desfasado (A) | ts CABA | 2481 | 0 | 4 / 1026 | 0.529 | 0.569 | 0.353 | 58 / 60 / 62 s |
| alineado (B) | ts OBA | 2785 | 0 | 0 / 1216 | 0.554 | 0.560 | 0.341 | 58 / 60 / 63 s |
| alineado (B) | ts CABA | 2785 | 0 | 0 / 1236 | 0.535 | 0.542 | 0.335 | 58 / 60 / 86 s |

Con `speed` reportada: la base CABA queda más cerca en 1146 intervalos y la base OBA en 744 (todos); 557 vs 339 (A); 400 vs 347 (B). Sobre todos los fixes de cada fuente con su propio ts: OBA 7 de 6523 intervalos > 25 m/s (0.1 %), 90 ceros raros de 2511; CABA 0 de 7705, 26 ceros raros de 3173; CV 0.603 (OBA) vs 0.548 (CABA).

Lectura: en el régimen A el ts de CABA da intervalos más regulares (58-62 s) y velocidades algo más estables y más cercanas a la `speed` reportada que el de OBA (menos dispersión, menos velocidades imposibles); en B los dos ts son casi iguales y la prueba no distingue. Ninguna base produce velocidades imposibles en cantidad (≤ 0.1 %): con intervalos de 60 s, 25 m/s son 1500 m y la prueba tiene poca potencia. Un desfase constante no cambia ninguna velocidad: esta prueba no puede medir el corrimiento absoluto de ningún ts respecto de la hora real, sólo su regularidad.

## 7. Extrapolación de OBA (90 min; respuestas con trip y `position`: 12 883; usadas 11 826; 1057 descartadas por perpendicular > 120 m)

Positivo = adelante en el sentido de marcha. Segundos = metros / velocidad media del coche sobre el shape (4 m/s por defecto si < 1 m/s: 3268 de 11 826 respuestas, 28 %).

| métrica | línea | p10 | p50 | p90 | 10 min (p50) |
|---|---|---|---|---|---|
| Δ position − GPS (m) | 39 | 195.5 | 304.1 | 442.2 | 381 |
| Δ position − GPS (m) | 168 | 294.6 | 464.4 | 631.3 | 512 |
| Δ position − GPS (s) | 39 | 54.0 | 96.9 | 203.5 | 100.0 |
| Δ position − GPS (s) | 168 | 74.9 | 126.3 | 257.2 | 117.0 |
| Δ position − GPS (s) | ambas | 63.7 | 111.8 | 227.0 | 106.2 |
| edad del GPS en la respuesta (s) | ambas | 49.6 | 87.5 | 129.1 | 131 / 116 |
| scheduleDeviation (s) | ambas | -220 | 386 | 1460 | 398 / 1324 |

Correlación entre `scheduleDeviation` y el delta: 0.02 (39) y -0.12 (168).

Acierto contra el GPS real a la hora de la respuesta (interpolado en el shape entre fixes reales con hueco ≤ 240 s; depende de la base de tiempo, y las bases difieren según el régimen, por eso se dan las dos):

| base de tiempo de la verdad | n | error `position` p10 / p50 / p90 (m) | error `position` (s) | error del último GPS p50 (m / s) |
|---|---|---|---|---|
| ts de OBA | 11 248 | -229 / 23 / 252 | -73 / 7 / 81 | -342 / -106 |
| ts de CABA | 11 594 | -141 / 67 / 280 | -47 / 20.5 / 90 | -292 / - |

`position` queda más cerca de la verdad que el último GPS en 9360 de 11 248 respuestas (83 %; base OBA). El último GPS de OBA está atrasado ~290-340 m (~100 s) respecto de la posición interpolada; `position` lo corrige en mediana pero con dispersión p10-p90 de ~±250 m. No se separó la extrapolación por régimen de ts.

## 8. Reloj de los servidores (90 min, n = 360)

OBA `currentTime` − hora real: p50 0.00 s (-0.22 a +0.02). Header HTTP `Date`: OBA -0.99 s, CABA -0.96 s (resolución 1 s, truncado). CABA `header.timestamp` − hora real: p50 -0.35 s (mín -3.23): el feed se regenera en cada consulta. Fixes con ts posterior a `server_time`: 0 de 42 464 (CABA) y 0 de 27 807 (OBA).

## Conclusión

Lo que sostienen los datos:

1. Misma fuente de GPS: 87 % de los fixes de OBA aparecen con posición idéntica en CABA (mismo id).
2. El ts de CABA es un estampado por lote (2026-11-12, 11.36 M actualizaciones; confirmado en la captura del 2026-11-13): segundos pares, ~1 valor distinto cada 78 coches en la flota completa, concentrado en los segundos 40-52 del minuto, estable durante las 90 min.
3. El ts de OBA no es un reloj de equipo estable: el 2026-11-13 ~21:53 cambió de "≈ ts CABA − 29/58 s" a "≈ ts CABA + 2 s" sin que cambiara nada en CABA. El desfase de 29/58 s medido en la corrida de 10 min era del régimen A y no es una propiedad fija de las fuentes.
4. CABA muestra cada fix ~25-50 s antes que OBA (primera recepción), con retraso de publicación de ~21 s por su ts; el de OBA es 51-90 s según el régimen. La hipótesis "CABA atrasa más que OBA al publicar" no se sostiene.
5. La extrapolación de OBA adelanta la posición ~300-460 m (~100-125 s de marcha, p50); parte de lo que muestra la app de CuandoSubo es extrapolación.

Implicancia para el ML (hipótesis, no verificada): entrenar con el ts de CABA mueve las muestras a la hora del lote (~1/min, cuantizada a 2 s) y no a la hora del GPS. Si el estampado va 30-60 s después del GPS real, el modelo aprende pasos ese tiempo más tarde y predice tarde, y el coche llega antes de lo anunciado (el error grave). Los datos de esta carpeta no establecen el signo ni la magnitud del corrimiento absoluto: lo único medido es que el ts de CABA es una estampa de lote y que el de OBA no sirve de referencia de "hora real".

Lo que no sostienen: cuál ts está más cerca de la hora real del GPS; si la extrapolación acierta mejor que no extrapolar con certeza fuera de la mediana; qué provocó el cambio de régimen de OBA.

## Aplicado en producción (2026-11-14, deployado: commits `20bf173` y `f6f2d5c` de consola-transporte)

- `proyectoconsola/public/prediccion/core.js`: `CABA_TS_OFFSET_S = 60` s (desde 2026-11-14 ~11 h; antes 29 s, commit `20bf173`). El ETA anunciado es `max(0, eta_modelo − (ahora − ts_ping) − 60)`: se toma como hora real del ping `ts_CABA − 60 s`.
- Observación en campo, 2026-11-14 10:56: línea 39, interno 93, parada Plaza de los Colegiales (39B). Con el offset de 29 s, la app no alcanzaba a cubrir el paso real; a partir de esa observación el valor se subió a 60 s. Es una sola muestra: el valor queda provisorio hasta tener más observaciones en parada.
- Base previa: `ts_CABA − ts_CuandoSubo` para el mismo punto GPS (mismo id y lat/lon), 50 550 puntos del 2026-11-14 04-09 h (régimen "de día" de CuandoSubo): p50 28 s, p90 30 s, p99 33 s; 85.7 % entre 20 y 35 s. De noche (~21:54-03 h) CuandoSubo copia casi la hora de CABA (−1 s) y no sirve de referencia; CABA estampa igual todo el día.
- Supuesto no validado: que en el régimen de día `lastUpdateTime` de CuandoSubo sea la hora real del GPS del equipo.
- Falta: más observaciones en campo (interno y hora de paso anotados en una parada, 10–15 coches) para fijar el corrimiento.
- Posiciones sin caché en el servidor (2026-11-14): `Cache-Control: no-store` en `/api/vehicles`, `/api/fleet` y `/api/fleet?all=1`, ttl de `lib/vehicles.js` y de `lib/eta_predict.js` en 0; cada pedido baja de la API CABA y la única caché es la del navegador. Motivo: Vercel serverless no comparte memoria entre instancias y hay ≤ 2 usuarios.
- Revisión: cambiar la constante `CABA_TS_OFFSET_S` (un solo lugar). No toca `ts_age` ni la hora del día del modelo: en entrenamiento las dos horas son de CABA y el corrimiento se cancela.

## Limitaciones

- Sin verdad de campo: ningún dato fija la hora real a la que un coche estuvo en un punto. Es la limitación que impide cuantificar el corrimiento de cualquier ts.
- Una sola captura de 90 min (21:14-22:44, viernes de noche, tráfico decreciente) y una de 10 min (20:46-20:56); sin pico de hora punta ni valle. El cambio de régimen de OBA se vio una sola vez.
- Resolución de poll: 15 s (CABA) y 30 s por agencia (OBA); los retrasos son cotas superiores. Las fases de poll y de fix se mantienen fijas, las diferencias de primera recepción son más estables que la variabilidad real.
- Las firmas de lote de la captura (118 coches por respuesta) usan sólo 39 y 168; no son comparables en valores absolutos con los del día completo (~10 900 coches).
- La prueba de velocidades no detecta corrimientos constantes y tiene poca potencia con intervalos de 60 s. La `speed` reportada de CABA es instantánea, no promedio del intervalo; se asumió m/s (máx. observado 15).
- La velocidad usada para pasar metros a segundos es la media del coche (incluye detenciones); 28 % de las respuestas usan 4 m/s por defecto.
- El shape se elige por coche y trip con la geometría; ida y vuelta se superponen en calles (1057 descartes por perpendicular > 120 m en 90 min).
- El cruce por posición excluye coches detenidos y usa umbral de 2 m (87 % de los fixes con par inequívoco).
- La corrida usa una sola cuenta/clave de OBA; el WAF no se activó con 360 requests en 90 min (1 cada 15 s).
- Latencia de la app propia (medido 2026-11-14 10:04–10:07, 18 requests a `/api/fleet?agency_id=56` cada 10 s contra la API CABA directa): con caché en memoria de 25 s + CDN `s-maxage=20, stale-while-revalidate=40`, recepción − `fetchedAt` p50 52 s / máx 93 s, y la app iba p50 60 s / máx 122 s detrás de la API CABA. Corregido y deployado el 2026-11-14: sin caché en el servidor (`Cache-Control: no-store`, `VEHICLES_TTL_MS` por defecto 0), cada pedido baja de la API CABA; la única caché es la del navegador. Motivo: Vercel serverless no comparte memoria entre instancias y hay ≤ 2 usuarios. Re-medido después del deploy (mismo método): sin caché y con timeout del upstream de 25 s, 12/18 pedidos frescos en ~0,6 s pero 6/18 tardaban 25,4 s (pedido Vercel→CABA sin respuesta) y devolvían el dato stale de hasta 85 s; con timeout de 5 s (`f6f2d5c`), 18/18 iguales a la API CABA directa en el mismo instante (atraso 0 s), 14/18 en ~0,6 s y 4/18 en ~5,5 s con dato stale de 14 s.

## Próximos pasos

1. Observación manual en una parada para obtener verdad de campo (hora real a la que pasa un coche) y fijar el corrimiento absoluto del ts de CABA; prioritario: sin esto el efecto sobre el ML sigue siendo una hipótesis.
2. Repetir la captura de 90 min en hora pico y en valle (`python captura.py --minutes 90 --max-oba 400`; 360 requests a 1 cada 15 s no activaron el WAF) para ver si el cambio de régimen de OBA reaparece y a qué hora.
3. Después del deploy, repetir la medición de la latencia de la app (mismo método: 18 requests cada 10 s contra la API CABA directa) y confirmar que el atraso agregado queda ≤ ~10–20 s.
4. Si la verdad de campo muestra que el ts de CABA va tardío, evaluar en el pipeline ML usar la hora de recepción del lote menos un retraso medido, o una base de tiempo corregida, y re-medir el error de arribo temprano en el horizonte de 5 min.

## Cómo correr

Desde `prediccion colectivos/analisis_latencia_fuentes/` (Python con `requests`, `gtfs-realtime-bindings` y `numpy`; credenciales en `proyectoconsola/.env.local`, nunca se imprimen ni se guardan). En Windows exportar `PYTHONIOENCODING=utf-8` para la consola; los scripts no se ejecutan con `python -I` porque `analisis_lote.py` importa `analisis.py` del mismo directorio.

```
python captura.py --prueba                                   # 1 tick de validación (1 CABA + 1 OBA 56)
python captura.py --minutes 90 --tick 15 --max-oba 400      # captura; escribe datos/captura_<fecha-hora>.ndjson
python analisis.py [--archivo datos/captura_XXXX.ndjson] [--sufijo _90min]
python analisis_lote.py [--archivo datos/captura_XXXX.ndjson] [--sufijo _90min]
python ts_grabador_dist.py  <dia>.ndjson.gz                  # ts del grabador CABA: distintos por foto, mod 60, saltos
python ts_grabador_dist2.py <dia>.ndjson.gz                  # ts del grabador CABA: pares, distintos por foto, paso por coche
```

- `analisis.py`: cruce de fixes, Δ de primera recepción, retraso de publicación, cadencia, relojes y extrapolación de OBA; escribe `resultados<sufijo>.md/json`.
- `analisis_lote.py`: firmas de lote (por respuesta, por punto y por bloque de 10 min), `ts_CABA − ts_OBA` por línea, bloques de 15 y 5 min e histograma, retraso y reparto de segundos por régimen (corte automático), plausibilidad de velocidades (mismos puntos y todos los fixes); escribe `resultados_lote<sufijo>.md/json`. Sin `--archivo` usan el último `captura_*.ndjson`.
- `ts_grabador_dist*.py`: leen un NDJSON diario del grabador (`.ndjson.gz`) pasado como argumento (p. ej. `//192.168.0.18/buffer/grabaciones/2026-11-12.ndjson.gz`).

Reglas de la captura contra el WAF de OBA: requests secuenciales, mínimo 15 s entre requests (`--tick` menor se rechaza), `allow_redirects=False`, respuesta no 200 o no JSON = pausa de 120 s, segunda anomalía = se aborta la parte OBA, tope `--max-oba` (default 45; subirlo para corridas largas).
