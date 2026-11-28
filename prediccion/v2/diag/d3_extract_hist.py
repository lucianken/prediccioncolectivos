"""
D3 (paso 1): recupera, para cada fila de eval_seen de la 39, los pings (lat, lon, ts) del viaje hasta P.

El eval parquet no guarda posiciones ni vehículo, así que se re-corre (solo lectura, mismas funciones del
pipeline v2: read_day + segment_vehicles + geometry_for_trip) la lectura del NDJSON de los días de validación para
la línea 39 y se emparejan las filas por (ts_p, shape_id, dist_along_m). No escribe nada en data/ml/v2 salvo
diag/eval_hist_39.pkl.

  PYTHONPATH=. python -m prediccion.v2.diag.d3_extract_hist [--workers 6]
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from prediccion.v2.diag import common as C
from prediccion.v2.day import geometry_for_trip, prev_day, read_day, segment_vehicles
from prediccion.v2.shapes import DEFAULT_DATA_DIR, DEFAULT_LABEL_MAP, DEFAULT_LINE_SHAPES_DIR, LineShapes


def _day(args):
    day, rows = args          # rows: list of (row_idx, ts_p, shape_id, dist_along_m)
    from red.label_map import load_label_line_data, resolve_label_line_index
    t0 = time.time()
    shapes = LineShapes(DEFAULT_LINE_SHAPES_DIR)
    label_data = load_label_line_data(DEFAULT_LABEL_MAP)
    label_index = resolve_label_line_index(label_data, on_date=day)
    label_map = {s: v["line"] for s, v in label_index.items()}
    carry = None
    pc = C.V2 / "daily" / f"{prev_day(day)}.carry.json"
    if pc.exists():
        with open(pc, encoding="utf-8") as f:
            carry = json.load(f)
    veh, _, _ = read_day(Path(DEFAULT_DATA_DIR) / f"{day}.ndjson.gz", label_map, {"39"}, carry, 30, False)
    trips = [t for t in segment_vehicles(veh, label_index, shapes, "geo") if t.line_number == "39"]
    idx = shapes.indices("39")
    by_ts: dict[int, list] = {}
    for r in rows:
        by_ts.setdefault(int(r[1]), []).append(r)
    out = {}
    for trip in sorted(trips, key=lambda t: t.start_time):
        g = geometry_for_trip(trip, idx)
        if g is None:
            continue
        valid = np.flatnonzero(g["valid"])
        for k in valid:
            p = trip.points[k]
            for r in by_ts.get(int(p.ts), ()):
                if r[2] == g["shape_id"] and abs(g["dist"][k] - r[3]) < 1.0 and r[0] not in out:
                    pts = trip.points[:k + 1]
                    out[r[0]] = {"lat": np.array([q.lat for q in pts]), "lon": np.array([q.lon for q in pts]),
                                 "ts": np.array([q.ts for q in pts]), "dist_expost": g["dist"][:k + 1],
                                 "n_trip_points": len(trip.points), "vehicle": trip.vehicle_id}
    return day, out, round(time.time() - t0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    df = C.load_df(C.DIAG / "eval_seen_39.parquet")
    days = json.load(open(C.V2 / "eval" / "eval_meta.json", encoding="utf-8"))["val_days"]
    rows = [(i, int(t), str(s), float(d)) for i, (t, s, d) in enumerate(zip(df.ts_p, df.shape_id, df.dist_along_m))]
    jobs = [(d, rows) for d in days]
    res = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for day, out, el in ex.map(_day, jobs):
            res.update(out)
            print(day, len(out), f"{el}s", flush=True)
    print(f"emparejadas {len(res)} / {len(rows)}")
    with open(C.DIAG / "eval_hist_39.pkl", "wb") as f:
        pickle.dump(res, f)


if __name__ == "__main__":
    main()
