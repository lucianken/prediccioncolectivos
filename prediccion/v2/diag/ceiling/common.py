"""
Utilidades del análisis de techo del tránsito (ARQUITECTURA.md §6.2.1). Solo lectura: no entrena ni toca modelos,
pipeline ni datos. Reusa grid.py (celda), A1Baseline y la vara (prediccion.eval).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.v2.shapes import DEFAULT_V2_DIR, DEFAULT_LINE_SHAPES_DIR, REPO_ROOT, LineShapes
from prediccion.v2.traffic.grid import GridSpec

V2 = Path(DEFAULT_V2_DIR)
TRAFFIC = V2 / "traffic"
DIAG = V2 / "diag"
A1_PKL = V2 / "models" / "a1_v1794415690.pkl"
NDJSON_DIR = Path("Z:/grabaciones")
ROWS_PQ = DIAG / "ceiling_rows.parquet"
CELL_LINES_NPZ = DIAG / "ceiling_cell_lines.npz"

TRAIN_LINES = ["26", "39", "42", "92", "124", "151", "168", "50", "106", "107", "108", "132"]
CONTROL_LINES = ["12", "15", "128"]
STEP_M = 100.0
TZ_OFFSET_S = -3 * 3600
WIN_S = 120
WIN_PER_DAY = 720
REAL_WINDOWS = 5          # realista: las 5 ventanas completas previas a la de t (10 min)
MIX_K = 2.0               # mezcla: A1 pesa como 2 coches en movimiento
MIN_SPEED = 0.5           # igual que A1Baseline._predict_core
MAX_ETA = 7200.0


def grid_spec() -> GridSpec:
    with open(TRAFFIC / "meta.json", encoding="utf-8") as f:
        return GridSpec(**json.load(f)["grid"])


def load_eval_subset() -> pd.DataFrame:
    """Todas las filas de eval_seen de las 12 líneas de train y de eval_heldout de las 3 de control."""
    import pyarrow.parquet as pq
    cols = ["line", "shape_id", "ramal_id", "dist_along_m", "dist_remaining_m", "speed_mps", "hour_sin", "hour_cos",
            "dow", "observed_eta_s", "ts_p", "time_since_start", "time_since_last_bus_s"]
    parts = []
    for which, lines, group in (("seen", TRAIN_LINES, "train"), ("heldout", CONTROL_LINES, "control")):
        d = pq.read_table(V2 / "eval" / f"eval_{which}.parquet", columns=cols).to_pandas()
        d = d[d.line.isin(lines)].copy()
        d["group"] = group
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    df["row_id"] = np.arange(len(df))
    loc = df.ts_p.to_numpy(np.int64) + TZ_OFFSET_S
    df["day"] = pd.to_datetime(loc, unit="s").strftime("%Y-%m-%d")
    df["hour"] = (loc % 86400) // 3600
    return df


def cell_line_counts(grid: GridSpec):
    """
    Por celda (id del encoder): (n60, n129) = cuántas líneas distintas tienen recorrido ahí, contando solo las 60
    líneas de la máscara de tránsito (meta.json) o las 129 de proyectoconsola. "Línea única" = n == 1.
    """
    from prediccion.v2.traffic.mask import densify
    from prediccion.v2.traffic.grid import cell_index
    if CELL_LINES_NPZ.exists():
        z = np.load(CELL_LINES_NPZ)
        return z["n60"], z["n129"]
    with open(TRAFFIC / "meta.json", encoding="utf-8") as f:
        lines60 = set(json.load(f)["lines"])
    n60 = np.zeros(grid.n_ids, dtype=np.int16)
    n129 = np.zeros(grid.n_ids, dtype=np.int16)
    for p in sorted(Path(DEFAULT_LINE_SHAPES_DIR).glob("*.json")):
        if p.stem == "index":
            continue
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        cells = set()
        for r in data.get("ramales", []):
            pts = r.get("points", [])
            if len(pts) >= 2:
                dp = densify(pts)
                cells.update(np.unique(cell_index(grid, dp[:, 0], dp[:, 1])).tolist())
        if cells:
            ix = np.fromiter(cells, dtype=np.int64)
            n129[ix] += 1
            if p.stem in lines60:
                n60[ix] += 1
    np.savez_compressed(CELL_LINES_NPZ, n60=n60, n129=n129)
    return n60, n129


def vehicle_lines(day: str) -> dict:
    """vehicle_id (str) -> set de líneas con viajes ese día (de `daily/<día>.trips.parquet`; solo las 60 líneas)."""
    import pyarrow.parquet as pq
    tr = pq.read_table(V2 / "daily" / f"{day}.trips.parquet", columns=["line", "vehicle_id"]).to_pandas()
    out: dict = {}
    for ln, v in zip(tr.line.to_numpy(), tr.vehicle_id.to_numpy()):
        out.setdefault(str(v), set()).add(str(ln))
    return out


def shapes_for(lines) -> dict:
    """shape_id -> ShapeIndex (con _pts y _cum_dist)."""
    ls = LineShapes()
    out = {}
    for ln in lines:
        out.update(ls.indices(ln))
    return out


def own_vehicles(day: str, sub: pd.DataFrame, max_own: int = 4):
    """
    Coche propio de cada fila: se casa la fila con los viajes del día (`daily/<día>.trips.parquet`) por
    (línea, shape_id, start_ts == ts_p - time_since_start). Con empate se devuelven todos los coches empatados
    (se excluyen todos: conservador). Devuelve (lista de listas de vehicle_id str, |dt| mínimo por fila).
    """
    import pyarrow.parquet as pq
    tr = pq.read_table(V2 / "daily" / f"{day}.trips.parquet",
                       columns=["line", "shape_id", "vehicle_id", "start_ts"]).to_pandas()
    tr["shape_id"] = tr["shape_id"].astype(str)
    sub = sub.assign(_rid=np.arange(len(sub)), shape_id=sub.shape_id.astype(str),
                     _start=sub.ts_p - sub.time_since_start)
    m = sub[["_rid", "line", "shape_id", "_start"]].merge(tr, on=["line", "shape_id"])
    m["dt"] = (m._start - m.start_ts).abs()
    mind = m.groupby("_rid").dt.transform("min")
    m = m[m.dt == mind]
    own = [[] for _ in range(len(sub))]
    best = np.full(len(sub), 10**9, dtype=np.int64)
    for rid, vid, dt in zip(m._rid.to_numpy(), m.vehicle_id.to_numpy(), m.dt.to_numpy()):
        if dt <= 60 and len(own[rid]) < max_own:
            own[rid].append(str(vid))
        best[rid] = dt
    return own, best
