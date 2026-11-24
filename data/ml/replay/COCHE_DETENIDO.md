# Coche detenido: ¿conviene no listarlo, o listarlo distinto?

Medido el 2026-11-16 sobre el replay de la vara de producto (`prediccion/replay/`, variante `base`, modelo de producción `data/ml/export/path_v3_l1_s1`, lógica fijada en `prediccion/replay/pinned/` con la regla de sentido `trailing_run`, contrato 2.3), 12 líneas de producción, los 10 días de `V3_PRODUCCION.md` (15–20 sep. y 3, 4, 6, 8 oct.; la 26 solo 3 días), 40 paradas por línea, instantes cada 10 min de 6 a 23 h. Sin entrenar nada; no se tocó `prediccion/replay/`, `pinned/` ni `geo_assign.py`. Arnés propio y datos crudos en `data/ml/replay/detenido/`.

**Vara usada.** La vara corregida de `data/ml/replay/VARA_CORREGIDA.md` (definición vigente, sin asociación por geometría: recorridos que sirven la parada = solo los de `ramales[].stops`; `core.py` con `tp2_s`/`unv`/`past` y `metrics.py` con `corrected=True`): paso = cruce firme `tp2_s`; falsas alarmas solo sobre los listados con ETA anunciado ≤ 40 min, sin los no verificables y sin los que ya pasaron; omisión y «viene» vacío con el paso corregido (instantes no verificables excluidos). Con la vara anterior (`out_vara_anterior/`) las diferencias entre variantes dan lo mismo en signo y casi en magnitud; solo cambian los niveles absolutos (falsas alarmas base 24,5 % con la vara anterior contra 14,7 % con la corregida).

**Registro (2026-11-16).** La primera versión de estas tablas usó la vara con asociación parada↔recorrido por geometría (columna `extra`), incorrecta (`VARA_CORREGIDA.md`, registro de error). Se recalcularon `tp2_s`, `unv`, `past` y los instantes de `run2/` sin volver a predecir (`vara/recalcula_verdad.py` → `run2_sg/`) y se repitió `agrega.py` (`out/`; la versión con geometría quedó en `out_con_geometria/`). Niveles de la base (agregado de los 10 días): falsas alarmas 14,2 → 14,7 %, omisión 11,3 → 10,7 %, «viene» vacío 11,5 → 11,2 %, MAE 99 s. Las diferencias pareadas de la regla no cambian de signo ni de magnitud (b2 con ventana 5 min y 50 m: falsas alarmas −0,34 → −0,32 pp, causa C −0,38 → −0,38 pp, omisión −0,05 → −0,05 pp, MAE −2,4 → −2,4 s, llega después −0,30 → −0,29 pp, «viene» vacío +0,16 → +0,16 pp, llega antes +0,08 → +0,08 pp; tratamiento (a): falsas alarmas −0,7 pp, omisión +0,5 pp, 10 de 10 días). La conclusión no cambia. La columna `extra` dejó de usarse y `omx` (omisión sin pasos por shapes no asociados) se eliminó de `agrega.py` y `tablas.py`.

## Conclusión

1. **Descartar el coche detenido (tratamiento a) no conviene:** baja las falsas alarmas 0,7 pp pero sube la omisión 0,5 pp (10 de 10 días), la de 3–7 min 0,5 pp y la del primer coche 0,4 pp. De los coches que la regla marcaría entre los listados (ventana 5 min, avance 50 m), **10,5 % pasa en ≤ 10 min y 44,3 % pasa en los 40 min**: hay muchos coches detenidos un rato que después siguen (cabecera que sale, pausa larga, semáforo largo, fila). Solo 55 % de los marcados es falsa alarma y 19 % causa C.
2. **Bajarlo en vez de sacarlo sí conviene, poco en el agregado y mucho en la 42.** Tratamiento b2 (el coche marcado pasa al grupo «sentido sin confirmar» y se ordena al final de la lista, después de todo coche no marcado; el ETA no cambia): falsas alarmas −0,32 pp (10/10 días), causa C −0,38 pp (de 1,33 pp), omisión −0,05 pp (ruido), MAE del próximo coche 3–7 min −2,4 s (10/10), llega después >60 s −0,30 pp. Costo: «viene» vacío +0,16 pp (10/10) y llega antes >60 s +0,08 pp (10/10; 15,8 → 15,9 %). **En la 42** (donde C pesa 10,2 pp de sus listados): causa C 10,2 → 6,9 pp, falsas alarmas 31,6 → 29,4 %, omisión 8,9 → 7,8 %, **MAE 197 → 170 s**, llega después 33,4 → 32,0 %, llega antes 16,8 → 16,7 %; costo «viene» vacío 12,9 → 13,8 %.
3. **El efecto máximo es chico por construcción:** la causa C es 1,3 pp de los listados y la regla recupera 0,4 pp. El resto de C son coches que se mueven después de t (cabeceras que arrancan: 88 % de los marcados en cabecera no es C) y los que no tienen aún cinco minutos de historial sobre el shape (coche recién aparecido: no evaluable, no se marca).
4. **Cabecera contra mitad de recorrido:** el filtro en cabecera (posición < 300 m del inicio del shape) no baja las falsas alarmas (−0,01 pp con b2): el 52 % de los coches detenidos en cabecera pasa por la parada en 40 min. Lo que baja falsas alarmas es el detenido a mitad de recorrido (70 % falsa alarma, 33 % causa C; −0,31 pp con b2). En cambio lo que baja el MAE (−2,1 s) es bajar de «viene» al detenido en cabecera: deja de anunciarse como próximo un coche que todavía no salió. Solo mitad (b2): falsas alarmas −0,31, MAE −0,4 s, «viene» vacío +0,03 pp.
5. **El avance mínimo casi no importa, la ventana sí:** 20 y 50 m dan lo mismo (falsas alarmas −0,31 / −0,32 pp; 100 m agrega costo: llega antes +0,11 pp, «viene» vacío +0,19 pp); con ventana de 10 min la ganancia en falsas alarmas es −0,23 pp y en MAE −0,9 s, con 15 min −0,08 pp y −0,2 s (se marcan menos coches). 5 min es el borde de la grilla; no se midió una ventana menor.

## Recomendación

**Adoptar b2 con ventana 5 min y avance mínimo 50 m, para cualquier posición (cabecera y mitad). No adoptar (a).** Criterio explícito (todas las condiciones, contra base, con diferencia pareada día por día sobre 10 días):
- la omisión total, la de 3–7 min y la del primer coche no suben más de 0,1 pp en promedio ni en más de 8 de 10 días (b2: −0,05 / −0,07 / 0,00 pp; (a) falla: +0,5 pp en 10 de 10);
- llega antes >60 s no sube más de 0,1 pp (b2: +0,08 pp; es el costo a vigilar, consistente en los 10 días pero 10 veces menor que el avance en falsas alarmas);
- baja falsas alarmas y MAE en los 10 días (b2: −0,32 pp y −2,4 s en 10/10);
- no empeora ninguna línea de forma apreciable (por línea, tabla T5: solo cambian la 42, −27 s de MAE, y marginalmente 108/124 con «viene» vacío +0,2–0,4 pp).
La ganancia es chica en el agregado (−0,32 pp de 14,7 %); la razón para adoptarla es la 42 y que no tiene costo en omisión. Si se prefiere el costo mínimo en «viene» vacío (+0,03 pp en vez de +0,16 pp) se puede aplicar solo a mitad de recorrido: queda el efecto sobre falsas alarmas (−0,31 pp) y se pierde casi todo el efecto sobre el MAE (−0,4 s) y sobre la 42 (MAE 197 → 193 s).

## Especificación (va en el pipeline; la app la porta)

Regla causal, solo pasado del mismo coche, en `prediccion/v2/geo_assign.py` junto a `direction_from_history` (propuesta, contrato 2.4; no se implementó):
- `stationary_run(pings, shape, window_s=300, min_advance_m=50)`: con los mismos pings y la misma proyección que `direction_from_history` (pings pasados de ≤ `HISTORY_WINDOW_S` con `ts` menor que el actual, más el actual; racha final de pings a ≤ `TOL_M` del shape), toma los pings de la racha de los últimos `window_s` s. Es evaluable solo si hay al menos 2 y cubren la ventana (el más viejo a ≤ `window_s` − 90 s del actual; coche recién aparecido o con racha cortada: no se marca). Marca `detenido` si `max(d) − min(d)` (distancia a lo largo del shape) < `min_advance_m`.
- Tratamiento: un coche `detenido` no se descarta: se informa como «sentido sin confirmar» (provisional) con su ETA, y en la lista se ordena después de todo coche no marcado (se muestran primero los «viene», luego «puede venir» y «sentido sin confirmar» no marcados por ETA, y al final los marcados por ETA), tope de 5.
- Parámetros al `manifest.json["assignment"]`: `stationary_window_s`, `stationary_min_advance_m`, `stationary_rule`.
- Evaluación en el replay: el coche se marca sobre el shape del ETA anunciado (o el primer shape compatible que sirve la parada si está «llegando»); no se probó por shape. Es una simplificación del arnés.

## Método

- **Una pasada de replay base y variantes derivadas** (`extrae.py`, `deriva.py`): descartar un coche o bajarlo de grupo no cambia las predicciones de los demás coches (ni el modelo, ni «último coche», que usa pings de los otros), así que se corrió la predicción una sola vez por (día, línea, parada, t) y por cada coche con ping vigente se guardó grupo, ETA, paso real y la variable de avance. Cada variante se deriva rearmando la lista de 5 (`build_list`: «viene» por ETA, luego «puede venir» y provisionales por ETA). Verificado: la base derivada reproduce `core.evaluate_line` fila por fila (listados, ETA, `has_seguro`, `ann0_*`, `real_next_s`, pasos corregidos, `unv`, `past`; `test_equiv.py`).
- **Avance:** `max(d) − min(d)` de los pings de la racha final (a ≤ 45 m del shape candidato, la misma que usa `trailing_run`) dentro de los últimos N min; los pings con ts del actual hacia atrás; N ∈ {5, 10, 15} min; mínimo ∈ {20, 50, 100} m. Coche marcado = avance < mínimo con la racha cubriendo la ventana.
- **Tratamientos:** (a) descartar; (b1) pasa a «sentido sin confirmar» y compite por ETA junto con «puede venir» (como en la presentación del replay); (b2) ídem y al final de la lista.
- **Posición:** cabecera = distancia a lo largo del shape < 300 m (`terminal_zone_m`), mitad = el resto.
- **Métricas:** las de `ARQUITECTURA.md` §5 con la vara corregida: falsas alarmas; causa C = falsa alarma que `falsas/clasif.parquet` (FALSAS_ALARMAS.md, clasificación jerárquica sobre la base) clasifica C, en pp de los evaluados; omisión (visibles que pasan ≤ 10 min, no listados; 3–7 min; primer coche que pasa); «viene» vacío; MAE del próximo coche anunciado (`ann0`) con real en 3–7 min; llega antes / después > 60 s. Un coche nuevo listado por la variante que no estaba en la base no tiene causa asignada y no cuenta en C (0,01 % de los listados).
- **Dispersión:** cada celda es la media de los 10 días ± desvío día a día (las 12 líneas juntas por día). La decisión se toma con la diferencia pareada contra base por día (media ± desvío; ↑ / ↓ = días con diferencia > 0 / < 0). Los agregados ponderados (`out/pooled.csv`) difieren levemente de las medias de días (falsas alarmas base 14,7 % contra 15,0 %).
- **Salvedades:** una corrida (sin semillas, 10 días); el arnés marca por vehículo sobre un shape (no por shape); causa C viene de una clasificación hecha con la vara anterior; no se probó N < 5 min ni la interacción con el factor de anuncio; los días y paradas son los de V3_PRODUCCION.md.

## Tablas

Archivos: `data/ml/replay/detenido/{extrae.py, deriva.py, agrega.py, tablas.py, tablas_md.py, pareado.py, test_equiv.py}`, datos `run2/` (extracción con la vara corregida), `run2_sg/` (la misma extracción con la verdad recalculada sin geometría; `run2/` conserva la versión con geometría), `out/` (`stats.csv`, `daily.csv`, `byline.csv`, `pooled.csv`, `pareado.csv`, `flags.csv`; con geometría en `out_con_geometria/`), vara anterior en `run/` y `out_vara_anterior/`.

### T1. Grilla completa (posición: cualquiera). Media de los 10 días ± desvío día a día

| variante | falsas alarmas % | falsas alarmas causa C (pp de los listados) | omisión % | omisión 3–7 min % | omisión 1.er coche % | «viene» vacío % | MAE próx. 3–7 (s) | llega antes >60 s % | llega después >60 s % |
|---|---|---|---|---|---|---|---|---|---|
| base (regla vigente, sin filtro) | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.4 ± 2.1 | 99 ± 12 | 15.6 ± 1.1 | 25.4 ± 5.9 |
| 5 min, 20 m, (a) descartar | 14.3 ± 1.6 | 0.89 ± 0.53 | 10.6 ± 2.1 | 9.4 ± 1.5 | 6.7 ± 0.6 | 11.5 ± 2.1 | 96 ± 12 | 15.7 ± 1.1 | 25.0 ± 5.9 |
| 5 min, 20 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.5 ± 2.1 | 98 ± 12 | 15.7 ± 1.1 | 25.1 ± 5.9 |
| 5 min, 20 m, (b2) provisional y al final | 14.6 ± 1.8 | 1.07 ± 0.58 | 10.1 ± 2.3 | 8.8 ± 1.7 | 6.3 ± 0.5 | 11.5 ± 2.1 | 97 ± 12 | 15.7 ± 1.1 | 25.1 ± 5.9 |
| 5 min, 50 m, (a) descartar | 14.2 ± 1.6 | 0.89 ± 0.53 | 10.6 ± 2.1 | 9.5 ± 1.5 | 6.7 ± 0.6 | 11.5 ± 2.1 | 96 ± 12 | 15.7 ± 1.1 | 25.0 ± 5.9 |
| 5 min, 50 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.5 ± 2.1 | 98 ± 12 | 15.7 ± 1.1 | 25.1 ± 5.9 |
| 5 min, 50 m, (b2) provisional y al final | 14.6 ± 1.8 | 1.06 ± 0.58 | 10.1 ± 2.3 | 8.8 ± 1.7 | 6.3 ± 0.5 | 11.5 ± 2.1 | 96 ± 12 | 15.7 ± 1.1 | 25.1 ± 5.9 |
| 5 min, 100 m, (a) descartar | 14.2 ± 1.6 | 0.89 ± 0.53 | 10.8 ± 2.1 | 9.6 ± 1.5 | 6.8 ± 0.5 | 11.6 ± 2.1 | 96 ± 12 | 15.7 ± 1.1 | 25.0 ± 5.9 |
| 5 min, 100 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.6 ± 2.1 | 98 ± 12 | 15.8 ± 1.1 | 25.1 ± 5.9 |
| 5 min, 100 m, (b2) provisional y al final | 14.6 ± 1.8 | 1.06 ± 0.58 | 10.1 ± 2.3 | 8.9 ± 1.7 | 6.3 ± 0.5 | 11.6 ± 2.1 | 96 ± 12 | 15.8 ± 1.1 | 25.0 ± 5.9 |
| 10 min, 20 m, (a) descartar | 14.5 ± 1.7 | 1.01 ± 0.60 | 10.3 ± 2.2 | 9.1 ± 1.6 | 6.5 ± 0.5 | 11.4 ± 2.1 | 98 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 10 min, 20 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.4 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 10 min, 20 m, (b2) provisional y al final | 14.7 ± 1.8 | 1.14 ± 0.63 | 10.1 ± 2.3 | 8.8 ± 1.7 | 6.3 ± 0.5 | 11.4 ± 2.1 | 98 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 10 min, 50 m, (a) descartar | 14.5 ± 1.7 | 1.00 ± 0.60 | 10.3 ± 2.2 | 9.1 ± 1.6 | 6.5 ± 0.5 | 11.5 ± 2.1 | 98 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 10 min, 50 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.5 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 10 min, 50 m, (b2) provisional y al final | 14.7 ± 1.8 | 1.13 ± 0.63 | 10.1 ± 2.3 | 8.8 ± 1.7 | 6.3 ± 0.5 | 11.5 ± 2.1 | 98 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 10 min, 100 m, (a) descartar | 14.5 ± 1.7 | 1.00 ± 0.60 | 10.4 ± 2.2 | 9.1 ± 1.6 | 6.5 ± 0.5 | 11.5 ± 2.1 | 98 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 10 min, 100 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.5 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 10 min, 100 m, (b2) provisional y al final | 14.7 ± 1.8 | 1.13 ± 0.63 | 10.1 ± 2.3 | 8.9 ± 1.7 | 6.3 ± 0.5 | 11.5 ± 2.1 | 98 ± 12 | 15.7 ± 1.1 | 25.2 ± 5.9 |
| 15 min, 20 m, (a) descartar | 14.8 ± 1.8 | 1.31 ± 0.82 | 10.2 ± 2.2 | 9.0 ± 1.6 | 6.4 ± 0.6 | 11.4 ± 2.1 | 99 ± 12 | 15.6 ± 1.1 | 25.3 ± 5.9 |
| 15 min, 20 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.4 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.3 ± 5.9 |
| 15 min, 20 m, (b2) provisional y al final | 14.9 ± 1.9 | 1.35 ± 0.83 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.5 | 11.4 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.3 ± 5.9 |
| 15 min, 50 m, (a) descartar | 14.8 ± 1.8 | 1.31 ± 0.82 | 10.2 ± 2.2 | 9.0 ± 1.6 | 6.4 ± 0.6 | 11.4 ± 2.1 | 99 ± 12 | 15.6 ± 1.1 | 25.3 ± 5.9 |
| 15 min, 50 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.4 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.3 ± 5.9 |
| 15 min, 50 m, (b2) provisional y al final | 14.9 ± 1.9 | 1.35 ± 0.83 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.5 | 11.4 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.3 ± 5.9 |
| 15 min, 100 m, (a) descartar | 14.8 ± 1.8 | 1.31 ± 0.82 | 10.2 ± 2.2 | 9.0 ± 1.6 | 6.4 ± 0.6 | 11.4 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.3 ± 5.9 |
| 15 min, 100 m, (b1) a provisional | 15.0 ± 1.9 | 1.44 ± 0.90 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.6 | 11.4 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.3 ± 5.9 |
| 15 min, 100 m, (b2) provisional y al final | 14.9 ± 1.9 | 1.35 ± 0.83 | 10.1 ± 2.3 | 8.9 ± 1.6 | 6.3 ± 0.5 | 11.4 ± 2.1 | 99 ± 12 | 15.7 ± 1.1 | 25.3 ± 5.9 |

### T2. Diferencia pareada contra base, por día (media ± desvío; días con diferencia > 0 ↑ / < 0 ↓), posición cualquiera

| variante | falsas alarmas % | falsas alarmas causa C (pp de los listados) | omisión % | omisión 3–7 min % | omisión 1.er coche % | «viene» vacío % | MAE próx. 3–7 (s) | llega antes >60 s % | llega después >60 s % |
|---|---|---|---|---|---|---|---|---|---|
| 5 min, 20 m, (a) descartar | -0.7 ± 0.4 (0↑/10↓) | -0.55 ± 0.40 (0↑/10↓) | +0.5 ± 0.2 (10↑/0↓) | +0.5 ± 0.1 (10↑/0↓) | +0.4 ± 0.1 (10↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -2.39 ± 0.79 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.0 (0↑/10↓) |
| 5 min, 20 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.41 ± 0.14 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.2 ± 0.0 (0↑/10↓) |
| 5 min, 20 m, (b2) provisional y al final | -0.3 ± 0.2 (0↑/10↓) | -0.37 ± 0.33 (0↑/10↓) | -0.1 ± 0.1 (1↑/9↓) | -0.1 ± 0.1 (1↑/9↓) | -0.0 ± 0.1 (7↑/3↓) | +0.1 ± 0.0 (10↑/0↓) | -2.26 ± 0.83 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.0 (0↑/10↓) |
| 5 min, 50 m, (a) descartar | -0.7 ± 0.4 (0↑/10↓) | -0.55 ± 0.40 (0↑/10↓) | +0.5 ± 0.2 (10↑/0↓) | +0.5 ± 0.1 (10↑/0↓) | +0.4 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | -2.58 ± 0.92 (0↑/10↓) | +0.1 ± 0.0 (9↑/1↓) | -0.4 ± 0.1 (0↑/10↓) |
| 5 min, 50 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | -0.41 ± 0.14 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.0 (0↑/10↓) |
| 5 min, 50 m, (b2) provisional y al final | -0.3 ± 0.2 (0↑/10↓) | -0.38 ± 0.33 (0↑/10↓) | -0.0 ± 0.1 (2↑/7↓) | -0.1 ± 0.1 (2↑/8↓) | -0.0 ± 0.1 (7↑/3↓) | +0.2 ± 0.1 (10↑/0↓) | -2.44 ± 0.91 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.0 (0↑/10↓) |
| 5 min, 100 m, (a) descartar | -0.7 ± 0.4 (0↑/10↓) | -0.55 ± 0.40 (0↑/10↓) | +0.6 ± 0.2 (10↑/0↓) | +0.7 ± 0.2 (10↑/0↓) | +0.5 ± 0.2 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | -2.52 ± 0.93 (0↑/10↓) | +0.1 ± 0.1 (10↑/0↓) | -0.4 ± 0.1 (0↑/10↓) |
| 5 min, 100 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | -0.37 ± 0.21 (1↑/9↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.1 (0↑/10↓) |
| 5 min, 100 m, (b2) provisional y al final | -0.3 ± 0.2 (0↑/10↓) | -0.38 ± 0.33 (0↑/10↓) | -0.0 ± 0.1 (7↑/3↓) | -0.0 ± 0.1 (7↑/3↓) | +0.0 ± 0.1 (7↑/3↓) | +0.2 ± 0.1 (10↑/0↓) | -2.38 ± 0.93 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.1 (0↑/10↓) |
| 10 min, 20 m, (a) descartar | -0.5 ± 0.3 (0↑/10↓) | -0.43 ± 0.36 (0↑/10↓) | +0.2 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (9↑/1↓) | +0.2 ± 0.1 (9↑/1↓) | +0.1 ± 0.0 (10↑/0↓) | -0.81 ± 0.50 (0↑/10↓) | +0.0 ± 0.0 (8↑/2↓) | -0.2 ± 0.0 (0↑/10↓) |
| 10 min, 20 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.16 ± 0.13 (1↑/9↓) | +0.0 ± 0.0 (10↑/0↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 20 m, (b2) provisional y al final | -0.2 ± 0.1 (0↑/10↓) | -0.30 ± 0.29 (0↑/10↓) | -0.1 ± 0.1 (1↑/9↓) | -0.1 ± 0.1 (0↑/9↓) | -0.0 ± 0.1 (6↑/4↓) | +0.1 ± 0.0 (10↑/0↓) | -0.76 ± 0.47 (0↑/10↓) | +0.0 ± 0.0 (8↑/1↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 50 m, (a) descartar | -0.5 ± 0.3 (0↑/10↓) | -0.44 ± 0.36 (0↑/10↓) | +0.2 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.92 ± 0.52 (0↑/10↓) | +0.0 ± 0.0 (8↑/2↓) | -0.2 ± 0.0 (0↑/10↓) |
| 10 min, 50 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.17 ± 0.14 (1↑/9↓) | +0.0 ± 0.0 (10↑/0↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 50 m, (b2) provisional y al final | -0.2 ± 0.1 (0↑/10↓) | -0.31 ± 0.29 (0↑/10↓) | -0.1 ± 0.1 (2↑/8↓) | -0.1 ± 0.1 (1↑/8↓) | -0.0 ± 0.1 (6↑/4↓) | +0.1 ± 0.0 (10↑/0↓) | -0.86 ± 0.51 (0↑/10↓) | +0.0 ± 0.0 (8↑/1↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 100 m, (a) descartar | -0.5 ± 0.3 (0↑/10↓) | -0.44 ± 0.35 (0↑/10↓) | +0.2 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.93 ± 0.52 (0↑/10↓) | +0.0 ± 0.0 (9↑/1↓) | -0.2 ± 0.0 (0↑/10↓) |
| 10 min, 100 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.19 ± 0.15 (1↑/9↓) | +0.0 ± 0.0 (10↑/0↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 100 m, (b2) provisional y al final | -0.2 ± 0.1 (0↑/10↓) | -0.31 ± 0.29 (0↑/10↓) | -0.0 ± 0.1 (4↑/6↓) | -0.1 ± 0.1 (3↑/7↓) | -0.0 ± 0.1 (7↑/3↓) | +0.1 ± 0.0 (10↑/0↓) | -0.88 ± 0.50 (0↑/10↓) | +0.0 ± 0.0 (9↑/0↓) | -0.2 ± 0.0 (0↑/10↓) |
| 15 min, 20 m, (a) descartar | -0.1 ± 0.1 (0↑/10↓) | -0.13 ± 0.11 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | +0.1 ± 0.0 (9↑/1↓) | +0.1 ± 0.0 (10↑/0↓) | +0.0 ± 0.0 (9↑/0↓) | -0.24 ± 0.51 (2↑/8↓) | +0.0 ± 0.0 (7↑/3↓) | -0.0 ± 0.0 (0↑/10↓) |
| 15 min, 20 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (9↑/0↓) | -0.02 ± 0.03 (3↑/7↓) | +0.0 ± 0.0 (9↑/0↓) | -0.0 ± 0.0 (0↑/10↓) |
| 15 min, 20 m, (b2) provisional y al final | -0.1 ± 0.0 (0↑/10↓) | -0.09 ± 0.08 (0↑/10↓) | -0.0 ± 0.0 (2↑/7↓) | -0.0 ± 0.0 (3↑/7↓) | -0.0 ± 0.0 (5↑/5↓) | +0.0 ± 0.0 (9↑/0↓) | -0.22 ± 0.52 (3↑/7↓) | +0.0 ± 0.0 (8↑/2↓) | -0.0 ± 0.0 (0↑/9↓) |
| 15 min, 50 m, (a) descartar | -0.2 ± 0.1 (0↑/10↓) | -0.13 ± 0.12 (0↑/10↓) | +0.1 ± 0.1 (10↑/0↓) | +0.1 ± 0.1 (9↑/1↓) | +0.1 ± 0.0 (10↑/0↓) | +0.0 ± 0.0 (9↑/0↓) | -0.25 ± 0.50 (1↑/9↓) | +0.0 ± 0.0 (7↑/3↓) | -0.0 ± 0.0 (0↑/10↓) |
| 15 min, 50 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (9↑/0↓) | -0.02 ± 0.03 (3↑/7↓) | +0.0 ± 0.0 (9↑/0↓) | -0.0 ± 0.0 (0↑/10↓) |
| 15 min, 50 m, (b2) provisional y al final | -0.1 ± 0.0 (0↑/10↓) | -0.09 ± 0.09 (0↑/10↓) | -0.0 ± 0.0 (2↑/7↓) | -0.0 ± 0.0 (3↑/7↓) | -0.0 ± 0.0 (6↑/3↓) | +0.0 ± 0.0 (9↑/0↓) | -0.24 ± 0.52 (3↑/7↓) | +0.0 ± 0.0 (8↑/2↓) | -0.0 ± 0.0 (0↑/9↓) |
| 15 min, 100 m, (a) descartar | -0.2 ± 0.1 (0↑/10↓) | -0.13 ± 0.11 (0↑/10↓) | +0.1 ± 0.1 (10↑/0↓) | +0.1 ± 0.1 (10↑/0↓) | +0.1 ± 0.1 (10↑/0↓) | +0.0 ± 0.0 (9↑/0↓) | -0.25 ± 0.51 (1↑/9↓) | +0.0 ± 0.0 (8↑/2↓) | -0.0 ± 0.0 (0↑/10↓) |
| 15 min, 100 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (9↑/0↓) | -0.02 ± 0.04 (2↑/8↓) | +0.0 ± 0.0 (10↑/0↓) | -0.0 ± 0.0 (0↑/10↓) |
| 15 min, 100 m, (b2) provisional y al final | -0.1 ± 0.0 (0↑/10↓) | -0.09 ± 0.09 (0↑/10↓) | -0.0 ± 0.0 (5↑/5↓) | -0.0 ± 0.0 (4↑/6↓) | -0.0 ± 0.0 (6↑/3↓) | +0.0 ± 0.0 (9↑/0↓) | -0.24 ± 0.53 (2↑/8↓) | +0.0 ± 0.0 (8↑/1↓) | -0.0 ± 0.0 (0↑/10↓) |

### T3. Cabecera contra mitad de recorrido (ventana 5 min, avance 50 m): diferencia pareada contra base

| variante | falsas alarmas % | falsas alarmas causa C (pp de los listados) | omisión % | omisión 3–7 min % | omisión 1.er coche % | «viene» vacío % | MAE próx. 3–7 (s) | llega antes >60 s % | llega después >60 s % |
|---|---|---|---|---|---|---|---|---|---|
| 5 min, 50 m, (a) descartar | -0.7 ± 0.4 (0↑/10↓) | -0.55 ± 0.40 (0↑/10↓) | +0.5 ± 0.2 (10↑/0↓) | +0.5 ± 0.1 (10↑/0↓) | +0.4 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | -2.58 ± 0.92 (0↑/10↓) | +0.1 ± 0.0 (9↑/1↓) | -0.4 ± 0.1 (0↑/10↓) |
| 5 min, 50 m, (a) descartar, solo cabecera | -0.4 ± 0.2 (0↑/10↓) | -0.22 ± 0.11 (0↑/10↓) | +0.5 ± 0.1 (10↑/0↓) | +0.6 ± 0.1 (10↑/0↓) | +0.3 ± 0.1 (10↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -2.13 ± 0.87 (0↑/10↓) | -0.0 ± 0.0 (3↑/7↓) | -0.1 ± 0.0 (0↑/10↓) |
| 5 min, 50 m, (a) descartar, solo mitad | -0.3 ± 0.2 (0↑/10↓) | -0.33 ± 0.32 (0↑/10↓) | +0.0 ± 0.1 (4↑/6↓) | -0.0 ± 0.1 (3↑/7↓) | +0.1 ± 0.1 (8↑/2↓) | +0.0 ± 0.0 (8↑/0↓) | -0.44 ± 0.17 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.0 (0↑/10↓) |
| 5 min, 50 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | -0.41 ± 0.14 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.0 (0↑/10↓) |
| 5 min, 50 m, (b1) a provisional, solo cabecera | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.14 ± 0.05 (0↑/10↓) | +0.0 ± 0.0 (7↑/0↓) | -0.1 ± 0.0 (0↑/10↓) |
| 5 min, 50 m, (b1) a provisional, solo mitad | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (8↑/0↓) | -0.26 ± 0.13 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.2 ± 0.0 (0↑/10↓) |
| 5 min, 50 m, (b2) provisional y al final | -0.3 ± 0.2 (0↑/10↓) | -0.38 ± 0.33 (0↑/10↓) | -0.0 ± 0.1 (2↑/7↓) | -0.1 ± 0.1 (2↑/8↓) | -0.0 ± 0.1 (7↑/3↓) | +0.2 ± 0.1 (10↑/0↓) | -2.44 ± 0.91 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.3 ± 0.0 (0↑/10↓) |
| 5 min, 50 m, (b2) provisional y al final, solo cabecera | -0.0 ± 0.0 (5↑/5↓) | -0.05 ± 0.03 (0↑/10↓) | +0.0 ± 0.0 (9↑/1↓) | +0.0 ± 0.0 (8↑/2↓) | +0.0 ± 0.0 (9↑/1↓) | +0.1 ± 0.0 (10↑/0↓) | -2.07 ± 0.88 (0↑/10↓) | -0.0 ± 0.0 (2↑/7↓) | -0.1 ± 0.0 (1↑/9↓) |
| 5 min, 50 m, (b2) provisional y al final, solo mitad | -0.3 ± 0.2 (0↑/10↓) | -0.32 ± 0.31 (0↑/10↓) | -0.1 ± 0.1 (2↑/8↓) | -0.1 ± 0.1 (1↑/9↓) | -0.0 ± 0.1 (7↑/3↓) | +0.0 ± 0.0 (8↑/0↓) | -0.36 ± 0.18 (0↑/10↓) | +0.1 ± 0.0 (10↑/0↓) | -0.2 ± 0.0 (0↑/10↓) |

### T3b. Idem con ventana 10 min, avance 50 m

| variante | falsas alarmas % | falsas alarmas causa C (pp de los listados) | omisión % | omisión 3–7 min % | omisión 1.er coche % | «viene» vacío % | MAE próx. 3–7 (s) | llega antes >60 s % | llega después >60 s % |
|---|---|---|---|---|---|---|---|---|---|
| 10 min, 50 m, (a) descartar | -0.5 ± 0.3 (0↑/10↓) | -0.44 ± 0.36 (0↑/10↓) | +0.2 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.92 ± 0.52 (0↑/10↓) | +0.0 ± 0.0 (8↑/2↓) | -0.2 ± 0.0 (0↑/10↓) |
| 10 min, 50 m, (a) descartar, solo cabecera | -0.2 ± 0.2 (0↑/10↓) | -0.17 ± 0.11 (0↑/10↓) | +0.2 ± 0.1 (10↑/0↓) | +0.3 ± 0.1 (10↑/0↓) | +0.2 ± 0.1 (10↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.72 ± 0.50 (2↑/8↓) | -0.0 ± 0.0 (2↑/8↓) | -0.0 ± 0.0 (2↑/8↓) |
| 10 min, 50 m, (a) descartar, solo mitad | -0.2 ± 0.1 (0↑/10↓) | -0.26 ± 0.27 (0↑/10↓) | -0.0 ± 0.1 (2↑/8↓) | -0.1 ± 0.1 (1↑/9↓) | +0.0 ± 0.1 (7↑/3↓) | +0.0 ± 0.0 (8↑/0↓) | -0.19 ± 0.12 (0↑/10↓) | +0.0 ± 0.0 (10↑/0↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 50 m, (b1) a provisional | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.17 ± 0.14 (1↑/9↓) | +0.0 ± 0.0 (10↑/0↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 50 m, (b1) a provisional, solo cabecera | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.1 ± 0.0 (10↑/0↓) | -0.02 ± 0.04 (2↑/8↓) | +0.0 ± 0.0 (4↑/0↓) | -0.0 ± 0.0 (0↑/9↓) |
| 10 min, 50 m, (b1) a provisional, solo mitad | +0.0 ± 0.0 (0↑/0↓) | +0.00 ± 0.00 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (0↑/0↓) | +0.0 ± 0.0 (8↑/0↓) | -0.16 ± 0.13 (1↑/9↓) | +0.0 ± 0.0 (10↑/0↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 50 m, (b2) provisional y al final | -0.2 ± 0.1 (0↑/10↓) | -0.31 ± 0.29 (0↑/10↓) | -0.1 ± 0.1 (2↑/8↓) | -0.1 ± 0.1 (1↑/8↓) | -0.0 ± 0.1 (6↑/4↓) | +0.1 ± 0.0 (10↑/0↓) | -0.86 ± 0.51 (0↑/10↓) | +0.0 ± 0.0 (8↑/1↓) | -0.1 ± 0.0 (0↑/10↓) |
| 10 min, 50 m, (b2) provisional y al final, solo cabecera | -0.0 ± 0.0 (2↑/8↓) | -0.05 ± 0.04 (0↑/10↓) | +0.0 ± 0.0 (9↑/0↓) | +0.0 ± 0.0 (8↑/0↓) | +0.0 ± 0.0 (8↑/1↓) | +0.1 ± 0.0 (10↑/0↓) | -0.70 ± 0.47 (1↑/9↓) | -0.0 ± 0.0 (3↑/6↓) | -0.0 ± 0.0 (3↑/7↓) |
| 10 min, 50 m, (b2) provisional y al final, solo mitad | -0.2 ± 0.1 (0↑/10↓) | -0.26 ± 0.27 (0↑/10↓) | -0.1 ± 0.1 (0↑/10↓) | -0.1 ± 0.1 (0↑/10↓) | -0.0 ± 0.1 (5↑/4↓) | +0.0 ± 0.0 (8↑/0↓) | -0.17 ± 0.14 (0↑/10↓) | +0.0 ± 0.0 (10↑/0↓) | -0.1 ± 0.0 (0↑/10↓) |

### T4. Coches que la regla marca entre los listados de la base (suma de 10 días): qué pasó con ellos

| ventana (min) | avance (m) | posición | marcados | pasan ≤10 min % | pasan en 3–7 min % | pasan en 40 min % | falsa alarma % | falsa alarma causa C % | inmóviles todo el horizonte % | estaban en «viene» % | a < 500 m de la parada % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | 20 | all | 48037 | 10.0 | 4.3 | 43.3 | 56.4 | 19.6 | 25.6 | 38.7 | 8.0 |
| 5 | 20 | cab | 33144 | 11.3 | 5.1 | 51.1 | 48.9 | 12.7 | 17.4 | 29.3 | 1.2 |
| 5 | 20 | mid | 14893 | 7.1 | 2.6 | 25.9 | 73.3 | 34.9 | 43.6 | 59.6 | 23.2 |
| 5 | 50 | all | 50982 | 10.5 | 4.5 | 44.3 | 55.4 | 18.7 | 24.4 | 39.4 | 8.0 |
| 5 | 50 | cab | 34674 | 11.6 | 5.3 | 51.5 | 48.5 | 12.2 | 16.8 | 29.4 | 1.2 |
| 5 | 50 | mid | 16308 | 8.0 | 3.0 | 28.9 | 70.2 | 32.5 | 40.6 | 60.6 | 22.5 |
| 5 | 100 | all | 54384 | 11.7 | 5.1 | 45.9 | 53.7 | 17.6 | 23.0 | 40.9 | 8.0 |
| 5 | 100 | cab | 36179 | 12.5 | 5.7 | 52.0 | 47.9 | 11.7 | 16.3 | 29.6 | 1.2 |
| 5 | 100 | mid | 18205 | 10.2 | 4.0 | 34.0 | 65.2 | 29.2 | 36.4 | 63.3 | 21.5 |
| 10 | 20 | all | 27321 | 8.0 | 3.4 | 36.3 | 63.4 | 26.8 | 35.1 | 40.4 | 9.0 |
| 10 | 20 | cab | 18333 | 9.5 | 4.2 | 45.5 | 54.4 | 17.4 | 24.0 | 33.6 | 0.8 |
| 10 | 20 | mid | 8988 | 4.9 | 1.8 | 17.4 | 81.8 | 46.0 | 57.5 | 54.3 | 25.8 |
| 10 | 50 | all | 29244 | 8.6 | 3.7 | 37.1 | 62.6 | 25.7 | 33.7 | 40.5 | 9.0 |
| 10 | 50 | cab | 19469 | 10.1 | 4.5 | 46.0 | 53.9 | 16.8 | 23.1 | 33.2 | 0.8 |
| 10 | 50 | mid | 9775 | 5.6 | 2.1 | 19.3 | 79.8 | 43.6 | 54.8 | 55.3 | 25.4 |
| 10 | 100 | all | 30751 | 9.2 | 4.0 | 38.2 | 61.5 | 24.6 | 32.3 | 41.1 | 8.9 |
| 10 | 100 | cab | 20335 | 10.8 | 4.8 | 46.5 | 53.4 | 16.2 | 22.4 | 33.3 | 0.8 |
| 10 | 100 | mid | 10416 | 6.1 | 2.3 | 21.8 | 77.3 | 41.0 | 51.8 | 56.4 | 24.6 |
| 15 | 20 | all | 8002 | 8.8 | 3.5 | 36.4 | 63.3 | 27.9 | 37.5 | 40.6 | 9.9 |
| 15 | 20 | cab | 5178 | 10.9 | 4.5 | 46.5 | 53.4 | 19.4 | 26.7 | 34.7 | 0.7 |
| 15 | 20 | mid | 2824 | 5.0 | 1.7 | 17.9 | 81.4 | 43.3 | 57.5 | 51.5 | 26.8 |
| 15 | 50 | all | 8964 | 9.5 | 3.8 | 37.7 | 62.1 | 26.2 | 35.4 | 40.7 | 10.1 |
| 15 | 50 | cab | 5655 | 11.7 | 4.9 | 47.3 | 52.6 | 18.3 | 25.2 | 33.5 | 0.7 |
| 15 | 50 | mid | 3309 | 5.8 | 2.1 | 21.2 | 78.2 | 39.8 | 53.0 | 52.9 | 26.3 |
| 15 | 100 | all | 9630 | 10.5 | 4.3 | 39.0 | 60.7 | 24.6 | 33.3 | 42.0 | 9.7 |
| 15 | 100 | cab | 6073 | 12.8 | 5.4 | 48.3 | 51.7 | 17.3 | 23.7 | 34.4 | 0.7 |
| 15 | 100 | mid | 3557 | 6.5 | 2.3 | 23.2 | 76.2 | 37.0 | 49.8 | 55.0 | 25.2 |

### T5. Por línea: base → 5 min, 50 m, (b2) provisional y al final (10 días; la 26 solo 3)

| línea | falsas alarmas % | causa C (pp) | omisión % | omisión 3–7 % | «viene» vacío % | MAE (s) | antes % | después % |
|---|---|---|---|---|---|---|---|---|
| 26 | 2.4 → 2.3 | 0.46 → 0.45 | 6.0 → 6.0 | 4.9 → 5.0 | 2.0 → 2.0 | 76 → 75 | 12.3 → 12.4 | 28.6 → 28.4 |
| 39 | 23.6 → 23.5 | 0.60 → 0.49 | 8.7 → 8.6 | 6.4 → 6.2 | 24.6 → 24.6 | 88 → 87 | 12.6 → 12.6 | 27.9 → 27.7 |
| 42 | 31.6 → 29.4 | 10.21 → 6.91 | 8.9 → 7.8 | 7.5 → 6.4 | 12.9 → 13.8 | 197 → 170 | 16.8 → 16.7 | 33.4 → 32.0 |
| 50 | 23.0 → 22.9 | 0.70 → 0.67 | 6.7 → 6.7 | 5.9 → 5.9 | 14.1 → 14.2 | 78 → 78 | 16.4 → 16.4 | 22.8 → 22.7 |
| 92 | 6.7 → 6.5 | 0.40 → 0.33 | 5.1 → 5.3 | 4.9 → 5.1 | 2.8 → 2.8 | 67 → 68 | 14.3 → 14.4 | 20.5 → 20.3 |
| 106 | 13.8 → 13.6 | 0.57 → 0.54 | 16.2 → 16.2 | 14.1 → 14.1 | 5.4 → 5.5 | 148 → 147 | 14.9 → 15.1 | 29.6 → 29.0 |
| 107 | 5.2 → 5.3 | 0.00 → 0.00 | 14.9 → 14.9 | 14.1 → 14.1 | 19.2 → 19.3 | 114 → 114 | 27.0 → 27.0 | 19.9 → 19.7 |
| 108 | 11.5 → 11.4 | 0.52 → 0.47 | 7.2 → 7.2 | 7.2 → 7.2 | 3.6 → 4.0 | 75 → 74 | 13.9 → 14.0 | 23.8 → 23.6 |
| 124 | 4.3 → 4.3 | 0.60 → 0.58 | 4.1 → 4.1 | 3.9 → 4.0 | 2.6 → 2.8 | 72 → 72 | 13.1 → 13.1 | 21.9 → 21.8 |
| 132 | 13.5 → 13.4 | 0.44 → 0.43 | 15.7 → 15.7 | 12.2 → 12.3 | 17.7 → 17.7 | 88 → 88 | 14.8 → 14.9 | 27.8 → 27.6 |
| 151 | 6.6 → 6.4 | 0.03 → 0.02 | 12.9 → 13.0 | 11.7 → 11.8 | 8.9 → 8.9 | 84 → 84 | 13.7 → 14.0 | 30.2 → 29.9 |
| 168 | 22.3 → 22.2 | 0.24 → 0.23 | 8.9 → 9.0 | 9.2 → 9.2 | 14.2 → 14.3 | 96 → 96 | 17.7 → 17.7 | 22.1 → 22.1 |

### T5b. Por línea: base → 5 min, 50 m, (b2) provisional y al final, solo mitad

| línea | falsas alarmas % | causa C (pp) | omisión % | omisión 3–7 % | «viene» vacío % | MAE (s) | antes % | después % |
|---|---|---|---|---|---|---|---|---|
| 26 | 2.4 → 2.3 | 0.46 → 0.46 | 6.0 → 6.0 | 4.9 → 5.0 | 2.0 → 2.0 | 76 → 75 | 12.3 → 12.4 | 28.6 → 28.4 |
| 39 | 23.6 → 23.5 | 0.60 → 0.50 | 8.7 → 8.6 | 6.4 → 6.2 | 24.6 → 24.6 | 88 → 88 | 12.6 → 12.6 | 27.9 → 27.9 |
| 42 | 31.6 → 29.5 | 10.21 → 7.25 | 8.9 → 7.9 | 7.5 → 6.4 | 12.9 → 13.0 | 197 → 193 | 16.8 → 17.1 | 33.4 → 32.0 |
| 50 | 23.0 → 22.9 | 0.70 → 0.70 | 6.7 → 6.7 | 5.9 → 5.9 | 14.1 → 14.1 | 78 → 78 | 16.4 → 16.4 | 22.8 → 22.7 |
| 92 | 6.7 → 6.6 | 0.40 → 0.40 | 5.1 → 5.2 | 4.9 → 5.1 | 2.8 → 2.8 | 67 → 68 | 14.3 → 14.4 | 20.5 → 20.4 |
| 106 | 13.8 → 13.6 | 0.57 → 0.57 | 16.2 → 16.2 | 14.1 → 14.0 | 5.4 → 5.4 | 148 → 148 | 14.9 → 15.1 | 29.6 → 29.2 |
| 107 | 5.2 → 5.3 | 0.00 → 0.00 | 14.9 → 14.9 | 14.1 → 14.1 | 19.2 → 19.3 | 114 → 114 | 27.0 → 27.0 | 19.9 → 19.7 |
| 108 | 11.5 → 11.5 | 0.52 → 0.52 | 7.2 → 7.2 | 7.2 → 7.3 | 3.6 → 3.6 | 75 → 75 | 13.9 → 14.0 | 23.8 → 23.7 |
| 124 | 4.3 → 4.3 | 0.60 → 0.60 | 4.1 → 4.1 | 3.9 → 4.0 | 2.6 → 2.6 | 72 → 72 | 13.1 → 13.1 | 21.9 → 21.9 |
| 132 | 13.5 → 13.4 | 0.44 → 0.44 | 15.7 → 15.7 | 12.2 → 12.3 | 17.7 → 17.7 | 88 → 88 | 14.8 → 14.9 | 27.8 → 27.7 |
| 151 | 6.6 → 6.4 | 0.03 → 0.02 | 12.9 → 13.0 | 11.7 → 11.8 | 8.9 → 8.9 | 84 → 84 | 13.7 → 13.9 | 30.2 → 30.0 |
| 168 | 22.3 → 22.2 | 0.24 → 0.24 | 8.9 → 9.0 | 9.2 → 9.2 | 14.2 → 14.2 | 96 → 96 | 17.7 → 17.7 | 22.1 → 22.1 |

### T5b. Por línea: base → 5 min, 50 m, (a) descartar

| línea | falsas alarmas % | causa C (pp) | omisión % | omisión 3–7 % | «viene» vacío % | MAE (s) | antes % | después % |
|---|---|---|---|---|---|---|---|---|
| 26 | 2.4 → 2.2 | 0.46 → 0.34 | 6.0 → 6.2 | 4.9 → 5.1 | 2.0 → 2.0 | 76 → 75 | 12.3 → 12.4 | 28.6 → 28.4 |
| 39 | 23.6 → 23.3 | 0.60 → 0.35 | 8.7 → 9.0 | 6.4 → 6.7 | 24.6 → 24.6 | 88 → 87 | 12.6 → 12.6 | 27.9 → 27.7 |
| 42 | 31.6 → 28.6 | 10.21 → 5.92 | 8.9 → 8.4 | 7.5 → 7.0 | 12.9 → 13.8 | 197 → 170 | 16.8 → 16.6 | 33.4 → 31.9 |
| 50 | 23.0 → 22.3 | 0.70 → 0.50 | 6.7 → 6.7 | 5.9 → 5.9 | 14.1 → 14.2 | 78 → 78 | 16.4 → 16.4 | 22.8 → 22.7 |
| 92 | 6.7 → 6.4 | 0.40 → 0.26 | 5.1 → 5.4 | 4.9 → 5.2 | 2.8 → 2.8 | 67 → 68 | 14.3 → 14.4 | 20.5 → 20.3 |
| 106 | 13.8 → 12.7 | 0.57 → 0.53 | 16.2 → 17.0 | 14.1 → 14.8 | 5.4 → 5.5 | 148 → 147 | 14.9 → 15.1 | 29.6 → 29.0 |
| 107 | 5.2 → 5.2 | 0.00 → 0.00 | 14.9 → 15.3 | 14.1 → 14.5 | 19.2 → 19.3 | 114 → 113 | 27.0 → 26.9 | 19.9 → 19.7 |
| 108 | 11.5 → 10.7 | 0.52 → 0.29 | 7.2 → 7.7 | 7.2 → 7.7 | 3.6 → 4.0 | 75 → 74 | 13.9 → 14.1 | 23.8 → 23.3 |
| 124 | 4.3 → 4.1 | 0.60 → 0.49 | 4.1 → 4.5 | 3.9 → 4.3 | 2.6 → 2.8 | 72 → 72 | 13.1 → 13.0 | 21.9 → 21.8 |
| 132 | 13.5 → 13.3 | 0.44 → 0.37 | 15.7 → 16.0 | 12.2 → 12.4 | 17.7 → 17.7 | 88 → 88 | 14.8 → 14.8 | 27.8 → 27.7 |
| 151 | 6.6 → 6.5 | 0.03 → 0.02 | 12.9 → 14.8 | 11.7 → 14.3 | 8.9 → 8.9 | 84 → 84 | 13.7 → 14.0 | 30.2 → 29.8 |
| 168 | 22.3 → 22.1 | 0.24 → 0.14 | 8.9 → 9.0 | 9.2 → 9.2 | 14.2 → 14.3 | 96 → 96 | 17.7 → 17.7 | 22.1 → 22.0 |
