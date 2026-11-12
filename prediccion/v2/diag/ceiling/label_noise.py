"""
Ruido de etiqueta (§6.2.1): la etiqueta (ETA real) es el pasaje por T interpolado entre pings de ~60 s.
Se mide con leave-one-out sobre trayectorias reales: para tripletas de pings consecutivos de un mismo coche
(p0, p1, p2; dt01 y dt12 en [40, 80] s, coche en movimiento y casi en línea recta) se interpola el tiempo de p1 desde
p0 y p2 por distancia recorrida (igual que la etiqueta) y se compara con el tiempo real de p1.
Eso corresponde a un hueco de ~120 s con el punto en el medio: es una COTA SUPERIOR del error de un hueco de 60 s.
Estimación para el hueco real de 60 s con T uniforme dentro del hueco: el error escala con el hueco (x1/2) y con
u(1-u) (promedio 2/3 del máximo del medio) -> ~1/3 del valor LOO. Es una estimación, no una medición directa.

  PYTHONPATH=. python -m prediccion.v2.diag.ceiling.label_noise [--days 2026-09-16,2026-10-06]
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from prediccion.v2.diag.ceiling import common as C
from prediccion.v2.diag.ceiling.run_ceiling import read_pings_ids
from prediccion.v2.traffic.grid import cell_index, _M_PER_DEG
from prediccion.v2.traffic.mask import cell_lookup


def loo_errors(day: str) -> np.ndarray:
    grid = C.grid_spec()
    cell_ok = cell_lookup(grid, np.load(C.TRAFFIC / "route_mask.npz")["cells"])
    vid, ts, lat, lon, _ = read_pings_ids(C.NDJSON_DIR / f"{day}.ndjson.gz")
    o = np.lexsort((ts, vid))
    vid, ts, lat, lon = vid[o], ts[o], lat[o], lon[o]
    cos = np.cos(np.radians(lat.mean()))
    x = lon * _M_PER_DEG * cos
    y = lat * _M_PER_DEG
    ok_c = cell_ok[cell_index(grid, lat, lon)]
    a, b, c = slice(0, -2), slice(1, -1), slice(2, None)
    same = (vid[a] == vid[b]) & (vid[b] == vid[c])
    d01 = np.hypot(x[b] - x[a], y[b] - y[a]); d12 = np.hypot(x[c] - x[b], y[c] - y[b]); d02 = np.hypot(x[c] - x[a], y[c] - y[a])
    t01 = ts[b] - ts[a]; t12 = ts[c] - ts[b]
    m = (same & (t01 >= 40) & (t01 <= 80) & (t12 >= 40) & (t12 <= 80) & (d02 >= 150) & (d01 + d12 <= 1.1 * d02)
         & (d01 >= 20) & (d12 >= 20) & ok_c[b])
    f = d01[m] / (d01[m] + d12[m])
    t_hat = f * (t01[m] + t12[m])
    return t_hat - t01[m]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default="2026-09-16,2026-09-22,2026-10-06")
    a = ap.parse_args()
    err = np.concatenate([loo_errors(d) for d in a.days.split(",")])
    ae = np.abs(err)
    out = {"n": int(len(err)), "loo_120s": {"mae": float(ae.mean()), "p50": float(np.percentile(ae, 50)),
                                          "p90": float(np.percentile(ae, 90)), "bias": float(err.mean())},
           "estimate_60s_gap_(x1/3)": {"mae": float(ae.mean() / 3), "p50": float(np.percentile(ae, 50) / 3),
                                       "p90": float(np.percentile(ae, 90) / 3)}}
    print(json.dumps(out, indent=1))
    (C.DIAG / "ceiling_label_noise.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
