# Oráculo de ramal: techo de ganancia de conocer el ramal en tiempo real

Replay en condiciones de producción (`prediccion/replay/`, comando: `python -m prediccion.replay.run --workers 3 --out data/ml/replay/run2`). Lógica de la app: `path_reference.predict_from_raw` + presentación de `app.js` (viene / puede venir / sentido sin confirmar, orden por ETA, tope de 5), solo con pings hasta t, historial de 15 min, ping máximo de 10 min.
- **Versión fijada:** `geo_assign.py` y `path_reference.py` del commit **e7479f7** (contrato 2.1, sentido por geometría), copiados a `prediccion/replay/pinned/`. Modelo: `data/ml/export/path_v2c_l1_s1` (2.1).
- **Muestras:** 12 líneas habilitadas, 40 paradas por línea (mitad tronco compartido, mitad tramo exclusivo; líneas con un recorrido por sentido: «únicas»), instantes cada 10 min de 6 a 23 h, 10 días del período de evaluación (6 hábiles: 15, 16, 17, 18 de sep., 6 y 8 de oct.; 4 de fin de semana: 19, 20 de sep., 3, 4 de oct.). La línea 26 solo tiene datos los 3 primeros días (15–17 de sep.).
- **Verdad:** cruce de la parada sobre un shape que la sirve, con pings futuros compatibles (`geo_assign`), interpolado entre dos pings a lo sumo 10 min separados; horizonte 40 min.
- **Variantes:** `base` (producción: ramal y sentido por historial + geometría); `solo sentido conocido` (shapes restringidos al sentido del recorrido ex post); `oráculo ramal` (shapes restringidos al recorrido ex post del viaje en curso, de `segment_vehicles` geo2 + `geometry_for_trip` geo3; si el coche no tiene viaje ex post queda sin restricción). Mismo modelo y presentación en las tres.
- **Salvedades:** los huecos de GPS impiden interpolar algunos cruces, así que falsas alarmas y omisiones están algo sobrestimadas (en las tres variantes por igual). La omisión no cuenta los coches sin ping vigente en t (aparte en los datos). Con el oráculo casi todo lo que queda en «puede venir» son coches sin viaje ex post: su tasa de falsas alarmas (~96 %) no es comparable con la de base. En la línea 151, tramo exclusivo, el MAE de la banda (225 → 862 s) viene de muy pocos instantes; no se interpreta.
## Conclusión

1. **Techo:** conocer el ramal mejora el MAE del próximo coche en la banda 3–7 min de 107 a 94 s (−12 %), baja las falsas alarmas de 24,0 % a 17,4 % y el «sin ningún viene con coche en ≤10 min» de 13,7 % a 7,9 %; la omisión no cambia (17,0 %). Conocer solo el sentido no aporta (−3 s, −0,5 pp): con 2.1 el sentido ya sale bien.
2. **Dónde (tronco vs exclusivo):** la ganancia está en las paradas de tramo exclusivo (MAE 113 → 82 s, falsas alarmas 45,6 % → 24,4 %, viene vacío 30,5 % → 7,5 %); en tronco compartido casi no hay (124 → 112 s, falsas alarmas 16,0 % → 15,1 %, viene vacío 11,0 % → 9,6 %).
3. **Líneas:** la 39 gana en confiabilidad más que en precisión (MAE 86 → 82 s; falsas alarmas 30,4 % → 11,3 %; viene vacío 24,6 % → 5,0 %, en su tramo exclusivo 42,1 % → 5,3 %). Mejoran claramente 42 (MAE 164 → 103 s), 106 (115 → 80), 132 (117 → 75, falsas alarmas 25,4 % → 7,1 %) y 168 (117 → 97). No mejoran 26, 92, 108, 124 (un solo recorrido por sentido) ni 107, 151, 50 en el MAE.
4. **¿Justifica integrar el ramal de CuandoSubo?** Sí, pero acotado: el valor es sacar de la lista los coches de otro ramal (falsas alarmas y «viene» vacío), no afinar la ETA; el techo es éste y supone un ramal siempre correcto, así que cualquier error de CuandoSubo lo reduce.
5. **Prioridad:** empezar por 39, 42, 106, 132 y 168, y verificar primero qué tan correcto es el ramal de CuandoSubo en cada una; en las líneas sin ramales no hay nada que ganar.


## Tablas

Días: 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18, 2026-09-19, 2026-09-20, 2026-10-03, 2026-10-04, 2026-10-06, 2026-10-08. Líneas: 26, 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168. Criterio «seguro»: primer coche del grupo pasa seguro (solo instantes en que hay); «seguro-o-fallback»: primero de pasa seguro y, si no hay, primero de pueden venir/provisional. «Antes»: el coche llega >60 s antes de lo anunciado; «después»: >60 s después.

#### Global

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 465560 | 3943505 | 90.0 | 106 (n=128563) | 19.2 / 21.8 | 107 | 19.5 / 22.2 | 119 (n=419184) | 7.5 | 24.0 (14.1 / 61.7 / 54.9) | 17.0 (n=755260) | 13.7 (n=353335) |
| solo sentido conocido | 465560 | 3846450 | 90.0 | 104 (n=128563) | 19.6 / 21.4 | 104 | 19.9 / 21.6 | 115 (n=419184) | 7.8 | 23.5 (14.1 / 62.6 / 51.8) | 17.2 (n=755260) | 13.6 (n=353335) |
| oráculo ramal | 465560 | 3321683 | 90.0 | 93 (n=128563) | 19.4 / 20.7 | 94 | 19.7 / 20.6 | 103 (n=419184) | 8.3 | 17.4 (16.4 / 96.1 / 48.6) | 17.0 (n=755260) | 7.9 (n=353335) |

#### Línea 39

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 41200 | 441835 | 97.5 | 83 (n=12973) | 13.6 / 23.0 | 86 | 14.8 / 22.7 | 104 (n=40166) | 2.7 | 30.4 (8.7 / 54.7 / 46.5) | 11.6 (n=78828) | 24.6 (n=35922) |
| solo sentido conocido | 41200 | 439619 | 97.5 | 82 (n=12973) | 13.6 / 22.9 | 83 | 14.7 / 22.6 | 97 (n=40166) | 2.8 | 30.1 (8.6 / 54.8 / 39.8) | 11.6 (n=78828) | 24.6 (n=35922) |
| oráculo ramal | 41200 | 308171 | 97.5 | 81 (n=12973) | 15.5 / 19.5 | 82 | 16.4 / 19.3 | 90 (n=40166) | 4.6 | 11.3 (10.2 / 92.9 / 55.5) | 13.6 (n=78828) | 5.0 (n=35922) |

#### Tronco compartido (todas las líneas)

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 207030 | 1641551 | 93.3 | 123 (n=57295) | 20.8 / 23.2 | 124 | 21.3 / 23.2 | 126 (n=193111) | 10.2 | 16.0 (13.8 / 48.1 / 55.0) | 21.5 (n=425407) | 11.0 (n=168613) |
| solo sentido conocido | 207030 | 1620146 | 93.3 | 122 (n=57295) | 21.1 / 22.8 | 123 | 21.7 / 22.7 | 124 (n=193111) | 10.5 | 15.7 (13.7 / 50.4 / 53.9) | 21.7 (n=425407) | 11.1 (n=168613) |
| oráculo ramal | 207030 | 1586029 | 93.3 | 111 (n=57295) | 21.5 / 22.4 | 112 | 22.0 / 22.2 | 114 (n=193111) | 10.8 | 15.1 (14.5 / 91.6 / 52.2) | 22.0 (n=425407) | 9.6 (n=168613) |

#### Tramo exclusivo (todas las líneas)

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 122570 | 1218628 | 81.6 | 118 (n=30265) | 18.3 / 21.9 | 113 | 18.5 / 23.3 | 139 (n=100071) | 5.5 | 45.6 (14.8 / 64.1 / 70.3) | 13.1 (n=137931) | 30.5 (n=78899) |
| solo sentido conocido | 122570 | 1192392 | 81.6 | 110 (n=30265) | 19.0 / 21.5 | 105 | 19.1 / 22.4 | 130 (n=100071) | 5.8 | 44.7 (14.2 / 63.8 / 64.7) | 13.3 (n=137931) | 30.0 (n=78899) |
| oráculo ramal | 122570 | 701742 | 81.6 | 81 (n=30265) | 17.4 / 19.1 | 82 | 17.7 / 19.1 | 96 (n=100071) | 7.4 | 24.4 (22.2 / 96.2 / 57.5) | 11.3 (n=137931) | 7.5 (n=78899) |

#### Línea 39, tronco compartido

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 20600 | 228036 | 98.2 | 92 (n=6329) | 13.9 / 24.6 | 97 | 15.4 / 23.6 | 88 (n=20227) | 4.1 | 13.5 (8.8 / 39.8 / 36.1) | 14.1 (n=54302) | 9.4 (n=19261) |
| solo sentido conocido | 20600 | 226938 | 98.2 | 90 (n=6329) | 13.9 / 24.4 | 93 | 15.3 / 23.5 | 82 (n=20227) | 4.3 | 13.2 (8.6 / 40.2 / 32.0) | 14.1 (n=54302) | 9.5 (n=19261) |
| oráculo ramal | 20600 | 212410 | 98.2 | 93 (n=6329) | 14.7 / 23.3 | 94 | 15.7 / 23.1 | 84 (n=20227) | 5.0 | 9.2 (8.5 / 85.0 / 37.7) | 15.1 (n=54302) | 4.8 (n=19261) |

#### Línea 39, tramo exclusivo

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 20600 | 213799 | 96.8 | 68 (n=6644) | 13.1 / 20.4 | 77 | 14.2 / 21.9 | 120 (n=19939) | 1.3 | 47.8 (8.5 / 57.3 / 60.5) | 6.0 (n=24526) | 42.1 (n=16661) |
| solo sentido conocido | 20600 | 212681 | 96.8 | 68 (n=6644) | 13.1 / 20.4 | 73 | 14.1 / 21.8 | 113 (n=19939) | 1.4 | 47.6 (8.5 / 57.2 / 52.1) | 6.0 (n=24526) | 42.1 (n=16661) |
| oráculo ramal | 20600 | 95761 | 96.8 | 70 (n=6644) | 16.3 / 15.8 | 71 | 17.0 / 15.7 | 96 (n=19939) | 4.1 | 13.9 (12.2 / 93.7 / 79.5) | 10.3 (n=24526) | 5.3 (n=16661) |

#### Líneas con un solo recorrido por sentido (paradas «únicas»)

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 135960 | 1083326 | 92.7 | 78 (n=41003) | 17.6 / 19.9 | 80 | 17.8 / 20.0 | 93 (n=126002) | 5.4 | 15.6 (14.2 / 45.7 / 39.4) | 10.0 (n=191922) | 5.5 (n=105823) |
| solo sentido conocido | 135960 | 1033912 | 92.7 | 78 (n=41003) | 18.0 / 19.5 | 79 | 18.2 / 19.6 | 91 (n=126002) | 5.5 | 15.2 (14.7 / 100.0 / 37.9) | 10.2 (n=191922) | 5.5 (n=105823) |
| oráculo ramal | 135960 | 1033912 | 92.7 | 78 (n=41003) | 18.0 / 19.5 | 79 | 18.2 / 19.6 | 91 (n=126002) | 5.5 | 15.2 (14.7 / 100.0 / 37.9) | 10.2 (n=191922) | 5.5 (n=105823) |

#### Por línea: base → oráculo ramal

| línea | n (parada,t) | MAE 3–7 min base → ramal (s) | falsas alarmas % | omisión % | seguro vacío % | MAE 3–7 min en tronco compartido | en exclusivo |
|---|---|---|---|---|---|---|---|
| 26 | 12360 | 81 → 80 | 7.2 → 7.0 | 16.8 → 16.8 | 10.2 → 10.3 | — → — | — → — |
| 39 | 41200 | 86 → 82 | 30.4 → 11.3 | 11.6 → 13.6 | 24.6 → 5.0 | 97 → 94 | 77 → 71 |
| 42 | 41200 | 164 → 103 | 39.9 → 36.2 | 16.4 → 18.5 | 18.9 → 10.3 | 166 → 104 | 115 → 87 |
| 50 | 41200 | 89 → 90 | 32.0 → 20.6 | 16.4 → 18.4 | 20.0 → 9.3 | 106 → 105 | 72 → 75 |
| 92 | 41200 | 82 → 83 | 15.0 → 14.4 | 9.1 → 9.4 | 4.1 → 3.6 | — → — | — → — |
| 106 | 41200 | 115 → 80 | 18.0 → 11.8 | 16.6 → 13.3 | 7.3 → 2.5 | 103 → 92 | 120 → 74 |
| 107 | 41200 | 203 → 205 | 17.9 → 17.1 | 32.8 → 33.0 | 18.0 → 17.5 | 210 → 211 | 101 → 80 |
| 108 | 41200 | 81 → 81 | 24.1 → 23.6 | 10.9 → 11.3 | 5.9 → 6.2 | — → — | — → — |
| 124 | 41200 | 77 → 75 | 10.0 → 9.9 | 7.3 → 7.4 | 5.3 → 5.3 | — → — | — → — |
| 132 | 41200 | 117 → 75 | 25.4 → 7.1 | 23.5 → 22.7 | 22.4 → 10.8 | 83 → 80 | 166 → 68 |
| 151 | 41200 | 91 → 104 | 12.7 → 10.9 | 22.1 → 22.6 | 13.3 → 11.8 | 87 → 87 | 225 → 862 |
| 168 | 41200 | 117 → 97 | 40.5 → 31.8 | 17.2 → 17.1 | 13.2 → 6.7 | 99 → 99 | 142 → 95 |
