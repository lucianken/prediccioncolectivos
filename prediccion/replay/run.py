"""
Lanzador del replay: python -m prediccion.replay.run --model data/ml/export/path_v2c_l1_s1 --days 2026-09-15,... \
    --lines 26,39,... --variants base,sentido,ramal --out data/ml/replay/run1 [--workers 3]
Escribe por (día, línea): {out}/{day}_{line}.veh.parquet y .inst.parquet (se salta lo ya hecho).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from prediccion.replay import core
from prediccion.replay.pinned import path_reference as PR

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LINES = "26,39,42,50,92,106,107,108,124,132,151,168"
DEFAULT_DAYS = "2026-09-15,2026-09-16,2026-09-17,2026-09-18,2026-09-19,2026-09-20,2026-10-03,2026-10-04,2026-10-06,2026-10-08"


def load_day(day, lines, data_dir, label_map, shapes_dir):
    """Pings por coche y recorrido ex post de sus viajes (segmentador geo2 + geo3, solo para la variante oráculo)."""
    from prediccion.pipeline.shapes_io import load_label_line_data, resolve_label_line_index
    from prediccion.v2.day import geometry_for_trip, read_day, segment_vehicles
    from prediccion.v2.shapes import LineShapes
    label_index = resolve_label_line_index(load_label_line_data(label_map), on_date=day)
    lm = {s: v["line"] for s, v in label_index.items()}
    vehicles, _, _ = read_day(Path(data_dir) / f"{day}.ndjson.gz", lm, set(lines), None, 30, False)
    shapes = LineShapes(shapes_dir)
    trips = segment_vehicles(vehicles, label_index, shapes, "geo2")
    per_line: dict[str, dict[str, core.Veh]] = {}
    for vid, rec in vehicles.items():
        ln = lm.get(rec["label"].split("-")[-1]) if rec["label"] else None
        if ln in lines and rec["obs"]:
            per_line.setdefault(ln, {})[vid] = core._veh_arrays(vid, rec["obs"])
    for tr in trips:
        ln = tr.line_number
        if ln not in lines or tr.vehicle_id not in per_line.get(ln, {}):
            continue
        idx = shapes.indices(ln)
        g = geometry_for_trip(tr, idx, assign="geo3") if idx else None
        per_line[ln][tr.vehicle_id].trips.append((float(tr.points[0].ts), float(tr.points[-1].ts), g["shape_id"] if g else ""))
    for d in per_line.values():
        for v in d.values():
            v.trips.sort()
    return per_line


def run_day(a):
    day, lines, kw = a
    out = Path(kw["out"])
    out.mkdir(parents=True, exist_ok=True)
    todo = [ln for ln in lines if not (out / f"{day}_{ln}.inst.parquet").exists()]
    if not todo:
        return day, 0.0
    try:
        os.nice(10)
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    t0 = time.time()
    bundle = PR.load_bundle(kw["model"])
    per_line = load_day(day, set(todo), kw["data_dir"], kw["label_map"], kw["shapes_dir"])
    insts = core.instants_for_day(day, step_min=kw["step_min"])
    for ln in todo:
        vs = list(per_line.get(ln, {}).values())
        if not vs:
            continue
        stops = core.prepare_stops(bundle, ln, kw["shapes_dir"], kw["stops"])
        with core.memoized():
            rv, ri = core.evaluate_line(bundle, ln, vs, stops, insts, kw["variants"], day)
            core.MEMO.clear()
        pd.DataFrame(rv).to_parquet(out / f"{day}_{ln}.veh.parquet")
        pd.DataFrame(ri).to_parquet(out / f"{day}_{ln}.inst.parquet")
        print(f"{day} {ln}: {len(stops)} paradas, {len(vs)} coches, {time.time()-t0:.0f}s", flush=True)
    return day, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "data/ml/export/path_v2c_l1_s1"))
    ap.add_argument("--days", default=DEFAULT_DAYS)
    ap.add_argument("--lines", default=DEFAULT_LINES)
    ap.add_argument("--variants", default="base,sentido,ramal")
    ap.add_argument("--stops", type=int, default=40)
    ap.add_argument("--step-min", type=int, default=10)
    ap.add_argument("--out", default=str(ROOT / "data/ml/replay/run1"))
    ap.add_argument("--data-dir", default="//192.168.0.18/buffer/grabaciones")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    kw = dict(model=a.model, out=a.out, data_dir=a.data_dir, label_map=str(ROOT / "LABEL_LINE_MAP.json"),
              shapes_dir=str(ROOT.parent / "proyectoconsola/data/line_shapes"), variants=tuple(a.variants.split(",")),
              stops=a.stops, step_min=a.step_min)
    days = a.days.split(",")
    lines = a.lines.split(",")
    with ProcessPoolExecutor(a.workers) as ex:
        for day, el in ex.map(run_day, [(d, lines, kw) for d in days]):
            print("hecho", day, f"{el:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
