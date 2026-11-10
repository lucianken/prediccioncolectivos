import sys; sys.path.insert(0, '.')
from prediccion.models.eta_dataset import ETADataset
from prediccion.pipeline.shapes_io import load_shapes, DEFAULT_SHAPES_PATH
from prediccion.pipeline.projector import polyline_length_m
import numpy as np

shapes = load_shapes(str(DEFAULT_SHAPES_PATH))
shape_lengths = {}
for line_num, line_data in shapes.items():
    for ramal in line_data.get("ramales", []):
        sh_id = ramal.get("shapeId")
        pts = [tuple(p) for p in ramal["points"]]
        if sh_id and len(pts) >= 2:
            shape_lengths[sh_id] = polyline_length_m(pts)

print(f"Shape lengths cargados: {len(shape_lengths)}")

ds = ETADataset("data/ml/training/eta_val.parquet", shape_lengths=shape_lengths, shuffle=False, max_groups=1)

dist_norms, dist_rems, etas = [], [], []
for batch in ds:
    dist_norms.append(batch["dist_remaining_norm"].numpy())
    dist_rems.append(batch["dist_remaining_m"].numpy())
    etas.append(batch["eta_seconds"].numpy())

dist_norms = np.concatenate(dist_norms)
dist_rems  = np.concatenate(dist_rems)
etas       = np.concatenate(etas)

mask = (dist_rems >= 100) & (dist_rems < 250)
print(f"Sub 100-250m rows en grupo 0: {mask.sum()}")
print(f"dist_rem_norm mean={dist_norms[mask].mean():.4f}  min={dist_norms[mask].min():.4f}  max={dist_norms[mask].max():.4f}")
print(f"eta_seconds clipped: mean={etas[mask].mean():.1f}  median={float(np.median(etas[mask])):.1f}")
print(f"Total rows en grupo 0: {len(dist_rems)}")
print(f"Sub-1km fraction: {((dist_rems < 1000) & (dist_rems >= 100)).mean():.1%}")

# Verificar si hay dist_rem_norm > 1 (out of distribution)
oor = (dist_norms > 1.0).sum()
print(f"Rows con dist_rem_norm > 1: {oor} ({100*oor/len(dist_norms):.1f}%)")
