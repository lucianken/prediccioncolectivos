# ML de predicción — arquitectura, estado y timeline

## Cuando hay datos suficientes (grabador corriendo desde ~finales de marzo 2026)

| Fase | Datos necesarios | Disponible aprox. |
|------|-----------------|-------------------|
| Phase 1: A1 Baseline (lookup velocidades) | 30+ días | ~finales de abril 2026 |
| Phase 2: Ramal ID (Fleet Transformer) | 90+ días | ~finales de junio 2026 |
| Phase 3: A3 ETA (MLP + tráfico actual) | 90-120 días | ~julio 2026 |

## Arquitectura de modelos

Ver `prediccion colectivos/prediccion_ml_plan.md` para el diseño completo. Resumen:

- **Modelo 1 — Ramal ID:** Fleet-level Transformer por línea. ~1.2M params. Fine-tune tras cada rotación de route_ids (~3 semanas). Output: probabilidad de ramal para cada vehículo activo.
- **Modelo 2 — ETA:** MLP unificado para TODAS las líneas (~300K params). Input: distancia restante + velocidad actual + fleet_state de la agencia + hora/día. Output: segundos al target. Un solo modelo, no uno por línea.
- Ambos se exportan a `.onnx` y se cargan en `proyectoconsola/server.js`.

## Arquitectura del pipeline de datos (build_dataset)

**Decisión central: unidad de trabajo = un día → un daily Parquet (idempotente)**

```
data/ml/
  daily/
    YYYY-MM-DD.parquet       ← output de procesar ese NDJSON (skip si ya existe)
    YYYY-MM-DD.carry.json    ← estado carry-forward (15 min) para el día siguiente
  training/
    eta_train.parquet        ← concat de daily/*.parquet con date < split_date
    eta_val.parquet          ← concat con date >= split_date
  manifest.json              ← {days: {date: {lines: [...], done: bool}}, val_days: 7}
```

**Dos operaciones separadas:**

1. **`process_day(date)`** — idempotente, el núcleo del pipeline
   - Si `daily/YYYY-MM-DD.parquet` ya existe → skip
   - Lee carry del día anterior si existe
   - Filtra vehículos por `label_line_map` **al leer** (no después) → solo líneas con shape en RAM. Desde 2026-07 el map es v2 con vigencias y se resuelve **por fecha del archivo** (`resolve_label_line_map(data, on_date=day_key)`): el cambio de flota AMBA de mayo-junio 2026 reasignó sufijos (ej. 151: 4045 hasta 29/05 → 4852 desde 11/06)
   - Escribe features ETA al Parquet **row a row, streaming** (no acumula lista en RAM — O(n²) pares es el costo correcto, la mitigación es el streaming write, no reducir los pares)
   - Escribe carry del día al terminar

2. **`assemble_dataset()`** — barato, siempre corre al final
   - Lee todos los `daily/*.parquet`
   - Split por fecha: últimos `val_days=7` días → val, resto → train (ventana deslizante, no porcentaje)
   - Concatena → `eta_train.parquet`, `eta_val.parquet`

**Agregar una línea nueva:**
- El manifest guarda `{date: {lines: [...], done: bool}}` por día procesado
- Al agregar línea nueva: `build_dataset` detecta qué días no incluyen esa línea → borra esos daily Parquets → los reprocesa
- Es el costo correcto — no hay atajo sin perder información

**Filter-first (decisión de memoria):**
- El NDJSON tiene ~5000-8000 vehículos de CABA/GBA
- Filtrar por `label_line_map` al acumular observaciones (no después de acumular todo)
- Reduce RAM de "toda CABA" a "solo vehículos de líneas con shape"

## Estructura del código

```
prediccion/
├── pipeline/
│   ├── reader.py        ← iter_frames, reconstruct_snapshots, iter_daily_files
│   ├── segmenter.py     ← segment_vehicle_history → list[Trip]
│   ├── projector.py     ← project_to_shape (linear scan O(n_shape), correcto para escala actual)
│   ├── features.py      ← make_training_rows_eta (genera todos los pares P→F, O(n²) necesario)
│   ├── shapes_io.py     ← load_shapes, load_label_line_data/resolve_label_line_map (v2 con on_date), get_shape_points
│   └── build_dataset.py ← CLI actual (PENDIENTE refactor a process_day + assemble_dataset)
├── models/
│   ├── a1_baseline.py   ← lookup tabla velocidad/segmento/hora/dow
│   ├── a3_eta.py        ← MLP unificado (Transformer en Fase 5)
│   └── ramal_id.py      ← Fleet-level Transformer
├── inference/
│   ├── predictor.py
│   ├── fleet_cache.py
│   └── shape_loader.py
├── api/app.py           ← FastAPI
├── train.py             ← CLI unificado de entrenamiento (phases 1/2/3)
├── serve.py             ← servidor de predicción
└── data/line_shapes.json ← shapes de las 7 líneas (578 KB, incluido en repo)
```

## Correr build_dataset (estado actual, antes del refactor)

```powershell
# PowerShell: usar backtick para continuar líneas, no backslash
python -m prediccion.pipeline.build_dataset `
    --data-dir "Z:\grabaciones" `
    --ml-dir "data\ml" `
    --lines 26,39,42,92,124,151,168
```

Montar SMB primero si hace falta:
```powershell
net use Z: \\192.168.0.18\buffer /user:laek /persistent:yes
```

## Shapes disponibles

7 líneas en `prediccion/data/line_shapes.json`: 26, 39, 42, 92, 124, 151, 168.
Para agregar líneas o regenerar: ver `prediccion/SHAPES_PIPELINE.md` (pipeline en `osm_lines/`, sin GTFS, sin BabusNova).

## Pendiente / estado del código

- `build_dataset.py`: funciona pero pendiente refactor a `process_day` + `assemble_dataset` + manifest (arquitectura acordada, no implementada aún)
- Phase 1 nunca corrió (esperando datos suficientes)
- Identificación de ramales (`ramal_id.py`) sin validar en producción
- Fine-tuning automático post-rotación de route_ids: Fase 4, post Phase 3
