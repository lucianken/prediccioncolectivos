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

## Docs de referencia del proyecto

- `prediccion_ml_plan.md` — diseño completo del sistema: ramal lookup (geométrica, no ML) y A3ETAModel (ETA)
- `prediccion/SHAPES_PIPELINE.md` — cómo se genera/regenera `line_shapes.json`
- `README.md` — setup SMB, comandos de uso
- `analisis_grabacion_mensual.md` — justificación de decisiones del grabador

## Estado (2026-06-05)

- Grabador: corriendo, ~10 semanas de datos acumulados
- Shapes: 7 líneas (26, 39, 42, 92, 124, 151, 168)
- Ramal ID: **lookup geométrica offline** (`ramal_lookup/`), no modelo ML. `route_id → shape` determinístico. Validado línea 39: 36/36 route_ids correctos.
- A3ETAModel (ETA): Fase 3 activa. No-fleet ep24 = **72.7s val MAE** (mejor a la fecha). Fleet bloqueado por costo computacional (~12× más lento). Ver `prediccion_ml_plan.md` §pendiente.
- Experimento "llegando": umbral recomendado `pred_eta < 150s OR dist_remaining < 300m` (F2=0.775, recall=89%).
