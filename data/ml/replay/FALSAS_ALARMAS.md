# Falsas alarmas del replay de producción: causas y techo de recuperación

> **Registro (2026-11-16):** las falsas alarmas, la omisión y el «viene» vacío de este informe usan la definición anterior de la vara de producto. Siguen válidos como comparaciones relativas; las falsas alarmas absolutas están infladas (≈ 24,5 contra ≈ 14,7 % con la vara corregida) y la omisión y el «viene» vacío absolutos algo subestimados. Ver `VARA_CORREGIDA.md` y `ARQUITECTURA.md` §5.

Medido el 2026-11-16 sobre el replay de la vara de producto (`prediccion/replay/`, modelo de producción `data/ml/export/path_v3_l1_s1`, lógica fijada en `prediccion/replay/pinned/`). Sin entrenar nada; no se modificó `pinned/`, `prediccion/v2/geo_assign.py` ni proyectoconsola. Estilo y método de `OMISIONES.md`.

## Conclusión

1. **Falsa alarma = coche listado (de los 5 mostrados) que no cruza la parada en 40 min: 24,5 % de los 1 933 795 listados** (10 días, 12 líneas; reproduce el 24,0–24,9 % de `V3_PRODUCCION.md` / `BARRIDO_SENTIDO.md`). En la banda de ETA anunciada 3–7 min es **14,6 %**.
2. **La definición de la vara sobrestima las falsas alarmas: 37,6 % de ellas (9,2 pp de 24,5) no son coches que no pasan**, son artefactos de cómo se mide el paso o el horizonte (X0, X2a–X2c, X3, X4, P abajo). En la banda 3–7 son 21,7 % (3,2 pp de 14,6). Descontados, la falsa alarma real es **~14,7 %** (global) y **~9,9 %** (3–7 min, medida con la vara de `VARA_CORREGIDA.md`).
3. **Lo que queda es sobre todo ramal desconocido:** otro ramal que diverge (R1) + sentido contrario (S) = 37,0 % de las falsas alarmas (9,1 pp) y **48,4 % de las de la banda 3–7 (7,1 pp de 14,6)**. El oráculo de ramal (replay con `only_shapes` = recorrido ex post) las baja de 24,5 a 17,4 % global y **de 14,6 a 6,7 % en 3–7 min**. 62 % de las falsas alarmas 3–7 salen del grupo «puede venir» (18 % de los listados de la banda, 50 % de ellos no pasa); los «viene» (seguro) fallan 6,0 %.
4. El resto (5,3 pp global, 3,3 pp en 3–7) son causas reales no resolubles con la asignación: coches detenidos o en cabecera sin viaje (1,25 pp, el 73 % no se mueve en todo el horizonte), viajes que terminan antes de la parada (1,6 pp), llegan después de 40 min (1,1 pp), desvíos (0,75 pp).

## Qué se midió

- **Muestra:** los 10 días de `V3_PRODUCCION.md` (15–20 sep. y 3, 4, 6, 8 oct.; la línea 26 solo 15–17 sep.): 113 pares (día, línea), 12 líneas de producción, 40 paradas por línea (mitad tronco compartido, mitad tramo exclusivo), instantes cada 10 min de 6 a 23 h. 1 933 795 coches listados en `base`, 474 285 falsas alarmas.
- **Regla de sentido nueva** (racha final k = 2 pings, avance neto ≥ 40 m, fracción de avance ≥ 0,6, T = 45 m, M = 20 m) reemplazada en memoria como en `barrido_sentido.py` (`falsas_diag.py: trailing_rule`). Resto de la lógica de la app idéntico (presentación, tope de 5, historial de 15 min, ping máximo 10 min, descuento de 60 s del sello de CABA).
- **Definición de falsa alarma (la de la vara, `metrics.false_alarms`):** coche en los 5 mostrados con `tp_s` vacío = sin cruce estricto de la parada en (t, t + 40 min]. Cruce estricto: par de pings consecutivos compatibles con d0 ≤ d_parada < d1, separados ≤ 600 s y ≤ 5 000 m, sobre un shape que sirve la parada (por nombre de recorrido).
- **Banda de ETA anunciada:** `eta0_s` (hora común, sin el descuento de 60 s), como `V3_PRODUCCION.md`.
- **Dos variantes en la misma corrida:** `base` y `ramal` (oráculo: `only_shapes` = recorrido ex post del viaje en curso). «El oráculo la saca» = el coche listado en `base` no figura entre los 5 de `ramal` en ese (parada, t).
- **Por cada falsa alarma de `base` se guardó** lo que decidió la app (grupo, sentido, forma elegida, shapes candidatos y motivos de descarte, distancia restante) y lo ex post: pings siguientes en 40 min (huecos, progreso sobre el shape elegido), todos los cruces posibles (estrictos, sin límite de horizonte; relajados: sin límite de hueco, de salto y de compatibilidad, perp ≤ 100 m; sobre shapes no asociados a la parada a ≤ 50 m), cruce entre el último ping y t, viaje ex post (forma, inicio, fin, posición del fin respecto de la parada y del largo del shape), sentido del viaje ex post contra el de los shapes que sirven la parada, velocidad y detención.
- **Clasificación:** jerárquica, una causa por falsa alarma, en el orden de la tabla (`clasifica.py`). Las causas X (artefactos) van primero porque contestan «¿el coche sí pasó?».
- Código y datos crudos: `data/ml/replay/falsas/` (`falsas_diag.py`, `pasado.py`, `clasifica.py`, `tablas.py`, `ejemplos.py`, `gaps.py`, `run/*.parquet`, `run_pasado/`, `clasif.parquet`, `tablas.md`, `ejemplos.txt`). Se corrieron 3 workers con prioridad baja; ~3 h.

## Tabla de causas (474 285 falsas alarmas = 24,5 % de los listados)

Orden = orden de la jerarquía. «pp de los listados» suma 24,5. «Oráculo la saca»: % de esas falsas alarmas que desaparecen de la lista sabiendo el ramal.

| causa | n | % de las FA | pp de los listados | % FA banda 3-7 | oraculo la saca % | provisional % | puede venir % |
|---|---|---|---|---|---|---|---|
| **X0** ETA anunciado > 40 min (fuera del horizonte de la vara) | 87276 | 18.4 | 4.51 | 0.0 | 29 | 5 | 35 |
| **X3** parada en el último tramo del shape (cruce imposible por construcción) | 14131 | 3.0 | 0.73 | 5.4 | 6 | 0 | 23 |
| **X2a** pasa en 40 min dentro de un hueco de GPS > 10 min | 21654 | 4.6 | 1.12 | 7.7 | 9 | 3 | 13 |
| **X2b** pasa en 40 min con salto > 5 km entre pings | 1844 | 0.4 | 0.10 | 0.6 | 56 | 1 | 70 |
| **X2c** pasa en 40 min con pings no compatibles (> 45 m) en el cruce | 10101 | 2.1 | 0.52 | 4.1 | 40 | 1 | 42 |
| **X2d** pasa por la calle de la parada con un recorrido que no la tiene en su lista (no para ahí; no es artefacto) | 19089 | 4.0 | 0.99 | 7.0 | 84 | 2 | 82 |
| **X1** pasa después de 40 min, mismo viaje (ETA subestimado) | 21549 | 4.5 | 1.11 | 1.5 | 7 | 15 | 15 |
| **X4** alcanza la parada pero ningún par de pings compatibles la cruza | 9944 | 2.1 | 0.51 | 3.7 | 2 | 2 | 6 |
| **P** ya había cruzado la parada antes de t (ping desactualizado) | 33059 | 7.0 | 1.71 | 0.2 | 1 | 0 | 2 |
| **S** sentido contrario (el viaje ex post va al revés) | 23117 | 4.9 | 1.20 | 7.1 | 94 | 23 | 45 |
| **R1** otro ramal: el recorrido ex post no sirve la parada | 152202 | 32.1 | 7.87 | 41.3 | 98 | 4 | 96 |
| **T1** el viaje termina antes de la parada, a mitad de recorrido | 23448 | 4.9 | 1.21 | 4.9 | 3 | 3 | 29 |
| **T2** el viaje termina antes de la parada, a < 1,5 km del final | 7687 | 1.6 | 0.40 | 2.4 | 1 | 0 | 4 |
| **C** coche sin viaje en t (84 %): detenido o en cabecera | 24232 | 5.1 | 1.25 | 7.4 | 13 | 20 | 33 |
| **G** hueco de GPS > 10 min que tapa el paso (paso no verificable) | 6458 | 1.4 | 0.33 | 0.9 | 4 | 3 | 13 |
| **D** desvío / sin pings a ≤ 300 m de la parada sobre el shape | 14447 | 3.0 | 0.75 | 4.6 | 3 | 3 | 28 |
| **O** otro (sirve la parada, sigue el viaje, no llega) | 4047 | 0.9 | 0.21 | 1.2 | 7 | 1 | 20 |

Banda 3-7: 347344 listados, FA 14.6 % (50585)

## Qué es cada causa

**Artefactos de la vara (el coche sí pasa por la parada, o la vara no puede verlo; sin X2d): 9,2 pp, 37,6 % de las falsas alarmas.**

- **X0 ETA anunciado > 40 min (4,5 pp).** La app lista hasta 5 coches sin tope de ETA y el horizonte de la verdad es 40 min: un coche anunciado a 50 min figura como falsa alarma (93,5 % de la banda > 40 min). 68 % de ellos sí pasa después, dentro de 2 × ETA + 10 min. No es una falsa alarma del usuario.
- **X3 parada en el último tramo del shape (0,73 pp; 5,4 % en 3–7).** La parada está a ≤ 100 m del final del shape (terminal: «Terminal 106 Liniers» a 19 468 m = largo del shape) y el coche llega, pero el cruce exige d0 ≤ d_parada < d1 y d no puede superar el largo: el cruce no existe por construcción. Líneas 106 (11 % de sus falsas alarmas), 124, 50, 42, 151.
- **X2a pasa dentro de un hueco de GPS (1,12 pp; 7,7 % en 3–7).** Hay un cruce interpolado dentro de 40 min entre dos pings que distan > 600 s (mediana 21 min); la vara descarta cruces con `PASS_MAX_DT_S` = 600. Pesa en 26 (21 %), 124 (15 %), 151 y 92 (9 %). 0,7 % de los intervalos entre pings de la línea 124 superan 10 min (241 huecos de > 10 min en 32 204 intervalos el 17-sep.; solo 3 de 116 ventanas de 5 min concentran ≥ 5 inicios: son de cada coche, no una caída global de la grabación).
- **X2b / X2c (0,6 pp).** Cruce con salto > 5 km entre pings (`STEP_JUMP_M`) o con un ping a 45–100 m del shape en el cruce (no compatible).
- **X2d pasa por la calle de la parada con un recorrido que no la tiene en su lista (0,99 pp; 7,0 % en 3–7).** El coche cruza a ≤ 50 m de la parada por un shape cuyo nombre no figura en `ramales[].stops` de la parada: ese recorrido no para ahí. No es un artefacto de la vara ni dato faltante de la parada: es una falsa alarma real (la app lista un coche de otro recorrido). Pesa en 132 (20 %), 50 (8 %), 151 (5 %). El oráculo lo saca en 84 % porque deja fuera ese shape.
- **X4 alcanza la parada sin cruce verificable (0,51 pp; 3,7 % en 3–7).** Sobre el shape elegido el coche llega a d ≥ d_parada con pings compatibles a ≤ 250 m de ella, pero entre pings consecutivos compatibles no hay ningún par que la encierre (ping intermedio fuera del shape, bucle).
- **P ya había cruzado antes de t (1,71 pp; 47 % de la banda 0–2 min, 0,2 % en 3–7).** El último ping está antes de la parada (rem de 100–300 m, status «llegando», ETA 0), pero el cruce interpolado entre ese ping y el siguiente cae antes de t (el ping tenía 28 s de edad mediana). El coche pasó segundos antes de lo anunciado: es «llega antes», no una falsa alarma.

**Causas reales (el coche listado no pasa ni se puede decir que pase): 14,3 pp.**

- **R1 otro ramal (7,87 pp, 32,1 %; 41,3 % en 3–7).** El recorrido ex post del viaje no sirve la parada: el coche comparte el tronco con el shape listado y diverge antes de llegar. 96 % cae en «puede venir» (el ramal depende de más de un shape), 57 % de las falsas alarmas de paradas de tramo exclusivo (FA de esas paradas: 47,9 % contra 15,7 % en compartido y 15,8 % en única). Líneas: 39 (75 % de sus falsas alarmas), 132 (52 %), 168 (43 %), 106 (39 %), 50 (34 %), 107 (21 %), 42 (18 %). El oráculo saca 98 %.
- **S sentido contrario (1,20 pp; 7,1 % en 3–7).** El viaje ex post va en el sentido opuesto al de los shapes que sirven la parada. 80 % con viaje en curso; el sentido lo dio la geometría en 48 %, el historial en 30 %, «sentido sin confirmar» (provisional) en 23 %. Muchos son coches en terminal o en calles compartidas por ida y vuelta (línea 92: 11,6 % de sus falsas alarmas; 151: 11,6 %). 33 % de los «sentido sin confirmar» de la banda 3–7 son esto. El oráculo saca 94 %.
- **T1 / T2 el viaje termina antes de la parada (1,6 pp; 7,3 % en 3–7).** El viaje ex post termina antes de la posición de la parada: a mitad de recorrido (T1, mediana a 67 % del largo; viaje fraccionado, vuelta corta, o el coche deja de transmitir: 14 % tiene un hueco de > 15 min) o a < 1,5 km del final (T2). Líneas 92 y 108 (15 y 10 % T1), 151 (14 %), 26 (T2 9,5 %).
- **C coche sin viaje en t (1,25 pp; 7,4 % en 3–7).** 84 % no tiene viaje ex post; 73 % no avanza ni 300 m en todo el horizonte con velocidad ~0: coche estacionado sobre el recorrido o en cabecera. 20 % está en «sentido sin confirmar». Línea 42: 25 % de sus falsas alarmas.
- **X1 pasa después de 40 min en el mismo viaje (1,11 pp; 1,5 % en 3–7):** ETA subestimado; 16 % de la banda 20–40 min.
- **D desvío (0,75 pp; 4,6 % en 3–7):** el coche sigue el viaje pero no hay ningún ping a ≤ 300 m de la parada sobre el shape: desvío o shape desactualizado. **G (0,33 pp)** hueco de GPS que tapa el paso sin cruce relajado dentro del horizonte. **O (0,21 pp)** resto.

## Por banda de ETA anunciada

Banda 3–7: 347 344 listados (3–5: 175 560; 5–7: 171 784), FA 14,6 % (13,2 y 16,0 %); sin ningún artefacto 10,4 %. Composición de las falsas alarmas de cada banda (%):

| causa | 0-2 | 2-3 | 3-5 | 5-7 | 7-10 | 10-20 | 20-40 | >40 |
|---|---|---|---|---|---|---|---|---|
| listados | 219376 | 87048 | 175560 | 171784 | 236004 | 549361 | 401366 | 93296 |
| FA % | 31.5 | 11.4 | 13.2 | 16.0 | 18.9 | 19.4 | 26.4 | 93.5 |
| X0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| X3 | 3.0 | 7.5 | 6.1 | 4.7 | 3.8 | 3.7 | 2.8 | 0.0 |
| X2a | 3.7 | 9.4 | 8.5 | 6.9 | 6.3 | 6.8 | 3.9 | 0.0 |
| X2b | 0.1 | 0.9 | 0.7 | 0.6 | 0.4 | 0.6 | 0.5 | 0.0 |
| X2c | 1.7 | 4.4 | 4.5 | 3.9 | 3.1 | 2.9 | 1.8 | 0.0 |
| X2d | 5.8 | 8.1 | 7.8 | 6.3 | 6.1 | 5.5 | 2.1 | 0.0 |
| X1 | 0.8 | 1.4 | 1.7 | 1.3 | 1.4 | 2.0 | 16.4 | 0.0 |
| X4 | 1.0 | 4.5 | 4.1 | 3.4 | 3.0 | 3.4 | 1.8 | 0.0 |
| P | 47.3 | 2.9 | 0.3 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| S | 4.8 | 8.2 | 7.4 | 6.9 | 6.0 | 5.2 | 6.7 | 0.0 |
| R1 | 8.5 | 25.1 | 36.7 | 45.2 | 48.7 | 51.5 | 43.6 | 0.0 |
| T1 | 2.7 | 4.9 | 4.9 | 4.9 | 4.6 | 6.7 | 8.9 | 0.0 |
| T2 | 1.5 | 4.9 | 2.7 | 2.2 | 1.7 | 2.0 | 1.9 | 0.0 |
| C | 10.3 | 10.4 | 7.3 | 7.4 | 9.7 | 3.9 | 3.6 | 0.0 |
| G | 6.4 | 1.4 | 1.1 | 0.8 | 0.7 | 0.7 | 0.4 | 0.0 |
| D | 1.3 | 4.7 | 4.9 | 4.4 | 3.7 | 4.1 | 4.5 | 0.0 |
| O | 1.2 | 1.5 | 1.2 | 1.1 | 0.8 | 1.0 | 1.0 | 0.0 |

Lectura: 0–2 min es el 31,5 % (P pasó segundos antes: 47 %, y cabecera/detenido 10 %); en 3–7 min domina R1 (37–45 %) con S (7 %) y artefactos de paso (X2a, X3, X4 y X2d, que no es artefacto: 8,5 + 7,8 + 6,1 + 4,1 en 3–5); en 20–40 min y > 40 pesan X1 y X0 (ETA lejano).

## Por línea

Composición de las falsas alarmas de cada línea (%). El oráculo de ramal baja la falsa alarma de la 39 de 31,5 a 12,1 %, 132 de 25,0 a 8,1 %, 106 de 22,4 a 13,1 %, 50 de 32,3 a 21,4 %, 168 de 40,8 a 32,0 %; no cambia 26, 92, 108, 124 (un recorrido por sentido) ni 42 (38,8 → 35,8 %: la 42 es sobre todo coche sin viaje y viajes que terminan).

| linea | FA % | FA % 3-7 | X0 | X3 | X2a | X2b | X2c | X2d | X1 | X4 | P | S | R1 | T1 | T2 | C | G | D | O |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 26 | 7.0 | 4.2 | 1.5 | 0.0 | 21.5 | 0.0 | 4.6 | 0.6 | 1.6 | 3.8 | 31.5 | 1.0 | 0.0 | 4.3 | 9.5 | 6.5 | 6.2 | 5.0 | 2.4 |
| 39 | 31.5 | 18.9 | 2.1 | 0.0 | 3.0 | 0.0 | 3.9 | 1.6 | 1.3 | 0.5 | 5.5 | 1.4 | 74.6 | 1.7 | 0.0 | 1.9 | 0.8 | 1.4 | 0.2 |
| 42 | 38.8 | 33.3 | 9.4 | 4.1 | 2.9 | 1.9 | 2.0 | 3.3 | 4.0 | 3.8 | 3.0 | 6.8 | 18.1 | 8.9 | 0.6 | 25.1 | 1.4 | 2.9 | 1.7 |
| 50 | 32.3 | 15.7 | 19.9 | 6.9 | 3.0 | 0.0 | 1.4 | 7.8 | 4.3 | 1.3 | 4.6 | 2.9 | 33.9 | 1.8 | 4.9 | 2.0 | 0.9 | 3.3 | 0.9 |
| 92 | 14.2 | 4.6 | 29.8 | 0.0 | 9.1 | 1.2 | 2.6 | 0.9 | 7.8 | 2.5 | 10.4 | 11.6 | 0.0 | 15.1 | 0.0 | 2.7 | 1.4 | 4.2 | 0.8 |
| 106 | 22.4 | 13.9 | 13.8 | 11.1 | 3.8 | 0.0 | 1.2 | 1.6 | 4.0 | 0.5 | 10.8 | 3.6 | 38.5 | 1.9 | 1.9 | 2.4 | 2.0 | 1.9 | 0.9 |
| 107 | 18.3 | 14.3 | 32.9 | 0.0 | 7.4 | 0.1 | 2.3 | 0.7 | 10.0 | 5.9 | 8.1 | 4.3 | 21.3 | 1.5 | 0.0 | 0.0 | 1.4 | 3.4 | 0.8 |
| 108 | 24.5 | 11.9 | 40.7 | 1.3 | 5.1 | 0.5 | 1.8 | 0.5 | 10.3 | 3.5 | 4.8 | 6.8 | 0.0 | 9.9 | 7.1 | 1.9 | 0.9 | 4.2 | 0.8 |
| 124 | 11.1 | 4.8 | 25.7 | 7.8 | 15.2 | 0.0 | 0.5 | 0.4 | 11.9 | 1.4 | 14.5 | 1.3 | 0.0 | 1.5 | 3.5 | 5.2 | 5.5 | 3.0 | 2.7 |
| 132 | 25.0 | 18.4 | 1.0 | 0.0 | 3.1 | 0.0 | 1.1 | 19.7 | 1.0 | 1.1 | 10.1 | 4.1 | 51.8 | 2.1 | 0.0 | 1.8 | 1.1 | 1.8 | 0.4 |
| 151 | 12.4 | 5.5 | 10.7 | 4.5 | 9.2 | 0.0 | 7.1 | 5.2 | 3.8 | 2.9 | 19.5 | 11.6 | 5.3 | 14.4 | 0.1 | 0.3 | 2.8 | 2.0 | 0.8 |
| 168 | 40.8 | 18.1 | 32.8 | 0.0 | 2.4 | 0.0 | 1.4 | 0.4 | 2.7 | 1.6 | 2.5 | 4.5 | 42.5 | 2.8 | 0.0 | 0.5 | 0.5 | 4.9 | 0.5 |

## Ejemplos (coche, día, hora, parada)

Trazas completas de pings en `data/ml/replay/falsas/ejemplos.txt`. Hora local; d = metros desde el inicio del shape.

- **R1, línea 39, 2026-10-08, t = 15:20:00, coche 77569, parada n11004527181 «Gorriti y Juan B Justo»** (tramo exclusivo del Ramal 3, a 3 038 m). Listado «puede venir» sobre el Ramal 3 con ETA 221 s. Hasta las 15:21:48 el coche está a 1–9 m de los dos shapes (2 495 m); a las 15:24:46 está a 3 325 m del Ramal 1 (2 m) y a 828 m del Ramal 3: el viaje ex post es del Ramal 1 y nunca pasa por la parada.
- **X2a, línea 124, 2026-09-18, t = 17:30:00, coche 98755, parada n11074325015 «Nazca y Álvarez Jonte»** (recorrido único, 8 220 m). Último ping 17:28:36 a 5 799 m; el siguiente 17:44:44 a 9 945 m (hueco de 16 min): cruza hacia las 17:38 (dentro de los 40 min) y la vara no interpola. ETA anunciado 476 s: el coche pasa unos 9 min después de t.
- **P, línea 106, 2026-10-04, t = 10:20:00, coche 78014, parada n3822177716 «Scalabrini Ortiz y Córdoba»** (13 646 m). Ping 10:18:50 a 13 437 m y el siguiente 10:20:50 a 13 818 m: cruce interpolado a las 10:19:56, 4 s antes de t. La app lo muestra «llegando» (ETA 0).
- **X3, línea 106, 2026-10-06, t = 15:30:00, coche 77839, parada n3230342361 «Terminal 106 Liniers»** (19 468 m = fin del shape 369522). Llega a 19 468 m a las 15:36:54 (el ETA de 393 s acierta) y queda allí: el cruce no existe.
- **C, línea 42, 2026-10-04, t = 11:00:00, coche 78996, parada n12159157754 «Alcorta y Ochoa»** (21 782 m del Ramal A). Parado en 18 310–18 314 m (3,5 km antes) con velocidad 0 entre las 10:30 y las 12:23, sin viaje ex post; la app lo lista «puede venir» con ETA 387 s.
- **T1 / hueco, línea 108, 2026-09-18, t = 15:50:00, coche 94340, parada n11888017467 «Hospital Rivadavia»** (21 125 m). Último ping 15:46:30 a 19 813 m; el siguiente recién a las 16:46:34, ya pasada la parada: silencio de 60 min (la mezcla T1/G/X2a depende de cuánto dura el hueco).

## Qué cambio en el pipeline o en la vara ataca cada causa y techo

La asignación coche→recorrido/sentido se define en el pipeline y la app la porta: nada de lo siguiente es una regla solo-app. Los techos son lo que desaparece de las falsas alarmas (pp de los listados); no se probó ningún cambio, y quitar falsas alarmas cambiando la vara no cambia lo que ve el usuario.

| causa | cambio | techo global | techo 3–7 min |
|---|---|---|---|
| X0 | Vara: contar falsa alarma solo si ETA anunciada ≤ 40 min, o horizonte de la verdad = max(40 min, ETA anunciada + 10 min). Producto: decidir si se muestran coches con ETA > 40 min (hoy se muestran) | 4,5 pp | 0 |
| X3 | Vara y pipeline (`crossing_times`): contar el cruce cuando d_parada ≥ largo − 1 m y el coche llega a ≤ 30 m del final; o excluir paradas a < 100 m del final del shape de la muestra | 0,7 pp | 0,8 pp |
| X2a, G | Vara: interpolar cruces con hueco ≤ 40 min si d es monótona y la velocidad media implícita es plausible; si no, marcar «no verificable» y excluir de falsas alarmas y de omisiones (hoy cuentan como falsas alarmas y como omisiones) | 1,1 + 0,3 pp | 1,1 pp |
| X2b, X2c, X4 | Vara: aceptar cruces entre pings no consecutivos compatibles; límite de salto por distancia/tiempo en lugar de 5 km fijo | 1,1 pp | 1,2 pp |
| P | Producto/pipeline: «llegando» y «pasado» con la posición extrapolada (rem − velocidad × edad del ping ≤ 0 = pasado). Es «llega antes de lo anunciado», no falsa alarma | 1,7 pp | 0,03 pp |
| **Total artefactos** | | **9,2 pp (37,6 %)** | **3,2 pp (21,7 %)** |
| R1 | Conocer el ramal en tiempo real: la excepción ya decidida (filtro de ramal CuandoSubo, parche de producción). Ninguna regla de geometría lo resuelve (el ramal diverge después del tramo compartido). Oráculo medido: 24,5 → 17,4 % global; 14,6 → 6,7 % en 3–7. Lo que el oráculo no saca de R1 es 0,2 pp | 7,7 pp | 5,9 pp |
| S | Regla de sentido en el pipeline: 20 % son coches sin viaje ex post todavía (terminal), 48 % tenían sentido por geometría y 30 % por historial: no se probó una regla concreta; el oráculo saca 94 % | 1,1 pp | 1,0 pp |
| C | Pipeline (`direction_from_history`): coche sin avance neto en la ventana de 15 min y sin ping en movimiento no es candidato (hoy un coche parado a 3 km de la parada se lista). 73 % de C está inmóvil todo el horizonte; el resto son cabeceras que arrancan después de 40 min o coches sin ping reciente. Con n_hist mediano 5 y 20 % de C en «sentido sin confirmar», el efecto depende de cuántos pings tenga el coche | 0,9 pp | 0,8 pp |
| T1, T2, X1, D, O | No son corregibles con reglas de asignación: viaje que termina o se fracciona (no se conoce al anunciar), desvío o shape desactualizado, ETA subestimado | 0 | 0 |

**Lo que queda aun con todo resuelto: 24,5 − 9,2 (vara) − 7,7 (ramal) − 0,9 (C) − 1,1 (S) ≈ 5,6 pp global y ≈ 3,7 pp en 3–7 min** (X2d + T1 + T2 + X1 + D + O + G + resto de C, S y R1).

## Veredicto sobre la vara

- **La definición de falsa alarma está mal en 37,6 % de los casos.** Contar como falsa alarma un coche anunciado a más de 40 min, que llega al final del shape, que cruza dentro de un hueco de GPS o entre pings no consecutivos, o que cruzó segundos antes de t no mide lo que le importa al usuario. Mejora de lectura: informar la falsa alarma **en la banda 3–7 min** (14,6 %; 9,9 % con la vara corregida) y **por grupo**: «viene» 14,1 % global y 6,0 % en 3–7; «puede venir» 59,7 % y 50,1 %; «sentido sin confirmar» 53,4 % y 45,3 %.
- **La falsa alarma real de la banda 3–7 es un problema de ramal:** 7,1 pp de 14,6 son R1 + S, y el oráculo la baja a 6,7 % (consistente con `ORACULO_RAMAL.md`: 24,0 → 17,4 % global con la regla de sentido vigente entonces; con la regla nueva la base queda en 24,5 %).
- **«Sentido sin confirmar» / 1 ping:** 2,5 % de los listados (48 786), 53,4 % falsa alarma, 5,5 % de las falsas alarmas. Solo 1,6 % de las falsas alarmas tiene 1 ping de historial. En la banda 3–7 las causas son S 33 %, R1 24 %, C 23 %.
- **Ramal y omisión son problemas distintos** (como en `OMISIONES.md`): quitar los «puede venir» de la lista bajaría la falsa alarma 3–7 a 6,0 % pero esos coches pasan la mitad de las veces; no se midió la omisión resultante.

## Salvedades

- La causa se asigna por jerarquía (una por coche, en el orden de la tabla). Un coche con dos explicaciones (por ejemplo, otro ramal y hueco de GPS) cuenta en la primera que cumple; reordenar mueve casos entre filas pero no el total.
- Las causas S, R1, T, C y D usan el viaje ex post (segmentador geo2 + `geometry_for_trip` geo3), que en calles compartidas por ida y vuelta o terminales puede ser ambiguo; las causas X no dependen de él.
- «El oráculo la saca» mide la salida de ese coche de los 5, no su paso: en el oráculo el tope de 5 se llena con otros coches (1 839 261 listados contra 1 933 795).
- X4 y D comparten el mismo síntoma (pings sin cruce verificable cerca de la parada) y se separan por un umbral de 250 m al shape elegido. X1 usa tp ≤ 90 min en el mismo viaje; los pasos más tardíos (otra vuelta del coche) caen en T1, T2 o C.
- Una corrida, 10 días (la línea 26 solo 3), 40 paradas por línea, instantes cada 10 min; los huecos de GPS sobrestiman falsas alarmas y omisiones por igual en el replay.
