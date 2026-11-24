# Omisiones del replay de producción: causas y techo de recuperación

> **Registro (2026-11-16):** las falsas alarmas, la omisión y el «viene» vacío de este informe usan la definición anterior de la vara de producto. Siguen válidos como comparaciones relativas; las falsas alarmas absolutas están infladas (≈ 24,5 contra ≈ 14,7 % con la vara corregida) y la omisión y el «viene» vacío absolutos algo subestimados. Ver `VARA_CORREGIDA.md` y `ARQUITECTURA.md` §5.

Medido el 2026-11-15 sobre el replay de la vara de producto (`prediccion/replay/`, variante `base`, modelo `data/ml/export/path_v2c_l1_s1`, lógica fijada en `prediccion/replay/pinned/`). Sin entrenar nada; no se modificó `pinned/` ni ningún dato.

## Qué se midió

- **Muestra:** 6 días (2026-09-15, 17, 19, 20, 10-04, 10-06), las 12 líneas, 40 paradas por línea, instantes cada 10 min de 6 a 23 h: 68 pares (día, línea). Un registro por (parada, t, coche) con paso real por la parada en ≤ 10 min: **427 207** registros (la línea 26 solo tiene datos hasta el 17-sep). Reproduce el criterio de `metrics.omissions` (sobre coches con ping vigente en t): **16,4 %** de omisión contra 17,0 % del informe (10 días); es la misma medida sobre otra muestra.
- **Definición vigente (correcta en lo esencial):** coche con cruce interpolado de la parada en (t, t+10 min] y con ping vigente (edad ≤ 600 s) que no está entre los 5 mostrados. Los coches sin ping vigente quedan fuera de ese 17 % (son aparte, abajo).
- **Por registro se guardó** el resultado de `predict_from_raw` (status, grupo, shapes descartados y motivo), el recorrido **S** por el que el coche cruza la parada, su posición en t sobre cada shape (error perpendicular, distancia a lo largo, compatibilidad T = 45 m / M = 20 m), y para las causas de sentido se recalculó la ventana de historial de 15 min sobre S: fracción de pings a ≤ 45 m, fracción de avance, avance neto, pings fuera de todo shape, tiempo desde el inicio del viaje ex post. La causa se asigna por lo que le pasa al coche **respecto de S** en t (el shape por el que de verdad llega a la parada).
- Scripts en `data/ml/replay/omisiones/`: `omis_diag.py` (clasificación), `omis_detalle_ventana.py` (detalle de la ventana de sentido), `omis_proto.py` (prototipo, abajo).

## Tabla de causas (omisiones: 69 318 = 16,4 % de los 423 225 coches con ping vigente que pasan en ≤ 10 min)

| causa | n | % de las omisiones | pp del total | % en banda real 3–7 min |
|---|---|---|---|---|
| **A** sentido por historial «incoherente»: viaje iniciado hace < 15 min (la ventana de 15 min incluye pings del viaje anterior o de la cabecera, fuera de S) | 22 849 | **33,0** | 5,40 | 35,5 |
| **B** sentido «incoherente»: el coche estuvo fuera de S (> 45 m) en parte de la ventana de 15 min y volvió (desvío, calle paralela, bucle de cabecera) | 14 345 | **20,7** | 3,39 | 20,2 |
| **C** sentido «incoherente»: retrocede en la ventana (fracción de avance < 0,6: 4,7 %) u otro (0,2 %) | 3 402 | 4,9 | 0,80 | 5,7 |
| **G** cortado por el tope de 5 (status ok / llegando / provisional pero fuera de los 5 mostrados) | 13 434 | **19,4** | 3,17 | 15,6 |
| **F** coche en t sobre otro shape de la línea, S todavía no es compatible; se une a S después (< 10 min) | 7 470 | 10,8 | 1,77 | 10,3 |
| **E** coche a > 45 m de todo shape de la línea en t (desvío, otra calle, cabecera); entra a S después | 5 937 | 8,6 | 1,40 | 10,0 |
| **D** idem E, pero proyectado al inicio de S (aún no arrancó: cabecera) | 1 814 | 2,6 | 0,43 | 2,7 |
| otro (status «pasado») | 67 | 0,1 | 0,02 | 0,1 |

A + B + C (el historial de sentido descarta a S estando el coche sobre S, T/M satisfechas): **58,5 % de las omisiones (9,6 pp)**; 61,4 % en la banda 3–7 min. Dentro de esas, la regla que las produce es la misma: `direction_from_history` exige ≥ 80 % de los pings de los últimos 15 min a ≤ 45 m del shape (`MIN_NEAR_FRAC`); si no, devuelve `sentido_incoherente`, que **descarta el shape aunque la geometría dé el sentido** (§4.5).

Causas pedidas que **no** son relevantes o no se pueden medir:

| candidata | resultado |
|---|---|
| Sin ping reciente (edad > 600 s o sin ping) | No entra en el 16,4 % (la definición ya lo excluye). Son 3 982 registros = **0,93 %** de los que pasan en ≤ 10 min (con ellos la omisión es 17,2 %): 70 % tenía el último ping de más de 15 min, 23 % entre 10 y 15 min, 7 % aún no había transmitido; 63 % cae en la banda 7–10 min. Subir `maxPingAgeS` a 900 s recuperaría 0,2 pp. |
| Fuera de T / M | 3 grupos E + D + F = **22,0 %** (3,6 pp); el rango 45–100 m (único recuperable subiendo T) es 3,0 % de las omisiones (0,5 pp). |
| Coche sin viaje en t (cabecera esperando / arranca después) | **11,4 %** de las omisiones: el coche no tiene viaje ex post en t y el siguiente arranca en ≤ 10 min (no existía como candidato). Se reparte en B (25 % de B), D (57 %), F (19 %), C (23 %). |
| Línea sin identificar (label fuera de `LABEL_LINE_MAP`) | **No medible con el replay y en él vale 0 por construcción:** solo carga coches con label resuelto, y la verdad también sale de esos coches. No puede explicar nada del 17 %. |
| Interpolación entre pings / definición de «pasó» | No es artefacto: la omisión es igual (16,1–16,7 %) con pings del cruce separados ≤ 60 s o ≥ 240 s. Sí sube cuando los dos pings del cruce son posteriores a t (17,2 % contra 7,9 %), que es lo esperable (el coche aún no entró a S). |
| Coche que pasa sin ser «el siguiente» | Pesa: la omisión es **12,8 % para el primer coche** que cruza la parada y 20,0 % para los siguientes (en tramo compartido 20,8 %, exclusivo 11,7 %, único 10,0 %). |

## Por qué el oráculo de ramal no las cambia

El oráculo **solo resta candidatos** (`only_shapes = [recorrido ex post]`); nunca agrega ni corrige un descarte. Las omisiones no vienen de elegir mal entre ramales sino de que el coche no tiene **ningún** shape aceptado: o el historial de sentido rechaza a S (A, B, C: 58,5 %), o el coche no es compatible con S en t (D, E, F: 22 %), o no entra en los 5 (G: 19 %). Restringir a S deja el mismo rechazo. Medición: en las omisiones el recorrido ex post del coche en t coincide con S en 60 % (el resto son hermanos del tronco compartido); en A y C es 70 % y 65 %. (En 39 la omisión sube de 11,6 a 13,6 % con el oráculo.)

## Por banda de ETA real (omisión % y composición)

| banda real | n que pasan | omisión % | A | B | C | G tope | F | E | D |
|---|---|---|---|---|---|---|---|---|---|
| 0–2 min | 85 360 | 8,9 | 57,2 | 29,2 | 5,6 | 2,8 | 1,9 | 2,7 | 0,2 |
| 2–3 min | 42 669 | 11,4 | 49,7 | 25,0 | 6,3 | 5,0 | 5,7 | 7,2 | 1,0 |
| 3–5 min | 84 242 | 14,0 | 40,4 | 21,3 | 6,4 | 11,2 | 8,9 | 9,3 | 2,3 |
| 5–7 min | 84 566 | 17,8 | 31,6 | 19,4 | 5,0 | 19,0 | 11,4 | 10,5 | 3,1 |
| 7–10 min | 126 388 | 23,8 | 21,9 | 18,2 | 3,8 | 29,3 | 14,3 | 9,0 | 3,4 |

Banda 3–7 min (foco): 168 808 coches, omisión **15,9 %** (26 808): A 35,5 %, B 20,2 %, G 15,6 %, F 10,3 %, E 10,0 %, C 5,7 %, D 2,7 %. Del primer coche de la banda (75 246) se omite 14,0 %.

## Por línea (omisión % y composición de sus omisiones, %)

| línea | omisión | A | B | C | G tope | F | E | D |
|---|---|---|---|---|---|---|---|---|
| 26 | 17,0 | 62,1 | 6,7 | 3,0 | 9,5 | 8,2 | 2,6 | 7,8 |
| 39 | 11,8 | 24,6 | 19,1 | 16,0 | 21,7 | 9,2 | 4,8 | 4,6 |
| 42 | 16,4 | 30,7 | 26,4 | 4,3 | 14,5 | 9,8 | 13,8 | 0,3 |
| 50 | 15,7 | 43,6 | 25,7 | 0,2 | 5,4 | 2,3 | 16,5 | 6,3 |
| 92 | 9,7 | 29,6 | 23,4 | 7,7 | 5,4 | 20,7 | 11,3 | 1,5 |
| 106 | 14,8 | 13,4 | 9,6 | 2,7 | **62,6** | 6,5 | 2,6 | 2,4 |
| 107 | **31,9** | 27,2 | **43,0** | 0,8 | 0,8 | 3,5 | 24,6 | 0,0 |
| 108 | 10,9 | 29,1 | 26,8 | 12,3 | 2,4 | 14,0 | 13,4 | 1,6 |
| 124 | 6,9 | 52,4 | 15,9 | 6,0 | 8,6 | 13,3 | 2,3 | 1,4 |
| 132 | 22,0 | 46,2 | 5,7 | 1,4 | 27,7 | 16,2 | 1,8 | 1,0 |
| 151 | 21,8 | 31,1 | 27,6 | 10,2 | 14,9 | 12,0 | 4,2 | 0,0 |
| 168 | 16,7 | 25,7 | 25,3 | 0,0 | 3,6 | 15,3 | 14,3 | 15,8 |

Todas las líneas están dominadas por A + B + C salvo la 106 (tope de 5: sus 14 coches simultáneos «ok» en la parada). La 107 (31,9 %) y la 151 son las peores: sentido B (la 107 tiene tramos donde sus pings quedan 260–360 m fuera de su shape durante varios minutos).

## Ejemplos (coche, día, hora, parada)

Columnas de las tablas: hora local, distancia a lo largo de S (m), error perpendicular a S (m), error perpendicular al shape más cercano de la línea (m), velocidad (m/s).

**A: línea 124, 2026-09-17, t = 08:00:00, coche 98922, parada n5732950134 «Avenida Córdoba» (recorrido único, 2 469 m de S), cruza a los 353 s.** Viaje ex post nuevo desde 07:51:28 (8,5 min antes); el viaje anterior terminó 07:48:52 y la cabecera quedó fuera de S. En t el coche está sobre S, avanzando (1 326 m de S, 2 469 m la parada), y la ventana de 15 min tiene 3 pings del viaje anterior a 58–87 m de S:
```
07:42:52 1682 131.4 | 07:43:54 1224 152.5 | 07:44:48 1077 133.4 | 07:45:48 723 87.2 | 07:46:48 762 26.4
07:48:52 0 58.2 | 07:49:50 0 59.8 | 07:50:52 38 22.7 | 07:51:28 48 9.7 | 07:52:50 179 3.9 ... 07:59:52 1326 4.3 <- t
```
Resultado: 11 de 14 pings a ≤ 45 m (0,79 < 0,8) → `sentido_incoherente` → `sin_sentido`, el coche no se lista. Con el sentido por la racha final (último tramo continuo sobre S: 10 pings, avance neto 1 288 m) queda «ok».

**B: línea 107, 2026-09-17, t = 22:10:00, coche 94505, parada n3268338426 «Avenida Rivadavia» (tronco compartido, 19 105 m de S), cruza a los 300 s.** Viaje en curso desde 21:08:34. Entre 22:01:36 y 22:05:36 los pings quedan **262–358 m fuera de S** (desvío o shape desactualizado) y desde 22:06:36 vuelve a S (0,5–3,5 m) y avanza (16 408 → 17 315 m):
```
21:59:36 15229 4.2 | 22:01:36 15768 280.8 | 22:03:36 16134 358.2 | 22:05:36 16306 261.8 | 22:06:36 16408 0.9 | 22:09:32 17315 2.4 <- t
```
Ventana de 15 min: 5 pings fuera de 15 (10/15 = 0,67 < 0,8) → incoherente → se omite. Es el patrón de la 107 (43 % de sus omisiones).

**F: línea 132, 2026-09-17, t = 10:50:00, coche 79126, parada n4584664461 «Retiro (San Martín)» (503 m de S), cruza a los 284 s.** El viaje anterior terminó 10:49:58 en la terminal; entre 10:47 y 10:49 el coche da la vuelta a 270–430 m de S (sobre el shape del viaje anterior) y recién entra a S a las 10:50:58; en t está a 85,7 m de S → `coche_fuera_del_recorrido` / `no_sirve_parada`. Es «coche en cabecera que arranca después de la consulta».

**E: línea 42, 2026-09-17, t = 10:40:00, coche 77868, parada n3048418214 «Alcorta y De Solier» (3 110 m de S), cruza a los 354 s.** El coche está a 96–174 m de todo shape entre 10:33:58 y 10:37:52 (la cabecera de la terminal, el viaje anterior termina 10:37:52) y entra a S a las 10:40:58.

**G: línea 106, 2026-09-17, t = 11:20:00, coche 88459, parada n3931528543 «Corrientes y Yatay» (exclusivo), cruza a los 204 s.** Está bien posicionado sobre S (10,9 m, 12 947 − 11 959 = 988 m de la parada) y con status ok, pero la parada tiene 14 coches «ok» y lo ordena 9.º. De los coches mostrados en instantes con corte (8 518 instantes): 68 % pasa en ≤ 10 min, 14 % pasa en > 10 min, 17,5 % no pasa en 40 min; en 39 % de los cortes el omitido llega **antes** de lo que se anuncia para el 5.º de la lista (28,5 % más de 60 s antes); 43 % de las veces los 5 mostrados pasan todos en ≤ 10 min (el corte es solo capacidad). El omitido cuesta rank 6 en 46 % de los casos, 7 en 23 %, 8 en 10 %; solo 4,3 % de los primeros coches omitidos lo son por el tope.

## Qué cambio de definición en el pipeline ataca cada causa y cuánto recupera

| causa | cambio en `prediccion/v2/geo_assign.py` (la app lo porta) | techo (% de omisiones / pp) | medido |
|---|---|---|---|
| A + B + C (58,5 %) | `direction_from_history` evalúa la **racha final de pings consecutivos a ≤ T de S** (desde el último ping fuera de S hasta el actual) en lugar de exigir `MIN_NEAR_FRAC` = 0,8 sobre toda la ventana de 15 min; mantiene ≥ 2 pings, fracción de avance ≥ 0,6 y avance neto ≥ 40 m sobre esa racha. Se elimina `MIN_NEAR_FRAC` del manifest. El dataset v2c no cambia (la máscara `valid` no usa el sentido). | 58,5 % / 9,6 pp | prototipo: ver abajo |
| G tope de 5 (19,4 %) | No es de asignación: es presentación (`LIST_MAX`). Por rango del omitido: 6 → 45,7 % de G, 7 → 68,3 %, 8 → 78,6 % (8,9 / 13,2 / 15,2 % de las omisiones). Pesa poco en lo que importa: 4,3 % de las omisiones del primer coche. | 19,4 % / 3,2 pp | no probado |
| F (10,8 %) | Candidatos «alcanzables»: un coche compatible con B es candidato para S si B y S comparten el tramo hacia adelante hasta la parada (requiere el grafo de convergencia de shapes; hoy `user_shapes` solo mira el nombre del recorrido). Concentrado en 132, 151, 92, 168, 106. | 10,8 % / 1,8 pp | no probado; costo alto |
| E + D (11,2 %) | Subir T no corresponde (T = 45 m se eligió contra la calle paralela a 100–130 m): el techo de T = 100 m es 3,0 % de las omisiones (0,5 pp). El resto son cabecera, desvío o shape desactualizado, no corregibles con reglas de asignación (D: sin hora de salida, el ETA no existe). | 3,0 % / 0,5 pp con T = 100 | no probado |
| Sin ping reciente | `maxPingAgeS` 600 → 900 s | 0,2 pp | no probado |

### Prototipo del cambio A + B + C (medición, no decisión)

Se corrió el mismo diagnóstico con `direction_from_history` reemplazada en memoria por la versión de racha final (`omis_proto.py`; `pinned/` intacto) sobre 45 pares (día, línea) de los días 15, 17, 19 y 20 de sep.; `base` comparado sobre los mismos pares (283 830 coches que pasan en ≤ 10 min):

| | base | racha final |
|---|---|---|
| omisión (coches con ping vigente) | 16,7 % | **8,5 %** |
| omisión con coches sin ping vigente | 17,5 % | 9,4 % |
| omisión, banda 3–7 min | 16,1 % | **7,7 %** |
| omisión del primer coche que pasa | 12,8 % | **4,2 %** |
| falsas alarmas (listados que no pasan en 40 min) | 24,3 % | 24,8 % |
| coches listados por instante | 3,66 | 4,05 |
| listados que pasan: llega antes > 60 s / después > 60 s | 19,7 / 12,0 % | 19,7 / 12,6 % |
| error absoluto medio de ETA en los listados que pasan (s) | 52,5 | 53,8 |

Recupera 8,1 pp de los 9,6 pp de techo (49 % de las omisiones); lo que falta es lo que vuelve a quedar en el tope de 5 o en «sin candidatos». Omisión por línea, base → racha final: 26 17,0 → 5,7; 39 11,9 → 6,4; 42 17,4 → 7,2; 50 16,7 → 5,5; 92 10,2 → 4,8; 106 14,6 → 13,0; 107 33,3 → 11,1; 108 11,6 → 6,5; 124 7,1 → 3,8; 132 22,0 → 11,2; 151 22,6 → 12,3; 168 15,0 → 5,9. Las omisiones que quedan (8,5 %): 50 % «sin candidatos» (coche no compatible con S: causas D, E, F), 42 % tope de 5, 5 % sin sentido.

Los coches recuperados no empeoran el error de ETA: la proporción de listados que llegan antes de lo anunciado en más de 60 s no cambia (19,7 %) y las falsas alarmas suben 0,5 pp. Falta validar sobre los 10 días y las 3 variantes del replay (MAE de la banda 3–7 min, «viene» vacío) antes de portarlo; el replay da 15 min de historial a todo coche, mientras que la app solo tiene el historial desde que está abierta, así que con historial corto la regla de racha final se comporta igual o mejor.

## Veredicto sobre la vara

- La definición de omisión es válida: no depende de la interpolación entre pings ni de coches sin ping; las 6 causas candidatas del pedido pesan 0,9 pp (sin ping) o 0 (línea sin identificar) salvo A/B/C (sentido), D/E/F (fuera de S) y G (tope).
- Mejora de lectura: informar la omisión **del primer coche** y **en la banda 3–7 min** (12,8 % y 15,9 % hoy), no la de todos los coches ≤ 10 min: esta última incluye coches 6.º a 20.º en líneas densas (G) y la banda 0–2 min que no se usa para decidir.
- El oráculo de ramal y la omisión son problemas distintos: el ramal ayuda a sacar falsas alarmas (§7), la omisión viene del sentido por historial y de la posición en t.
