# Filtro de ramal CuandoSubo (parche de producción): medición con la vara corregida

Medido el 2026-11-16 (tablas recalculadas ese mismo día con la verdad de `VARA_CORREGIDA.md`: recorridos que sirven la parada solo por su lista y cruce contado solo si el recorrido ex post del coche tiene la parada; ver los registros al final). El parche está en `proyectoconsola` (no se tocó): `public/config/ramal_cuandosubo.json` (terna estable `longName|shortName|description` → `shape_ids`, 34 pares, 12 líneas), `lib/vehicles.js` (`csRamalOf`: route_id del feed CABA → `ROUTE_AGENCY_MAP` → terna) y `public/prediccion/core.js` (`ramalCsShapes`: intersección de los shapes de la terna con los compatibles del coche por geometría; sin dato, terna fuera de la tabla o intersección vacía = sin restricción). Es solo de producción (decisión del usuario): NO es regla del pipeline; acá se replica únicamente como variante de medición `cs` del replay (`core._allowed`, `run.build_cs_rid`).

## Método

- **Variantes** (misma vara corregida de `VARA_CORREGIDA.md`, modelo `data/ml/export/path_v3_l1_s1`, regla de sentido vigente, 40 paradas por línea, instantes cada 10 min de 6 a 23 h): `base` (producción sin el parche), `cs` (el coche se restringe a lo que informa CuandoSubo, con el route_id del ping vigente del grabador) y `ramal` (oráculo: recorrido ex post del viaje).
- **Días: solo donde existe una copia de `ROUTE_AGENCY_MAP` vigente.** Los route_id de CuandoSubo rotan cada ~3 semanas (`mapping_cuandosubo_osm/INFORME.md` §7). Copias fechadas: 2026-02-07, 2026-03-28, 2026-08-03 (= commit 75cd601 del 2026-08-02) y 2026-11-13 (vigente; el commit anterior del 2026-05-31 no se pudo recuperar del repo de VMagente). Se midió, por día, qué fracción de los pings de las 12 líneas resuelve con cada copia a una ruta de la línea correcta: la copia del 2026-08-02 resuelve el 2026-08-05 (74,5 %) pero ya no el 25-ago (11 %) ni el 15-sep (5 %); **la copia del 2026-11-13 resuelve desde el 2026-09-23 (69 %) hasta el 2026-11-14, y no resuelve el 15 al 22-sep (3,5–4,1 %)**. **Los días 15–20 de septiembre del replay no tienen copia vigente: no se pueden medir.** Se midieron 6 días con la copia del 2026-11-13: 23, 24, 25, 26 sep., 2 y 3 oct. (los otros días con copia vigente, 4, 6, 8 oct. y 7, 9, 10 oct., no se corrieron por tiempo de cómputo: cada día de 3 variantes tarda ~3 h de CPU). La línea 26 no tiene datos esos días.
- **Reproducción del dato histórico:** el grabador guarda `route_id` por ping (obs[10]); en cada t el coche usa el `route_id` de su último ping (como la app usa el `route_id` del feed actual) → terna por `csRamalOf` (espacios colapsados) → `shape_ids` de la tabla → intersección con los shapes compatibles del coche en esa posición.
- **Acierto del ramal informado:** contra el viaje ex post (segmentador geo2 + `geometry_for_trip` geo3: el recorrido del viaje en curso, o del próximo si está en espera ≤ 20 min). «Correcto» = el recorrido real ∈ shapes de la terna (ramal y sentido); «restricción correcta» = el recorrido real ∈ la intersección aplicada.
- Tablas generadas: `data/ml/replay/vara/tablas_cs.md`; crudos `data/ml/replay/vara/run_cs_xp/` (las predicciones de `run_cs/` con la verdad corregida recalculada desde los pings crudos y los viajes ex post, `vara/recalcula_verdad.py`; antes / después: `vara/antes_despues.md`; incluye `*.cs.parquet`: un registro por (t, coche) con lo que informa CuandoSubo).

## Resultados

Días: 2026-09-23, 2026-09-24, 2026-09-25, 2026-09-26, 2026-10-02, 2026-10-03. Líneas: 39, 42, 50, 92, 106, 107, 108, 124, 132, 151, 168.

### Global

| métrica (vara corregida) | base | cs (filtro CuandoSubo) | oráculo de ramal |
|---|---|---|---|
| Falsas alarmas %, todo ETA anunciado | 18.2 | 11.9 | 8.3 |
| Falsas alarmas %, ETA anunciado 3–7 min | 14.0 | 8.8 | 4.8 |
|   «viene» % | 7.2 | 8.4 | 7.3 |
|   «puede venir» % | 57.1 | 60.7 | 87.0 |
|   «sentido sin confirmar» % | 55.1 | 44.2 | 35.0 |
| Omisión ≤10 min % | 10.2 | 10.1 | 9.4 |
| «Viene» vacío % | 10.0 | 4.4 | 2.9 |
| MAE próximo coche 3–7 min (s) | 107 | 94 | 87 |
| Llega antes >60 s % (3–7) | 14.4 | 15.3 | 15.1 |
| Llega después >60 s % (3–7) | 28.8 | 26.8 | 26.1 |
| Sin anuncio % (3–7) | 2.6 | 3.0 | 3.0 |
| MAE solo «viene» 3–7 (s) | 105 | 87 | 85 |
| Coches listados | 1036576 | 1009526 | 994055 |

### Por línea

| línea | n banda | FA % base → cs → oráculo | omisión % | «viene» vacío % | MAE 3–7 (s) | llega antes % | llega después % |
|---|---|---|---|---|---|---|---|
| 39 | 6660 | 30.4 → 13.5 → 5.7 | 7.4 → 8.5 → 6.9 | 22.4 → 2.3 → 1.7 | 103 → 94 → 91 | 10.4 → 13.9 → 12.6 | 34.8 → 25.8 → 27.6 |
| 42 | 5716 | 32.2 → 29.3 → 22.8 | 9.2 → 10.3 → 11.3 | 12.4 → 8.7 → 4.9 | 224 → 132 → 102 | 17.6 → 18.2 → 19.0 | 34.5 → 33.9 → 30.1 |
| 50 | 5640 | 25.9 → 17.2 → 11.4 | 7.1 → 9.5 → 6.8 | 12.9 → 5.6 → 1.5 | 80 → 98 → 75 | 16.1 → 18.6 → 17.3 | 24.1 → 21.5 → 20.6 |
| 92 | 6511 | 8.3 → 7.5 → 7.2 | 5.1 → 5.2 → 5.3 | 3.0 → 2.7 → 2.7 | 76 → 76 → 76 | 13.1 → 13.4 → 14.4 | 23.7 → 23.2 → 22.5 |
| 106 | 6051 | 13.5 → 13.6 → 5.6 | 17.0 → 13.6 → 11.1 | 5.1 → 3.8 → 1.2 | 163 → 111 → 98 | 14.2 → 10.8 → 9.5 | 33.5 → 34.0 → 32.7 |
| 107 | 5894 | 9.7 → 6.2 → 4.9 | 10.0 → 9.9 → 9.9 | 12.5 → 7.3 → 6.8 | 94 → 92 → 92 | 20.4 → 22.6 → 23.1 | 23.7 → 20.7 → 20.2 |
| 108 | 6130 | 12.8 → 12.7 → 11.7 | 6.2 → 6.6 → 6.3 | 3.9 → 3.8 → 4.3 | 77 → 77 → 75 | 14.5 → 14.7 → 14.7 | 23.5 → 23.4 → 22.9 |
| 124 | 7572 | 6.3 → 6.3 → 6.1 | 4.9 → 4.9 → 4.9 | 2.8 → 2.8 → 2.5 | 85 → 85 → 85 | 13.6 → 13.6 → 13.6 | 26.7 → 26.7 → 26.5 |
| 132 | 5966 | 20.8 → 6.4 → 3.3 | 13.7 → 13.9 → 12.8 | 14.9 → 2.4 → 1.8 | 100 → 90 → 85 | 11.0 → 14.5 → 13.7 | 35.5 → 30.2 → 30.1 |
| 151 | 6167 | 8.5 → 8.5 → 5.1 | 13.1 → 13.1 → 13.5 | 7.6 → 7.6 → 3.4 | 91 → 91 → 90 | 12.4 → 12.4 → 13.3 | 33.1 → 33.1 → 31.8 |
| 168 | 5314 | 28.7 → 9.3 → 8.9 | 7.7 → 7.8 → 7.5 | 13.2 → 2.9 → 2.8 | 96 → 90 → 86 | 16.4 → 16.9 → 16.6 | 23.3 → 21.1 → 21.1 |

### Diferencia cs − base por día

| día | Δ falsas alarmas (pp) | Δ omisión (pp) | Δ «viene» vacío (pp) | Δ MAE 3–7 (s) | Δ llega antes (pp) | Δ llega después (pp) |
|---|---|---|---|---|---|---|
| 2026-09-23 | -6.3 | -0.0 | -5.4 | -14.5 | +1.0 | -1.9 |
| 2026-09-24 | -6.1 | -0.2 | -5.3 | -15.2 | +0.7 | -1.9 |
| 2026-09-25 | -5.7 | -0.1 | -5.1 | -15.0 | +0.9 | -2.3 |
| 2026-09-26 | -6.4 | -0.2 | -6.0 | -6.7 | +0.5 | -1.8 |
| 2026-10-02 | -6.2 | -0.1 | -5.6 | -18.3 | +1.1 | -2.6 |
| 2026-10-03 | -7.0 | -0.1 | -6.0 | -9.1 | +0.8 | -1.9 |
| **media (rango)** | -6.3 (-7.0…-5.7) | -0.1 (-0.2…-0.0) | -5.6 (-6.0…-5.1) | -13.1 (-18.3…-6.7) | +0.8 (+0.5…+1.1) | -2.1 (-2.6…-1.8) |
| días con Δ < 0 | 6 | 6 | 6 | 6 | 0 | 6 |

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

### Efecto de los errores (omisiones ≤ 10 min, 426 062 coches visibles que pasan)

| concepto | n | % |
|---|---|---|
| omisiones base → cs | 43 670 → 43 232 | 10,2 → 10,1 % |
| omisiones nuevas con cs (listado en base, no en cs) | 3 446 | 0,8 % de los pasos |
| omisiones arregladas con cs (no listado en base, sí en cs) | 3 884 | 0,9 % |
| de las nuevas: filtro aplicado con ramal informado EQUIVOCADO (el recorrido real quedó fuera de la restricción) | 2 486 | 72,1 % |
| de las nuevas: filtro aplicado y correcto | 333 | 9,7 % |
| de las nuevas: sin filtro (la omisión viene de otra causa) | 627 | 18,2 % |

Falsas alarmas corregidas: 179 996 de 989 533 evaluados en base (18,2 %) → 112 351 de 944 064 en cs (11,9 %); de las de cs, 15 356 (13,7 %) son coches a los que el parche les restringió un ramal equivocado.

Omisión por recorrido real del coche: la verdad ya cuenta solo los pasos de coches cuyo recorrido ex post tiene la parada en su lista (`VARA_CORREGIDA.md`, punto 7); los pasos de coches de recorridos sin la parada (4,1 % de los cruces, 20 693 de 502 499) no son paso ni omisión. Un filtro correcto que deja un solo recorrido sin la parada ya no genera omisión.

## Lectura

1. **Qué informa CuandoSubo:** el route_id resuelve a una ruta (ramal informado) en 75,3 % de los (t, coche); está en la tabla de 34 pares en 60,4 %; el filtro se aplica (intersección no vacía) en 56,6 %. Dos líneas no reciben el parche: 124 (el feed CABA no trae route_id en esos días: 0 %) y 151 (sus route_id resuelven a rutas de la línea 65 en `ROUTE_AGENCY_MAP`, `JCCABA065|65A|...`, que no están en la tabla: 41,6 % «informado», 0 % aplicado); por eso base = cs en 124 y 151. Las líneas con más cobertura: 108 (84 % aplicado), 132 (83 %), 168 (80 %), 106 (80 %), 39 (74 %), 50 (70 %).
2. **Acierto del ramal:** 88,6 % de los coches con viaje ex post y en la tabla tienen el recorrido real entre los shapes de su terna; la restricción aplicada contiene el recorrido real en 91,3 % (8,7 % la excluye; 11,1 % en los casos ambiguos, 0,6 % si hay un solo shape compatible). Por línea, la restricción excluye el recorrido real en: 42 57,4 % (CuandoSubo da el ramal equivocado más de la mitad de las veces), 50 18,0 %, 132 11,8 %, 168 5,4 %, 39 4,3 %, 106 3,9 %, 92 3,0 %, 107 2,5 %, 108 2,1 %.
3. **Efecto sobre la vara corregida** (6 días, mismas paradas e instantes, diferencia pareada día por día): falsas alarmas 18,2 → 11,9 % (−6,3 pp, los 6 días), «viene» vacío 10,0 → 4,4 % (−5,6 pp, los 6 días), MAE 3–7 min 107 → 94 s (−13,1 s, los 6 días), llega después 28,8 → 26,8 % (−2,1 pp), **llega antes 14,4 → 15,3 % (+0,8 pp, los 6 días en contra)**, omisión 10,2 → 10,1 % (−0,1 pp: sin cambio).
4. **Contra el oráculo de ramal** (falsas alarmas 8,3 %, «viene» vacío 2,9 %, MAE 87 s, llega antes 15,1 %, omisión 9,4 %): el parche recupera el 64 % de la baja de falsas alarmas (18,2 → 11,9 de 18,2 → 8,3), el 79 % de la del «viene» vacío (10,0 → 4,4 de 10,0 → 2,9) y el 65 % de la del MAE (107 → 94 de 107 → 87). El llega antes del oráculo también sube (15,1 %): es parte de saber el ramal.
5. **Por línea:** el parche ayuda mucho en 39 (falsas alarmas 30,4 → 13,5; «viene» vacío 22,4 → 2,3; MAE 103 → 94 s), 168 (28,7 → 9,3; 13,2 → 2,9), 132 (20,8 → 6,4; 14,9 → 2,4; MAE 100 → 90 s), 106 (MAE 163 → 111 s), 42 (MAE 224 → 132 s, falsas alarmas 32,2 → 29,3 %, aunque acierta el ramal solo 43 %) y 50 en falsas alarmas (25,9 → 17,2). Empeora el MAE en 50 (80 → 98 s; restricción incorrecta 18 %). Sube el llega antes en 39 (10,4 → 13,9 %), 132 (11,0 → 14,5 %) y 107 (20,4 → 22,6 %): al ocultar el «puede venir» sobre ramal vecino entra al banco de instantes 3–7 min un próximo coche que antes no se anunciaba y que llega antes. 92, 108, 124 y 151 no cambian (un recorrido por sentido o sin dato).
6. **Resumen:** el parche baja las falsas alarmas y el «viene» vacío con un acierto de ramal alto (≥ 94 %) en 6 de las 11 líneas, y baja el MAE; sube el llega antes ~0,8 pp (error grave, aunque contenido). La omisión no cambia. En la 42 el dato de CuandoSubo es poco confiable (restricción equivocada 57 %); en la 50 y la 132 deja ~12–18 % de restricciones equivocadas; el 72 % de las omisiones nuevas con cs son de esas restricciones equivocadas.

## Salvedades

- 6 días con copia vigente de `ROUTE_AGENCY_MAP` (23–26 sep., 2 y 3 oct.); septiembre 15–20 no se puede medir. Si el route_id de un coche cambiara dentro del día (rotación en vivo), el replay usa el del último ping, como la app; la rotación entre 2026-09-22 y 2026-09-23 no afecta los días medidos (la copia vigente resuelve 69 % desde el 23-sep.).
- El acierto se compara con el viaje ex post (segmentador), que en terminales y calles compartidas puede ser ambiguo; los porcentajes de acierto son del orden de la precisión de ese viaje.
- Las líneas 124 (sin route_id en el feed) y 151 (route_id de la 65) y la 26 (sin datos) no aportan al efecto del parche.

## Registro de error (2026-11-16): asociación parada↔recorrido por geometría

La primera versión de estas tablas usaba la vara corregida con asociación por geometría (shapes del mismo sentido a ≤ 45 m de la parada contaban como servicio de la parada; `VARA_CORREGIDA.md`, registro). Era incorrecto: el recorrido que no tiene la parada en su lista no para ahí. Contaba como pasos reales (y como omisiones de la base, de cs y del oráculo) a coches que pasan por la calle sin parar, e interpretaba el 6,7 % de pasos de recorridos sin la parada en su lista como «dato incompleto de `ramales[].stops`» (omisión 9,3 / 9,1 / 8,0 % «con el recorrido real asociado por nombre»; 49,4 / 83,0 / 100 % «no asociado»). Cifras anteriores, base / cs / oráculo: falsas alarmas 15,5 / 11,0 / 8,2 %; 3–7 min 10,6 / 7,8 / 4,7 %; omisión 12,0 / 14,2 / 14,2 %; «viene» vacío 11,6 / 5,7 / 3,9 %; MAE 110 / 103 / 97 s; llega antes 15,8 / 17,1 / 17,1 %; llega después 27,9 / 26,4 / 25,7 %. Las diferencias cs − base no cambian de signo (falsas alarmas −4,4 → −4,7 pp, omisión +2,2 → +1,9 pp, MAE −5,9 → −9,2 s, llega antes +1,3 → +1,2 pp). Cambia lo que se dijo de la línea 132 (MAE 104 → 138 s con el parche: ahora 104 → 100 s).

## Registro de cambio (2026-11-16): verdad por recorrido ex post del coche

La verdad contaba como paso a coches cuyo recorrido no tiene la parada en su lista si iban compatibles con un shape que sí la sirve (tronco compartido): 4,1 % de los cruces. Se interpretaba como omisión de la base (35,7 %), de cs (85,0 %) y del oráculo (96,0 %), y movía la omisión del parche (+1,9 pp). Desde ahora un cruce cuenta solo si el recorrido ex post del coche tiene la parada (`VARA_CORREGIDA.md`, registro). 6 días, 11 líneas; base / cs / oráculo, anterior → vigente:

| métrica | base | cs | oráculo |
|---|---|---|---|
| falsas alarmas % (todo ETA) | 16,0 → 18,2 | 11,3 → 11,9 | 8,2 → 8,3 |
| falsas alarmas % (3–7 min) | 11,2 → 14,0 | 8,1 → 8,8 | 4,7 → 4,8 |
| omisión ≤ 10 min % | 11,4 → 10,2 | 13,3 → 10,1 | 13,0 → 9,4 |
| «viene» vacío % | 11,2 → 10,0 | 5,4 → 4,4 | 3,7 → 2,9 |
| MAE 3–7 min (s) | 110 → 107 | 100 → 94 | 94 → 87 |
| llega antes / después >60 s % | 15,7 / 28,0 → 14,4 / 28,8 | 16,9 / 26,5 → 15,3 / 26,8 | 16,8 / 25,8 → 15,1 / 26,1 |
| coches que pasan en ≤ 10 min con ping vigente | 444 997 → 426 062 | idem | idem |

Diferencias cs − base (anterior → vigente): falsas alarmas −4,7 → −6,3 pp, omisión +1,9 → −0,1 pp, «viene» vacío −5,9 → −5,6 pp, MAE −9,2 → −13,1 s, llega antes +1,2 → +0,8 pp, llega después −1,4 → −2,1 pp. Cambia la lectura de la omisión: el aumento de omisión con cs era el contar como pasos a coches que no paran ahí; ya no existe. Se retira la tabla «omisión por recorrido real» y `vara/omision_por_recorrido.py` queda como medición histórica (`vara/omision_por_recorrido.txt`).
