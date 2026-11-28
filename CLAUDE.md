# prediccion-colectivos

Predicción de ETA de colectivos AMBA: grabador en la NUC → NDJSON diarios → pipeline v2 (Python, RTX 3080) → modelo por tramos `.onnx` → proyectoconsola (producción: `path_v4_l1_s1`, 129 líneas).

## Documento rector
`ARQUITECTURA.md` manda sobre cualquier otro doc: objetivo, reglas, datos, pipeline, asignación, varas de medida, estado de producción, cómo correr y pendientes priorizados (§11).
**Lo de producción se muda a `lucianken/bondi` (`red/`)**: `LABEL_LINE_MAP`, recorridos, asignación, export ONNX, armado del paquete y servicio de identificación de recorrido. Este proyecto queda como investigación. Detalle: ARQUITECTURA §11, «Lo de producción se muda a `bondi/red`»; reglas de convivencia: `../bondi/docs/ROADMAP.md`, sección «Transición».

**Reglas de producción: paquete `red`, importado por tag (desde 2026-11-28, F1.5).** La asignación de ping a recorrido y sentido (`red.geo_assign`), la referencia de inferencia (`red.path_reference`), la geometría (`red.geometria`: `ShapeIndex`, `ShapeGeo`), las paradas por tramo (`red.stops`), la carga del `LABEL_LINE_MAP` (`red.label_map`) y `encode_time_np` (`red.tiempo`) no existen en este repo: se importan de `red`. Versión fijada en `prediccion/requirements-train.txt` (hoy `red-v0.1.0`); cada dataset y cada corrida registra `red_version` en su `meta`.
- **Cambiar una regla:** se cambia en `../bondi/red/python/` con su test, se publica un tag nuevo `red-vX.Y.Z` (la versión de `pyproject.toml`), y acá se sube el tag en `requirements-train.txt` y se reinstala (`& $PY -m pip install "red[proyeccion] @ git+https://github.com/lucianken/bondi@red-vX.Y.Z#subdirectory=red/python"`). Para medir una regla nueva antes de publicarla: `pip install -e ../bondi/red/python` en una rama de `bondi`, y el `meta` de la corrida dice qué versión usó.
- Sin copias ni módulos de compatibilidad: si algo de `red` hace falta acá, se importa de `red`.
- Siguen acá hasta el corte (F1.2): el espejo `LABEL_LINE_MAP.json` (lo lee el grabador de CuandoSubo de la NUC), `prediccion/v2/shapes.py` y `prediccion/label_map/`. Export y fixture de paridad (`export_path_onnx.py`, `gen_path_parity_fixture.py`) importan `red` y se mudan en F1.6.
Resultados y registros de error: `RESULTADOS.md`. Historia y diseños abandonados (A3, ramal por route_id, research de junio): `docs_old/`; versión del 2026-11-10 en el tag git `pre-arquitectura-2026-11`.

## Stack
- NUC (192.168.0.18): grabador Docker, datos en `/mnt/buffer/grabaciones`.
- Esta PC: lee `Z:\grabaciones` (SMB), entrena en la RTX 3080 (Python313 con CUDA; corridas largas con `prediccion/scripts/keep_awake.py`).
- proyectoconsola: sirve el `.onnx` y es la fuente de shapes (`proyectoconsola/data/line_shapes/`).

## Mapa
- `prediccion/v2/`: pipeline de dataset (la asignación la importa de `red`). `prediccion/train_path.py`, `eval.py`, `replay/`: entrenamiento, evaluación y vara de producto. `prediccion/scripts/run_v*.py`: lanzadores.
- `prediccion/INFERENCIA_PATH.md`: contrato de inferencia (modelo → app). `prediccion/SHAPES_PIPELINE.md`: shapes.
- `prediccion/label_map/`: `scan_suffix_changes.py` y `apply_scan_results.py`, herramienta para cuando cambia la flota (el scan tiene fechas fijas de julio 2026: ajustarlas antes de reusarlo).
- `grabador/`, `grabador_cuandosubo/`: captura de la API CABA y de CuandoSubo.
- `experiments/`: mediciones con informe (`INFORME.md` por carpeta).
- `legacy/`: scripts de un solo uso y `analisis_flota/`; no se usan. (El resto del código del A3 sigue en `prediccion/` hasta la Fase 2.)

## Reglas
- La línea de un coche sale solo del sufijo del label (`LABEL_LINE_MAP.json`); nunca route_id, trip_id ni start_time.
- Tests de comportamiento observable, sin change detectors.

## Skills (en `../.claude/skills/`, cargar según tarea)
`grabador_nuc.md`, `shapes_fuente.md`, `oba_identificacion.md`, `route_map_watcher.md`, `osm_fix_estado.md`, `proyectos_estado.md`, `enrichment_ramal.md` (gate por label; el ramal por route_id está muerto), `ml_timeline.md` (puntero a ARQUITECTURA §4 y §10).
