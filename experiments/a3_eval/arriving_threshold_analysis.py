#!/usr/bin/env python3
"""
Experimento: distribución de error del modelo A3 por distancia/ETA
y búsqueda del umbral óptimo para mostrar "llegando" en la UI.

Para cada fila del val parquet: corre el modelo ONNX, compara predicción
con ETA real observado, y hace grid search sobre (time_threshold, dist_threshold).

Uso: python experiments/arriving_threshold_analysis.py
"""
import sys, json, time, datetime
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

import numpy as np
import pyarrow.parquet as pq
import torch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from prediccion.pipeline.shapes_io import load_shapes, DEFAULT_SHAPES_PATH
from prediccion.pipeline.projector import polyline_length_m

CKPT_PATH   = ROOT / "data/ml/models/eta_a3_best.pt"
VAL_PARQUET = ROOT / "data/ml/training/eta_val.parquet"
OUTPUT_DIR  = ROOT / "data/ml/experiments"
BATCH       = 8192  # batch más grande en GPU

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {DEVICE}")

# ── Shape lengths ─────────────────────────────────────────────────────────────
print("Cargando shape lengths...")
shapes = load_shapes(str(DEFAULT_SHAPES_PATH))
shape_lengths: dict[str, float] = {}
for line_num, line_data in shapes.items():
    for ramal in line_data.get("ramales", []):
        sh_id = ramal.get("shapeId")
        if sh_id:
            pts = [tuple(p) for p in ramal["points"]]
            if len(pts) >= 2:
                shape_lengths[sh_id] = polyline_length_m(pts)
print(f"  {len(shape_lengths)} shapes")

# ── Modelo PyTorch ────────────────────────────────────────────────────────────
print(f"Cargando modelo: {CKPT_PATH}")
from prediccion.models.a3_eta import A3ETAModel
ckpt = torch.load(CKPT_PATH, map_location=DEVICE)
d_model = ckpt.get("d_model", 64)
model = A3ETAModel(d_model=d_model).to(DEVICE)
model.load_state_dict(ckpt["model_state_dict"])
model.eval()
print(f"  d_model={d_model}, device={DEVICE}")

# ── Inferencia sobre val parquet ──────────────────────────────────────────────
READ_COLS = [
    "ramal_id", "dist_remaining_m", "dist_along_norm",
    "hour_sin", "hour_cos", "dow", "has_active_bus", "observed_eta_s",
    "time_since_start", "ts_age_s", "traj_flat", "traj_len",
]

pf = pq.ParquetFile(str(VAL_PARQUET))
n_groups = pf.metadata.num_row_groups
print(f"\nVal parquet: {pf.metadata.num_rows:,} filas, {n_groups} grupos")

all_dist, all_obs, all_pred = [], [], []

t0 = time.time()
for g in range(n_groups):
    tbl = pf.read_row_group(g, columns=READ_COLS)

    ramal_ids  = tbl["ramal_id"].to_pylist()
    dist_rem   = np.asarray(tbl["dist_remaining_m"], dtype=np.float32)
    dist_along = np.asarray(tbl["dist_along_norm"],  dtype=np.float32)
    hour_sin   = np.asarray(tbl["hour_sin"],         dtype=np.float32)
    hour_cos   = np.asarray(tbl["hour_cos"],         dtype=np.float32)
    dow        = np.asarray(tbl["dow"],              dtype=np.int64)
    has_bus    = np.asarray(tbl["has_active_bus"],   dtype=np.float32)
    obs_eta    = np.asarray(tbl["observed_eta_s"], dtype=np.float32)
    tss        = np.asarray(tbl["time_since_start"], dtype=np.float32) / 3600.0
    ts_age     = np.asarray(tbl["ts_age_s"],         dtype=np.float32) / 600.0
    traj_len_a = np.asarray(tbl["traj_len"],         dtype=np.int32)

    # traj_flat: FixedSizeList(30) → (N, 10, 3), aplicar misma normalización que ETADataset
    col = tbl["traj_flat"]
    combined = col.combine_chunks() if hasattr(col, "combine_chunks") else col
    traj_all = np.asarray(combined.flatten(), dtype=np.float32).reshape(-1, 10, 3).copy()
    np.clip(traj_all[:, :, 0], 0.0, 1.0, out=traj_all[:, :, 0])  # dist_along_norm
    traj_all[:, :, 1] /= 30.0                                      # speed / 30
    traj_all[:, :, 2] /= 30.0                                      # dt / 30
    np.clip(traj_all[:, :, 2], 0.0, 5.0, out=traj_all[:, :, 2])  # dt capped
    np.nan_to_num(traj_all, nan=0.0, posinf=0.0, neginf=0.0, copy=False)

    traj_mask = np.arange(10)[None, :] >= traj_len_a[:, None]  # True = padding

    # Vectorized shape length lookup — sin loop Python por fila
    unique_ids = list(dict.fromkeys(ramal_ids))  # orden de aparición
    id_to_len  = {rid: max(shape_lengths.get(rid, 1.0), 1.0) for rid in unique_ids}
    id_to_idx  = {rid: i for i, rid in enumerate(unique_ids)}
    len_lut    = np.array([id_to_len[rid] for rid in unique_ids], dtype=np.float32)
    row_idx    = np.array([id_to_idx[rid] for rid in ramal_ids], dtype=np.int32)
    shape_len_arr = len_lut[row_idx]
    dist_rem_norm = dist_rem / shape_len_arr

    # Filtrar filas sin shape_length conocido (ramal_id no en line_shapes.json → dist_rem_norm inválida)
    has_shape = np.array([rid in shape_lengths for rid in ramal_ids], dtype=bool)

    # Filtrar obs_eta > 7200s: gap GPS, no representan viaje real
    valid = np.where(
        has_shape & (obs_eta > 0) & (obs_eta <= 7200.0) & (dist_rem >= 100.0) & (dist_along >= 0) & (dist_along <= 1.0)
    )[0]
    if len(valid) == 0:
        continue

    preds_g = np.zeros(len(valid), dtype=np.float32)

    with torch.no_grad():
        for start in range(0, len(valid), BATCH):
            sl = valid[start:start + BATCH]
            b  = len(sl)

            t = lambda x, dt=torch.float32: torch.from_numpy(np.ascontiguousarray(x)).to(dt).to(DEVICE)

            out = model(
                trajectory          = t(traj_all[sl]),
                trajectory_mask     = t(traj_mask[sl], torch.bool),
                fleet               = torch.zeros(b, 0, 5, device=DEVICE),
                fleet_mask          = torch.zeros(b, 0, dtype=torch.bool, device=DEVICE),
                hour_sin            = t(hour_sin[sl, None]),
                hour_cos            = t(hour_cos[sl, None]),
                dow                 = t(dow[sl, None], torch.int64).squeeze(-1),
                dist_remaining_norm = t(dist_rem_norm[sl, None]),
                time_since_start    = t(tss[sl, None]),
                ts_age_s            = t(ts_age[sl, None]),
                has_active_bus      = t(has_bus[sl, None]),
            )
            preds_g[start:start + b] = out.squeeze(-1).cpu().numpy()

    all_dist.append(dist_rem[valid])
    all_obs.append(obs_eta[valid])
    all_pred.append(preds_g)

    elapsed = time.time() - t0
    eta_remaining = (elapsed / (g + 1)) * (n_groups - g - 1)
    print(f"  grupo {g+1}/{n_groups}  {elapsed:.0f}s  ETA restante: {eta_remaining:.0f}s")

dist_arr = np.concatenate(all_dist)
obs_arr  = np.concatenate(all_obs)
pred_arr = np.concatenate(all_pred)
err_arr  = pred_arr - obs_arr   # positivo = sobreestimé
abs_err  = np.abs(err_arr)

print(f"\nInferencia completa: {time.time()-t0:.1f}s  —  {len(dist_arr):,} filas")

# ── Error por bucket de distancia ─────────────────────────────────────────────
DIST_BUCKETS = [
    ("100-250m",  100,   250),
    ("250-500m",  250,   500),
    ("500m-1km",  500,  1000),
    ("1km-2km",  1000,  2000),
    ("2km-5km",  2000,  5000),
    ("5km+",     5000, 99999),
]

print("\n=== ERROR POR BUCKET DE DISTANCIA ===")
print(f"{'Bucket':15s}  {'N':>8}  {'MAE':>7}  {'P50':>7}  {'P90':>7}  {'Bias':>8}  {'Under%':>7}")
dist_results = {}
for name, lo, hi in DIST_BUCKETS:
    m = (dist_arr >= lo) & (dist_arr < hi)
    if not m.any(): continue
    ae, er = abs_err[m], err_arr[m]
    n = m.sum()
    r = {"n": int(n), "mae": float(ae.mean()), "p50": float(np.percentile(ae, 50)),
         "p90": float(np.percentile(ae, 90)), "bias": float(er.mean()),
         "under_pct": float((er < 0).mean() * 100)}
    dist_results[name] = r
    print(f"{name:15s}  {r['n']:>8,}  {r['mae']:>7.1f}  {r['p50']:>7.1f}  {r['p90']:>7.1f}  {r['bias']:>8.1f}  {r['under_pct']:>6.1f}%")

# ── Error por bucket de ETA predicho ─────────────────────────────────────────
ETA_BUCKETS = [
    ("<60s",     0,   60),
    ("60-120s",  60,  120),
    ("120-180s", 120, 180),
    ("3-5min",   180, 300),
    ("5-10min",  300, 600),
    ("10min+",   600, 99999),
]

print("\n=== ERROR POR BUCKET DE ETA PREDICHO ===")
print(f"{'Bucket':15s}  {'N':>8}  {'MAE':>7}  {'P50':>7}  {'P90':>7}  {'Bias':>8}  {'Under%':>7}")
pred_eta_results = {}
for name, lo, hi in ETA_BUCKETS:
    m = (pred_arr >= lo) & (pred_arr < hi)
    if not m.any(): continue
    ae, er = abs_err[m], err_arr[m]
    n = m.sum()
    r = {"n": int(n), "mae": float(ae.mean()), "p50": float(np.percentile(ae, 50)),
         "p90": float(np.percentile(ae, 90)), "bias": float(er.mean()),
         "under_pct": float((er < 0).mean() * 100)}
    pred_eta_results[name] = r
    print(f"{name:15s}  {r['n']:>8,}  {r['mae']:>7.1f}  {r['p50']:>7.1f}  {r['p90']:>7.1f}  {r['bias']:>8.1f}  {r['under_pct']:>6.1f}%")

# ── Grid search umbral "llegando" ─────────────────────────────────────────────
# "llegando" = pred_eta < time_t OR dist_rem < dist_t
# Definición de "realmente llegando": obs_eta < 90s
# Precision = P(obs_eta < 90s | mostré llegando)
# Recall    = P(mostré llegando | obs_eta < 90s)
ARRIVING_DEF_S = 90.0
TIME_THRESHOLDS = [60, 90, 120, 150, 180, 240]
DIST_THRESHOLDS = [100, 150, 200, 250, 300, 400, 500]

actually_arriving = obs_arr < ARRIVING_DEF_S

print(f"\n=== GRID SEARCH UMBRAL 'LLEGANDO' (real = obs_eta < {ARRIVING_DEF_S}s) ===")
print(f"{'time_t':>8}  {'dist_t':>7}  {'N flag':>9}  {'Prec':>8}  {'Recall':>8}  {'F1':>7}")

grid_results = []
for tt in TIME_THRESHOLDS:
    for dt in DIST_THRESHOLDS:
        flagged   = (pred_arr < tt) | (dist_arr < dt)
        n_flagged = int(flagged.sum())
        if n_flagged == 0: continue
        tp        = int((actually_arriving & flagged).sum())
        prec      = tp / n_flagged
        rec       = tp / int(actually_arriving.sum()) if actually_arriving.any() else 0.0
        f1        = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        grid_results.append({"time_t": tt, "dist_t": dt, "n_flagged": n_flagged,
                              "precision": prec, "recall": rec, "f1": f1})

grid_results.sort(key=lambda x: -x["f1"])
for r in grid_results[:12]:
    print(f"{r['time_t']:>8}  {r['dist_t']:>7}  {r['n_flagged']:>9,}  {r['precision']:>7.1%}  {r['recall']:>7.1%}  {r['f1']:>7.3f}")

best = grid_results[0]
print(f"\nMejor: pred_eta < {best['time_t']}s OR dist_rem < {best['dist_t']}m")
print(f"  Precision {best['precision']:.1%}  Recall {best['recall']:.1%}  F1 {best['f1']:.3f}")

# ── Guardar ────────────────────────────────────────────────────────────────────
ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
result = {
    "experiment":  "arriving_threshold_grid_search",
    "date":        datetime.datetime.now().isoformat(),
    "model": {
        "checkpoint":   "data/ml/models/eta_a3_best.pt",
        "inference":    f"PyTorch directo, device={DEVICE}",
        "config":       "no-fleet, d_model=64, linea 39, pinball loss",
        "best_epoch":   14,
        "val_mae_s":    75.9,
        "trained_date": "2026-06-03",
    },
    "data": {
        "val_parquet":       str(VAL_PARQUET),
        "n_rows_evaluated":  int(len(dist_arr)),
        "dist_filter_m":     100,
    },
    "overall": {
        "mae_s":             float(abs_err.mean()),
        "p50_s":             float(np.percentile(abs_err, 50)),
        "p90_s":             float(np.percentile(abs_err, 90)),
        "bias_s":            float(err_arr.mean()),
        "under_pct":         float((err_arr < 0).mean() * 100),
    },
    "by_dist_bucket":        dist_results,
    "by_pred_eta_bucket":    pred_eta_results,
    "arriving_definition_s": ARRIVING_DEF_S,
    "arriving_grid":         grid_results,
    "best_arriving_threshold": best,
}

out_path = OUTPUT_DIR / f"arriving_threshold_{ts_str}.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print(f"\nResultados guardados: {out_path}")
