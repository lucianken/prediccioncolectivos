# prediccion-colectivos

Pipeline ML para predicción de ETA de colectivos CABA/GBA.
Grabador en NUC → NDJSON diarios → pipeline Python → modelos .onnx → proyectoconsola.

## Stack

- **NUC (192.168.0.18)**: grabador Docker, datos en `/mnt/buffer/grabaciones`
- **Windows (esta PC)**: pipeline ML lee de `Z:\grabaciones` (SMB), entrena en RTX 3080
- **proyectoconsola**: sirve los modelos `.onnx` en producción al frontend

## Skills (cargar según tarea)

En `c:\Users\LK\Documents\Dondeestaelbondi\.claude\skills\`:
- `grabador_nuc.md` — formato NDJSON, deploy, monitoreo, guardrails, reconstrucción de estado
- `ml_timeline.md` — arquitectura pipeline ML, decisiones de diseño, código, timeline de fases
- `168_ramal_analysis.md` — análisis exhaustivo línea 168: ramal map completo, bug Darwin, 10 features testeadas, metodología generalizable a otras líneas
- `enrichment_ramal.md` — pipeline de enriquecimiento, RamalEngine, bug Darwin (resumen)

## Documento rector

**`ARQUITECTURA.md`** — plan vigente desde 2026-11-10 (pipeline v2 sin route_id, vara de medir, escalera de experimentos). Manda sobre cualquier otro doc. Copias de los docs anteriores: `docs_old/2026-11-10/` (tag git `pre-arquitectura-2026-11`).

## Docs de referencia del proyecto

- `prediccion_ml_plan.md` — **histórico**: diseño original (A3ETAModel, experimentos, porqué de las decisiones); su estado, fases y todo lo de ramal lookup quedaron sin efecto.
- `prediccion/SHAPES_PIPELINE.md` — cómo se genera/regenera `line_shapes.json`
- `README.md` — setup SMB, comandos de uso
- `analisis_grabacion_mensual.md` — justificación de decisiones del grabador

## Estado (2026-07-11) — desactualizado, ver `ARQUITECTURA.md`

- Grabador: corriendo, ~15 semanas de datos acumulados
- **LABEL_LINE_MAP v3** (2026-07): schema por línea con vigencias `from`/`to` (cambio de flota AMBA mayo-junio 2026: ej. 151: 4045 hasta 29/05 → 4852 desde 11/06) y dos secciones: `lines` = SOLO AMBA / `other_lines` = homónimos del resto del país (la API reporta todo el país). Todo lo no resuelto en `proyectoconsola/pending_label_work.json` (único archivo de trabajo con `scope`; MD generado; resolver con `node scripts/resolve_pending.js` interactivo, que promueve y sincroniza el espejo del map acá). Loader date-aware y AMBA-only por defecto: `shapes_io.load_label_line_map(path, on_date=...)` (`resolve_label_line_index(..., include_other=True)` para incluir interior); el pipeline resuelve el map por fecha de cada NDJSON. Tras un scan nuevo: `apply_scan_results.py` mergea al pending.
- Shapes: 7 líneas (26, 39, 42, 92, 124, 151, 168)
- Ramal ID: **abandonado** (usaba route_id). El pipeline nuevo elige el recorrido por geometría (`ARQUITECTURA.md` §4.1).
- A3ETAModel (ETA): no-fleet ep21/ep24 ~72 s val MAE solo línea 39 (no comparable con A1/naive, ver `ARQUITECTURA.md` §5). No hay modelo en producción. Fleet bloqueado por costo computacional (~12× más lento). Ver `prediccion_ml_plan.md` §pendiente.
- Experimento "llegando": umbral recomendado `pred_eta < 150s OR dist_remaining < 300m` (F2=0.775, recall=89%).
