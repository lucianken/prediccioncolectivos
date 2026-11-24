# Resultados automáticos (analisis.py)

Archivo: `captura_20261113-204553.ndjson`
Offset NTP (remoto - local): +0.2612 s; muestras: [0.2611992, 0.2610912, 0.2617714]. Todas las horas locales se corrigen como t_real = t_local + offset.

## Polls válidos

- caba agencia=None: 40 respuestas válidas
- oba agencia=56: 20 respuestas válidas
- oba agencia=80: 20 respuestas válidas
- Requests OBA en esta captura: 40; incidentes WAF/anomalías: 0 ([])

- Coches OBA sin GPS/location (descartados): 18

## 1-2) Cruce de fixes (mismo id, |Δts| <= 1 s)

Coches distintos vistos: CABA 137, OBA 158, en ambas 129 (solo CABA 8, solo OBA 29).

Fixes (coches presentes en ambas fuentes). Un fix cuenta como coincidente si el mismo id tiene ts_gps a ±1 s en la otra fuente.

| línea | coinciden | solo OBA | solo CABA |
|---|---|---|---|
| 39 | 13 | 518 | 712 |
| 168 | 5 | 433 | 484 |
| todas | 18 | 951 | 1196 |

Distancia entre posiciones de fixes coincidentes (m) y Δts (OBA − CABA, s):

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| dist m (39) | 13 | 0.02 | 0.05 | 283.44 | 0.02 | 320.65 |
| Δts s (39) | 13 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 |
| dist m (168) | 5 | 0.03 | 160.28 | 208.75 | 0.02 | 229.99 |
| Δts s (168) | 5 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| dist m (todas) | 18 | 0.02 | 53.96 | 251.33 | 0.02 | 320.65 |
| Δts s (todas) | 18 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 |

Fixes de OBA sin par en CABA: Δts al fix CABA más cercano del mismo coche (s):

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| OBA sin par (39) | 518 | -36.7 | -26.0 | 27.3 | -2920.5 | 105.1 |
| OBA sin par (168) | 433 | -29.0 | -12.5 | 15.8 | -16301.6 | 68.0 |
| OBA sin par (todas) | 951 | -30.0 | -25.0 | 26.0 | -16301.6 | 105.1 |

## 2b) Cruce por posición (mismo id, posición idéntica ≤ 2 m, sin importar ts_gps)

Sólo pares inequívocos: exactamente un fix CABA y un fix OBA del coche dentro de 2 m entre sí (se descartan coches detenidos con posiciones repetidas). Δts = ts_gps(CABA) − ts_gps(OBA) para el mismo punto. Δrecv = primera recepción CABA − primera recepción OBA (negativo: CABA lo mostró antes); sólo fixes aparecidos después del primer poll de ambas fuentes.

- 39: 531 fixes OBA de coches comunes; pares inequívocos por posición: 460
- 168: 438 fixes OBA de coches comunes; pares inequívocos por posición: 388
- todas: 969 fixes OBA de coches comunes; pares inequívocos por posición: 848

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| Δts CABA−OBA (s) [39] | 460 | 27.0 | 29.0 | 58.0 | -4.0 | 85.0 |
| Δrecv CABA−OBA (s) [39] | 414 | -48.6 | -47.6 | -45.3 | -107.0 | -45.3 |
| Δts CABA−OBA (s) [168] | 388 | 27.0 | 29.0 | 58.0 | -44.6 | 63.0 |
| Δrecv CABA−OBA (s) [168] | 348 | -33.4 | -33.1 | -30.9 | -33.6 | -30.2 |
| Δts CABA−OBA (s) [todas] | 848 | 27.0 | 29.0 | 58.0 | -44.6 | 85.0 |
| Δrecv CABA−OBA (s) [todas] | 762 | -48.5 | -45.3 | -31.7 | -107.0 | -30.2 |

## 3) Retraso de publicación (primera recepción − ts_gps, corregido por NTP)

Resolución: CABA se consulta cada 15 s, OBA cada 30 s por agencia: el valor observado es cota superior del retraso real, con error de hasta +15 s (CABA) / +30 s (OBA). Sólo fixes de coches ya vistos antes y que aparecen después del primer poll válido de esa fuente/agencia.

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| CABA 39 | 656 | 22.4 | 26.2 | 29.1 | 22.1 | 58.4 |
| CABA 168 | 439 | 22.4 | 26.1 | 29.1 | 22.1 | 62.8 |
| CABA todas | 1095 | 22.4 | 26.2 | 29.1 | 22.1 | 62.8 |
| OBA 39 | 452 | 101.1 | 104.7 | 130.0 | 27.3 | 157.5 |
| OBA 168 | 388 | 85.8 | 90.2 | 114.7 | 12.1 | 119.7 |
| OBA todas | 840 | 86.4 | 104.5 | 127.8 | 12.1 | 157.5 |

Edad del dato en cada respuesta (server_time − ts_gps, s; independiente del reloj local):

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| CABA 39 | 3181 | 26.0 | 56.0 | 504.0 | 22.0 | 3193.0 |
| CABA 168 | 2234 | 26.0 | 56.0 | 1684.9 | 22.0 | 3191.0 |
| CABA todas | 5415 | 26.0 | 56.0 | 774.0 | 22.0 | 3193.0 |
| OBA 39 | 1806 | 103.7 | 157.8 | 7588.0 | 27.2 | 122067.1 |
| OBA 168 | 1315 | 87.6 | 141.8 | 110180.7 | 12.1 | 963049.1 |
| OBA todas | 3121 | 101.2 | 147.2 | 26757.6 | 12.1 | 963049.1 |

## 4) Cadencia: intervalo entre fixes consecutivos del mismo coche (s)

Medida con fixes observados; un poll más espaciado que la cadencia real (OBA cada 30 s) puede saltear fixes y sobreestimar el intervalo.

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| CABA 39 | 656 | 58.0 | 60.0 | 63.0 | 28.0 | 1684.0 |
| CABA 168 | 439 | 58.0 | 60.0 | 62.0 | 26.0 | 2642.0 |
| CABA todas | 1095 | 58.0 | 60.0 | 62.0 | 26.0 | 2642.0 |
| OBA 39 | 452 | 31.1 | 60.0 | 84.8 | 16.5 | 1875.4 |
| OBA 168 | 388 | 31.0 | 60.0 | 80.0 | 15.2 | 2501.6 |
| OBA todas | 840 | 31.0 | 60.0 | 82.0 | 15.2 | 2501.6 |
| unión CABA+OBA (fixes separados >1 s) | 2036 | 4.0 | 31.0 | 60.0 | 2.0 | 16301.6 |

## 6) Reloj de los servidores

OBA: currentTime − (t_recv + offset NTP). CABA: header.timestamp es la generación del feed (no un reloj en vivo): su diferencia con t_recv es la edad del feed; el reloj sale del header HTTP Date (resolución 1 s).

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| OBA currentTime − t_real (s) | 40 | -0.02 | -0.02 | -0.02 | -0.03 | -0.01 |
| OBA HTTP Date − t_real (s) | 40 | -1.53 | -0.99 | -0.6 | -1.74 | -0.24 |
| CABA header.timestamp − t_real (s) [edad del feed, negativo] | 40 | -0.91 | -0.1 | -0.04 | -2.77 | -0.0 |
| CABA HTTP Date − t_real (s) | 40 | -1.11 | -1.06 | -0.44 | -1.48 | -0.26 |

Fixes con ts_gps en el futuro (reloj a bordo adelantado):

- CABA: 5415 observaciones; ts_gps > server_time: 0 (máx 0.0 s); ts_gps > hora real local: 0
- OBA: 3121 observaciones; ts_gps > server_time: 0 (máx 0.0 s); ts_gps > hora real local: 0

## 5) Extrapolación de OBA (tripStatus.position vs GPS real)

Respuestas OBA con trip y `position`: 1719; usadas: 1588; descartadas: {'perp>120m': 131}.
Shape elegido por (coche, trip): el de menor mediana de distancia perpendicular de sus fixes reales (penalizando avance negativo). Velocidad del coche = progreso medio sobre el shape entre su primer y último fix real de la captura si es ≥ 1.0 m/s; si no, 4.0 m/s (por defecto, indicado en la columna de abajo).

| métrica | n | p10 | p50 | p90 | min | max |
|---|---|---|---|---|---|---|
| Δ pred−GPS (m) [39] | 890 | 275.9 | 380.6 | 494.8 | -591.9 | 1186.3 |
| Δ pred−GPS (s) [39] | 890 | 71.5 | 100.0 | 142.8 | -155.7 | 315.7 |
| edad del GPS en la respuesta (s) [39] | 890 | 102.7 | 131.2 | 158.1 | 99.2 | 281.7 |
| velocidad implícita Δm/edad (m/s) [39] | 890 | 2.22 | 2.89 | 3.67 | -5.75 | 6.02 |
| scheduleDeviation (s) [39] | 890 | -200.0 | 398.0 | 1070.2 | -398.0 | 2900.0 |
| error pred vs GPS real a la misma hora (m) [39] | 621 | -324.9 | -109.0 | 85.6 | -896.3 | 718.4 |
| error pred vs GPS real a la misma hora (s) [39] | 621 | -88.4 | -29.1 | 24.8 | -386.8 | 265.3 |
| error del último GPS vs GPS real a la misma hora (m) [39] | 621 | -730.2 | -467.6 | -269.2 | -1355.1 | -3.3 |
| error del último GPS vs GPS real a la misma hora (s) [39] | 621 | -199.5 | -127.9 | -74.6 | -642.0 | -0.8 |
| (base ts CABA) error pred vs real (m) [39] | 796 | -164.1 | 22.9 | 195.7 | -657.4 | 673.7 |
| (base ts CABA) error pred vs real (s) [39] | 796 | -42.0 | 6.5 | 58.2 | -213.3 | 248.8 |
| (base ts CABA) error del último GPS vs real (m) [39] | 796 | -579.7 | -341.7 | -161.1 | -1116.9 | -1.1 |
| Δ pred−GPS (m) [168] | 698 | 350.3 | 511.7 | 572.1 | -718.3 | 914.5 |
| Δ pred−GPS (s) [168] | 698 | 75.7 | 117.0 | 186.3 | -179.6 | 422.1 |
| edad del GPS en la respuesta (s) [168] | 698 | 86.9 | 115.8 | 143.1 | 84.8 | 149.8 |
| velocidad implícita Δm/edad (m/s) [168] | 698 | 3.12 | 4.17 | 4.84 | -6.22 | 6.91 |
| scheduleDeviation (s) [168] | 698 | 149.4 | 1324.0 | 2455.2 | -856.0 | 5936.0 |
| error pred vs GPS real a la misma hora (m) [168] | 564 | -247.4 | 21.9 | 243.3 | -682.3 | 547.5 |
| error pred vs GPS real a la misma hora (s) [168] | 564 | -51.7 | 5.8 | 80.1 | -130.9 | 289.0 |
| error del último GPS vs GPS real a la misma hora (m) [168] | 564 | -720.2 | -421.9 | -202.6 | -1208.3 | 0.0 |
| error del último GPS vs GPS real a la misma hora (s) [168] | 564 | -175.3 | -113.2 | -58.8 | -275.2 | 0.0 |
| (base ts CABA) error pred vs real (m) [168] | 613 | -58.4 | 180.3 | 342.8 | -466.8 | 547.8 |
| (base ts CABA) error pred vs real (s) [168] | 613 | -13.2 | 45.4 | 116.6 | -143.1 | 297.1 |
| (base ts CABA) error del último GPS vs real (m) [168] | 613 | -512.6 | -278.4 | -88.9 | -1010.0 | 485.6 |
| Δ pred−GPS (m) [todas] | 1588 | 283.5 | 390.0 | 562.1 | -718.3 | 1186.3 |
| Δ pred−GPS (s) [todas] | 1588 | 72.4 | 106.2 | 168.7 | -179.6 | 422.1 |
| edad del GPS en la respuesta (s) [todas] | 1588 | 89.9 | 122.1 | 156.2 | 84.8 | 281.7 |
| velocidad implícita Δm/edad (m/s) [todas] | 1588 | 2.35 | 3.24 | 4.72 | -6.22 | 6.91 |
| scheduleDeviation (s) [todas] | 1588 | -105.0 | 550.0 | 1983.8 | -856.0 | 5936.0 |
| error pred vs GPS real a la misma hora (m) [todas] | 1185 | -296.1 | -51.6 | 178.4 | -896.3 | 718.4 |
| error pred vs GPS real a la misma hora (s) [todas] | 1185 | -76.9 | -12.6 | 57.4 | -386.8 | 289.0 |
| error del último GPS vs GPS real a la misma hora (m) [todas] | 1185 | -723.4 | -450.0 | -239.7 | -1355.1 | 0.0 |
| error del último GPS vs GPS real a la misma hora (s) [todas] | 1185 | -186.3 | -120.1 | -68.1 | -642.0 | 0.0 |
| (base ts CABA) error pred vs real (m) [todas] | 1409 | -134.6 | 86.7 | 299.1 | -657.4 | 673.7 |
| (base ts CABA) error pred vs real (s) [todas] | 1409 | -33.4 | 22.7 | 87.9 | -213.3 | 297.1 |
| (base ts CABA) error del último GPS vs real (m) [todas] | 1409 | -557.2 | -314.4 | -128.4 | -1116.9 | 485.6 |

Positivo = pred adelante (en el sentido de marcha) del GPS / de la posición real. La verdad a la hora `currentTime` se interpola en el shape entre el fix real anterior y el siguiente (fixes de OBA con su ts; variante: fixes de CABA con su ts, +29 s respecto de OBA); sólo si el hueco es ≤ 240 s.

- 39: pred más cercana a la verdad que el último GPS en 605 de 621 respuestas; respuestas con velocidad por defecto: 51; correlación(scheduleDeviation, Δm) = 0.03
- 168: pred más cercana a la verdad que el último GPS en 496 de 564 respuestas; respuestas con velocidad por defecto: 16; correlación(scheduleDeviation, Δm) = -0.4
- todas: pred más cercana a la verdad que el último GPS en 1101 de 1185 respuestas; respuestas con velocidad por defecto: 67; correlación(scheduleDeviation, Δm) = -0.11
