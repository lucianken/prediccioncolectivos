# Historial de la flota para la entrada «coche de adelante»

Medido el 2026-11-23 con el replay de producto (`prediccion/replay/`), modelo `path_v4_l1_s1` (contrato 2.3), regla de sentido `trailing_run`, vara vigente de `ARQUITECTURA.md` §5. Solo cambia la ventana de historial de los otros coches que recibe `last_bus`; el sentido (900 s), el historial propio, la lista, la verdad y el modelo son idénticos en todas las variantes (comparación pareada: mismas filas).

## 1. Cómo se arma la entrada

- **Estado del modelo:** `log1p(clip(tlb, 0, 3600)) / log1p(3600)` y `last_bus_found` (0/1), 2 de las 9 entradas de `state` (`INFERENCIA_PATH.md` §3). `tlb` = segundos desde que el coche anterior pasó por T, tope `tlb_cap_s` = 3600 (manifest). Sin coche encontrado: `tlb = 3600`, `found = 0`.
- **Entrenamiento (`prediccion/v2/rows.py`, `_find_prev_trip` / `_interp_passage`):** paso del viaje anterior de otro coche sobre el mismo shape (recorrido ex post), con el día completo; un paso más viejo que 3600 s queda en `tlb = 3600` con `found = 1`.
- **App (`core.js` `lastBus`, `path_reference.last_bus`):** con los pings guardados de los otros coches de la línea, proyecta cada coche sobre el shape, descarta los que no cumplen perp ≤ `tol_m` y `forward_fraction ≥ min_forward_frac`, toma el **primer** cruce de d_T entre dos pings consecutivos (si no, el ping a ≤ 250 m), solo si es anterior a `ts_ping`, y el paso más reciente entre coches. Historial de la app: `HISTORY_KEEP_S` = 20 min (`prediccion.js`); antes del servicio de historial de flota, solo lo de la sesión.
- **Replay hasta hoy (`core.py`):** `HISTORY_S` = 900 s (15 min): otros coches con ping en los últimos 15 min y sus pings en [t − 900 s, t]. No es la ventana de la app (20 min). El flag nuevo `others_windows` de `core.evaluate_line` (default `None` = comportamiento anterior) parametriza la ventana de «coche de adelante».
- **Chequeo:** la variante de 900 s reproduce `v4prod/v4` (línea 26, 2026-09-15: 42.430 filas, diferencia máxima de ETA 0,0 s). 20 min cambia el ETA anunciado en 0,7 % de las filas respecto de 15 min.

## 2. Variantes

| variante | historial de los otros coches | qué es |
|---|---|---|
| `w20` (referencia) | pings de los últimos 20 min | lo que da el servicio de historial hoy |
| `w60` | pings de los últimos 60 min | igual a `tlb_cap_s`: todo lo que el tope deja distinguir |
| `wdia` | todos los pings del día hasta t, con el `last_bus` de la app sin cambios | día completo con la función de la app |
| `wviaje` | cada viaje ex post del coche sobre el shape (segmentador geo2 + geo3), pings hasta t | día completo por viaje, análogo al entrenamiento (usa el recorrido ex post: solo medición) |

`wdia` no es el entrenamiento: `last_bus` toma el primer cruce de d_T dentro de los pings recibidos, que con día completo es el de la mañana (las ventanas cortas solo tienen el reciente), y `forward_fraction` mezcla viajes de ida y vuelta. `wviaje` sí reproduce el criterio del entrenamiento, pero no hay viaje ex post para todos los coches (ver salvedades).

## 3. Método

- Código: `prediccion/replay/historial_ca.py` (corrida; `last_bus` vectorizado con los pings proyectados una vez, equivalente al de `path_reference`), `historial_ca_report.py` (métricas y bootstrap), `historial_ca_tablas.py` (tablas). Crudos: `data/ml/replay/histca/run2/`; resumen: `data/ml/replay/histca/resumen.json`.
- Mismos 10 días que `V3_PRODUCCION.md` (2026-09-15 a 20, 10-03, 10-04, 10-06, 10-08; la línea 26 solo tiene 3), 40 paradas por línea, instantes cada 10 min de 6 a 23 h, `ts_offset` 60 s.
- **No entró el replay de las 126 líneas habilitadas.** Con 4 variantes, 8 procesos Idle calcularon ~2,3 pares línea-día por minuto (57 líneas planeadas ≈ 4,7 h); se cortó a las 17:36. Subconjunto: **23 líneas** con los 10 días (26 con sus 3), elegidas entre las de menos de ~70 coches por día y estratificadas por intervalo medio entre coches (quedaron afuera 152, 106, 98, 21, 28, 60, 176 y otras de más de 70 coches/día). Incluye líneas de frecuencia baja: 62, 93, 136, 154, 163, 185.
- **Grupo de frecuencia** = intervalo medio entre coches de la línea = 20 min / media de coches que pasan en los 20 min siguientes por (parada, t), instantes de 6 a 23 h: alta ≤ 5 min (12, 17, 34, 68, 102, 151), media 5–8 (2, 26, 64, 67, 92, 124), baja 8–12 (4, 25, 114, 123, 184), muy baja > 12 (62, 93, 136, 154, 163, 185). Intervalos en `data/ml/replay/histca/headway.csv`.
- **Métricas.** Próximo coche: banda de ETA real 3–7 min, MAE (s), llega antes / después de lo anunciado > 60 s; bondi fantasma y bondi no anunciado con la vara vigente. Error por coche: cada coche listado con paso firme (`tp2_s`) en 3–7 min, error = ETA anunciado (`eta0_s`) − tiempo real hasta su propio paso. `last_bus_found = 0`: % de las filas cuyo candidato que fija el ETA no tiene coche de adelante (coches de la banda 3–7 min, y todos los listados).
- **IC95:** diferencia contra `w20` por día (10 días), bootstrap de días (10.000 remuestras de las diferencias diarias). Como la diferencia pareada es casi constante entre días, los IC de las métricas de error son angostos; son IC de la diferencia entre variantes, no del nivel absoluto.

## 4. Resultados

Δ = variante − `w20`, con IC95 por bootstrap de días entre corchetes.

### Todas las líneas
| métrica | 20 min (servicio hoy) | 60 min | día completo, función de la app | día completo por viaje (≈ entrenamiento) | Δ 60 min vs 20 [IC95] | Δ día-app vs 20 [IC95] | Δ día-viaje vs 20 [IC95] |
|---|---|---|---|---|---|---|---|
| MAE próximo coche, 3–7 min (s) | 82.80 | 82.79 | 82.76 | 82.81 | -0.00 [-0.02, +0.01] | -0.03 [-0.05, -0.00] | +0.01 [+0.01, +0.02] |
| próximo coche llega antes > 60 s % | 14.15 | 14.26 | 14.74 | 14.24 | +0.11 [+0.08, +0.15] | +0.59 [+0.55, +0.62] | +0.08 [+0.06, +0.12] |
| próximo coche llega después > 60 s % | 24.93 | 24.84 | 24.34 | 24.88 | -0.10 [-0.13, -0.07] | -0.60 [-0.64, -0.55] | -0.06 [-0.08, -0.04] |
| bondi fantasma % | 13.81 | 13.81 | 13.80 | 13.81 | +0.00 [-0.00, +0.00] | -0.01 [-0.01, -0.00] | +0.00 [-0.00, +0.01] |
| bondi no anunciado % | 11.52 | 11.52 | 11.52 | 11.52 | -0.00 [-0.00, +0.00] | -0.00 [-0.00, -0.00] | +0.00 [-0.00, +0.00] |
| MAE por coche, 3–7 min (s) | 55.12 | 55.15 | 55.34 | 55.14 | +0.02 [+0.01, +0.03] | +0.20 [+0.14, +0.27] | +0.02 [+0.01, +0.02] |
| coche llega antes > 60 s % | 18.69 | 18.82 | 19.48 | 18.77 | +0.14 [+0.11, +0.16] | +0.77 [+0.73, +0.82] | +0.08 [+0.07, +0.11] |
| coche llega después > 60 s % | 16.79 | 16.70 | 16.14 | 16.73 | -0.10 [-0.12, -0.09] | -0.64 [-0.68, -0.59] | -0.07 [-0.09, -0.05] |
| last_bus_found = 0 %, coches de la banda | 3.9 | 0.6 | 14.2 | 5.1 | -4.3 [-6.7, -2.3] | +8.6 [+4.3, +12.4] | +0.6 [-1.2, +2.0] |
| last_bus_found = 0 %, todos los listados | 8.6 | 2.7 | 14.8 | 3.7 | -6.3 [-8.4, -4.7] | +5.4 [+1.8, +8.8] | -5.3 [-7.8, -3.5] |

n: próximo coche en banda 217251, coches en banda 443114, coches listados con last_bus_found definido 2983042.

### Frecuencia alta (<= 5 min) (6 líneas)
| métrica | 20 min (servicio hoy) | 60 min | día completo, función de la app | día completo por viaje (≈ entrenamiento) | Δ 60 min vs 20 [IC95] | Δ día-app vs 20 [IC95] | Δ día-viaje vs 20 [IC95] |
|---|---|---|---|---|---|---|---|
| MAE próximo coche, 3–7 min (s) | 87.09 | 87.05 | 86.93 | 87.09 | -0.04 [-0.06, -0.01] | -0.16 [-0.21, -0.11] | -0.00 [-0.02, +0.02] |
| próximo coche llega antes > 60 s % | 10.41 | 10.52 | 10.96 | 10.44 | +0.11 [+0.08, +0.14] | +0.55 [+0.49, +0.61] | +0.03 [+0.02, +0.05] |
| próximo coche llega después > 60 s % | 31.48 | 31.36 | 30.85 | 31.46 | -0.12 [-0.15, -0.09] | -0.63 [-0.68, -0.57] | -0.02 [-0.05, +0.02] |
| bondi fantasma % | 12.84 | 12.84 | 12.83 | 12.84 | +0.00 [-0.00, +0.00] | -0.01 [-0.01, -0.00] | +0.00 [-0.00, +0.00] |
| bondi no anunciado % | 16.84 | 16.84 | 16.84 | 16.85 | -0.00 [-0.00, +0.00] | -0.01 [-0.01, -0.00] | +0.00 [-0.00, +0.00] |
| MAE por coche, 3–7 min (s) | 55.53 | 55.56 | 55.74 | 55.55 | +0.02 [+0.01, +0.04] | +0.19 [+0.14, +0.26] | +0.03 [+0.01, +0.04] |
| coche llega antes > 60 s % | 17.86 | 18.02 | 18.68 | 17.92 | +0.16 [+0.14, +0.17] | +0.80 [+0.74, +0.85] | +0.06 [+0.04, +0.07] |
| coche llega después > 60 s % | 18.25 | 18.12 | 17.56 | 18.20 | -0.12 [-0.14, -0.11] | -0.67 [-0.72, -0.64] | -0.04 [-0.07, +0.00] |
| last_bus_found = 0 %, coches de la banda | 0.9 | 0.1 | 17.8 | 9.0 | -1.1 [-1.9, -0.4] | +15.5 [+11.6, +19.2] | +8.5 [+7.6, +9.6] |
| last_bus_found = 0 %, todos los listados | 3.4 | 1.2 | 18.7 | 6.8 | -2.3 [-3.4, -1.3] | +14.8 [+11.1, +18.3] | +3.3 [+2.2, +4.4] |

n: próximo coche en banda 67273, coches en banda 210976, coches listados con last_bus_found definido 983507.

### Frecuencia media (5-8 min) (6 líneas)
| métrica | 20 min (servicio hoy) | 60 min | día completo, función de la app | día completo por viaje (≈ entrenamiento) | Δ 60 min vs 20 [IC95] | Δ día-app vs 20 [IC95] | Δ día-viaje vs 20 [IC95] |
|---|---|---|---|---|---|---|---|
| MAE próximo coche, 3–7 min (s) | 74.18 | 74.18 | 74.14 | 74.17 | -0.01 [-0.02, +0.00] | -0.04 [-0.11, +0.02] | -0.01 [-0.02, -0.01] |
| próximo coche llega antes > 60 s % | 13.15 | 13.20 | 13.82 | 13.20 | +0.05 [+0.03, +0.08] | +0.66 [+0.59, +0.74] | +0.05 [+0.03, +0.07] |
| próximo coche llega después > 60 s % | 24.86 | 24.80 | 24.13 | 24.80 | -0.06 [-0.09, -0.04] | -0.73 [-0.81, -0.65] | -0.06 [-0.07, -0.05] |
| bondi fantasma % | 8.01 | 8.01 | 8.00 | 8.01 | +0.00 [-0.00, +0.00] | -0.01 [-0.01, -0.00] | +0.00 [-0.00, +0.00] |
| bondi no anunciado % | 5.24 | 5.24 | 5.24 | 5.24 | +0.00 [+0.00, +0.00] | -0.00 [-0.00, +0.00] | +0.00 [-0.00, +0.00] |
| MAE por coche, 3–7 min (s) | 55.23 | 55.26 | 55.48 | 55.22 | +0.03 [+0.02, +0.04] | +0.25 [+0.16, +0.34] | -0.01 [-0.02, +0.01] |
| coche llega antes > 60 s % | 19.87 | 19.94 | 20.71 | 19.93 | +0.07 [+0.05, +0.09] | +0.82 [+0.74, +0.90] | +0.07 [+0.05, +0.09] |
| coche llega después > 60 s % | 15.70 | 15.66 | 14.99 | 15.63 | -0.05 [-0.06, -0.03] | -0.69 [-0.76, -0.62] | -0.08 [-0.10, -0.06] |
| last_bus_found = 0 %, coches de la banda | 1.5 | 0.1 | 6.8 | 0.0 | -1.8 [-2.8, -1.0] | +4.4 [+1.7, +7.1] | -1.8 [-2.8, -1.1] |
| last_bus_found = 0 %, todos los listados | 2.3 | 0.3 | 6.8 | 0.1 | -2.1 [-3.0, -1.4] | +4.1 [+1.0, +7.0] | -2.4 [-3.6, -1.5] |

n: próximo coche en banda 67723, coches en banda 132328, coches listados con last_bus_found definido 880221.

### Frecuencia baja (8-12 min) (5 líneas)
| métrica | 20 min (servicio hoy) | 60 min | día completo, función de la app | día completo por viaje (≈ entrenamiento) | Δ 60 min vs 20 [IC95] | Δ día-app vs 20 [IC95] | Δ día-viaje vs 20 [IC95] |
|---|---|---|---|---|---|---|---|
| MAE próximo coche, 3–7 min (s) | 81.23 | 81.24 | 81.27 | 81.23 | +0.00 [-0.03, +0.03] | +0.04 [-0.00, +0.08] | +0.00 [-0.02, +0.02] |
| próximo coche llega antes > 60 s % | 16.88 | 16.97 | 17.46 | 16.94 | +0.10 [+0.06, +0.16] | +0.58 [+0.51, +0.65] | +0.07 [+0.03, +0.15] |
| próximo coche llega después > 60 s % | 19.63 | 19.56 | 19.15 | 19.59 | -0.10 [-0.16, -0.04] | -0.49 [-0.55, -0.41] | -0.06 [-0.13, +0.01] |
| bondi fantasma % | 13.86 | 13.86 | 13.85 | 13.86 | +0.00 [+0.00, +0.01] | -0.01 [-0.02, -0.00] | +0.01 [-0.00, +0.02] |
| bondi no anunciado % | 6.14 | 6.14 | 6.14 | 6.14 | +0.00 [+0.00, +0.00] | +0.00 [+0.00, +0.00] | +0.00 [+0.00, +0.00] |
| MAE por coche, 3–7 min (s) | 51.86 | 51.87 | 52.01 | 51.86 | +0.00 [-0.02, +0.03] | +0.13 [+0.06, +0.19] | -0.00 [-0.02, +0.01] |
| coche llega antes > 60 s % | 17.83 | 17.91 | 18.51 | 17.89 | +0.11 [+0.06, +0.17] | +0.67 [+0.60, +0.75] | +0.07 [+0.02, +0.15] |
| coche llega después > 60 s % | 14.70 | 14.63 | 14.19 | 14.64 | -0.09 [-0.16, -0.04] | -0.49 [-0.57, -0.41] | -0.07 [-0.14, -0.00] |
| last_bus_found = 0 %, coches de la banda | 7.8 | 0.4 | 15.1 | 3.8 | -11.8 [-22.2, -3.8] | +2.7 [-7.1, +10.9] | -7.4 [-17.1, -0.2] |
| last_bus_found = 0 %, todos los listados | 8.1 | 1.4 | 13.3 | 3.2 | -8.7 [-15.1, -3.8] | +2.8 [-4.1, +8.9] | -6.9 [-14.1, -1.7] |

n: próximo coche en banda 56046, coches en banda 69712, coches listados con last_bus_found definido 689765.

### Frecuencia muy baja (> 12 min) (6 líneas)
| métrica | 20 min (servicio hoy) | 60 min | día completo, función de la app | día completo por viaje (≈ entrenamiento) | Δ 60 min vs 20 [IC95] | Δ día-app vs 20 [IC95] | Δ día-viaje vs 20 [IC95] |
|---|---|---|---|---|---|---|---|
| MAE próximo coche, 3–7 min (s) | 98.71 | 98.77 | 98.88 | 98.83 | +0.05 [+0.01, +0.09] | +0.16 [+0.11, +0.21] | +0.12 [+0.07, +0.17] |
| próximo coche llega antes > 60 s % | 20.48 | 20.78 | 21.00 | 20.82 | +0.38 [+0.21, +0.57] | +0.57 [+0.45, +0.68] | +0.45 [+0.23, +0.69] |
| próximo coche llega después > 60 s % | 20.04 | 19.86 | 19.65 | 19.85 | -0.25 [-0.43, -0.09] | -0.45 [-0.61, -0.28] | -0.29 [-0.52, -0.08] |
| bondi fantasma % | 32.29 | 32.29 | 32.28 | 32.29 | -0.00 [-0.01, +0.01] | -0.02 [-0.03, -0.00] | -0.00 [-0.02, +0.01] |
| bondi no anunciado % | 10.39 | 10.39 | 10.39 | 10.39 | +0.00 [+0.00, +0.00] | +0.00 [+0.00, +0.00] | +0.00 [+0.00, +0.00] |
| MAE por coche, 3–7 min (s) | 59.37 | 59.41 | 59.63 | 59.47 | +0.03 [-0.00, +0.07] | +0.22 [+0.15, +0.30] | +0.10 [+0.05, +0.14] |
| coche llega antes > 60 s % | 21.31 | 21.58 | 21.92 | 21.63 | +0.37 [+0.21, +0.56] | +0.65 [+0.57, +0.74] | +0.45 [+0.24, +0.71] |
| coche llega después > 60 s % | 16.28 | 16.11 | 15.84 | 16.10 | -0.26 [-0.43, -0.11] | -0.49 [-0.63, -0.35] | -0.30 [-0.52, -0.10] |
| last_bus_found = 0 %, coches de la banda | 27.4 | 6.6 | 19.9 | 3.6 | -25.4 [-34.3, -17.9] | -12.8 [-22.7, -4.3] | -31.3 [-46.5, -19.2] |
| last_bus_found = 0 %, todos los listados | 33.9 | 13.0 | 24.9 | 4.9 | -23.6 [-29.1, -19.0] | -11.8 [-17.5, -6.6] | -33.5 [-43.0, -25.7] |

n: próximo coche en banda 26209, coches en banda 30098, coches listados con last_bus_found definido 429549.

### Por línea (todos los días)

| línea | intervalo medio (min) | grupo | MAE próximo coche 20 → 60 → viaje (s) | last_bus_found = 0 %, todos los listados, 20 → 60 → viaje |
|---|---|---|---|---|
| 2 | 6.6 | media (5-8 min) | 77 → 77 → 77 | 5.3 → 1.0 → 0.2 |
| 4 | 10.9 | baja (8-12 min) | 70 → 70 → 70 | 11.1 → 4.3 → 0.4 |
| 12 | 3.5 | alta (<= 5 min) | 91 → 91 → 91 | 0.2 → 0.0 → 8.1 |
| 17 | 4.7 | alta (<= 5 min) | 67 → 67 → 67 | 1.0 → 0.1 → 0.0 |
| 25 | 11.5 | baja (8-12 min) | 80 → 80 → 80 | 7.4 → 0.4 → 0.0 |
| 26 | 5.1 | media (5-8 min) | 77 → 77 → 77 | 0.4 → 0.1 → 0.0 |
| 34 | 4.4 | alta (<= 5 min) | 95 → 95 → 95 | 10.8 → 4.3 → 0.0 |
| 62 | 13.1 | muy baja (> 12 min) | 107 → 107 → 107 | 8.2 → 2.7 → 1.2 |
| 64 | 5.9 | media (5-8 min) | 91 → 91 → 91 | 1.8 → 0.4 → 0.0 |
| 67 | 5.9 | media (5-8 min) | 66 → 66 → 66 | 1.2 → 0.1 → 0.0 |
| 68 | 2.8 | alta (<= 5 min) | 111 → 111 → 111 | 0.3 → 0.0 → 33.5 |
| 92 | 6.5 | media (5-8 min) | 67 → 67 → 67 | 2.8 → 0.3 → 0.2 |
| 93 | 24.7 | muy baja (> 12 min) | 73 → 73 → 73 | 26.9 → 4.1 → 3.8 |
| 102 | 4.8 | alta (<= 5 min) | 85 → 85 → 85 | 1.6 → 0.2 → 0.0 |
| 114 | 11.5 | baja (8-12 min) | 110 → 110 → 110 | 10.1 → 0.9 → 16.4 |
| 123 | 11.0 | baja (8-12 min) | 79 → 79 → 79 | 6.5 → 0.4 → 0.0 |
| 124 | 6.8 | media (5-8 min) | 70 → 70 → 70 | 1.4 → 0.2 → 0.0 |
| 136 | 61.8 | muy baja (> 12 min) | 255 → 255 → 255 | 47.8 → 25.3 → 5.2 |
| 151 | 4.7 | alta (<= 5 min) | 82 → 82 → 82 | 5.0 → 2.2 → 1.4 |
| 154 | 21.1 | muy baja (> 12 min) | 70 → 70 → 70 | 33.6 → 8.9 → 0.3 |
| 163 | 54.9 | muy baja (> 12 min) | 75 → 75 → 75 | 71.8 → 38.3 → 18.5 |
| 184 | 10.3 | baja (8-12 min) | 74 → 74 → 74 | 5.0 → 0.1 → 0.0 |
| 185 | 22.9 | muy baja (> 12 min) | 78 → 78 → 78 | 25.8 → 4.7 → 2.0 |

## 5. Conclusiones

1. **La ventana de historial de «coche de adelante» no mueve el error.** Todas las líneas, 60 min contra 20 min: MAE del próximo coche 82,79 contra 82,80 s (Δ −0,00 s, IC [−0,02, +0,01]); llega antes > 60 s +0,11 puntos [+0,08, +0,15], llega después −0,10 puntos [−0,13, −0,07]; bondi fantasma y bondi no anunciado sin cambio (Δ ≤ 0,01 puntos). MAE por coche 55,12 → 55,15 s (Δ +0,02 s). Igual en los 4 grupos de frecuencia (Δ MAE del próximo coche ≤ 0,1 s).
2. **60 min reduce los «no encontrado», no el error.** `last_bus_found = 0` en los listados: 8,6 % (20 min) → 2,7 % (60 min) (Δ −6,3 puntos, IC [−8,4, −4,7]); frecuencia muy baja 33,9 % → 13,0 %; baja 8,1 % → 1,4 %; alta 3,4 % → 1,2 %. En frecuencia muy baja el próximo coche llega antes > 60 s sube 20,5 → 20,8 % (+0,4 puntos, IC [+0,2, +0,6]) y el MAE +0,1 s: un coche de adelante más viejo, con el tope de 3600 s, no ayuda al modelo.
3. **Día completo con la función de la app es peor.** `wdia`: llega antes > 60 s +0,59 puntos (14,74 contra 14,15 %), llega después −0,6 puntos (el anuncio se corre hacia más tarde); `last_bus_found = 0` sube a 14,8 % en los listados. No guardar el día completo sin cambiar `last_bus` (cruce más reciente por viaje).
4. **Día completo por viaje (≈ entrenamiento) tampoco mejora:** MAE 82,81 s (Δ +0,01 s), llega antes +0,08 puntos. `last_bus_found = 0` baja en frecuencia muy baja (4,9 % de los listados), el MAE no se mueve.
5. **Recomendación: el servicio de historial no necesita guardar más de 20 min para la predicción.** 60 min o más no baja el error medido (ΔMAE del próximo coche 0,00 s, por coche +0,02 s) y solo reduce los casos «no encontrado» (8,6 → 2,7 %), sin efecto medible en llega antes / después, bondi fantasma ni bondi no anunciado. Si guardar 60 min es gratis se puede hacer (inocuo), pero no se justifica por la predicción. Coincide con `INFERENCIA_PATH.md` §1 (sin coche de adelante cuesta ≈ 0,35 s de MAE).

## 6. Salvedades

- 23 de las 126 líneas habilitadas (sin las de más de ~70 coches por día), 40 paradas por línea, 10 días, una corrida. En frecuencia muy baja hay 6 líneas; su MAE absoluto lo domina la 136 (255 s).
- `wviaje` depende de que el coche tenga viaje ex post sobre el shape: en las líneas 12, 68 y 114 su `last_bus_found = 0` (8,1 %, 33,5 %, 16,4 % de los listados) refleja la cobertura del segmentador, no el historial. Su MAE coincide con el de `w20` en todas las líneas.
- `last_bus_found` se registra para el candidato que fija el ETA anunciado de cada coche con ETA (los «llegando» quedan afuera).
- Los IC de 10 días no incluyen la variación entre líneas ni entre las paradas muestreadas.
- La verdad y el replay usan la hora del sello de CABA (ver `V3_PRODUCCION.md`); no se midió con verdad de campo.
