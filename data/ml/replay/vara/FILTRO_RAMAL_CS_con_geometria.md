# Filtro de ramal CuandoSubo (parche de producción): medición con la vara corregida

Medido el 2026-11-16. El parche está en `proyectoconsola` (no se tocó): `public/config/ramal_cuandosubo.json` (terna estable `longName|shortName|description` → `shape_ids`, 34 pares, 12 líneas), `lib/vehicles.js` (`csRamalOf`: route_id del feed CABA → `ROUTE_AGENCY_MAP` → terna) y `public/prediccion/core.js` (`ramalCsShapes`: intersección de los shapes de la terna con los compatibles del coche por geometría; sin dato, terna fuera de la tabla o intersección vacía = sin restricción). Es solo de producción (decisión del usuario): NO es regla del pipeline; acá se replica únicamente como variante de medición `cs` del replay (`core._allowed`, `run.build_cs_rid`).

## Método

- **Variantes** (misma vara corregida de `VARA_CORREGIDA.md`, modelo `data/ml/export/path_v3_l1_s1`, regla de sentido vigente, 40 paradas por línea, instantes cada 10 min de 6 a 23 h): `base` (producción sin el parche), `cs` (el coche se restringe a lo que informa CuandoSubo, con el route_id del ping vigente del grabador) y `ramal` (oráculo: recorrido ex post del viaje).
- **Días: solo donde existe una copia de `ROUTE_AGENCY_MAP` vigente.** Los route_id de CuandoSubo rotan cada ~3 semanas (`mapping_cuandosubo_osm/INFORME.md` §7). Copias fechadas: 2026-02-07, 2026-03-28, 2026-08-03 (= commit 75cd601 del 2026-08-02) y 2026-11-13 (vigente; el commit anterior del 2026-05-31 no se pudo recuperar del repo de VMagente). Se midió, por día, qué fracción de los pings de las 12 líneas resuelve con cada copia a una ruta de la línea correcta: la copia del 2026-08-02 resuelve el 2026-08-05 (74,5 %) pero ya no el 25-ago (11 %) ni el 15-sep (5 %); **la copia del 2026-11-13 resuelve desde el 2026-09-23 (69 %) hasta el 2026-11-14, y no resuelve el 15 al 22-sep (3,5–4,1 %)**. **Los días 15–20 de septiembre del replay no tienen copia vigente: no se pueden medir.** Se midieron 6 días con la copia del 2026-11-13: 23, 24, 25, 26 sep., 2 y 3 oct. (los otros días con copia vigente, 4, 6, 8 oct. y 7, 9, 10 oct., no se corrieron por tiempo de cómputo: cada día de 3 variantes tarda ~3 h de CPU). La línea 26 no tiene datos esos días.
- **Reproducción del dato histórico:** el grabador guarda `route_id` por ping (obs[10]); en cada t el coche usa el `route_id` de su último ping (como la app usa el `route_id` del feed actual) → terna por `csRamalOf` (espacios colapsados) → `shape_ids` de la tabla → intersección con los shapes compatibles del coche en esa posición.
- **Acierto del ramal informado:** contra el viaje ex post (segmentador geo2 + `geometry_for_trip` geo3: el recorrido del viaje en curso, o del próximo si está en espera ≤ 20 min). «Correcto» = el recorrido real ∈ shapes de la terna (ramal y sentido); «restricción correcta» = el recorrido real ∈ la intersección aplicada.
- Tablas generadas: `data/ml/replay/vara/tablas_cs.md`; crudos `data/ml/replay/vara/run_cs/` (incluye `*.cs.parquet`: un registro por (t, coche) con lo que informa CuandoSubo).

## Resultados

Días: 2026-09-23, 2026-09-24, 2026-09-25, 2026-09-26, 2026-10-02, 2026-10-03. Líneas: 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168.

### Global

| métrica (vara corregida) | base | cs (filtro CuandoSubo) | oráculo de ramal |
|---|---|---|---|
| Falsas alarmas %, todo ETA anunciado | 15.5 | 11.0 | 8.2 |
| Falsas alarmas %, ETA anunciado 3–7 min | 10.6 | 7.8 | 4.7 |
|   «viene» % | 7.1 | 8.1 | 7.2 |
|   «puede venir» % | 44.8 | 50.7 | 83.3 |
|   «sentido sin confirmar» % | 46.8 | 39.7 | 34.5 |
| Omisión ≤10 min % | 12.0 | 14.2 | 14.2 |
| «Viene» vacío % | 11.6 | 5.7 | 3.9 |
| MAE próximo coche 3–7 min (s) | 110 | 103 | 97 |
| Llega antes >60 s % (3–7) | 15.8 | 17.1 | 17.1 |
| Llega después >60 s % (3–7) | 27.9 | 26.4 | 25.7 |
| Sin anuncio % (3–7) | 2.9 | 3.8 | 4.0 |
| MAE solo «viene» 3–7 (s) | 107 | 92 | 94 |
| Coches listados | 1036576 | 1009526 | 994055 |

### Por línea

| línea | n banda | FA % base → cs → oráculo | omisión % | «viene» vacío % | MAE 3–7 (s) | llega antes % | llega después % |
|---|---|---|---|---|---|---|---|
| 39 | 6583 | 23.8 → 11.4 → 5.5 | 10.2 → 16.8 → 16.7 | 24.1 → 3.0 → 2.3 | 104 → 111 → 108 | 12.7 → 18.9 → 17.5 | 31.9 → 25.3 → 27.0 |
| 42 | 5805 | 30.9 → 27.9 → 22.7 | 9.6 → 10.7 → 13.6 | 13.5 → 9.7 → 5.1 | 228 → 133 → 111 | 17.9 → 18.4 → 20.2 | 34.4 → 33.8 → 29.9 |
| 50 | 5737 | 23.2 → 16.0 → 11.3 | 7.9 → 12.6 → 10.9 | 14.3 → 6.8 → 2.0 | 79 → 100 → 86 | 16.4 → 19.1 → 19.1 | 23.0 → 21.1 → 20.3 |
| 92 | 6516 | 8.3 → 7.4 → 7.2 | 5.1 → 5.2 → 5.4 | 3.0 → 2.8 → 2.7 | 76 → 76 → 76 | 13.2 → 13.5 → 14.6 | 23.7 → 23.2 → 22.5 |
| 106 | 6045 | 13.1 → 13.2 → 5.4 | 18.6 → 15.2 → 13.0 | 5.1 → 3.8 → 1.2 | 167 → 115 → 101 | 14.7 → 11.2 → 10.0 | 33.6 → 34.1 → 32.6 |
| 107 | 6354 | 6.0 → 5.5 → 4.9 | 15.2 → 20.6 → 22.0 | 19.1 → 13.9 → 13.3 | 104 → 106 → 105 | 27.1 → 27.5 → 27.2 | 20.7 → 19.6 → 19.5 |
| 108 | 6152 | 12.6 → 12.5 → 11.6 | 7.0 → 7.5 → 7.1 | 4.0 → 3.9 → 4.4 | 79 → 79 → 77 | 14.8 → 15.1 → 15.0 | 23.5 → 23.3 → 22.8 |
| 124 | 7587 | 6.3 → 6.3 → 6.1 | 5.0 → 5.0 → 5.0 | 2.9 → 2.9 → 2.5 | 86 → 86 → 86 | 13.6 → 13.6 → 13.7 | 26.7 → 26.7 → 26.6 |
| 132 | 5875 | 12.6 → 5.1 → 3.2 | 17.4 → 23.0 → 22.6 | 17.7 → 4.8 → 3.6 | 104 → 138 → 116 | 13.9 → 20.7 → 20.0 | 33.3 → 28.7 → 28.7 |
| 151 | 6242 | 6.2 → 6.2 → 5.1 | 13.4 → 13.4 → 15.7 | 8.9 → 8.9 → 3.7 | 91 → 91 → 109 | 12.9 → 12.9 → 14.3 | 32.7 → 32.7 → 31.6 |
| 168 | 5387 | 24.6 → 9.0 → 8.9 | 9.1 → 12.8 → 12.7 | 15.0 → 2.9 → 2.9 | 98 → 110 → 103 | 17.6 → 19.5 → 19.4 | 22.5 → 20.5 → 20.4 |

### Diferencia cs − base por día

| día | Δ falsas alarmas (pp) | Δ omisión (pp) | Δ «viene» vacío (pp) | Δ MAE 3–7 (s) | Δ llega antes (pp) | Δ llega después (pp) |
|---|---|---|---|---|---|---|
| 2026-09-23 | -4.4 | +2.2 | -5.7 | -10.5 | +1.4 | -1.4 |
| 2026-09-24 | -4.6 | +1.8 | -5.5 | -10.5 | +1.1 | -1.3 |
| 2026-09-25 | -4.1 | +2.0 | -5.3 | -7.0 | +1.3 | -1.6 |
| 2026-09-26 | -4.4 | +2.2 | -6.6 | +1.9 | +1.3 | -1.2 |
| 2026-10-02 | -4.4 | +2.2 | -5.8 | -10.0 | +1.7 | -2.0 |
| 2026-10-03 | -4.8 | +2.6 | -6.7 | +0.4 | +1.2 | -1.4 |
| **media (rango)** | -4.4 (-4.8…-4.1) | +2.2 (+1.8…+2.6) | -5.9 (-6.7…-5.3) | -5.9 (-10.5…+1.9) | +1.3 (+1.1…+1.7) | -1.5 (-2.0…-1.2) |
| días con Δ < 0 | 6 | 0 | 6 | 4 | 0 | 6 |

### Qué informa CuandoSubo y cuánto acierta

| grupo | (t, coche) | ramal informado % | y en la tabla (34 pares) % | filtro aplicado % | n con viaje ex post y en tabla | ramal correcto % (recorrido real ∈ shapes de la terna) | n aplicado con viaje ex post | recorrido real ∈ restricción % | restricción que excluye el recorrido real % |
|---|---|---|---|---|---|---|---|---|---|
| todos | 290390 | 75.3 | 60.4 | 56.6 | 173119 | 88.6 | 163277 | 91.3 | 8.7 |
| ambiguos (≥2 shapes compatibles en la posición) | 200497 | 81.1 | 64.3 | 63.1 | 127940 | 87.5 | 125578 | 88.9 | 11.1 |
| no ambiguos (1 shape compatible) | 66917 | 72.4 | 60.8 | 56.7 | 40319 | 93.9 | 37699 | 99.4 | 0.6 |
| línea 39 | 31632 | 87.2 | 75.0 | 73.5 | 23472 | 95.2 | 23055 | 95.7 | 4.3 |
| línea 42 | 20276 | 73.8 | 36.4 | 34.2 | 7175 | 42.1 | 6908 | 42.6 | 57.4 |
| línea 50 | 21645 | 87.7 | 87.2 | 69.6 | 18512 | 68.9 | 14833 | 82.0 | 18.0 |
| línea 92 | 29640 | 84.1 | 55.5 | 53.4 | 16270 | 96.2 | 15767 | 97.0 | 3.0 |
| línea 106 | 42991 | 82.4 | 82.4 | 79.5 | 35214 | 93.5 | 34018 | 96.1 | 3.9 |
| línea 107 | 19332 | 89.7 | 42.5 | 37.3 | 8104 | 94.0 | 7176 | 97.5 | 2.5 |
| línea 108 | 17616 | 90.0 | 90.0 | 84.2 | 15391 | 96.4 | 14687 | 97.9 | 2.1 |
| línea 124 | 18469 | 0.0 | 0.0 | 0.0 | 0 | — | 0 | — | — |
| línea 132 | 32747 | 87.3 | 87.2 | 83.3 | 28235 | 87.2 | 27110 | 88.2 | 11.8 |
| línea 151 | 31372 | 41.6 | 0.0 | 0.0 | 0 | — | 0 | — | — |
| línea 168 | 24670 | 89.0 | 85.4 | 80.5 | 20746 | 94.3 | 19723 | 94.6 | 5.4 |

### Efecto de los errores (omisiones ≤ 10 min, 451 221 coches visibles que pasan)

| concepto | n | % |
|---|---|---|
| omisiones base → cs | 54 175 → 63 853 | 12,0 → 14,2 % |
| omisiones nuevas con cs (listado en base, no en cs) | 13 680 | 3,0 % de los pasos |
| omisiones arregladas con cs (no listado en base, sí en cs) | 4 002 | 0,9 % |
| de las nuevas: filtro aplicado con ramal informado EQUIVOCADO (el recorrido real quedó fuera de la restricción) | 2 645 | 19,3 % |
| de las nuevas: filtro aplicado y correcto | 10 221 | 74,7 % |
| de las nuevas: sin filtro (la omisión viene de otra causa) | 814 | 6,0 % |
| de las nuevas con filtro correcto: el recorrido real NO sirve esa parada por nombre (`ramales[].stops`) | 9 956 | 97,4 % |

Falsas alarmas corregidas: 153 078 de 990 511 evaluados en base (15,5 %) → 103 949 de 945 170 en cs (11,0 %); de las de cs, 13 401 (12,9 %) son coches a los que el parche les restringió un ramal equivocado.

Las omisiones nuevas con filtro correcto no son error de CuandoSubo: el filtro deja un solo recorrido (el verdadero) y ese recorrido no figura entre los que sirven la parada en `ramales[].stops`; la base lo listaba solo por casualidad, como candidato de un ramal vecino que sí sirve la parada. Restringiendo la comparación a los pasos cuyo recorrido real sirve la parada por nombre (93,3 % de los pasos), la omisión es **9,3 % base / 9,1 % cs / 8,0 % oráculo** (`data/ml/replay/vara/omision_por_nombre.txt`); con los que no lo sirven (6,7 %): 49,4 / 83,0 / 100 %. Por línea (omisión con recorrido real asociado: base / cs / oráculo): 39 6,9 / 8,0 / 6,3; 50 7,0 / 9,4 / 6,6; 106 17,2 / 13,7 / 11,3; 132 11,4 / 11,5 / 10,3; el resto sin cambio (± 0,2).

## Lectura

1. **Qué informa CuandoSubo:** el route_id resuelve a una ruta (ramal informado) en 75,3 % de los (t, coche); está en la tabla de 34 pares en 60,4 %; el filtro se aplica (intersección no vacía) en 56,6 %. Dos líneas no reciben el parche: 124 (el feed CABA no trae route_id en esos días: 0 %) y 151 (sus route_id resuelven a rutas de la línea 65 en `ROUTE_AGENCY_MAP`, `JCCABA065|65A|...`, que no están en la tabla: 41,6 % «informado», 0 % aplicado); por eso base = cs en 124 y 151. Las líneas con más cobertura: 108 (84 % aplicado), 132 (83 %), 168 (80 %), 106 (80 %), 39 (74 %), 50 (70 %).
2. **Acierto del ramal:** 88,6 % de los coches con viaje ex post y en la tabla tienen el recorrido real entre los shapes de su terna; la restricción aplicada contiene el recorrido real en 91,3 % (8,7 % la excluye; 11,1 % en los casos ambiguos, 0,6 % si hay un solo shape compatible). Por línea, la restricción excluye el recorrido real en: 42 57,4 % (CuandoSubo da el ramal equivocado más de la mitad de las veces), 50 18,0 %, 132 11,8 %, 168 5,4 %, 39 4,3 %, 106 3,9 %, 92 3,0 %, 107 2,5 %, 108 2,1 %.
3. **Efecto sobre la vara corregida** (6 días, mismas paradas e instantes, diferencia pareada día por día en la tabla de arriba): falsas alarmas 15,5 → 11,0 % (−4,4 pp, los 6 días), «viene» vacío 11,6 → 5,7 % (−5,9 pp, los 6 días), MAE 3–7 min 110 → 103 s (−5,9 s, 4 de 6 días; +0,4 a +1,9 s los otros dos), llega después 27,9 → 26,4 % (−1,5 pp), **llega antes 15,8 → 17,1 % (+1,3 pp, los 6 días en contra)**, omisión 12,0 → 14,2 % (+2,2 pp, los 6 días en contra; ver arriba: 3/4 es dato de paradas, 1/5 error de CuandoSubo).
4. **Contra el oráculo de ramal** (falsas alarmas 8,2 %, «viene» vacío 3,9 %, MAE 97 s, llega antes 17,1 %): el parche recupera el 62 % de la baja de falsas alarmas (15,5 → 11,0 de 15,5 → 8,2), el 77 % de la del «viene» vacío (11,6 → 5,7 de 11,6 → 3,9) y el 54 % de la del MAE (110 → 103 de 110 → 97). El oráculo también sube la omisión (14,2 %) y el llega antes (17,1 %): es parte de saber el ramal.
5. **Por línea:** el parche ayuda mucho en 39 (falsas alarmas 23,8 → 11,4; «viene» vacío 24,1 → 3,0), 168 (24,6 → 9,0; 15,0 → 2,9), 132 (12,6 → 5,1; 17,7 → 4,8), 106 (MAE 167 → 115 s), 42 (MAE 228 → 133 s, falsas alarmas 30,9 → 27,9 %, aunque acierta el ramal solo 43 %) y 50 en falsas alarmas (23,2 → 16,0). Empeora el MAE en 50 (79 → 100 s; restricción incorrecta 18 %), 132 (104 → 138 s), 168 (98 → 110 s) y 39 (104 → 111 s): al ocultar el «puede venir» sobre ramal vecino entra al banco de instantes 3–7 min un próximo coche que antes no se anunciaba y que llega antes (llega antes: 39 12,7 → 18,9 %; 132 13,9 → 20,7 %). 92, 108, 124 y 151 no cambian (un recorrido por sentido o sin dato).
6. **Resumen:** el parche baja las falsas alarmas y el «viene» vacío con un acierto de ramal alto (≥ 94 %) en 6 de las 11 líneas, pero sube el llega antes ~1,3 pp (error grave, aunque contenido) y la omisión ~2 pp (en gran parte un dato incompleto de `ramales[].stops`, no del filtro). En la 42 el dato de CuandoSubo es poco confiable (restricción equivocada 57 %); en la 50 y la 132 deja ~12–18 % de restricciones equivocadas.

## Salvedades

- 6 días con copia vigente de `ROUTE_AGENCY_MAP` (23–26 sep., 2 y 3 oct.); septiembre 15–20 no se puede medir. Si el route_id de un coche cambiara dentro del día (rotación en vivo), el replay usa el del último ping, como la app; la rotación entre 2026-09-22 y 2026-09-23 no afecta los días medidos (la copia vigente resuelve 69 % desde el 23-sep.).
- El acierto se compara con el viaje ex post (segmentador), que en terminales y calles compartidas puede ser ambiguo; los porcentajes de acierto son del orden de la precisión de ese viaje.
- Las líneas 124 (sin route_id en el feed) y 151 (route_id de la 65) y la 26 (sin datos) no aportan al efecto del parche.
