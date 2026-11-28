"""Ruido de interpolación de un cruce: cadenas de k intervalos consecutivos (pings compatibles, dt<=300 s, avance plausible).
Se interpola linealmente entre los extremos (como crossings_v2) un objetivo a fracción f de la distancia y se compara con la
referencia por tramos usando los pings intermedios. MAE(k) para k=2..6 y extrapolación log-log a k=1 (no validable).
python experiments/piso_gemelos/ruido_interp.py 2026-09-16"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
import gemelos as GM  # noqa: E402
from red import geo_assign as G  # noqa: E402
from prediccion.v2.shapes import LineShapes  # noqa: E402

day = sys.argv[1]
lines = ("39", "42", "92", "107", "132", "168")
per_line = GM.load_vehicles(day, lines)
ls = LineShapes(GM.SHAPES_DIR)
KS = (2, 3, 4, 5, 6)
FS = (0.2, 0.4, 0.6, 0.8)
errs = {k: [] for k in KS}
spd = {k: [] for k in KS}
for ln, vs in per_line.items():
    ixs = {x.shape_id: x.index for x in ls.get(ln)}
    for vid, v in vs.items():
        if len(v.ts) < 10:
            continue
        proj = {s: ix.project_many(v.lat, v.lon) for s, ix in ixs.items()}
        masks = G.compat_masks({s: p for s, (_, p) in proj.items()})
        sid = max(masks, key=lambda s: masks[s].sum())
        ok = np.flatnonzero(masks[sid])
        if len(ok) < 8:
            continue
        t = v.ts[ok]; d = proj[sid][0][ok]
        dt = np.diff(t); dd = np.diff(d)
        good = (dt > 0) & (dt <= 300) & (dd >= 0) & (dd <= 25 * dt + 50) & (np.diff(ok) >= 1)
        for k in KS:
            n = len(t) - k
            if n <= 0:
                continue
            # ventana de k intervalos buenos
            gk = np.array([good[i:i + k].all() for i in range(n)])
            for i in np.flatnonzero(gk):
                d0, dk = d[i], d[i + k]
                if dk - d0 < 100:
                    continue
                for f in FS:
                    ds = d0 + f * (dk - d0)
                    that = t[i] + f * (t[i + k] - t[i])
                    j = np.searchsorted(d[i:i + k + 1], ds, "right") - 1
                    j = min(max(j, 0), k - 1)
                    a, b = d[i + j], d[i + j + 1]
                    if b <= a:
                        continue
                    ref = t[i + j] + (ds - a) / (b - a) * (t[i + j + 1] - t[i + j])
                    errs[k].append(abs(that - ref))
                    spd[k].append((dk - d0) / (t[i + k] - t[i]))
res = {}
for k in KS:
    e = np.array(errs[k])
    res[k] = dict(n=int(len(e)), mae=float(e.mean()), p90=float(np.quantile(e, .9)),
                  mae_mov=float(e[np.array(spd[k]) >= 3].mean()))
ks = np.array(KS, float)
m = np.array([res[k]["mae"] for k in KS])
b, a = np.polyfit(np.log(ks), np.log(m), 1)
res["fit_k1_mae"] = float(np.exp(a)); res["exponent"] = float(b)
res["day"] = day
print(json.dumps(res, indent=1))
json.dump(res, open(HERE / "raw" / f"ruido_interp_{day}.json", "w"), indent=1)
