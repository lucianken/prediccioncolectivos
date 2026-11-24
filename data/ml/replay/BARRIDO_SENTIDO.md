# Barrido de la regla de sentido (racha final) y curva de arranque

> **Registro (2026-11-16):** las falsas alarmas, la omisión y el «viene» vacío de este informe usan la definición anterior de la vara de producto. Siguen válidos como comparaciones relativas; las falsas alarmas absolutas están infladas (≈ 24,5 contra ≈ 14,7 % con la vara corregida) y la omisión y el «viene» vacío absolutos algo subestimados. Ver `VARA_CORREGIDA.md` y `ARQUITECTURA.md` §5.

Medido el 2026-11-16 sobre el replay de la vara de producto (`prediccion/replay/`, variante `base`, modelo de producción `data/ml/export/path_v3_l1_s1`, lógica fijada en `prediccion/replay/pinned/`), 12 líneas de producción, los mismos 10 días de `V3_PRODUCCION.md` (15–20 sep. y 3, 4, 6, 8 oct.; la línea 26 solo 15–17 sep.), 40 paradas por línea, instantes cada 10 min de 6 a 23 h. Sin entrenar nada; no se modificó `pinned/` ni `prediccion/v2/geo_assign.py`. La regla `base` reproduce `V3_PRODUCCION.md` (MAE 107 s, llega antes 17,0 %, llega después 24,5 %, falsas alarmas 24,0 %, omisión 17,0 %, «viene» vacío 13,7 %).

## Qué se midió

- **Reglas.** `base`: la vigente (`direction_from_history`: ≥ 80 % de los pings de la ventana de 15 min a ≤ 45 m del shape, fracción de avance ≥ 0,6, avance neto ≥ 40 m). `racha final (k, avance)`: el sentido se evalúa solo sobre la racha final de pings consecutivos a ≤ 45 m del shape (desde el último ping fuera hasta el actual); se exige al menos k pings en la racha, fracción de avance ≥ 0,6 (fija) y avance neto ≥ el valor indicado. TOL_M 45 y MARGIN_M 20 fijos. k = 2, 3, 4 por avance = 20, 40, 80 m, más un eje aparte de MIN_FORWARD_FRAC (0,5 y 0,75) sobre k = 2 / 40 m. La regla se reemplaza en memoria en el replay; el resto de la lógica de la app es idéntica.
- **Métricas.** Omisión: coches con ping vigente que pasan en ≤ 10 min y no están en la lista de 5 (total; con ETA real en 3–7 min; el primer coche que pasa por la parada). Falsas alarmas: listados que no pasan en 40 min. «Viene» vacío: instantes con paso en ≤ 10 min sin ningún coche «viene». MAE del próximo coche anunciado con ETA real 3–7 min (hora común, `ann0`, igual que `V3_PRODUCCION.md`); «llega antes» = el coche llega más de 60 s antes de lo anunciado; «llega después» = más de 60 s después.
- **Dispersión.** Por día se agregan las 12 líneas; las tablas dan media de los 10 días ± desvío día a día [mín–máx]. Como los días comparten el nivel (un día difícil lo es para todas las reglas), el criterio de decisión es la **diferencia pareada con `base` día por día** (media ± desvío, y en cuántos de los 10 días la diferencia es > 0).
- **Curva de arranque.** El recorte limita a los últimos N pings (incluido el actual) los que usa la regla de sentido; el historial para el ETA y para «último coche» queda completo, para aislar el efecto de la regla. N = 1 es solo el ping actual. Se corrió para `base` y para k=2/20 m, k=2/40 m y k=3/40 m (con N < k la regla de racha final no puede confirmar sentido: igual que N = 1).
- Código y datos crudos: `data/ml/replay/barrido/` (`barrido_sentido.py`, `agg.py`, `mk.py`, `run/*.json`, `daily.csv`, `byline.csv`, `pooled.csv`).

## Resultados

### Barrido (historial completo de 15 min)

Cada celda: media de los 10 días ± desvío día a día [mín–máx].

| regla | omisión % | omisión 3–7 min % | omisión 1.er coche % | falsas alarmas % | «viene» vacío % | MAE próx. 3–7 (s) | llega antes >60 s % | llega después >60 s % |
|---|---|---|---|---|---|---|---|---|
| base (≥80 % de la ventana) | 16.5 ± 2.0 [13.1–19.0] | 16.1 ± 1.5 [13.3–18.2] | 12.7 ± 0.9 [10.9–14.3] | 24.4 ± 4.1 [19.6–32.1] | 13.9 ± 2.2 [10.9–17.3] | 107 ± 14 [81–128] | 17.0 ± 1.1 [15.5–19.3] | 24.3 ± 6.0 [16.0–33.1] |
| racha final k=2, avance ≥20 m | 8.7 ± 2.3 [5.3–11.3] | 7.9 ± 1.7 [5.3–9.9] | 4.4 ± 0.5 [3.6–5.2] | 24.9 ± 4.4 [20.2–33.2] | 10.2 ± 1.5 [8.3–13.0] | 97 ± 12 [78–118] | 14.4 ± 1.1 [13.3–17.1] | 26.2 ± 6.1 [17.4–35.0] |
| racha final k=2, avance ≥40 m | 8.7 ± 2.3 [5.3–11.4] | 7.9 ± 1.7 [5.3–10.0] | 4.4 ± 0.5 [3.6–5.2] | 24.9 ± 4.4 [20.2–33.2] | 10.1 ± 1.5 [8.3–13.0] | 98 ± 13 [78–120] | 14.4 ± 1.1 [13.4–17.1] | 26.2 ± 6.1 [17.4–35.0] |
| racha final k=2, avance ≥80 m | 8.7 ± 2.3 [5.3–11.4] | 7.9 ± 1.7 [5.3–10.0] | 4.5 ± 0.5 [3.6–5.2] | 24.9 ± 4.4 [20.2–33.2] | 10.2 ± 1.5 [8.3–13.0] | 98 ± 12 [78–119] | 14.4 ± 1.1 [13.4–17.1] | 26.2 ± 6.1 [17.4–35.0] |
| racha final k=3, avance ≥20 m | 8.7 ± 2.4 [5.3–11.6] | 8.0 ± 1.7 [5.3–10.2] | 4.5 ± 0.5 [3.6–5.3] | 25.0 ± 4.4 [20.2–33.3] | 10.2 ± 1.5 [8.4–13.0] | 98 ± 12 [78–120] | 14.4 ± 1.1 [13.5–17.3] | 26.2 ± 6.1 [17.4–34.9] |
| racha final k=3, avance ≥40 m | 8.7 ± 2.4 [5.3–11.6] | 8.0 ± 1.7 [5.3–10.2] | 4.5 ± 0.5 [3.6–5.3] | 25.0 ± 4.4 [20.3–33.3] | 10.2 ± 1.5 [8.4–13.0] | 99 ± 12 [78–120] | 14.5 ± 1.1 [13.6–17.3] | 26.2 ± 6.1 [17.4–34.9] |
| racha final k=3, avance ≥80 m | 8.7 ± 2.4 [5.3–11.6] | 8.0 ± 1.7 [5.3–10.2] | 4.5 ± 0.5 [3.7–5.3] | 25.0 ± 4.4 [20.2–33.3] | 10.2 ± 1.5 [8.4–13.0] | 99 ± 12 [78–120] | 14.5 ± 1.1 [13.6–17.3] | 26.2 ± 6.1 [17.4–34.9] |
| racha final k=4, avance ≥20 m | 8.8 ± 2.4 [5.3–11.9] | 8.1 ± 1.8 [5.2–10.4] | 4.6 ± 0.6 [3.7–5.4] | 25.1 ± 4.4 [20.3–33.4] | 10.4 ± 1.5 [8.4–13.1] | 100 ± 13 [80–128] | 14.6 ± 1.1 [13.8–17.3] | 26.2 ± 6.1 [17.5–34.8] |
| racha final k=4, avance ≥40 m | 8.8 ± 2.4 [5.3–11.9] | 8.1 ± 1.8 [5.2–10.4] | 4.6 ± 0.6 [3.7–5.4] | 25.1 ± 4.4 [20.3–33.4] | 10.4 ± 1.5 [8.4–13.1] | 100 ± 13 [80–128] | 14.6 ± 1.1 [13.8–17.3] | 26.2 ± 6.1 [17.5–34.8] |
| racha final k=4, avance ≥80 m | 8.8 ± 2.4 [5.3–11.9] | 8.1 ± 1.8 [5.2–10.4] | 4.6 ± 0.5 [3.7–5.4] | 25.1 ± 4.4 [20.3–33.4] | 10.4 ± 1.5 [8.4–13.1] | 100 ± 13 [80–128] | 14.6 ± 1.1 [13.9–17.3] | 26.2 ± 6.1 [17.5–34.8] |
| eje frac: k=2, 40 m, frac 0,5 | 8.5 ± 2.3 [5.2–11.2] | 7.8 ± 1.7 [5.2–9.8] | 4.3 ± 0.5 [3.4–5.1] | 24.9 ± 4.4 [20.2–33.2] | 10.0 ± 1.5 [8.2–12.9] | 98 ± 13 [78–120] | 14.3 ± 1.1 [13.3–17.1] | 26.2 ± 6.1 [17.4–35.0] |
| eje frac: k=2, 40 m, frac 0,75 | 8.9 ± 2.3 [5.5–11.5] | 8.1 ± 1.7 [5.5–10.1] | 4.7 ± 0.5 [3.9–5.6] | 24.9 ± 4.4 [20.2–33.2] | 10.4 ± 1.5 [8.5–13.3] | 98 ± 13 [78–120] | 14.4 ± 1.1 [13.4–17.1] | 26.1 ± 6.1 [17.4–35.0] |

### Diferencia pareada contra base (por día, luego media ± desvío; días con diferencia > 0)

| regla | omisión % | omisión 3–7 min % | omisión 1.er coche % | falsas alarmas % | «viene» vacío % | MAE próx. 3–7 (s) | llega antes >60 s % | llega después >60 s % |
|---|---|---|---|---|---|---|---|---|
| k=2, 20 m | -7.82 ± 0.76 (0/10) | -8.15 ± 0.67 (0/10) | -8.28 ± 0.68 (0/10) | +0.49 ± 0.47 (10/10) | -3.77 ± 0.91 (0/10) | -9.9 ± 4.2 (0/10) | -2.69 ± 0.47 (0/10) | +1.90 ± 0.29 (10/10) |
| k=2, 40 m | -7.83 ± 0.77 (0/10) | -8.15 ± 0.68 (0/10) | -8.29 ± 0.69 (0/10) | +0.51 ± 0.47 (10/10) | -3.79 ± 0.90 (0/10) | -8.6 ± 4.1 (0/10) | -2.66 ± 0.44 (0/10) | +1.91 ± 0.28 (10/10) |
| k=2, 80 m | -7.81 ± 0.77 (0/10) | -8.14 ± 0.69 (0/10) | -8.27 ± 0.70 (0/10) | +0.51 ± 0.47 (10/10) | -3.77 ± 0.90 (0/10) | -8.8 ± 4.0 (0/10) | -2.66 ± 0.44 (0/10) | +1.90 ± 0.27 (10/10) |
| k=3, 20 m | -7.74 ± 0.79 (0/10) | -8.06 ± 0.70 (0/10) | -8.21 ± 0.70 (0/10) | +0.57 ± 0.47 (10/10) | -3.70 ± 0.90 (0/10) | -8.6 ± 3.7 (0/10) | -2.59 ± 0.45 (0/10) | +1.92 ± 0.29 (10/10) |
| k=3, 40 m | -7.75 ± 0.79 (0/10) | -8.07 ± 0.70 (0/10) | -8.22 ± 0.70 (0/10) | +0.58 ± 0.47 (10/10) | -3.71 ± 0.90 (0/10) | -7.8 ± 3.5 (0/10) | -2.58 ± 0.43 (0/10) | +1.92 ± 0.29 (10/10) |
| k=3, 80 m | -7.74 ± 0.80 (0/10) | -8.05 ± 0.70 (0/10) | -8.21 ± 0.71 (0/10) | +0.59 ± 0.47 (10/10) | -3.70 ± 0.90 (0/10) | -7.7 ± 3.5 (0/10) | -2.56 ± 0.43 (0/10) | +1.91 ± 0.28 (10/10) |
| k=4, 20 m | -7.67 ± 0.84 (0/10) | -7.99 ± 0.73 (0/10) | -8.15 ± 0.73 (0/10) | +0.67 ± 0.45 (10/10) | -3.58 ± 0.90 (0/10) | -6.9 ± 4.5 (0/10) | -2.43 ± 0.47 (0/10) | +1.95 ± 0.34 (10/10) |
| k=4, 40 m | -7.68 ± 0.84 (0/10) | -8.00 ± 0.72 (0/10) | -8.16 ± 0.73 (0/10) | +0.69 ± 0.46 (10/10) | -3.59 ± 0.90 (0/10) | -6.5 ± 4.4 (0/10) | -2.42 ± 0.46 (0/10) | +1.95 ± 0.33 (10/10) |
| k=4, 80 m | -7.68 ± 0.84 (0/10) | -7.99 ± 0.73 (0/10) | -8.15 ± 0.73 (0/10) | +0.69 ± 0.46 (10/10) | -3.58 ± 0.90 (0/10) | -6.4 ± 4.4 (0/10) | -2.41 ± 0.46 (0/10) | +1.95 ± 0.33 (10/10) |
| k=2, 40 m, f 0,5 | -7.94 ± 0.76 (0/10) | -8.28 ± 0.68 (0/10) | -8.44 ± 0.69 (0/10) | +0.50 ± 0.48 (10/10) | -3.90 ± 0.88 (0/10) | -8.7 ± 4.1 (0/10) | -2.69 ± 0.46 (0/10) | +1.91 ± 0.28 (10/10) |
| k=2, 40 m, f 0,75 | -7.60 ± 0.73 (0/10) | -7.95 ± 0.64 (0/10) | -7.99 ± 0.65 (0/10) | +0.53 ± 0.47 (10/10) | -3.57 ± 0.85 (0/10) | -8.4 ± 4.0 (0/10) | -2.60 ± 0.41 (0/10) | +1.88 ± 0.26 (10/10) |

### Curva de arranque (historial recortado a N pings usados por la regla de sentido; N = pings incluido el actual; 15 min = completo)

Agregado de los 10 días (ponderado). «desc.» = coches que pasan en ≤ 10 min y no quedan ni en la cola (sin sentido); «prov.» = % de los listados en «sentido sin confirmar».

| regla | N | omisión % | omisión 3–7 % | omisión 1.er coche % | desc. % | falsas alarmas % | «viene» vacío % | MAE 3–7 (s) | antes % | después % | prov. % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 1 | 23.0 | 21.6 | 15.8 | 3.6 | 35.1 | 17.1 | 230 | 28.7 | 25.8 | 29.4 |
| base | 2 | 9.7 | 8.6 | 4.7 | 3.8 | 25.0 | 9.8 | 99 | 15.0 | 26.5 | 4.8 |
| base | 3 | 9.9 | 8.9 | 5.1 | 5.5 | 24.3 | 9.9 | 99 | 14.9 | 25.7 | 2.8 |
| base | 5 | 11.3 | 10.4 | 6.4 | 7.2 | 24.1 | 10.5 | 100 | 15.3 | 25.2 | 2.3 |
| base | 15 min | 17.0 | 16.4 | 12.7 | 13.4 | 24.0 | 13.7 | 107 | 17.0 | 24.5 | 1.9 |
| k=2, 20 m | 1 | 23.0 | 21.6 | 15.8 | 3.6 | 35.1 | 17.1 | 230 | 28.7 | 25.8 | 29.4 |
| k=2, 20 m | 2 | 9.2 | 8.1 | 4.3 | 3.9 | 24.9 | 9.7 | 97 | 14.6 | 26.6 | 4.2 |
| k=2, 20 m | 3 | 8.6 | 7.5 | 3.7 | 4.1 | 24.5 | 9.6 | 95 | 14.2 | 26.5 | 2.8 |
| k=2, 20 m | 5 | 8.8 | 7.8 | 4.0 | 4.4 | 24.5 | 9.7 | 96 | 14.2 | 26.4 | 2.6 |
| k=2, 20 m | 15 min | 9.3 | 8.4 | 4.4 | 4.9 | 24.5 | 10.0 | 97 | 14.3 | 26.4 | 2.4 |
| k=2, 40 m | 1 | 23.0 | 21.6 | 15.8 | 3.6 | 35.1 | 17.1 | 230 | 28.7 | 25.8 | 29.4 |
| k=2, 40 m | 2 | 9.7 | 8.6 | 4.7 | 3.8 | 25.0 | 9.8 | 99 | 15.0 | 26.5 | 4.8 |
| k=2, 40 m | 3 | 8.6 | 7.5 | 3.8 | 4.0 | 24.5 | 9.6 | 96 | 14.2 | 26.5 | 2.9 |
| k=2, 40 m | 5 | 8.8 | 7.8 | 3.9 | 4.3 | 24.5 | 9.7 | 97 | 14.2 | 26.4 | 2.7 |
| k=2, 40 m | 15 min | 9.3 | 8.3 | 4.4 | 4.8 | 24.5 | 10.0 | 98 | 14.4 | 26.4 | 2.5 |
| k=3, 40 m | 1 | 23.0 | 21.6 | 15.8 | 3.6 | 35.1 | 17.1 | 230 | 28.7 | 25.8 | 29.4 |
| k=3, 40 m | 2 | 23.0 | 21.6 | 15.8 | 3.6 | 35.1 | 17.1 | 230 | 28.7 | 25.8 | 29.4 |
| k=3, 40 m | 3 | 8.7 | 7.6 | 3.8 | 4.0 | 24.6 | 9.7 | 97 | 14.3 | 26.5 | 3.4 |
| k=3, 40 m | 5 | 8.9 | 7.9 | 4.0 | 4.3 | 24.6 | 9.8 | 98 | 14.3 | 26.4 | 3.1 |
| k=3, 40 m | 15 min | 9.3 | 8.4 | 4.5 | 4.8 | 24.6 | 10.1 | 99 | 14.4 | 26.4 | 3.0 |

### Por línea: base → k=2, 40 m, frac 0,6 (10 días; la 26 solo tiene 3)

| línea | omisión % | omisión 3–7 % | falsas alarmas % | «viene» vacío % | MAE (s) | antes % | después % |
|---|---|---|---|---|---|---|---|
| 26 | 16.8 → 5.7 | 16.3 → 4.7 | 7.2 → 7.0 | 10.2 → 2.6 | 81 → 76 | 14.4 → 12.2 | 28.6 → 28.9 |
| 39 | 11.6 → 7.0 | 10.6 → 5.6 | 30.4 → 31.5 | 24.6 → 23.2 | 87 → 88 | 13.7 → 10.8 | 23.9 → 29.3 |
| 42 | 16.4 → 7.5 | 16.2 → 6.8 | 39.9 → 38.8 | 18.9 → 12.0 | 165 → 195 | 18.4 → 17.0 | 31.3 → 32.2 |
| 50 | 16.4 → 5.7 | 15.8 → 5.1 | 32.0 → 32.3 | 20.0 → 14.4 | 89 → 79 | 17.4 → 15.9 | 22.4 → 23.0 |
| 92 | 9.1 → 4.7 | 9.4 → 4.7 | 15.0 → 14.2 | 4.1 → 3.0 | 81 → 67 | 16.7 → 13.8 | 19.7 → 20.8 |
| 106 | 16.7 → 15.1 | 15.1 → 12.9 | 18.1 → 22.4 | 7.3 → 5.6 | 115 → 155 | 15.8 → 14.8 | 28.4 → 30.4 |
| 107 | 32.8 → 10.3 | 33.8 → 12.0 | 17.9 → 18.3 | 18.0 → 12.3 | 202 → 106 | 30.9 → 21.1 | 18.8 → 21.9 |
| 108 | 10.9 → 6.6 | 10.8 → 7.0 | 24.1 → 24.5 | 5.9 → 3.8 | 81 → 75 | 15.7 → 13.9 | 22.0 → 23.7 |
| 124 | 7.3 → 3.9 | 7.5 → 3.9 | 10.0 → 11.1 | 5.3 → 2.8 | 76 → 75 | 13.4 → 13.0 | 22.1 → 22.9 |
| 132 | 23.5 → 13.0 | 21.1 → 10.2 | 25.4 → 25.0 | 22.4 → 16.0 | 118 → 84 | 14.6 → 11.2 | 29.9 → 31.1 |
| 151 | 22.1 → 12.8 | 22.2 → 11.6 | 12.7 → 12.4 | 13.3 → 8.7 | 91 → 84 | 16.2 → 13.5 | 28.8 → 30.6 |
| 168 | 17.2 → 7.0 | 17.5 → 7.9 | 40.5 → 40.8 | 13.2 → 10.1 | 117 → 95 | 21.0 → 16.3 | 21.0 → 23.0 |


## Lectura

1. **El barrido es plano: casi todo el efecto está en cambiar de regla, no en los parámetros.** Las 9 combinaciones (k, avance) bajan la omisión de 16,5 % a 8,7–8,8 % (pareado: −7,7 a −7,8 pp, y −8 pp en la banda 3–7 min y en el primer coche, que baja de 12,7 a 4,4–4,6 %; los 10 días mejoran), «viene» vacío de 13,9 a 10,1–10,4 % y «llega antes» de 17,0 a 14,4–14,6 %. El avance neto (20, 40, 80 m) no cambia nada visible (diferencias ≤ 0,1 pp). Subir k de 2 a 4 empeora apenas: +0,1 pp de omisión y +0,2 pp de falsas alarmas; con k = 2 el MAE baja 9–10 s y con k = 4 6–7 s. El eje MIN_FORWARD_FRAC se mueve ±0,2 pp (0,5: 8,5 %; 0,75: 8,9 %), menos que el desvío día a día de la mejora (0,7–0,8 pp): no hay razón fuerte para cambiarlo.
2. **Costos.** Las falsas alarmas suben +0,5 pp con k = 2 (de 24,4 a 24,9 %; pareado +0,5 ± 0,5, positivo los 10 días, contra una dispersión día a día no pareada de 4,1 pp), porque se listan más coches (3,80 → 4,15 por instante). «Llega después de lo anunciado» sube +1,9 pp (24,3 → 26,2 %) los 10 días: coches antes omitidos ahora se anuncian, con error de ETA hacia el lado de llegar después. «Llega antes» baja 2,7 pp: el error grave no empeora.
3. **Por línea** (k=2, 40 m): la omisión baja en las 12 líneas (la 107 de 32,8 a 10,3 %, la 132 de 23,5 a 13,0 %, la 151 de 22,1 a 12,8 %; la 106 casi no cambia, 16,7 → 15,1 %, porque su problema es el tope de 5). Dos líneas empeoran el MAE: la 42 de 165 a 195 s y la 106 de 115 a 155 s (la 106 además sube falsas alarmas de 18,1 a 22,4 %). En las demás el MAE baja o queda igual y las falsas alarmas se mueven ≤ 1,1 pp.
4. **Curva de arranque.**
   - **Con 1 ping el coche se muestra igual:** con cualquier regla queda descartado solo 3,6 % de los que pasan en ≤ 10 min (13,4 % con la regla actual y 15 min), y 29 % de los listados pasan a «sentido sin confirmar» (sentido por geometría cuando alcanza, provisional si no). Pero el costo es alto: omisión 23,0 %, falsas alarmas 35,1 %, MAE 230 s, llega antes 28,7 %. Es igual para todas las reglas porque con un solo ping ninguna tiene historial; mejorarlo exige otra cosa (por ejemplo, darle menos peso o ubicar más abajo en el orden a «sentido sin confirmar»), no un parámetro de esta regla. No se midió.
   - **Regla actual: agregar historial empeora, y mucho.** De N = 2 a 15 min la omisión sube de 9,7 a 17,0 %, la del primer coche de 4,7 a 12,7 %, «viene» vacío de 9,8 a 13,7 %, el MAE de 99 a 107 s y «llega antes» de 15,0 a 17,0 %. Con 5 pings ya está en 11,3 %. Es el efecto esperado de exigir ≥ 80 % de la ventana a ≤ 45 m: más ventana, más pings de cabecera o del viaje anterior fuera del shape.
   - **Racha final: no empeora de forma relevante, pero no es estrictamente monótona.** Con k=2/40 m la omisión va 9,7 % (N=2) → 8,6 % (3) → 8,8 % (5) → 9,3 % (15 min); el MAE 99 → 96 → 97 → 98 s; llega antes 15,0 → 14,2 → 14,2 → 14,4 %. Entre N = 3 y la ventana completa hay +0,7 pp de omisión y +2 s de MAE (k=2/20 m: 8,6 → 9,3 % y 95 → 97 s; k=3/40 m: 8,7 → 9,3 %), contra +7,3 pp de la regla actual en el mismo tramo. Se señala como empeoramiento chico con más historial; no se estudió si acotar el largo de la racha (por ejemplo a los últimos 5–8 pings) lo evita: la curva en N = 5 (8,8 %) lo sugiere, pero no está medido por separado.
   - Con N = 2 solo k = 2 confirma sentido (k = 3 da lo mismo que con 1 ping). Con 2 pings k=2/40 m y la regla actual coinciden (9,7 %); k=2/20 m da 9,2 %.

## Recomendación

**`direction_from_history` por racha final con k = 2 pings, avance neto mínimo 40 m (se conserva `MIN_NET_FORWARD_M`; no se agrega constante), `MIN_FORWARD_FRAC` 0,6, TOL_M 45, MARGIN_M 20; se elimina `MIN_NEAR_FRAC`.**

- Razón: k = 2 es lo que más baja omisión, «viene» vacío y MAE, y es el único valor que confirma sentido con 2 pings (relevante cuando la app recién se abre). El avance 20, 40 u 80 m es indistinguible (≤ 0,1 pp de omisión; MAE ±1 s, contra un desvío pareado de 4 s); se conserva 40 m para no introducir un número nuevo. MIN_FORWARD_FRAC queda en 0,6: moverlo cambia ±0,2 pp.
- Efecto medido (10 días, pareado con la regla actual): omisión −7,8 pp (16,5 → 8,7 %), primer coche −8,3 pp, «viene» vacío −3,8 pp, MAE −9 s, llega antes −2,7 pp; mejora en los 10 días. Costo: falsas alarmas +0,5 pp y llega después +1,9 pp (los 10 días), contra una dispersión día a día no pareada de 4,1 y 6,0 pp. Criterio pedido: se baja la omisión, «llega antes» baja y las falsas alarmas suben una fracción (0,5 pp, 1/8) de su dispersión día a día.
- Pendiente antes de portar: las líneas 42 y 106 (MAE +30 y +40 s; en la 106 además +4,3 pp de falsas alarmas); el caso de 1 ping (omisión 23 %, falsas alarmas 35 %, llega antes 29 %), que ninguna regla de sentido resuelve; y la leve pérdida entre 3 pings y 15 min (+0,7 pp), con una racha acotada como candidata sin medir. Salvedades: una corrida, 10 días, sin semillas; el replay le da 15 min de historial a todo coche, mientras que la app solo tiene el que lleva abierta; el recorte de la curva de arranque afecta solo la regla de sentido, no el ETA.
