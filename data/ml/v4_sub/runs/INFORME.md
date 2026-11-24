# Informe v4 (2026-11-21/22)

Modelo `path_v4_l1_s1`: receta de producción sin cambios (geo2/geo3, K=32, por tramos `--loss l1 --stops-feature`, LR 2e-3, 12 épocas, OneCycle, batch 1024, train 2026-07-20 -> 09-14, val 09-15 -> 10-14 con muestra del 40 %), con todas las líneas AMBA < 200.

## Líneas
- Candidatas: 129 (en `LABEL_LINE_MAP.json` `lines` y con shapes en `proyectoconsola/data/line_shapes`). La 148 tiene label pero no shapes: excluida. Identificación solo por sufijo de label.
- Criterio mínimo (`select()` del lanzador): >= 12 viajes con forma por día y >= 1000 filas de validación. Resultado: las 129 lo cumplen (`data/ml/v4/validation/summary.md`, `selection.json`).

## Datos y tiempos
- Build nuevo en `data/ml/v4` (no se tocó `data/ml/v3`): 71 días disponibles, 119 min con 3 workers (RAM libre ~15 GB).
- v4_sub (run 2, full): 82.258.188 filas train, 17.797.165 val. v4_ctrl (run 1): 73.313.316 / 15.848.181.
- Entrenamiento (cuda confirmado): ~14,5 min por época; run 2 (full, semilla 1) 175 min, val MAE 80,5 s; run 1 (control, semilla 0) 156 min, val MAE 81,0 s.
- Lanzador: `prediccion/scripts/run_v4.py` (reanudable, keep_awake verificado). Eval nuevo congelado: `data/ml/v4/eval`.

## Resultados
- Run 1 (control, 12 líneas fuera del train, eval heldout de v3): ver `no_regresion.md` (sección de control del run full) y evaluaciones `eval/ctrl_s0_*`.
- Run 2 (full) contra producción en las 46 habilitadas, eval congelado v3, banda 3-7 min (n = 13.136): MAE 55,5 s contra 55,1 s (dif. +0,38 s, criterio <= +1 s: cumple); P90 117,4 contra 115,6 s; llega antes > 60 s 14,5 contra 14,6 %; llega después > 60 s 20,8 contra 20,5 %. Ninguna línea de las 46 peor en más de 5 s con n >= 100 (la 26, n = 42, informativa: mejora 2,1 s). Tabla por línea en `no_regresion.md`.
- Las 12 de control, que el run full ya vio: 54,4 s contra 74,4 s del v3 (no es medida de generalización).
- Replay de producto: no se corrió (sin tiempo asignado); las métricas de producto (bondi fantasma, bondi no anunciado, sin aviso firme) no cambian por el modelo en lo medido antes.

## Decisión: publicar (criterios cumplidos). Habilitación
- 46 actuales mantenidas con sus 8 avisos `quality: "baja"`. 61 y 88 siguen sin habilitar.
- 72 nuevas habilitadas (MAE banda 3-7 min <= 1,3 x mediana de las 46 = 71,1 s y n >= 100): 1, 2, 8, 10, 12, 15, 17, 19, 21, 22, 24, 31, 32, 37, 45, 51, 53, 55, 56, 57, 59, 60, 63, 64, 65, 67, 68, 70, 71, 78, 79, 80, 86, 87, 91, 93, 95, 96, 100, 101, 103, 105, 109, 111, 117, 126, 128, 129, 130, 133, 134, 135, 136, 140, 145, 146, 150, 152, 158, 159, 160, 161, 166, 172, 174, 176, 177, 178, 179, 181, 182, 195.
- No habilitadas: 49 (n 97), 97 (99), 119 (97), 153 (70), 154 (68), 163 (57), 185 (92), 193 (71) por n < 100; 164 por MAE 72,4 s > 71,1 s.
- Sin avisos de calidad nuevos: no hay dato de producto para las nuevas (los 8 avisos vigentes salieron de la vara de producto). Pendiente: replay de las nuevas.

## Publicación
- Export `data/ml/export/path_v4_l1_s1` (ONNX 2.649.787 B contra 2.644.602 B de v3; export completo 17 MB contra 7,4 MB), fixture de paridad regenerado (35 MB), instalado y activado en proyectoconsola; `npm test` 113/113; e2e de predicción 60/60.
- Commit local 576aeb5 en proyectoconsola main; push y verificación de Vercel a cargo del coordinador.
