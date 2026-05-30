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

## Docs de referencia del proyecto

- `prediccion_ml_plan.md` — diseño completo de Modelo 1 (ramal ID) y Modelo 2 (ETA)
- `prediccion/SHAPES_PIPELINE.md` — cómo se genera/regenera `line_shapes.json`
- `README.md` — setup SMB, comandos de uso
- `analisis_grabacion_mensual.md` — justificación de decisiones del grabador

## Estado (2026-04-17)

- Grabador: corriendo, ~3 semanas de datos acumulados
- Shapes: 7 líneas (26, 39, 42, 92, 124, 151, 168)
- Pipeline ML: funcional pero pendiente refactor arquitectónico (ver `ml_timeline.md`)
- Phase 1 (A1 Baseline): no corrió aún, disponible ~finales de abril 2026
