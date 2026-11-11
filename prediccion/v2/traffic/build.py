"""
CLI: tabla de tránsito por (ventana, celda) para un rango de días.

  python -m prediccion.v2.traffic.build --days 2026-03-28:2026-10-14 --window-min 2 --workers 3

Salida (window_min=2): data/ml/v2/traffic/{meta.json, route_mask.npz, daily/YYYY-MM-DD.parquet}.
Con otra ventana, el mismo árbol bajo data/ml/v2/traffic/w{N}/. Idempotente: si el parquet del día existe, se saltea.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from prediccion.pipeline.build_dataset import EXCLUDED_DAYS
from prediccion.v2.shapes import DEFAULT_DATA_DIR, DEFAULT_LINE_SHAPES_DIR, DEFAULT_V2_DIR
from prediccion.v2.traffic.day import (DEPOT_FIT_M, MAX_DT_S, MAX_MPS, MIN_DT_S, MOVING_MPS, TZ_OFFSET_S,
                                       process_day)
from prediccion.v2.traffic.grid import GridSpec, grid_from_encoder
from prediccion.v2.traffic.mask import DENSIFY_M, build_route_geometry, cell_lookup

VERSION = 1
TRAFFIC_DIR = DEFAULT_V2_DIR / "traffic"

_W: dict = {}


def _lower_priority() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def _init_worker(grid_d, window_min, mask_path, data_dir, out_dir):
    _lower_priority()
    g = GridSpec(**grid_d)
    z = np.load(mask_path)
    _W.update(grid=g, window_min=window_min, cell_ok=cell_lookup(g, z["cells"]), points=z["points"],
              data_dir=Path(data_dir), out_dir=Path(out_dir))


def _work(day: str) -> dict:
    try:
        return process_day(day, data_dir=_W["data_dir"], out_dir=_W["out_dir"], grid=_W["grid"],
                           window_min=_W["window_min"], cell_ok=_W["cell_ok"], route_points=_W["points"])
    except Exception as exc:  # un día corrupto no tira el build
        return {"day": day, "status": "error", "error": f"{type(exc).__name__}: {exc}"}


def parse_days(spec: str) -> list[str]:
    from datetime import date, timedelta
    out: list[str] = []
    for part in spec.split(","):
        if ":" in part:
            a, b = (date.fromisoformat(x) for x in part.split(":"))
            while a <= b:
                out.append(a.isoformat())
                a += timedelta(days=1)
        else:
            out.append(date.fromisoformat(part).isoformat())
    return sorted(set(out))


def prepare(out_dir: Path, window_min: int, shapes_dir: Path, lines_json: Path, cell_m: float = 500.0):
    """Calcula (o reutiliza) la máscara y escribe meta.json. Devuelve (grid, mask_path)."""
    grid = grid_from_encoder(cell_m)
    spec = json.loads(Path(lines_json).read_text(encoding="utf-8"))
    lines = sorted({*spec["train"], *spec["heldout"]}, key=lambda s: (len(s), s))
    out_dir.mkdir(parents=True, exist_ok=True)
    mask_path = out_dir / "route_mask.npz"
    geo = build_route_geometry(grid, shapes_dir, lines)
    np.savez_compressed(mask_path, cells=geo["cells"], points=geo["points"])
    meta = {
        "version": VERSION,
        "grid": grid.to_dict(),
        "cell_id": "i0 * (n_lon + 1) + j0 (vértice inferior de la celda en CityGridEncoder)",
        "window_min": window_min,
        "window": f"minuto del día en hora de Buenos Aires (UTC{TZ_OFFSET_S // 3600}) // {window_min}",
        "lines": lines,
        "mask": {"n_cells": int(len(geo["cells"])), "n_polylines": geo["n_polylines"], "densify_m": DENSIFY_M,
                 "sha1": hashlib.sha1(geo["cells"].tobytes()).hexdigest()},
        "speed": {"source": "desplazamiento entre pings consecutivos del mismo coche, asignado al 2º ping",
                  "moving_mps": MOVING_MPS, "min_dt_s": MIN_DT_S, "max_dt_s": MAX_DT_S, "max_mps": MAX_MPS},
        "depot": {"rule": "quieto y a más de depot_fit_m de todo recorrido", "depot_fit_m": DEPOT_FIT_M},
        "columns": {"window": "int16", "cell": "int32", "speed_mps": "float16 (NaN = nadie en movimiento)",
                    "n": "uint16 coches distintos", "n_stopped": "uint16 coches sin intervalos en movimiento"},
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return grid, mask_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", required=True)
    ap.add_argument("--window-min", type=int, default=2)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--shapes-dir", type=Path, default=DEFAULT_LINE_SHAPES_DIR)
    ap.add_argument("--lines-json", type=Path, default=DEFAULT_V2_DIR / "lines.json")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    _lower_priority()
    out_dir = a.out_dir or (TRAFFIC_DIR if a.window_min == 2 else TRAFFIC_DIR / f"w{a.window_min}")
    days = [d for d in parse_days(a.days) if d not in EXCLUDED_DAYS and (a.data_dir / f"{d}.ndjson.gz").exists()]
    todo = [d for d in days if a.force or not (out_dir / "daily" / f"{d}.parquet").exists()]
    print(f"{len(days)} días válidos, {len(days) - len(todo)} ya hechos, {len(todo)} a procesar -> {out_dir}", flush=True)
    grid, mask_path = prepare(out_dir, a.window_min, a.shapes_dir, a.lines_json)
    if a.force:
        for d in todo:
            (out_dir / "daily" / f"{d}.parquet").unlink(missing_ok=True)
    t0, done = time.time(), 0
    initargs = (grid.to_dict(), a.window_min, str(mask_path), str(a.data_dir), str(out_dir))
    with ProcessPoolExecutor(max_workers=max(1, a.workers), initializer=_init_worker, initargs=initargs) as ex:
        futs = [ex.submit(_work, d) for d in todo]
        for fu in as_completed(futs):
            r = fu.result()
            done += 1
            el = time.time() - t0
            eta = el / done * (len(todo) - done)
            if r["status"] == "ok":
                msg = (f"{r['day']} filas={r['rows']} {r['bytes'] / 1e6:.1f}MB cpu={r['cpu_s']}s "
                       f"depot={r.get('depot', 0)}")
            else:
                msg = f"{r['day']} {r['status']} {r.get('error', '')}"
            print(f"[{done}/{len(todo)}] {msg} | transcurrido {el / 60:.1f} min, resta ~{eta / 60:.1f} min", flush=True)
    print("FIN", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
