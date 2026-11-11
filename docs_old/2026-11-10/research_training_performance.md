# Research: optimización de entrenamiento A3ETAModel

**Contexto actual:** 1 línea, 12 shapes, 10 días → 11M filas, ~12 min/época  
**Target:** 4+ líneas, 90 días → estimado ~150-200M filas. Con velocidad actual: inviable.

---

## Bottlenecks identificados (en orden de impacto)

### 1. Loop Python por sample en `_iter_group` ★★★ (mayor impacto)

**Problema:** por cada fila válida del row group se ejecuta un loop Python que hace
`.copy()` + crea 12 objetos tensor individuales. Con 11M filas y 4 workers son ~44M
iteraciones Python de overhead puro.

**Solución: yield en bloques (batch tensors pre-armados)**

En vez de `yield {dict_por_sample}`, construir directamente tensores del tamaño
`batch_size` dentro del dataset y yieldarlos como un único dict ya colateado:

```python
# _iter_group construye slices de batch_size y los emite como un batch completo
# DataLoader recibe batch_size=1 (cada "sample" ya ES un batch)
# Elimina collate_fn y el loop por sample

BATCH = 2048
for start in range(0, len(valid), BATCH):
    sl = valid[start:start+BATCH]
    yield {
        "trajectory":      torch.from_numpy(np.ascontiguousarray(traj_all[sl])),
        "fleet":           torch.from_numpy(np.ascontiguousarray(fleet_all[sl])),
        ...
    }
```

`np.ascontiguousarray` hace UN copy por batch (no por sample) y garantiza que el buffer
sea writable. El batch entero es una operación numpy vectorizada.

**Impacto estimado:** 5-10x speedup en data loading. Es el cambio más importante.

**Cambios requeridos:**
- `eta_dataset.py`: `_iter_group` emite dicts con shape `(batch, ...)` en vez de `(...)` 
- `trainer.py`: `DataLoader(batch_size=1, collate_fn=lambda x: x[0])`
- `collate_eta`: puede eliminarse o simplificarse a passthrough

---

### 2. `collate_eta` usa `pad_sequence` sobre tensores de tamaño fijo ★★

**Problema:** `pad_sequence` itera en Python sobre los items del batch para calcular
la longitud máxima, aunque traj siempre es (10,3) y fleet siempre es (N_FLEET,5).

**Solución:** si se implementa el batch-level yield (#1), `collate_fn` desaparece.
Si no, reemplazar con `torch.stack` directo:

```python
"trajectory": torch.stack([item["trajectory"] for item in batch]),  # vs pad_sequence
```

**Impacto estimado:** 10-20% speedup en collate overhead.

---

### 3. Reducir redundancia intra-viaje en `features.py` ★★★

**Problema:** `make_training_rows_eta` genera todos los pares (P, F) de cada viaje —
O(N²) filas. Un viaje de 40 puntos genera 780 filas. La mayoría son redundantes:
si sabés que el bus tarda 10 min desde el punto P al punto F, podés inferirlo
casi igual desde P+1. El modelo ve el mismo viaje cientos de veces con mínima
variación.

**Por qué stratified sampling por (hora, dow) no es la solución correcta:**
El tráfico no es estacionario — un martes lluvioso se parece más a un sábado que
a un martes normal. Las categorías discretas capturan el patrón promedio pero no
la varianza real. Lo que querés conservar es diversidad de condiciones de tráfico,
y eso está en los viajes, no en las categorías.

**Solución: samplear M pares por viaje** en vez de todos los pares.

Conservás todos los viajes (diversidad de días, horas, tráfico real), solo reducís
la redundancia interna de cada uno. Si hay 40 puntos por viaje y sampleás 5 pares,
reducís 8x el tamaño del dataset manteniendo la misma diversidad de condiciones.

```python
# en make_training_rows_eta, después de construir todos los pares válidos:
import random
MAX_PAIRS_PER_TRIP = 8   # hiperparámetro a tunear

if len(rows) > MAX_PAIRS_PER_TRIP:
    rows = random.sample(rows, MAX_PAIRS_PER_TRIP)
```

**Tamaño óptimo de MAX_PAIRS_PER_TRIP:** desconocido — requiere experimentar.
Entrenar con 4, 8, 16 pares por viaje y comparar MAE en val. Si el MAE no empeora
al bajar de 16 a 8, 8 es suficiente. Hacer este experimento una vez que el pipeline
end-to-end esté validado y haya datos de 3 meses.

**Impacto estimado:** reducción proporcional al parámetro. Con MAX_PAIRS=8 y viajes
promedio de 40 puntos → ~5x menos filas. Completamente escalable: agregar líneas
no multiplica el dataset, solo agrega más viajes con sus M pares.

---

### 4. Formato Arrow IPC (Feather v2) en vez de Parquet ★

**Problema:** Parquet requiere decompresión por row group antes de poder leer.
Arrow IPC (`.arrow` / `.feather`) es lectura directa del buffer sin decompresión —
ideal para lectura repetida en entrenamiento.

**Solución:** post-procesado único: convertir `eta_train.parquet` → `eta_train.arrow`
con `pyarrow.ipc.new_file`. Las lecturas de `_iter_group` pasan de ~0.5s a ~0.1s/grupo.

```python
import pyarrow as pa, pyarrow.ipc as ipc, pyarrow.parquet as pq

tbl = pq.read_table("eta_train.parquet")
with ipc.new_file("eta_train.arrow", tbl.schema) as writer:
    for batch in tbl.to_batches(max_chunksize=825_000):
        writer.write_batch(batch)
```

`ETADataset` puede soportar ambos formatos detectando la extensión.

**Impacto estimado:** 3-5x speedup en I/O por época. Especialmente útil con múltiples
épocas (el parquet se lee N veces).

**Trade-off:** archivo más grande en disco (~3-4x, sin compresión). Pero dado que el
dataset estará en la misma máquina, vale la pena.

---

### 5. Ramal ID como índice entero, no string ★

**Problema:** `shape_lengths.get(ramal_id, 1.0)` por cada sample es un dict lookup
con string hash. Menor pero acumulable.

**Solución:** al inicio de `_iter_group`, codificar `ramal_ids` a índices enteros
y pre-computar `shape_len_arr` como array numpy:

```python
ramal_ids_arr = df["ramal_id"]  # pylist de strings
shape_len_arr = np.array([
    max(shape_lengths.get(r, 1.0), 1.0) for r in ramal_ids_arr
], dtype=np.float32)
# luego: dist_rem / shape_len_arr[valid] — vectorizado
```

Esto ya está parcialmente en el código. Completar la vectorización elimina el
`shape_lengths.get()` del loop por sample.

**Impacto estimado:** 5-10% speedup en el loop interno.

---

## Resumen de prioridades

| # | Cambio | Impacto | Esfuerzo | Estado |
|---|--------|---------|----------|--------|
| 1 | Batch-level yield en `_iter_group` | 5-10x data loading | Medio | ✅ Implementado |
| 2 | Eliminar pad_sequence en collate | 10-20% | — | ✅ Resuelto con #1 (collate_fn=identity) |
| 5 | Vectorizar shape_len lookup | 5-10% | — | ✅ Resuelto con #1 (shape_len_arr pre-computado) |
| 3 | Reducir pares por viaje en build_dataset | 5-10x menos datos | Bajo | **Pendiente — requiere experimentar con MAE** |
| 4 | Arrow IPC en vez de Parquet | 3-5x I/O | Bajo | Pendiente |

**Próximo paso:** medir MAE con el modelo entrenado en datos completos de 3 meses, luego
experimentar con `MAX_PAIRS_PER_TRIP` para encontrar el mínimo que mantiene el MAE.

---

## Target de performance post-optimización

Con stratified sampling (5M filas) + batch-level yield:
- Época estimada: **2-4 min** en lugar de 12+ min
- Escalable a 4+ líneas × 90 días sin cambiar nada más
- La GPU (3080) debería estar al 80-90% de utilización en vez del 20-30% actual
