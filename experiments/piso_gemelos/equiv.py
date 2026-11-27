"""Equivalencia geométrica de tramos entre shapes (para elegir gemelos A de otro ramal / otra línea).

Un tramo de un shape objetivo s (nodos cada NODE_M m, de largo m nodos) es equivalente en otro shape s' si las muestras cada
SAMPLE_M m del tramo quedan a <= EQ_PERP_M de s' y la distancia a lo largo de s' avanza igual que en s (mismo sentido).
Resultado: eq[s] = {s': (Dp (n_nodos,), node_ok (n_nodos,), seg_ok {m: bool (n_nodos,)})}.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prediccion.v2.shapes import LineShapes  # noqa: E402

NODE_M = 250.0
SAMPLE_M = 50.0
EQ_PERP_M = 25.0
END_TOL_M = 50.0
SEG_NODES = (4, 6, 8, 10)          # largos 1000, 1500, 2000, 2500 m
TARGET_LINES = ("39", "42", "92", "107", "132", "168")
STEP_MIN, STEP_MAX = 20.0, 90.0    # avance de s' por cada muestra de 50 m de s


def build(shapes_dir, target_lines=TARGET_LINES, cache: Path | None = None):
    if cache and cache.exists():
        return pickle.load(open(cache, "rb"))
    ls = LineShapes(shapes_dir)
    all_lines = ls.available_lines()
    cand = {}
    for ln in all_lines:
        for s in ls.get(ln):
            cand[s.shape_id] = (ln, s.index)
    k_per = int(NODE_M / SAMPLE_M)
    out = {"eq": {}, "shape_line": {sid: v[0] for sid, v in cand.items()}, "target": {}}
    for ln in target_lines:
        for sh in ls.get(ln):
            ix = sh.index
            L = ix.total_length_m
            n_nodes = int((L - END_TOL_M) // NODE_M) + 1
            smp = np.arange(0.0, (n_nodes - 1) * NODE_M + 1e-6, SAMPLE_M)
            lat = np.interp(smp, ix._cum_dist, ix._pts[:, 0])
            lon = np.interp(smp, ix._cum_dist, ix._pts[:, 1])
            out["target"][sh.shape_id] = dict(line=ln, length=L, n_nodes=n_nodes)
            eq = {}
            for sid, (ln2, ix2) in cand.items():
                if sid == sh.shape_id:
                    Dp = np.arange(n_nodes) * NODE_M
                    node_ok = np.ones(n_nodes, bool)
                    seg_ok = {m: np.ones(max(n_nodes - m, 0), bool) for m in SEG_NODES}
                    eq[sid] = (Dp, node_ok, seg_ok)
                    continue
                d2, p2 = ix2.project_many(lat, lon)
                ok = p2 <= EQ_PERP_M
                if ok.sum() < 5 * k_per:
                    continue
                step = np.diff(d2)
                sok = ok[:-1] & ok[1:] & (step >= STEP_MIN) & (step <= STEP_MAX)
                cs = np.concatenate([[0], np.cumsum(~sok)])      # pasos malos acumulados
                seg_ok = {}
                for m in SEG_NODES:
                    a = np.arange(max(n_nodes - m, 0)) * k_per
                    b = a + m * k_per
                    seg_ok[m] = (cs[b] - cs[a]) == 0
                if not any(v.any() for v in seg_ok.values()):
                    continue
                node_ok = ok[::k_per][:n_nodes]
                eq[sid] = (d2[::k_per][:n_nodes], node_ok, seg_ok)
            out["eq"][sh.shape_id] = eq
    if cache:
        pickle.dump(out, open(cache, "wb"))
    return out


if __name__ == "__main__":
    shp = Path(__file__).resolve().parents[3] / "proyectoconsola" / "data" / "backup_line_shapes_2026-11-26"
    r = build(shp, cache=Path(__file__).parent / "raw" / "equiv.pkl")
    lines = set()
    for s, eq in r["eq"].items():
        t = r["target"][s]
        tot = {m: int(sum(v[2][m].sum() for v in eq.values())) for m in SEG_NODES}
        print(s, t["line"], round(t["length"]), t["n_nodes"], "shapes eq:", len(eq), "lineas:", len({r["shape_line"][x] for x in eq}), tot)
        lines |= {r["shape_line"][x] for x in eq}
    print(len(lines), sorted(lines, key=lambda x: (len(x), x)))
