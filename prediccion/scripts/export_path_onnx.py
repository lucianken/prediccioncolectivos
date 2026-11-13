"""
Exporta un checkpoint del modelo por tramos (models/path_eta.py) a los archivos que necesita la inferencia en el
navegador (contrato: prediccion/INFERENCIA_PATH.md).

  python -m prediccion.scripts.export_path_onnx --ckpt data/ml/v2b_sub/runs/path_lr2e-3_s0/path_eta_best.pt \
      --out data/ml/export/path_v2b_s0

Salida en <out>/:
  path_eta.onnx        red (tramos de entrada, B y N dinámicos)
  manifest.json        versiones, constantes, normalizaciones, tabla de líneas, E/S del ONNX, tamaños y sha256
  lines/<línea>.json   por línea del modelo: shapes con puntos del recorrido y puntos medios de las celdas de 250 m
Solo se exportan las líneas con embedding (`line_ids` del checkpoint). Las líneas que el checkpoint solo usa como
geometría (control) no se exportan: en producción no se predice para ellas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

CONTRACT_VERSION = "1.0"
STATE_NAMES = ["speed_norm", "stopped", "ts_age_norm", "time_since_start_norm", "dist_along_norm_50km",
               "time_since_last_bus_norm", "last_bus_found", "dist_remaining_norm", "start_unknown"]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _round_flat(arr, nd=6) -> list:
    return [round(float(x), nd) for x in np.asarray(arr).reshape(-1)]


def export(ckpt_path: Path, out_dir: Path, shapes_dir=None, verify: bool = True, model_version: str | None = None) -> dict:
    import torch
    from prediccion.inference.path_onnx import INPUT_NAMES, OUTPUT_NAMES, export_onnx
    from prediccion.models.geo import ShapeGeo
    from prediccion.models.path_eta import (MAX_SEG, SEG_BASE_M, STOPPED_MPS, PathETAModel, load_shape_points)
    from prediccion.v2.shapes import DEFAULT_LINE_SHAPES_DIR

    ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    model = PathETAModel.from_checkpoint(ckpt).eval()
    out_dir = Path(out_dir)
    (out_dir / "lines").mkdir(parents=True, exist_ok=True)
    shapes_dir = Path(shapes_dir or DEFAULT_LINE_SHAPES_DIR)
    ck_ids = {s: i for i, s in enumerate(model.shape_ids)}
    off = model.shape_off.numpy()

    # ── datos estáticos por línea (la geometría de celdas sale del checkpoint; los puntos, de line_shapes) ──
    n_cells_total, exported = 0, set()
    for ln in model.line_ids:
        data = json.loads((shapes_dir / f"{ln}.json").read_text(encoding="utf-8"))
        shapes = []
        for r in data.get("ramales", []):
            sid, pts = r.get("shapeId"), r.get("points", [])
            if sid is None or len(pts) < 2 or str(sid) not in ck_ids:
                continue
            sid = str(sid)
            i = ck_ids[sid]
            lat = model.seg_lat[off[i]:off[i + 1]].numpy()
            lon = model.seg_lon[off[i]:off[i + 1]].numpy()
            sg = ShapeGeo(pts)
            exp_n = max(1, int(np.ceil(sg.length_m / SEG_BASE_M)))
            mid = np.minimum((np.arange(exp_n) + 0.5) * SEG_BASE_M, sg.length_m)
            elat, elon = sg.latlon_at(mid)
            if len(lat) != exp_n or np.abs(lat - elat).max() > 1e-5 or np.abs(lon - elon).max() > 1e-5:
                raise SystemExit(f"shape {sid} (línea {ln}): la geometría de {shapes_dir} no coincide con las celdas del "
                                 "checkpoint (cambió el recorrido desde el entrenamiento); reentrenar o usar el shapes-dir original")
            shapes.append({"id": sid, "name": r.get("name", ""), "short_name": r.get("shortName", ""),
                           "length_m": round(sg.length_m, 2), "n_cells": int(len(lat)),
                           "points": _round_flat(np.asarray(pts, dtype=np.float64)),
                           "cells": _round_flat(np.stack([lat, lon], axis=1))})
            n_cells_total += len(lat)
            exported.add(sid)
        if not shapes:
            raise SystemExit(f"línea {ln}: ningún shape del checkpoint en {shapes_dir}")
        (out_dir / "lines" / f"{ln}.json").write_text(json.dumps({"line": ln, "shapes": shapes}, separators=(",", ":")),
                                                      encoding="utf-8")

    # ── red ──
    onnx_p = out_dir / "path_eta.onnx"
    export_onnx(model, onnx_p, opset=17)

    files = {"path_eta.onnx": onnx_p} | {f"lines/{p.name}": p for p in sorted((out_dir / "lines").glob("*.json"))}
    version = model_version or out_dir.name
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "model_version": version,
        "checkpoint": {"path": str(ckpt_path).replace("\\", "/"), "epoch": ckpt.get("epoch"), "val_mae_s": ckpt.get("val_mae_s")},
        "onnx": {"file": "path_eta.onnx", "opset": 17, "inputs": INPUT_NAMES, "outputs": OUTPUT_NAMES,
                 "dtypes": {"line_idx": "int32", "dow": "int32", "*": "float32"},
                 "state_columns": STATE_NAMES[:model.n_state - 1], "dynamic_axes": {"B": "candidatos", "N": "tramos"}},
        "lines": {ln: i + 1 for i, ln in enumerate(model.line_ids)},          # índice de línea (0 = desconocida, no usar)
        "start_unknown": model.start_unknown,
        "constants": {
            "seg_base_m": SEG_BASE_M, "max_seg": MAX_SEG, "stopped_mps": STOPPED_MPS,
            "speed_norm_div": 30.0, "speed_norm_max": 2.0, "ts_age_div": 600.0, "ts_age_max": 1.5, "ts_age_cap_s": 600.0,
            "tss_div": 3600.0, "tss_max": 4.0, "d0_div": 50000.0, "d0_max": 2.0, "tlb_cap_s": 3600.0,
            "rem_cap_m": 80000.0, "min_rem_m": 100.0, "m_per_deg_lat": 111320.0, "tz_offset_s": -3 * 3600,
            "max_perp_m": 150.0, "min_forward_frac": 0.6, "user_max_perp_m": 100.0, "history_window_s": 900,
            "terminal_zone_m": 300.0,
        },
        "n_shapes": len(exported), "n_cells": n_cells_total,
        "files": {k: {"bytes": p.stat().st_size, "sha256": _sha(p)} for k, p in files.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    if verify:
        _verify(model, onnx_p)
    return manifest


def _verify(model, onnx_p: Path, n: int = 400, tol_s: float = 0.05) -> None:
    """ONNX vs PyTorch sobre filas sintéticas (d0/rem aleatorios en cada shape); falla si difieren más de tol_s."""
    import onnxruntime as ort
    import torch
    from prediccion.inference.path_onnx import run_onnx, segment_inputs_from_rows
    rng = np.random.default_rng(0)
    off = model.shape_off.numpy()
    lens = (off[1:] - off[:-1]) * 250.0
    sidx = rng.integers(0, len(lens), n)
    d0 = rng.random(n) * lens[sidx] * 0.5
    rem = 100.0 + rng.random(n) * (lens[sidx] - d0 - 100.0).clip(min=1.0)
    d0t, remt = torch.tensor(d0, dtype=torch.float32), torch.tensor(rem, dtype=torch.float32)
    sidt = torch.tensor(sidx)
    lidx = torch.tensor(rng.integers(0, len(model.line_ids) + 1, n))
    ang = rng.random(n) * 2 * np.pi
    hs, hc = torch.tensor(np.sin(ang), dtype=torch.float32)[:, None], torch.tensor(np.cos(ang), dtype=torch.float32)[:, None]
    dow = torch.tensor(rng.integers(0, 7, n))[:, None]
    state = torch.tensor(rng.random((n, model.n_state)), dtype=torch.float32)
    state[:, -1] = 0.0
    with torch.no_grad():
        ref = model(sidt, lidx, d0t, remt, hs, hc, dow, state)[0].numpy()
    seg = segment_inputs_from_rows(model, sidt, d0t, remt)
    sess = ort.InferenceSession(str(onnx_p), providers=["CPUExecutionProvider"])
    got = run_onnx(sess, {**seg, "line_idx": lidx.numpy(), "dow": dow[:, 0].numpy(), "h_sin": hs[:, 0].numpy(),
                          "h_cos": hc[:, 0].numpy(), "state": state[:, :-1].numpy()})[0]
    err = float(np.abs(got - ref).max())
    if err > tol_s:
        raise SystemExit(f"verificación ONNX fallida: error máximo {err:.4f} s > {tol_s} s")
    print(f"verificación ONNX vs PyTorch: error máximo {err:.5f} s sobre {n} filas sintéticas")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shapes-dir", type=Path, default=None, help="default: proyectoconsola/data/line_shapes")
    ap.add_argument("--model-version", default=None, help="default: nombre del directorio de salida")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args(argv)
    m = export(a.ckpt, a.out, a.shapes_dir, verify=not a.no_verify, model_version=a.model_version)
    for k, v in m["files"].items():
        print(f"{k:24s} {v['bytes']:>10,d} B")
    print(f"total {sum(v['bytes'] for v in m['files'].values()):,d} B; {m['n_shapes']} shapes, {m['n_cells']} celdas -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
