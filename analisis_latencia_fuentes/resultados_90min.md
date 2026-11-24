# Resultados automáticos (analisis.py)

Archivo: `captura_20261113-211401.ndjson`
Offset NTP (remoto - local): +0.2725 s; muestras: [0.2737172, 0.2725213, 0.2722178]. Todas las horas locales se corrigen como t_real = t_local + offset.

## Polls válidos

- caba agencia=None: 360 respuestas válidas
- oba agencia=56: 180 respuestas válidas
- oba agencia=80: 180 respuestas válidas
- Requests OBA en esta captura: 360; incidentes WAF/anomalías: 0 ([])

- Coches OBA sin GPS/location (descartados): 24

## 1-2) Cruce de fixes (mismo id, |Δts| <= 1 s)

Coches distintos vistos: CABA 133, OBA 161, en ambas 131 (solo CABA 2, solo OBA 30).

Fixes (coches presentes en ambas fuentes). Un fix cuenta como coincidente si el mismo id tiene ts_gps a ±1 s en la otra fuente.

| línea | coinciden | solo OBA | solo CABA |
|---|---|---|---|
| 39 | 562 | 3102 | 3882 |
| 168 | 485 | 2489 | 2908 |
| todas | 1047 | 5591 | 6790 |

Distancia entre posiciones de fixes coincidentes (m) y Δts (OBA − CABA, s):

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| dist m (39) | 562 | 0.02 | 0.04 | 0.06 | 0.0 | 606.86 |
| Δts s (39) | 562 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 |
| dist m (168) | 485 | 0.02 | 0.04 | 0.06 | 0.0 | 544.12 |
| Δts s (168) | 485 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 |
| dist m (todas) | 1047 | 0.02 | 0.04 | 0.06 | 0.0 | 606.86 |
| Δts s (todas) | 1047 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 |

Fixes de OBA sin par en CABA: Δts al fix CABA más cercano del mismo coche (s):

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| OBA sin par (39) | 3102 | -29.0 | 2.0 | 16.4 | -1066.8 | 875.0 |
| OBA sin par (168) | 2489 | -29.0 | 2.0 | 4.0 | -18047.7 | 452.4 |
| OBA sin par (todas) | 5591 | -29.0 | 2.0 | 13.1 | -18047.7 | 875.0 |

## 2b) Cruce por posición (mismo id, posición idéntica ≤ 2 m, sin importar ts_gps)

Sólo pares inequívocos: exactamente un fix CABA y un fix OBA del coche dentro de 2 m entre sí (se descartan coches detenidos con posiciones repetidas). Δts = ts_gps(CABA) − ts_gps(OBA) para el mismo punto. Δrecv = primera recepción CABA − primera recepción OBA (negativo: CABA lo mostró antes); sólo fixes aparecidos después del primer poll de ambas fuentes.

- 39: 3664 fixes OBA de coches comunes; pares inequívocos por posición: 3118
- 168: 2974 fixes OBA de coches comunes; pares inequívocos por posición: 2659
- todas: 6638 fixes OBA de coches comunes; pares inequívocos por posición: 5777

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| Δts CABA−OBA (s) [39] | 3118 | -3.0 | -1.0 | 56.0 | -46.1 | 89.0 |
| Δrecv CABA−OBA (s) [39] | 3074 | -44.9 | -39.8 | -14.8 | -96.7 | -13.9 |
| Δts CABA−OBA (s) [168] | 2659 | -3.0 | -1.0 | 54.0 | -44.7 | 88.0 |
| Δrecv CABA−OBA (s) [168] | 2624 | -50.1 | -29.8 | -25.3 | -52.7 | -23.4 |
| Δts CABA−OBA (s) [todas] | 5777 | -3.0 | -1.0 | 56.0 | -46.1 | 89.0 |
| Δrecv CABA−OBA (s) [todas] | 5698 | -47.8 | -34.7 | -24.2 | -96.7 | -13.9 |

## 3) Retraso de publicación (primera recepción − ts_gps, corregido por NTP)

Resolución: CABA se consulta cada 15 s, OBA cada 30 s por agencia: el valor observado es cota superior del retraso real, con error de hasta +15 s (CABA) / +30 s (OBA). Sólo fixes de coches ya vistos antes y que aparecen después del primer poll válido de esa fuente/agencia.

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| CABA 39 | 4364 | 17.7 | 21.2 | 27.3 | 15.6 | 96.6 |
| CABA 168 | 3341 | 17.7 | 21.2 | 26.2 | 15.7 | 66.6 |
| CABA todas | 7705 | 17.7 | 21.2 | 27.0 | 15.6 | 96.6 |
| OBA 39 | 3597 | 36.7 | 66.8 | 108.7 | 4.5 | 124698.6 |
| OBA 168 | 2930 | 44.1 | 54.9 | 102.7 | 3.2 | 197374.6 |
| OBA todas | 6527 | 38.3 | 66.2 | 108.4 | 3.2 | 197374.6 |

Edad del dato en cada respuesta (server_time − ts_gps, s; independiente del reloj local):

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| CABA 39 | 25264 | 21.0 | 62.0 | 1641.7 | 15.0 | 3221.0 |
| CABA 168 | 17200 | 20.0 | 51.0 | 1384.0 | 15.0 | 3221.0 |
| CABA todas | 42464 | 21.0 | 54.0 | 1540.0 | 15.0 | 3221.0 |
| OBA 39 | 16561 | 64.8 | 392.8 | 11430.4 | 4.4 | 127670.4 |
| OBA 168 | 11246 | 50.8 | 142.1 | 102903.9 | 3.2 | 968652.4 |
| OBA todas | 27807 | 62.1 | 279.1 | 26449.7 | 3.2 | 968652.4 |

## 4) Cadencia: intervalo entre fixes consecutivos del mismo coche (s)

Medida con fixes observados; un poll más espaciado que la cadencia real (OBA cada 30 s) puede saltear fixes y sobreestimar el intervalo.

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| CABA 39 | 4364 | 58.0 | 60.0 | 64.0 | 26.0 | 2852.0 |
| CABA 168 | 3341 | 58.0 | 60.0 | 62.0 | 26.0 | 2340.0 |
| CABA todas | 7705 | 58.0 | 60.0 | 64.0 | 26.0 | 2852.0 |
| OBA 39 | 3597 | 30.1 | 60.0 | 87.0 | 3.8 | 3076.2 |
| OBA 168 | 2930 | 35.0 | 60.0 | 65.0 | 0.1 | 4057.5 |
| OBA todas | 6527 | 30.6 | 60.0 | 84.0 | 0.1 | 4057.5 |
| unión CABA+OBA (fixes separados >1 s) | 13296 | 2.0 | 32.0 | 60.0 | 1.0 | 18023.5 |

## 6) Reloj de los servidores

OBA: currentTime − (t_recv + offset NTP). CABA: header.timestamp es la generación del feed (no un reloj en vivo): su diferencia con t_recv es la edad del feed; el reloj sale del header HTTP Date (resolución 1 s).

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| OBA currentTime − t_real (s) | 360 | -0.02 | 0.0 | 0.02 | -0.22 | 0.02 |
| OBA HTTP Date − t_real (s) | 360 | -1.54 | -0.99 | -0.46 | -1.95 | -0.07 |
| CABA header.timestamp − t_real (s) [edad del feed, negativo] | 360 | -1.15 | -0.35 | 0.01 | -3.23 | 0.33 |
| CABA HTTP Date − t_real (s) | 360 | -1.43 | -0.96 | -0.28 | -2.07 | -0.08 |

Fixes con ts_gps en el futuro (reloj a bordo adelantado):

- CABA: 42464 observaciones; ts_gps > server_time: 0 (máx 0.0 s); ts_gps > hora real local: 0
- OBA: 27807 observaciones; ts_gps > server_time: 0 (máx 0.0 s); ts_gps > hora real local: 0

## 5) Extrapolación de OBA (tripStatus.position vs GPS real)

Respuestas OBA con trip y `position`: 12883; usadas: 11826; descartadas: {'perp>120m': 1057}.
Shape elegido por (coche, trip): el de menor mediana de distancia perpendicular de sus fixes reales (penalizando avance negativo). Velocidad del coche = progreso medio sobre el shape entre su primer y último fix real de la captura si es ≥ 1.0 m/s; si no, 4.0 m/s (por defecto, indicado en la columna de abajo).

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| Δ pred−GPS (m) [39] | 6430 | 195.5 | 304.1 | 442.2 | -1318.8 | 9988.5 |
| Δ pred−GPS (s) [39] | 6430 | 54.0 | 96.9 | 203.5 | -624.1 | 2497.1 |
| edad del GPS en la respuesta (s) [39] | 6430 | 60.0 | 90.3 | 128.3 | 33.8 | 299.3 |
| velocidad implícita Δm/edad (m/s) [39] | 6430 | 2.34 | 3.83 | 4.71 | -11.11 | 145.51 |
| scheduleDeviation (s) [39] | 6430 | -318.0 | 192.0 | 738.0 | -824.0 | 1500.0 |
| error pred vs GPS real a la misma hora (m) [39] | 5999 | -258.1 | -36.9 | 173.6 | -1157.8 | 8954.1 |
| error pred vs GPS real a la misma hora (s) [39] | 5999 | -90.7 | -12.0 | 61.1 | -861.3 | 2238.5 |
| error del último GPS vs GPS real a la misma hora (m) [39] | 5999 | -589.0 | -341.0 | -114.2 | -1624.0 | 4.8 |
| error del último GPS vs GPS real a la misma hora (s) [39] | 5999 | -232.3 | -111.5 | -35.8 | -1009.9 | 1.6 |
| (base ts CABA) error pred vs real (m) [39] | 6263 | -173.2 | 11.2 | 183.8 | -1316.7 | 1764.1 |
| (base ts CABA) error pred vs real (s) [39] | 6263 | -60.9 | 3.5 | 64.9 | -678.2 | 441.0 |
| (base ts CABA) error del último GPS vs real (m) [39] | 6263 | -525.5 | -290.2 | -105.3 | -1488.4 | 5.5 |
| Δ pred−GPS (m) [168] | 5396 | 294.6 | 464.4 | 631.3 | -931.7 | 1876.8 |
| Δ pred−GPS (s) [168] | 5396 | 74.9 | 126.3 | 257.2 | -232.9 | 812.8 |
| edad del GPS en la respuesta (s) [168] | 5396 | 48.0 | 81.3 | 129.1 | 39.6 | 291.0 |
| velocidad implícita Δm/edad (m/s) [168] | 5396 | 3.82 | 6.19 | 6.64 | -5.68 | 15.51 |
| scheduleDeviation (s) [168] | 5396 | 25.0 | 772.0 | 2175.0 | -772.0 | 8278.0 |
| error pred vs GPS real a la misma hora (m) [168] | 5249 | -156.8 | 102.3 | 296.3 | -1818.7 | 724.0 |
| error pred vs GPS real a la misma hora (s) [168] | 5249 | -43.8 | 29.0 | 99.7 | -454.7 | 483.2 |
| error del último GPS vs GPS real a la misma hora (m) [168] | 5249 | -658.8 | -342.3 | -125.8 | -1471.8 | 6.5 |
| error del último GPS vs GPS real a la misma hora (s) [168] | 5249 | -208.2 | -99.6 | -35.4 | -872.3 | 1.9 |
| (base ts CABA) error pred vs real (m) [168] | 5331 | -68.0 | 146.5 | 330.3 | -1453.8 | 735.9 |
| (base ts CABA) error pred vs real (s) [168] | 5331 | -19.2 | 41.7 | 111.6 | -363.4 | 482.6 |
| (base ts CABA) error del último GPS vs real (m) [168] | 5331 | -556.9 | -294.5 | -112.3 | -1573.1 | 6.8 |
| Δ pred−GPS (m) [todas] | 11826 | 222.0 | 351.3 | 604.1 | -1318.8 | 9988.5 |
| Δ pred−GPS (s) [todas] | 11826 | 63.7 | 111.8 | 227.0 | -624.1 | 2497.1 |
| edad del GPS en la respuesta (s) [todas] | 11826 | 49.6 | 87.5 | 129.1 | 33.8 | 299.3 |
| velocidad implícita Δm/edad (m/s) [todas] | 11826 | 2.59 | 4.28 | 6.52 | -11.11 | 145.51 |
| scheduleDeviation (s) [todas] | 11826 | -220.0 | 386.0 | 1460.0 | -824.0 | 8278.0 |
| error pred vs GPS real a la misma hora (m) [todas] | 11248 | -229.2 | 22.6 | 252.3 | -1818.7 | 8954.1 |
| error pred vs GPS real a la misma hora (s) [todas] | 11248 | -73.4 | 7.0 | 81.4 | -861.3 | 2238.5 |
| error del último GPS vs GPS real a la misma hora (m) [todas] | 11248 | -619.6 | -341.5 | -121.3 | -1624.0 | 6.5 |
| error del último GPS vs GPS real a la misma hora (s) [todas] | 11248 | -220.0 | -106.1 | -35.7 | -1009.9 | 1.9 |
| (base ts CABA) error pred vs real (m) [todas] | 11594 | -140.9 | 67.1 | 279.5 | -1453.8 | 1764.1 |
| (base ts CABA) error pred vs real (s) [todas] | 11594 | -46.9 | 20.5 | 90.0 | -678.2 | 482.6 |
| (base ts CABA) error del último GPS vs real (m) [todas] | 11594 | -539.9 | -292.3 | -108.7 | -1573.1 | 6.8 |

Positivo = pred adelante (en el sentido de marcha) del GPS / de la posición real. La verdad a la hora `currentTime` se interpola en el shape entre el fix real anterior y el siguiente (fixes de OBA con su ts; variante: fixes de CABA con su ts, +29 s respecto de OBA); sólo si el hueco es ≤ 240 s.

- 39: pred más cercana a la verdad que el último GPS en 5245 de 5999 respuestas; respuestas con velocidad por defecto: 2009; correlación(scheduleDeviation, Δm) = 0.02
- 168: pred más cercana a la verdad que el último GPS en 4115 de 5249 respuestas; respuestas con velocidad por defecto: 1259; correlación(scheduleDeviation, Δm) = -0.12
- todas: pred más cercana a la verdad que el último GPS en 9360 de 11248 respuestas; respuestas con velocidad por defecto: 3268; correlación(scheduleDeviation, Δm) = 0.04
