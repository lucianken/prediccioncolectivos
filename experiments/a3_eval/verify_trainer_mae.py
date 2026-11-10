"""Verifica que el checkpoint cargado reproduce el val MAE del trainer."""
import sys; sys.path.insert(0, '.')
import torch, numpy as np
from pathlib import Path
from prediccion.models.a3_eta import A3ETAModel
from prediccion.models.eta_dataset import ETADataset
from prediccion.pipeline.shapes_io import load_shapes, DEFAULT_SHAPES_PATH
from prediccion.pipeline.projector import polyline_length_m

shapes = load_shapes(str(DEFAULT_SHAPES_PATH))
shape_lengths = {}
for line_num, line_data in shapes.items():
    for ramal in line_data.get("ramales", []):
        sh_id = ramal.get("shapeId")
        pts = [tuple(p) for p in ramal["points"]]
        if sh_id and len(pts) >= 2:
            shape_lengths[sh_id] = polyline_length_m(pts)

ckpt = torch.load("data/ml/models/eta_a3_best.pt", map_location="cpu")
print(f"Checkpoint epoch: {ckpt.get('epoch')}  val_mae_s: {ckpt.get('val_mae_s'):.1f}")
print(f"d_model en ckpt: {ckpt.get('d_model', 'no guardado')}")

model = A3ETAModel(d_model=64)
model.load_state_dict(ckpt["model_state_dict"])
model.eval()

ds = ETADataset("data/ml/training/eta_val.parquet", shape_lengths=shape_lengths,
                shuffle=False, max_groups=3, use_fleet=False)

errors, dist_rems = [], []
with torch.no_grad():
    for batch in ds:
        traj       = batch["trajectory"]
        traj_mask  = batch["trajectory_mask"]
        fleet      = batch["fleet"]
        fleet_mask = batch["fleet_mask"]
        h_sin      = batch["hour_sin"]
        h_cos      = batch["hour_cos"]
        dow        = batch["dow"]
        dist_rem   = batch["dist_remaining_norm"]
        dist_rem_m = batch["dist_remaining_m"]
        tss        = batch["time_since_start"]
        ts_age     = batch["ts_age_s"]
        has_bus    = batch["has_active_bus"]
        eta_target = batch["eta_seconds"]

        pred = model(traj, traj_mask, fleet, fleet_mask,
                     h_sin, h_cos, dow, dist_rem, tss, ts_age, has_bus)

        errors.append(torch.abs(pred - eta_target).squeeze(-1).numpy())
        dist_rems.append(dist_rem_m.squeeze(-1).numpy())

errors   = np.concatenate(errors)
dist_rems = np.concatenate(dist_rems)

print(f"\nMAE total (3 grupos): {errors.mean():.1f}s")
for lo, hi, label in [(100,500,"0-500m"),(500,2000,"500m-2km"),(2000,99999,"2km+")]:
    m = (dist_rems >= lo) & (dist_rems < hi)
    if m.any():
        print(f"  {label}: {errors[m].mean():.1f}s  (N={m.sum():,})")
