"""Un día de NDJSON (toda la flota) -> tabla sparse (window, cell, speed_mps, n, n_stopped)."""

from __future__ import annotations

import math
import time
from array import array
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

from prediccion.pipeline.reader import iter_frames
from prediccion.v2.traffic.grid import GridSpec, cell_index, _M_PER_DEG

TZ_OFFSET_S = -3 * 3600     # Buenos Aires, sin horario de verano
MIN_DT_S = 10               # pares de pings más cercanos que esto: ruido de timestamps
MAX_DT_S = 150              # los coches reportan cada ~60 s; más allá hay un hueco y la velocidad no vale
MOVING_MPS = 1.0            # velocidad por desplazamiento >= esto = en movimiento
MAX_MPS = 35.0              # > 126 km/h: salto de GPS, se descarta
DEPOT_FIT_M = 150.0         # = FIT_M del segmentador v2: quieto y a más de esto de todo recorrido = depósito


def window_of(ts, window_min: int):
    """Ventana = minuto del día en hora de Buenos Aires // window_min."""
    return ((np.asarray(ts, dtype=np.int64) + TZ_OFFSET_S) % 86400) // (60 * window_min)


def read_pings(fp: Path):
    """
    Lee el día completo (toda la flota, sin filtrar por línea). Mismo descarte que el reader v2: se ignoran los
    updates que no traen un ts nuevo (re-observaciones, solo cambia seq/stop) y los ts viejos o repetidos.
    Devuelve arrays (vid_int, ts, lat, lon) sin ordenar.
    """
    vid_ids: dict[str, int] = {}
    state: dict[str, dict] = {}
    last_ts: dict[str, int] = {}
    a_vid, a_ts, a_lat, a_lon = array("i"), array("q"), array("d"), array("d")

    def emit(vid: str):
        f = state[vid]
        t = f.get("ts")
        lat, lon = f.get("lat"), f.get("lon")
        if t is None or lat is None or lon is None:
            return
        if t <= last_ts.get(vid, -1):
            return
        last_ts[vid] = t
        k = vid_ids.get(vid)
        if k is None:
            k = vid_ids[vid] = len(vid_ids)
        a_vid.append(k)
        a_ts.append(t)
        a_lat.append(lat)
        a_lon.append(lon)

    for frame in iter_frames(fp):
        if frame.get("gap"):
            continue
        if frame.get("keyframe", False):
            state = {}
            for v in frame.get("new", []):
                state[v["id"]] = dict(v)
                emit(v["id"])
        else:
            for v in frame.get("new", []):
                state[v["id"]] = dict(v)
                emit(v["id"])
            for vid in frame.get("del", []):
                state.pop(vid, None)
            for u in frame.get("upd", []):
                vid = u["id"]
                if vid in state:
                    state[vid].update(u)
                    emit(vid)
    return (np.frombuffer(a_vid, dtype=np.int32), np.frombuffer(a_ts, dtype=np.int64),
            np.frombuffer(a_lat, dtype=np.float64), np.frombuffer(a_lon, dtype=np.float64))


def build_route_tree(points: np.ndarray):
    """cKDTree en metros (lat*M, lon*M*cos) sobre los puntos densos de recorrido; devuelve (tree, cos)."""
    cos = math.cos(math.radians(float(points[:, 0].mean())))
    xy = np.column_stack([points[:, 0].astype(np.float64) * _M_PER_DEG,
                          points[:, 1].astype(np.float64) * _M_PER_DEG * cos])
    return cKDTree(xy), cos


def aggregate(vid, ts, lat, lon, *, grid: GridSpec, window_min: int, cell_ok: np.ndarray,
              route_tree: cKDTree | None, route_cos: float, stats: dict | None = None):
    """
    Arrays de pings -> (window, cell, speed, n, n_stopped) sparse.
    Cada par de pings consecutivos del mismo coche (10 s <= dt <= 150 s) da una velocidad por desplazamiento, que
    se asigna a la celda y ventana del segundo ping. Por (ventana, celda): n = coches distintos, n_stopped = coches
    sin ningún intervalo en movimiento, speed = media de los intervalos en movimiento (NaN si no hay).
    Se descartan: celdas fuera de la máscara y coches de depósito (quietos y a > DEPOT_FIT_M de todo recorrido).
    """
    empty = (np.zeros(0, np.int32), np.zeros(0, np.int32), np.zeros(0, np.float32),
             np.zeros(0, np.uint16), np.zeros(0, np.uint16))
    if len(ts) < 2:
        return empty
    order = np.lexsort((ts, vid))
    vid, ts, lat, lon = vid[order], ts[order], lat[order], lon[order]
    dt = np.diff(ts)
    same = (vid[1:] == vid[:-1]) & (dt >= MIN_DT_S) & (dt <= MAX_DT_S)
    cos = math.cos(math.radians(float(np.mean(lat))))
    dx = (lon[1:] - lon[:-1]) * _M_PER_DEG * cos
    dy = (lat[1:] - lat[:-1]) * _M_PER_DEG
    v = np.hypot(dx, dy) / np.maximum(dt, 1)
    keep = same & (v <= MAX_MPS)
    if stats is not None:
        stats["pings"] = int(len(ts))
        stats["pairs"] = int(keep.sum())
    idx = np.flatnonzero(keep) + 1                      # el ping "b" de cada par
    v, b_vid, b_ts, b_lat, b_lon = v[idx - 1], vid[idx], ts[idx], lat[idx], lon[idx]
    cell = cell_index(grid, b_lat, b_lon)
    ok = cell_ok[cell]
    moving = v >= MOVING_MPS
    if route_tree is not None:
        ci = np.flatnonzero(ok & ~moving)               # solo los quietos pueden ser depósito
        depot = np.zeros(len(ok), dtype=bool)
        if len(ci):
            q = np.column_stack([b_lat[ci] * _M_PER_DEG, b_lon[ci] * _M_PER_DEG * route_cos])
            d, _ = route_tree.query(q, k=1, workers=1)
            depot[ci] = d > DEPOT_FIT_M
        if stats is not None:
            stats["depot"] = int(depot.sum())
        ok &= ~depot
    sel = np.flatnonzero(ok)
    if len(sel) == 0:
        return empty
    v, b_vid, b_ts, cell, moving = v[sel], b_vid[sel], b_ts[sel], cell[sel], moving[sel]
    win = window_of(b_ts, window_min)
    nc = grid.n_ids
    nv = int(b_vid.max()) + 1
    key2 = (win * nc + cell) * nv + b_vid               # (ventana, celda, coche)
    u2, inv2 = np.unique(key2, return_inverse=True)
    m_any = np.bincount(inv2, weights=moving, minlength=len(u2)) > 0
    sp_sum = np.bincount(inv2, weights=np.where(moving, v, 0.0), minlength=len(u2))
    sp_cnt = np.bincount(inv2, weights=moving, minlength=len(u2))
    uk, inv = np.unique(u2 // nv, return_inverse=True)
    n = np.bincount(inv, minlength=len(uk))
    n_mov = np.bincount(inv, weights=m_any, minlength=len(uk))
    s = np.bincount(inv, weights=sp_sum, minlength=len(uk))
    c = np.bincount(inv, weights=sp_cnt, minlength=len(uk))
    speed = np.where(c > 0, s / np.maximum(c, 1), np.nan).astype(np.float32)
    return ((uk // nc).astype(np.int32), (uk % nc).astype(np.int32), speed,
            n.astype(np.uint16), (n - n_mov).astype(np.uint16))


def table_of(win, cell, speed, n, n_stopped) -> pa.Table:
    return pa.table({
        "window": pa.array(win, type=pa.int16()),
        "cell": pa.array(cell, type=pa.int32()),
        "speed_mps": pa.array(speed.astype(np.float16)),
        "n": pa.array(n, type=pa.uint16()),
        "n_stopped": pa.array(n_stopped, type=pa.uint16()),
    })


def process_day(day: str, *, data_dir: Path, out_dir: Path, grid: GridSpec, window_min: int, cell_ok: np.ndarray,
                route_points: np.ndarray, force: bool = False) -> dict:
    out = Path(out_dir) / "daily" / f"{day}.parquet"
    if out.exists() and not force:
        return {"day": day, "status": "skip"}
    fp = Path(data_dir) / f"{day}.ndjson.gz"
    t0, c0 = time.perf_counter(), time.process_time()
    tree, cos = build_route_tree(route_points)
    vid, ts, lat, lon = read_pings(fp)
    stats: dict = {}
    cols = aggregate(vid, ts, lat, lon, grid=grid, window_min=window_min, cell_ok=cell_ok,
                     route_tree=tree, route_cos=cos, stats=stats)
    tbl = table_of(*cols)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    pq.write_table(tbl, tmp, compression="zstd")
    tmp.replace(out)
    return {"day": day, "status": "ok", "rows": tbl.num_rows, "bytes": out.stat().st_size,
            "elapsed_s": round(time.perf_counter() - t0, 1), "cpu_s": round(time.process_time() - c0, 1), **stats}
