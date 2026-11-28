"""Filas de entrenamiento v2 (columnar, numpy) a partir de un viaje ya proyectado."""

from __future__ import annotations

import numpy as np

from prediccion.pipeline.features import _CAP_S, _find_prev_trip, _interp_passage, SEGMENT_SIZE_M, N_FLEET
from prediccion.v2.pairs import sample_pairs
from red.tiempo import encode_time_np

TRAJ_K = 10

COLUMNS = [
    "line", "shape_id", "ramal_id", "seg_idx", "dist_along_m", "dist_remaining_m",
    "dist_along_norm", "speed_mps", "hour_sin", "hour_cos", "dow", "has_active_bus",
    "observed_eta_s", "time_since_start", "ts_age_s", "traj_flat", "traj_len",
    "time_since_last_bus_s", "last_bus_found", "ts_p",
]


def trip_rows(
    *,
    line: str,
    shape_id: str,
    shape_length_m: float,
    vehicle_id: str,
    ts: np.ndarray,
    frame_ts: np.ndarray,
    speed: np.ndarray,
    dist: np.ndarray,
    k_pairs: int,
    seed: int,
    passage_cache: dict | None = None,
    start_unknown: bool = False,
    seg: np.ndarray | None = None,
    targets: tuple | None = None,
) -> dict | None:
    """
    Devuelve dict de columnas (arrays de largo n_rows) o None si el viaje no da pares.
    `ts`, `dist`, ... son los puntos válidos (perp <= 150 m) en orden cronológico.
    Semántica por fila idéntica a features.make_training_rows_eta; solo cambia que se
    muestrean k_pairs por viaje en vez de todos.
    start_unknown (segmentador v2b): el viaje no arranca en su cabecera, así que time_since_start no es real y se
    guarda NaN (nunca un 0 falso). seg: id de tramo continuo por punto; los pares no cruzan tramos distintos.
    targets (opcional): (pi, d_target, t_target) ya elegidos (T en paradas, v2/stop_targets.py); si no, T = un ping
    cualquiera adelante de P (sample_pairs, el comportamiento de siempre).
    """
    L = max(float(shape_length_m), 1.0)
    if targets is None:
        pi, fj = sample_pairs(dist, ts, k_pairs, seed, seg)
        d_t, t_t = dist[fj].astype(np.float64), ts[fj]
    else:
        pi, d_t, t_t = targets
    m = len(pi)
    if m == 0:
        return None

    # Historia de trayectoria (hasta 10 puntos terminando en P), paddeada
    hist_len = np.minimum(TRAJ_K, pi + 1)
    start = pi - hist_len + 1
    traj = np.zeros((m, TRAJ_K, 3), dtype=np.float32)
    for j in range(TRAJ_K):
        valid = j < hist_len
        src = np.where(valid, start + j, 0)
        traj[:, j, 0] = np.where(valid, dist[src] / L, 0.0)
        traj[:, j, 1] = np.where(valid, speed[src], 0.0)
        if j > 0:
            prev = np.where(valid, src - 1, 0)
            traj[:, j, 2] = np.where(valid, ts[src] - ts[prev], 0.0)

    p_ts = ts[pi]
    hs, hc, dow = encode_time_np(p_ts)
    dist_p = dist[pi]
    dist_rem = d_t - dist_p
    eta = (t_t - p_ts).astype(np.float32)

    tlb = np.full(m, _CAP_S, dtype=np.float32)
    lbf = np.zeros(m, dtype=bool)
    if passage_cache is not None:
        prev_by_p: dict[int, tuple] = {}
        for r in range(m):
            p = int(pi[r])
            if p not in prev_by_p:
                prev_by_p[p] = _find_prev_trip(passage_cache, shape_id, vehicle_id, int(ts[p]))
            pd_, pt_ = prev_by_p[p]
            if pd_ is not None:
                t, f = _interp_passage(pd_, pt_, float(d_t[r]), int(ts[p]))
                tlb[r] = t
                lbf[r] = f

    return {
        "line": np.full(m, line, dtype=object),
        "shape_id": np.full(m, shape_id, dtype=object),
        "ramal_id": np.full(m, shape_id, dtype=object),
        "seg_idx": (dist_p // SEGMENT_SIZE_M).astype(np.int32),
        "dist_along_m": dist_p.astype(np.float32),
        "dist_remaining_m": dist_rem.astype(np.float32),
        "dist_along_norm": (dist_p / L).astype(np.float32),
        "speed_mps": speed[pi].astype(np.float32),
        "hour_sin": hs.astype(np.float32),
        "hour_cos": hc.astype(np.float32),
        "dow": dow,
        "has_active_bus": np.ones(m, dtype=bool),
        "observed_eta_s": eta,
        "time_since_start": (np.full(m, np.nan, dtype=np.float32) if start_unknown
                             else (p_ts - ts[0]).astype(np.float32)),
        "start_unknown": np.full(m, bool(start_unknown), dtype=bool),
        "ts_age_s": np.minimum(frame_ts[pi] - p_ts, 600).astype(np.float32),
        "traj_flat": traj.reshape(m, TRAJ_K * 3),
        "traj_len": hist_len.astype(np.int8),
        "time_since_last_bus_s": tlb,
        "last_bus_found": lbf,
        "ts_p": p_ts.astype(np.int64),
    }


def add_trip_to_passage_cache(cache: dict, shape_id: str, vehicle_id: str,
                              dist: np.ndarray, ts: np.ndarray, max_entries: int = 10) -> None:
    """Misma lógica que build_dataset._add_trip_to_cache, sobre arrays."""
    if len(dist) < 2:
        return
    order = np.argsort(dist, kind="stable")
    dl = dist[order].tolist()
    tl = ts[order].tolist()
    entries = cache.setdefault(shape_id, [])
    entries.append((vehicle_id, dl, tl, min(tl)))
    if len(entries) > max_entries:
        del entries[0]
