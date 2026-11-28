"""Reexporta el checkpoint v4 SIN reentrenar con los line_shapes actuales.
El modelo no tiene parámetros por shape: el tiempo de cada tramo sale de (celda de 500 m del lugar, embedding de LÍNEA, hora, paradas
del tramo). El shape_id solo indexa las tablas estáticas seg_lat/seg_lon/shape_off/stop_key (buffers, no pesos). Se reconstruyen
esos buffers desde los line_shapes actuales (shapes del checkpoint que ya no están: se conservan, no se exportan) y se llama
a export_path_onnx.export, que verifica geometría/paradas contra los buffers y ONNX contra PyTorch."""
import json, sys
from pathlib import Path
import numpy as np, torch
from prediccion.models.path_eta import (PathETAModel, build_shape_table, build_stop_key, load_shape_points, STOP_KEY_SPAN)
from red.stops import load_shape_stops
from prediccion.scripts.export_path_onnx import export
ROOT = Path(__file__).resolve().parents[2]
CKPT = ROOT / "data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt"
SHAPES = ROOT.parent / "proyectoconsola/data/line_shapes"
OUT = ROOT / "data/ml/export/path_v4_l1_s1_shapes20261126"
TMP = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/ml/replay/recorridos_nuevos_42/cache/ckpt_nuevos_shapes.pt"

ck = torch.load(str(CKPT), map_location="cpu", weights_only=False)
old = PathETAModel.from_checkpoint(ck)
all_lines = [p.stem for p in SHAPES.glob("*.json") if p.stem != "index"]
npts = load_shape_points(all_lines, SHAPES)
nstops = load_shape_stops(all_lines, SHAPES)
# geometría vieja de lo que ya no está
off = old.shape_off.numpy()
pts_cells, stops_by = {}, {}
sk = old.stop_key.numpy()
for i, sid in enumerate(old.shape_ids):
    stops_by[sid] = (sk[(sk >= i * STOP_KEY_SPAN) & (sk < (i + 1) * STOP_KEY_SPAN)] - i * STOP_KEY_SPAN).tolist()
    pts_cells[sid] = (old.seg_lat[off[i]:off[i + 1]].numpy(), old.seg_lon[off[i]:off[i + 1]].numpy())
ids_new = sorted(set(old.shape_ids) | set(npts))
from prediccion.models.path_eta import shape_cell_midpoints
lats, lons, offs = [], [], [0]
for sid in ids_new:
    la, lo = shape_cell_midpoints(npts[sid]) if sid in npts else pts_cells[sid]
    lats.append(la); lons.append(lo); offs.append(offs[-1] + len(la))
st = {sid: (nstops[sid] if sid in npts else stops_by[sid]) for sid in ids_new}
sd = dict(ck["model_state_dict"])
sd["seg_lat"] = torch.tensor(np.concatenate(lats), dtype=torch.float32)
sd["seg_lon"] = torch.tensor(np.concatenate(lons), dtype=torch.float32)
sd["shape_off"] = torch.tensor(offs, dtype=torch.long)
sd["stop_key"] = torch.tensor(build_stop_key(ids_new, st), dtype=torch.float64)
ck2 = dict(ck); ck2["model_state_dict"] = sd; ck2["shape_ids"] = ids_new; ck2["n_seg_total"] = int(sd["seg_lat"].numel())
TMP.parent.mkdir(parents=True, exist_ok=True)
torch.save(ck2, str(TMP))
print("shapes ckpt", len(old.shape_ids), "-> tabla", len(ids_new), "(nuevos ids:", sorted(set(npts) - set(old.shape_ids))[:10], ")")
m = export(TMP, OUT, SHAPES, verify=True, model_version=OUT.name)
mp = OUT / "manifest.json"
man = json.loads(mp.read_text(encoding="utf-8"))
man["checkpoint"]["path"] = "data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt"
man["checkpoint"]["nota"] = "pesos sin reentrenar; tablas de shapes (seg_lat/lon, shape_off, stop_key) reconstruidas de proyectoconsola/data/line_shapes del 2026-11-26"
mp.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
print(m["n_shapes"], "shapes", m["n_cells"], "celdas")
