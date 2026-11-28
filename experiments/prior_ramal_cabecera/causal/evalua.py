"""Etapa 3: precision del prior causal contra el techo (test 2026-09-15 a 10-14). Lee res_P.pkl / res_A.pkl / meta.json de modelo.py.
Escribe evalua_out.txt (tablas en texto) y evalua_lineas.csv. Correr desde 'prediccion colectivos' con Python313.
"""
from __future__ import annotations
import json, pickle, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from prior import TEST   # noqa: E402
from modelo import reliability, DGRID   # noqa: E402

OUT = ROOT / "data/ml/replay/prior"
P = pickle.load(open(OUT / "res_P.pkl", "rb")); A = pickle.load(open(OUT / "res_A.pkl", "rb"))
meta = json.load(open(OUT / "meta.json"))
out = []; w = lambda *a: out.append(" ".join(str(i) for i in a))
LINES = ["39", "168", "132", "106", "42", "33", "110", "181", "9", "20", "85", "180", "98", "188"]
cols = [("freq", 0), ("techo", 0)] + [(m, d) for d in (0, 300, 1200) for m in ("token", "cadena")]


def sel(gk, D, sub):
    a = A[gk]; te = (a["day"] >= TEST[0]) & (a["day"] <= TEST[1]) & a["tgt"]
    if sub == "ambiguo":     # el propio coche aun no revelo su ramal a Tq = det + D
        te &= a["rvts"] > a["ts"] + D
    return te


def stats(sub, D):
    rows = []
    for gk in meta:
        L = gk.split("|")[0]
        for (m, d) in cols:
            dd = D if m in ("token", "cadena") else 0
            if m in ("token", "cadena") and d != D:
                continue
            te = sel(gk, D, sub)
            Pm = P[(gk, m, d)][te]; y = A[gk]["y"][te]
            if not len(y):
                continue
            rows.append(dict(line=L, gk=gk, modelo=m + (f"@{d}" if m in ("token", "cadena") else ""), n=len(y), c=int((Pm.argmax(1) == y).sum()),
                             ll=float(-np.log(np.clip(Pm[np.arange(len(y)), y], 1e-9, 1)).sum())))
    return pd.DataFrame(rows)


res_all = []
for sub in ("todos", "ambiguo"):
    for D in (0, 300, 1200):
        d = stats(sub, D)
        if sub == "ambiguo" or D == 0:
            pass
        g = d.groupby(["line", "modelo"]).agg(n=("n", "sum"), c=("c", "sum"), ll=("ll", "sum")).reset_index()
        g["acc"] = g.c / g.n; g["logloss"] = g.ll / g.n; g["sub"] = sub; g["D"] = D
        res_all.append(g)
R = pd.concat(res_all)
R.to_csv(HERE / "evalua_lineas.csv", index=False)
for sub in ("todos", "ambiguo"):
    for D in (0, 300, 1200):
        r = R[(R["sub"] == sub) & (R.D == D)]
        mods = ["freq", "techo", f"token@{D}", f"cadena@{D}"]
        w(f"\n## sub={sub} D={D}s (acc / logloss); n = eventos de test")
        w("linea | n | " + " | ".join(mods))
        for L in LINES:
            z = r[r.line == L].set_index("modelo")
            if not len(z):
                continue
            w(f"{L} | {int(z.n.iloc[0])} | " + " | ".join(f"{z.loc[m, 'acc']:.3f} / {z.loc[m, 'logloss']:.3f}" for m in mods))
        z = r.groupby("modelo").agg(n=("n", "sum"), c=("c", "sum"), ll=("ll", "sum"))
        w("TODAS | " + str(int(z.n.iloc[0])) + " | " + " | ".join(f"{z.loc[m, 'c'] / z.loc[m, 'n']:.3f} / {z.loc[m, 'll'] / z.loc[m, 'n']:.3f}" for m in mods))
# calibracion y resolucion (todas las cabeceras), D=300
for m in ("techo", "token@300", "cadena@300"):
    Ps, ys, ps_max, ok = [], [], [], []
    for gk in meta:
        mm, d = (m.split("@") + ["0"])[:2]
        te = sel(gk, 300, "todos")
        Pm = P[(gk, mm, int(d))][te]; y = A[gk]["y"][te]
        Ps.append(Pm); ys.append(y)
    Pc = np.vstack([p for p in Ps]) if False else None
    # reliability por pares evento-ramal (K distinto por cabecera: se concatenan los vectores)
    p = np.concatenate([x.ravel() for x in Ps]); o = np.concatenate([(np.arange(x.shape[1])[None, :] == y[:, None]).ravel() for x, y in zip(Ps, ys)]).astype(float)
    q = pd.qcut(p, 10, duplicates="drop"); df = pd.DataFrame(dict(p=p, o=o, q=q)).groupby("q", observed=True).agg(p=("p", "mean"), o=("o", "mean"), n=("p", "size"))
    ece = (abs(df.p - df.o) * df.n).sum() / df.n.sum()
    pm = np.concatenate([x.max(1) for x in Ps]); okk = np.concatenate([x.argmax(1) == y for x, y in zip(Ps, ys)])
    w(f"\n## Calibracion {m} (D=300, todos), ECE {ece:.3f}")
    w(df.round(3).to_string())
    w(f"P>=0.8: {(pm >= .8).mean():.3f} acierto {okk[pm >= .8].mean():.3f}; P>=0.6: {(pm >= .6).mean():.3f} acierto {okk[pm >= .6].mean():.3f}")
# cobertura de la revelacion causal
rows = []
for gk in meta:
    a = A[gk]; te = (a["day"] >= TEST[0]) & (a["day"] <= TEST[1]) & a["tgt"]
    ts = a["ts"][te]; rt = a["rvts"][te]
    rows.append(dict(line=gk.split("|")[0], n=int(te.sum()), rev=int(np.isfinite(rt).sum()), ok=int((a["rv"][te] == a["y"][te]).sum() * 0 + ((a["rv"][te] == a["y"][te]) & np.isfinite(rt)).sum()),
                     d_med=float(np.nanmedian(np.where(np.isfinite(rt), rt - ts, np.nan))) if np.isfinite(rt).any() else np.nan,
                     **{f"rev{D}": int((rt <= ts + D).sum()) for D in DGRID}))
c = pd.DataFrame(rows).groupby("line").agg({"n": "sum", "rev": "sum", "ok": "sum", **{f"rev{D}": "sum" for D in DGRID}})
c["rev_pct"] = 100 * c.rev / c.n; c["acuerdo_pct"] = 100 * c.ok / c.rev
for D in DGRID:
    c[f"rev{D}_pct"] = 100 * c[f"rev{D}"] / c.n
w("\n## Revelacion propia (test): % de salidas con ramal revelado alguna vez / a det+D, y acuerdo con la etiqueta ex post")
w(c[["n", "rev_pct", "acuerdo_pct"] + [f"rev{D}_pct" for D in DGRID]].round(1).to_string())
open(HERE / "evalua_out.txt", "w", encoding="utf8").write("\n".join(out))
print("\n".join(out))
