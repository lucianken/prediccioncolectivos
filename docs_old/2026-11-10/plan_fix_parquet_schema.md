# Plan: corregir schema del parquet de entrenamiento

**Para pasar a otra instancia. Self-contained.**

---

## Problema raíz

`build_dataset.py` escribe `traj_dist`, `traj_speed`, `traj_dt` y `fleet_features_flat` como
columnas Arrow `List<double>` (variable-length, float64). Esto causa dos problemas en entrenamiento:

1. **No son convertibles a numpy zero-copy.** PyArrow `ChunkedArray.to_numpy()` falla para
   listas de longitud variable; hay que llamar `to_pylist()` que crea ~300M objetos Python
   por row group → RAM explosion e inicialización muy lenta.

2. **float64 es el doble de tamaño necesario.** Las features de trayectoria y flota no
   necesitan más de float32.

El parquet actual tiene 75M filas, ~1.27 GB comprimido, pero se expande a ~55 GB en RAM
si se carga todo. Eso no cabe en 32 GB. El streaming por row groups (IterableDataset)
es la estrategia correcta, pero la lectura de columnas list<double> dentro de cada
row group sigue siendo el cuello de botella.

**La solución es corregir el schema en origen (build_dataset.py / features.py),
no agregar conversión HDF5 ni ninguna otra capa.**

---

## Schema correcto del parquet

### Columnas actuales (MALO)

```
traj_dist:           List<double>   variable-length, 1–10 elementos
traj_speed:          List<double>   variable-length, 1–10 elementos
traj_dt:             List<double>   variable-length, 1–10 elementos
fleet_features_flat: List<double>   variable-length, 0–100 elementos
n_fleet:             int64
dist_remaining_m:    double
dist_along_norm:     double
speed_mps:           double
hour_sin:            double
hour_cos:            double
dow:                 int64
has_active_bus:      bool
observed_eta_s:      int64
time_since_start:    double
```

### Columnas nuevas (CORRECTO)

```
traj_flat:           FixedSizeList<float32>[30]   10 puntos × 3 features (dist_norm, speed, dt)
                                                   paddeado con ceros si hay menos de 10 puntos
traj_len:            int8                          longitud real de la trayectoria (1–10)
fleet_flat:          FixedSizeList<float32>[N_FLEET*5]  hasta N_FLEET buses × 5 features
                                                        paddeado con ceros
n_fleet:             int8                              cantidad real de buses activos
dist_remaining_m:    float32
dist_along_norm:     float32
speed_mps:           float32
hour_sin:            float32
hour_cos:            float32
dow:                 int8
has_active_bus:      bool
observed_eta_s:      float32
time_since_start:    float32
```

### Por qué FixedSizeList funciona y List no

Arrow `FixedSizeList<float32>[N]` almacena los datos como un buffer contiguo de float32.
`np.asarray(chunked_array)` devuelve una view numpy de shape `(n_rows, N)` — zero-copy,
sin crear objetos Python. Luego se puede `.reshape(-1, 10, 3)` para traj.

Arrow `List<double>` no tiene ese buffer contiguo. Requiere `to_pylist()`.

---

## Archivos a cambiar

### 1. `prediccion/pipeline/features.py`

Función `make_training_rows_eta` — cambiar la estructura de salida:

**Antes:**
```python
rows.append({
    ...
    "traj_dist": traj_dist,           # list[float], variable len
    "traj_speed": traj_speed,         # list[float], variable len
    "traj_dt": traj_dt,               # list[float], variable len
    "fleet_features_flat": fleet_features_flat,  # list[float], variable len
    "n_fleet": n_fleet,
})
```

**Después:**
```python
# Construir traj_flat: (10, 3) → flatten → (30,) float32, paddeado
traj_arr = [0.0] * 30
traj_actual_len = len(traj_dist)
for j in range(min(traj_actual_len, 10)):
    traj_arr[j * 3 + 0] = float(traj_dist[j])
    traj_arr[j * 3 + 1] = float(traj_speed[j])
    traj_arr[j * 3 + 2] = float(traj_dt[j])

# Construir fleet_flat: (20, 5) → flatten → (100,) float32, paddeado
fleet_arr = [0.0] * 100
for j, row in enumerate(fleet_rows[:20]):   # fleet_rows ya existe en la función
    for k, v in enumerate(row[:5]):
        fleet_arr[j * 5 + k] = float(v)

rows.append({
    ...
    "traj_flat": traj_arr,     # list[float] de exactamente 30 elementos
    "traj_len": min(traj_actual_len, 10),
    "fleet_flat": fleet_arr,   # list[float] de exactamente 100 elementos
    "n_fleet": n_fleet,
    # ELIMINAR: traj_dist, traj_speed, traj_dt, fleet_features_flat
})
```

### 2. `prediccion/pipeline/build_dataset.py`

Buscar el lugar donde se construye el schema Arrow o se llama `pa.Table.from_pydict` /
`pd.DataFrame.to_parquet`. Forzar los tipos correctos al escribir.

Si se usa pandas:
```python
import pyarrow as pa
import pyarrow.parquet as pq

schema = pa.schema([
    pa.field("ramal_id",        pa.string()),
    pa.field("seg_idx",         pa.int32()),
    pa.field("dist_remaining_m", pa.float32()),
    pa.field("dist_along_norm", pa.float32()),
    pa.field("speed_mps",       pa.float32()),
    pa.field("hour_sin",        pa.float32()),
    pa.field("hour_cos",        pa.float32()),
    pa.field("dow",             pa.int8()),
    pa.field("has_active_bus",  pa.bool_()),
    pa.field("observed_eta_s",  pa.float32()),
    pa.field("time_since_start", pa.float32()),
    pa.field("traj_flat",       pa.list_(pa.float32(), 30)),   # FixedSizeList
    pa.field("traj_len",        pa.int8()),
    pa.field("fleet_flat",      pa.list_(pa.float32(), 100)),  # FixedSizeList
    pa.field("n_fleet",         pa.int8()),
])

# Al escribir:
table = pa.Table.from_pydict(batch_dict, schema=schema)
writer.write_table(table)
```

Si actualmente se usa `df.to_parquet(...)`, reemplazar con escritura explícita via
`pq.ParquetWriter` con el schema forzado. El schema es lo que garantiza el tipo correcto;
sin él pandas infiere float64 por defecto.

**Leer build_dataset.py para encontrar exactamente dónde se escribe el parquet antes de
implementar.**

### 3. `prediccion/models/eta_dataset.py`

La clase es `ETADataset(IterableDataset)`. Cambiar `_iter_group`:

**Antes (slow):**
```python
_LIST_COLS = {"traj_dist", "traj_speed", "traj_dt", "fleet_features_flat"}
for col in self._read_cols:
    if col == "ramal_id" or col in _LIST_COLS:
        df[col] = tbl[col].to_pylist()       # crea millones de objetos Python
    else:
        df[col] = np.asarray(tbl[col])

# y en el loop por sample:
td  = np.array(df["traj_dist"][idx], dtype=np.float32)   # pylist → numpy por item
ts  = np.array(df["traj_speed"][idx], dtype=np.float32)
tdt = np.array(df["traj_dt"][idx], dtype=np.float32)
```

**Después (fast):**
```python
# Todas las columnas son escalares o FixedSizeList → np.asarray funciona en todas
for col in self._read_cols:
    if col == "ramal_id":
        df[col] = tbl[col].to_pylist()   # único string column, inevitable
    else:
        df[col] = np.asarray(tbl[col])   # zero-copy para todo, incluyendo FixedSizeList

# Pre-construir arrays de traj y fleet para todo el row group a la vez:
traj_flat  = df["traj_flat"].reshape(-1, 10, 3).astype(np.float32)   # (N_rg, 10, 3)
traj_len   = df["traj_len"].astype(np.int32)                          # (N_rg,)
fleet_flat = df["fleet_flat"].reshape(-1, 20, 5).astype(np.float32)  # (N_rg, 20, 5)

# Construir máscaras vectorizadas (sin loop por fila):
traj_mask  = np.arange(10)[None, :] >= traj_len[:, None]   # (N_rg, 10) bool
fleet_mask = np.arange(20)[None, :] >= df["n_fleet"][:, None]  # (N_rg, 20) bool

# En el loop por sample (solo indexar arrays, sin crear objetos):
for idx in valid:
    yield {
        "trajectory":      torch.from_numpy(traj_flat[idx]),         # (10, 3)
        "trajectory_mask": torch.from_numpy(traj_mask[idx]),         # (10,)
        "fleet":           torch.from_numpy(fleet_flat[idx]),        # (20, 5)
        "fleet_mask":      torch.from_numpy(fleet_mask[idx]),        # (20,)
        ...
    }
```

Eliminar `self._has_full_traj` y `self._has_fleet` — con el nuevo schema siempre están.
Actualizar `_OPTIONAL_COLS`, `_LIST_COLS`, y `_BASE_COLS` acorde.

### 4. `prediccion_ml_plan.md`

En la sección §5 "Pipeline de datos", subsección "Paso 4 — Construir dataset de entrenamiento",
actualizar el schema del dataset de ETA:

- Reemplazar `traj_dist / traj_speed / traj_dt (list)` por `traj_flat (FixedSizeList[30], float32)`
  y `traj_len (int8)`
- Reemplazar `fleet_features_flat (list)` por `fleet_flat (FixedSizeList[100], float32)`
- Agregar nota: "Todas las columnas numéricas en float32. Las columnas FixedSizeList se
  leen con np.asarray() sin pasar por Python (zero-copy)."
- Actualizar la nota en §9 "Hardware": tamaño del parquet de entrenamiento aumenta de
  ~1.3 GB a ~3-6 GB por el padding de FixedSizeList, pero la carga es mucho más rápida.

---

## Determinar N_FLEET antes de implementar

**El cap actual de 20 en `features.py` es incorrecto.** El plan ML especifica 40-200
vehículos por agencia. La línea 39 tiene ~94 en flota total; en hora pico pueden estar
activos 40-60 simultáneamente reportando posición.

**Paso previo obligatorio:** medir el máximo real de buses activos por línea en los NDJSON.
Correr esto sobre una muestra de datos antes de fijar N_FLEET:

```python
# medir_fleet_max.py — correr sobre un subset de NDJSON antes de decidir N_FLEET
import gzip, json, collections

line_targets = {"39", "42", "26", "92", "124", "151", "168"}
max_per_line: dict[str, int] = collections.defaultdict(int)

# reconstruir estado de la flota y contar por línea en cada snapshot
# leer algunos días de NDJSON y anotar el máximo simultáneo por line_number
```

**Recomendación según el plan ML:** usar N_FLEET = 60 como punto de partida razonable
(cubre la mayoría de los casos sin triplicar el tamaño del parquet). Si el máximo
observado es mayor, ajustar.

| N_FLEET | FixedSizeList size | Raw 75M filas | Parquet estimado (con compresión) |
|---------|-------------------|--------------|----------------------------------|
| 20 (actual, incorrecto) | [100]  | 30 GB | ~1–2 GB |
| 60 (recomendado)        | [300]  | 90 GB | ~3–6 GB |
| 100 (máximo conservador)| [500]  | 150 GB| ~5–10 GB |

Los ceros de padding comprimen muy bien en Parquet (Snappy/Zstd). El parquet real
probablemente sea la mitad del estimado. Incluso con N_FLEET=100, el parquet debería
quedar en ~5-10 GB — manejable en disco, y el IterableDataset lee un row group a la vez.

**Actualizar también en `eta_dataset.py` y en el plan:**
`N_FLEET = 60  # ajustar según medir_fleet_max.py`

---

## Qué NO cambiar

- La estrategia `IterableDataset` (stream por row groups) — sigue siendo necesaria;
  los 75M rows × float32 siguen sin caber en 32 GB RAM.
- La arquitectura `A3ETAModel` (a3_eta.py) — no depende del formato de lectura.
- El script `convert_to_hdf5.py` — puede eliminarse, ya no es necesario.
- `collate_eta` — sin cambios.

---

## Tamaño estimado del nuevo parquet

| Columna | Bytes/fila | 75M filas |
|---------|-----------|-----------|
| traj_flat (30 float32) | 120 | 9 GB raw |
| fleet_flat (100 float32) | 400 | 30 GB raw |
| Escalares (10 float32 + bools) | ~44 | 3.3 GB raw |
| **Total raw** | ~564 | **~42 GB** |

Con compresión snappy/zstd en Parquet (los ceros de padding comprimen bien):
estimado **~2-5 GB** en disco. El parquet actual es 1.27 GB con variable-length (sin padding);
el nuevo es más grande pero eso es aceptable.

Por row group (75M / 91 grupos = ~825K filas):
- Raw: ~465 MB
- Al leer np.asarray(): instantáneo (zero-copy del buffer Arrow)
- Sin loop Python por fila en la etapa de construcción de arrays

---

## Prerequisito: regenerar el parquet

Los parquets existentes (`data/ml/training/eta_train.parquet` y `eta_val.parquet`) tienen
el schema viejo. Después de cambiar features.py y build_dataset.py:

```
python -m prediccion.pipeline.build_dataset \
  --data-dir Z:\grabaciones \
  --ml-dir data\ml \
  --shapes-url prediccion/data/line_shapes.json
```

O si ya existen los archivos cacheados por día, usar `--merge-only` para solo re-mergear
con el nuevo schema (requiere borrar los parquets viejos primero).

**Los parquets existentes pueden eliminarse** — se regeneran desde los NDJSON que están
en el NUC. Los NDJSON son la fuente de verdad, no los parquets.

---

## Orden de implementación sugerido

1. Leer `build_dataset.py` completo para entender cómo escribe el parquet hoy.
2. Cambiar `features.py` (output de `make_training_rows_eta`).
3. Cambiar `build_dataset.py` (schema Arrow al escribir).
4. Regenerar el parquet (correr phase 1).
5. Cambiar `eta_dataset.py` (lectura con np.asarray + reshape).
6. Verificar que el entrenamiento corra sin errores con el nuevo parquet.
7. Actualizar `prediccion_ml_plan.md` §5 y §9.
8. Eliminar `prediccion/pipeline/convert_to_hdf5.py` (ya no necesario).
