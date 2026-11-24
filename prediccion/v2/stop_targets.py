"""
Puntos objetivo T en paradas reales (ARQUITECTURA.md §7, "Entrenar con T en paradas").

El build de siempre elige T = un ping cualquiera del viaje, adelante de P. Acá T es una PARADA del recorrido y la etiqueta es
la hora de paso del coche por esa parada, interpolada entre los dos pings consecutivos que la encierran.

Paradas de un recorrido: SOLO las de su propia lista (`ramales[].stops` de la relación OSM de ese shape), proyectadas sobre
  el shape con `models/stops.py::project_stops` (ShapeIndex exacto, 2 decimales: la misma distancia que usa la app y el modelo,
  `stops_m`). NO se agregan paradas de otros recorridos por geometría: una parada que existe en un ramal y no figura en otro
  significa que ese otro ramal no para ahí. Dos paradas a < DEDUP_M entre sí en un recorrido cuentan una (ids duplicados del
  mismo poste). Una parada a menos de END_TOL_M del final del recorrido se cruza al llegar a END_TOL_M del final (como la vara).

Cruce firme de una parada (misma regla que la vara corregida, `replay/core.py::crossings_v2`): par de pings consecutivos
válidos (compatibles con el recorrido) k, k+1 del mismo tramo continuo con d_k <= d_parada < d_(k+1), 0 < dt <= PASS_MAX_DT_S
(10 min) y avance <= V_MAX_MPS * dt + JUMP_SLACK_M (sin saltos de GPS). La hora de paso es la interpolación lineal en la
distancia entre los dos pings. Ruido esperado (medido con `interpolation_noise`, ver ARQUITECTURA §7): error de interpolar
el ping central de tres pings seguidos, mediana ~ decenas de segundos, P90 ~ 1 min; el `ts` ya es el estampado por lote de CABA
(~1/min), igual que la etiqueta de siempre.

Pares (P, parada): P = ping válido con d_P <= d_parada - MIN_DIST_M (100 m, igual que el resto del pipeline), en el mismo
tramo continuo que el cruce y anterior a él. Se muestrea con la misma estratificación por distancia restante que
`pairs.sample_pairs` (5 buckets de 100 m a 5+ km, ~K/5 cada uno).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from prediccion.v2.pairs import DIST_EDGES_M, MIN_DIST_M, N_BUCKETS, _allocate, sample_pairs

DEDUP_M = 10.0
END_TOL_M = 50.0
PASS_MAX_DT_S = 600.0
V_MAX_MPS = 25.0
JUMP_SLACK_M = 50.0

_CACHE: dict = {}


def associate_stops(shapes: dict[str, list], own_stops: dict[str, list[dict]], dedup_m: float = DEDUP_M) -> dict[str, np.ndarray]:
    """
    {shape_id: metros desde el inicio de sus paradas, ordenados}. Solo pertenencia a la lista del propio recorrido.
    shapes: {shape_id: [(lat, lon), ...]}; own_stops: {shape_id: [{id, lat, lng}, ...]}.
    """
    from prediccion.models.stops import project_stops
    out: dict[str, np.ndarray] = {}
    for sid, pts in shapes.items():
        keep: list[float] = []
        for d in project_stops(pts, own_stops.get(sid, [])):
            if not keep or d - keep[-1] >= dedup_m:
                keep.append(d)
        out[sid] = np.asarray(keep, dtype=np.float64)
    return out


def line_stop_targets(line: str, shapes_dir) -> dict[str, np.ndarray]:
    """Paradas asociadas por shape de una línea (cacheado por proceso)."""
    key = (str(shapes_dir), str(line))
    if key not in _CACHE:
        p = Path(shapes_dir) / f"{line}.json"
        shapes, own = {}, {}
        if p.exists():
            for r in json.loads(p.read_text(encoding="utf-8")).get("ramales", []):
                sid, pts = r.get("shapeId"), r.get("points", [])
                if sid is None or len(pts) < 2:
                    continue
                shapes[str(sid)] = pts
                own[str(sid)] = r.get("stops", []) or []
        _CACHE[key] = associate_stops(shapes, own) if shapes else {}
    return _CACHE[key]


def stop_crossings(ts: np.ndarray, dist: np.ndarray, seg: np.ndarray | None, d_stop: float):
    """
    Cruces firmes de `d_stop` entre pings válidos consecutivos. Devuelve (k, t_cruce): k = índice del ping anterior al cruce.
    """
    n = len(ts)
    if n < 2:
        return np.empty(0, np.int64), np.empty(0)
    t0, t1 = ts[:-1].astype(np.float64), ts[1:].astype(np.float64)
    d0, d1 = dist[:-1], dist[1:]
    dt = t1 - t0
    m = (d0 <= d_stop) & (d_stop < d1) & (dt > 0) & (dt <= PASS_MAX_DT_S) & ((d1 - d0) <= V_MAX_MPS * dt + JUMP_SLACK_M)
    if seg is not None:
        m &= seg[:-1] == seg[1:]
    k = np.flatnonzero(m)
    if len(k) == 0:
        return k.astype(np.int64), np.empty(0)
    tc = t0[k] + (d_stop - d0[k]) / (d1[k] - d0[k]) * dt[k]
    return k.astype(np.int64), tc


def stop_pair_targets(dist: np.ndarray, ts: np.ndarray, stops_m: np.ndarray, length_m: float, k: int, seed: int,
                      seg: np.ndarray | None = None):
    """
    Hasta k pares (P, parada). Devuelve (pi, d_target, t_target): índice del ping P, distancia de la parada (m desde el inicio
    del shape) y hora de paso (s, float) — o None si no hay ninguno. Estratificado por distancia restante como sample_pairs.
    """
    n = len(dist)
    if n < 2 or k <= 0 or len(stops_m) == 0:
        return None
    seg_ = seg if seg is not None else np.zeros(n, np.int64)
    I, D, T = [], [], []
    idx = np.arange(n)
    for ds0 in stops_m:
        ds = min(float(ds0), max(length_m - END_TOL_M, 0.0))
        ks, tc = stop_crossings(ts, dist, seg_, ds)
        if len(ks) == 0:
            continue
        j = np.searchsorted(ks, idx, side="left")              # primer cruce con k >= i
        ok = (j < len(ks)) & (dist <= ds - MIN_DIST_M)
        jj = np.minimum(j, len(ks) - 1)
        ok &= (seg_[ks[jj]] == seg_) & (tc[jj] > ts)
        ii = idx[ok]
        if len(ii) == 0:
            continue
        I.append(ii)
        D.append(np.full(len(ii), ds))
        T.append(tc[jj[ok]])
    if not I:
        return None
    pi, d_t, t_t = np.concatenate(I), np.concatenate(D), np.concatenate(T)
    if len(pi) > k:
        d = d_t - dist[pi]
        bucket = np.searchsorted(np.asarray(DIST_EDGES_M[1:]), d, side="right")
        members = [np.flatnonzero(bucket == b) for b in range(N_BUCKETS)]
        alloc = _allocate([len(x) for x in members], k)
        rng = np.random.default_rng(seed)
        chosen = [rng.choice(members[b], size=alloc[b], replace=False) for b in range(N_BUCKETS) if alloc[b] > 0]
        sel = np.sort(np.concatenate(chosen))
        pi, d_t, t_t = pi[sel], d_t[sel], t_t[sel]
    return pi.astype(np.int64), d_t, t_t


def mixed_targets(dist: np.ndarray, ts: np.ndarray, stops_m: np.ndarray, length_m: float, k: int, seed: int,
                  seg: np.ndarray | None, stop_frac: float):
    """
    stop_frac = 1.0: solo paradas. 0 < stop_frac < 1: round(k * stop_frac) pares en paradas y el resto en puntos cualquiera
    del camino (los de siempre). Devuelve (pi, d_target, t_target) o None.
    """
    k_stop = k if stop_frac >= 1.0 else int(round(k * stop_frac))
    parts = []
    r = stop_pair_targets(dist, ts, stops_m, length_m, k_stop, seed, seg)
    if r is not None:
        parts.append(r)
    if stop_frac < 1.0 and k - k_stop > 0:
        pi, fj = sample_pairs(dist, ts, k - k_stop, seed + 1, seg)
        if len(pi):
            parts.append((pi, dist[fj].astype(np.float64), ts[fj].astype(np.float64)))
    if not parts:
        return None
    return tuple(np.concatenate([p[i] for p in parts]) for i in range(3))


def interpolation_noise(ts: np.ndarray, dist: np.ndarray, seg: np.ndarray | None = None, max_span_s: float = 120.0) -> np.ndarray:
    """
    Error (s) de interpolar la hora de un ping a partir de los dos vecinos (hora interpolada - hora real), con la misma
    interpolación lineal en la distancia que la etiqueta de paradas. Solo ternas del mismo tramo, con avance y span <= max_span_s
    (los dos vecinos a lo sumo a 2 min entre sí: la brecha típica de la etiqueta). Es el ruido que agrega interpolar en vez de
    observar el paso.
    """
    n = len(ts)
    if n < 3:
        return np.empty(0)
    t = ts.astype(np.float64)
    a, b, c = np.arange(n - 2), np.arange(1, n - 1), np.arange(2, n)
    ok = ((dist[c] - dist[a]) > 20.0) & (dist[a] < dist[b]) & (dist[b] < dist[c]) & ((t[c] - t[a]) <= max_span_s)
    if seg is not None:
        ok &= (seg[a] == seg[b]) & (seg[b] == seg[c])
    a, b, c = a[ok], b[ok], c[ok]
    hat = t[a] + (dist[b] - dist[a]) / (dist[c] - dist[a]) * (t[c] - t[a])
    return hat - t[b]
