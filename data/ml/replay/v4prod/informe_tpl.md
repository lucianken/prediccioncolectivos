# Vara de producto (replay) de `path_v4_l1_s1` y re-evaluación de las líneas sin habilitar

Medido el 2026-11-22. Modelo en producción `data/ml/export/path_v4_l1_s1` (contrato 2.3), 118 líneas habilitadas. Bondi fantasma, bondi no anunciado, sin aviso firme y llega antes / después usan la vara vigente de `ARQUITECTURA.md` §5 (verdad por recorrido ex post; bondi fantasma = coche listado con ETA anunciado ≤ 40 min que no cruza). «Sin aviso firme» es un problema de la app (cómo agrupa los coches que ya encontró), no del modelo. «Llega antes / después» = el próximo coche anunciado llega más de 60 s antes / después de lo anunciado, banda de ETA real 3–7 min.

## Método

- Variante `base`, regla `trailing_run`, lógica de la app fijada en `prediccion/replay/pinned/`; mismos 10 días que `V3_PRODUCCION.md` (2026-09-15 a 20, 10-03, 10-04, 10-06, 10-08), 40 paradas por línea (mitad tronco compartido, mitad tramo exclusivo; menos si la línea tiene menos paradas utilizables, p. ej. 154 con 18), instantes cada 10 min de 6 a 23 h. No se redujeron las paradas.
- v4: 118 habilitadas + 9 sin habilitar (49, 97, 119, 153, 154, 163, 164, 185, 193) = 127 líneas × 10 días (1.263 pares línea-día; la 26 solo tiene 3 días). Crudos: `data/ml/replay/v4prod/v4/`.
- v3 (`path_v3_l1_s1`) con la vara vigente: 12 líneas viejas reusadas de `data/ml/replay/vara/run_base_xp` (9 días) y `run_cs_xp` (3 de oct., variante `base`); las otras 34 de las 46 habilitadas con v3, corridas de nuevo con el pin vigente en `data/ml/replay/v4prod/v3/` (340 pares línea-día).
- Comparación pareada: ambas corridas se restringen a los mismos (línea, día, parada, t). La verdad (`real_next2_s`) es idéntica en todas las filas comunes (0 diferencias) y los coches listados coinciden; por eso bondi fantasma, bondi no anunciado y sin aviso firme son casi idénticos entre v3 y v4 (dependen de la lista de candidatos, no del modelo).
- Corrida: 4 lanzadores con 2 workers (8 procesos), prioridad Idle (también los workers), afinidad 8 núcleos (máscara 0xFF hasta las 16:08 y 0x5555 después: 8 hilos en 8 núcleos físicos distintos); 15:52 a 21:52 (6,0 h de pared). `data/ml/replay/v4prod/run_idle.py` fuerza Idle en los workers (`run.run_day` los deja en BELOW_NORMAL).

## Resultado

### Grupos (v4)

@@GRP@@

(Promedio de las tasas por línea ponderado por n de la banda; no es una tasa agregada recalculada.)

### v4 contra v3, pareado (46 líneas habilitadas con v3)

@@PAR@@

Lectura: v4 no cambia el producto en las 46 líneas habilitadas (MAE 121,0 → 119,6 s; llega antes 17,6 → 17,5 %; llega después 23,8 → 23,8 %). Bondi fantasma, bondi no anunciado y sin aviso firme coinciden dentro de 0,1 pp en el agregado. La mejora mayor es la 39 (89 → 78 s); la peor diferencia por línea es +1,3 s. Las 12 líneas viejas reproducen la referencia de §5 (97 → 95 s).

## Líneas nuevas: propuesta de aviso `quality: "baja"`

Criterio idéntico al usado con v3 (`V3_PRODUCCION.md`, conclusión 4) con la vara vigente. Para cada una de 6 métricas (MAE 3–7 min, llega antes, llega después, bondi fantasma, bondi no anunciado, sin aviso firme) umbral = mediana + 1,5 × (MAD × 1,4826), calculado sobre las 72 líneas nuevas. Una línea se marca si supera el umbral en el MAE o en 2 o más métricas.

Umbrales (72 líneas): MAE 136 s, llega antes 25,8 %, llega después 28,9 %, bondi fantasma 46,0 %, bondi no anunciado 15,1 %, sin aviso firme 30,3 % (mediana de MAE 89 s; MAD×1,4826 = 32 s).

@@NUE@@

**Propuesta (23 líneas):** @@PROP@@.

- 18 por MAE > 136 s: 8 (464 s), 45, 80, 182, 145, 136, 166, 21, 96, 100, 160, 95, 55, 159, 57, 178, 15, 195 (139 s).
- 5 por 2 o más métricas sin MAE alto: 12, 68, 86, 152, 158. Son marginales: en 12, 152 y 158 la métrica más baja pasa el umbral por 3 pp o menos.
- Con la mediana de las 118 líneas como referencia (MAE 129 s) se agrega la 60 y el resto no cambia (24 líneas).
- Muestras chicas (n de la banda < 4.000): 136 (2.463), 158 (1.826), 79 (1.783), 177 (3.685). La marca de 136 y 158 es menos firme.
- Las 72 pasaron el criterio de habilitación en la vara del modelo (MAE ≤ 71,1 s en el eval congelado); en el replay el MAE del próximo coche de varias es 2 a 6 veces mayor. La diferencia viene de qué coche se anuncia como próximo (ramal / sentido desconocido, §5), no del ETA por coche.

Solo propuesta: no se aplicó en `proyectoconsola`.

### Las 8 líneas con aviso actual, medidas con v4

@@ACT@@

Con v4, 7 queda sin marca (su único motivo restante es sin aviso firme, problema de la app) y las otras 7 siguen marcadas. Con los umbrales de las 34 líneas de v3 también quedarían marcadas 34, 102 y 118, que hoy no tienen aviso (34: llega después 43,0 %; 102: bondi no anunciado 23,7 %; 118: MAE 190 s); no se propone cambiarlas en este informe.

## Experimento 2: líneas sin habilitar (49, 97, 119, 153, 154, 163, 185, 193 y 164)

Eval ampliado (no toca `data/ml/v4/eval`): todas las filas válidas de los 25 días de val de `data/ml/v4/daily` (los de `eval_meta.json`, 2026-09-15 a 10-14) con ETA real 3–7 min, de las 9 líneas, evaluadas con el checkpoint de `path_v4_l1_s1` (`@@CKPT@@`). @@N@@ filas, de las cuales @@NFZ@@ ya estaban en el eval congelado. Carpeta: `data/ml/v4_eval_ext/` (`ext_seen.parquet`, `ext_pred.npy`, `resultados.csv`, `build_and_eval.py`, `analisis.py`). Criterio de habilitación de §7: n ≥ 100 y MAE ≤ 71,1 s (1,3 × la mediana de 54,7 s de las 46 habilitadas; el umbral no se recalculó). Las filas de un mismo viaje están correlacionadas: el IC principal es un bootstrap de 2.000 réplicas remuestreando clusters (día, línea, recorrido, ventana de 30 min de `ts_p`); el IC iid es optimista. La muestra es la población de la banda, no la estratificada por ETA del eval congelado, así que el MAE difiere un poco del congelado.

@@EXP2@@

- Pasan las 9 el criterio de la vara del modelo. 164: 67,6 s (IC 66,2–69,0; el límite superior queda debajo de 71,1 s). Las otras 8: 44,5 a 54,6 s con límite superior del IC ≤ 55,5 s. El MAE en las filas adicionales coincide con el del pool completo; el 72,4 s de la 164 se reproduce en las filas congeladas (72,3 s, 276 filas).
- `start_unknown`: 164 74 %, 163 43 %, 97 39 %.

### Esas líneas en el replay (vara de producto, v4, mismos 10 días)

@@EXT@@

- 49, 97, 119, 153, 154, 163, 185 y 193: MAE del próximo coche 58–82 s, llega antes 16,6–22,8 %, bondi fantasma 5–26 %, bondi no anunciado 2–13 %, sin aviso firme 2–16 %; dentro de lo mejor de las líneas habilitadas (mediana de MAE de las 72 nuevas: 89 s). Las muestras más chicas: 154 (n = 3.376, 18 paradas) y 163 (n = 2.920).
- 164 no pasa en el replay: MAE 404 s, llega antes 37,9 %, bondi fantasma 58,0 %. Pasa la vara del modelo y falla la de producto (coincide con su `start_unknown` de 74 %). No se propone habilitarla.

## Conclusiones

1. v4 equivale a v3 en producto en las 46 líneas habilitadas: MAE 121,0 → 119,6 s, mediana de la diferencia por línea −0,9 s, v4 mejor en 37 de 46.
2. Propuesta de `quality: "baja"` para 23 de las 72 líneas nuevas (18 por MAE > 136 s, 5 por 2 o más métricas).
3. Líneas a habilitar: 49, 97, 119, 153, 154, 163, 185, 193. 164: no.

## Salvedades

Una corrida por modelo (sin semillas); 10 días; 40 paradas por línea muestreadas; los huecos de GPS afectan igual a v3 y v4; la propuesta de calidad compara cada línea con la dispersión del grupo de 72, no con un valor absoluto.

## Comandos

Desde `prediccion colectivos/`, Python `C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe`, `PYTHONPATH=.`:
```powershell
# replay: 3 lanzadores v4 (data/ml/replay/v4prod/lines_v4_{0,1,2}.txt) y 1 de v3 (lines_v3_34.txt), 2 workers c/u, Idle
powershell -File data/ml/replay/v4prod/lanzar.ps1 -Out data/ml/replay/v4prod/v4 -Model data/ml/export/path_v4_l1_s1 -Lines <lista> -Days <10 días> -Workers 2 -Tag v4_0
powershell -File data/ml/replay/v4prod/lanzar.ps1 -Out data/ml/replay/v4prod/v3 -Model data/ml/export/path_v3_l1_s1 -Lines <34 líneas> -Days <10 días> -Workers 2 -Tag v3_34
#   lanzar.ps1: python -u data/ml/replay/v4prod/run_idle.py --model .. --variants base --lines .. --days .. --stops 40 --out .. --workers 2  (+ keep_awake.py <pid>)
# tablas
powershell -File data/ml/replay/v4prod/rep.ps1        # reporte.py -> resumen.pkl
python data/ml/replay/v4prod/tablas_md.py             # tablas.md
python data/ml/replay/v4prod/informe.py               # este informe
# experimento 2
powershell -File data/ml/v4_eval_ext/lanzar.ps1       # build_and_eval.py (~50 s)
python data/ml/v4_eval_ext/analisis.py                # resultados.csv
```
