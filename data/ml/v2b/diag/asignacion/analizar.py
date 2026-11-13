"""Agrega los pickles de _days y arma las tablas del informe (resultados en resumen.json)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
LINES = ["26", "39", "42", "92", "124", "151", "168", "50", "106", "107", "108", "132", "12", "15", "128"]


def load():
    out = []
    for p in sorted((HERE / "_days").glob("*.pkl")):
        out.append(pickle.load(open(p, "rb")))
    return out


def pct_from_hist(h, qs, upto):
    h = h[:upto + 1].astype(np.float64)
    c = np.cumsum(h) / max(h.sum(), 1)
    return [float(np.searchsorted(c, q) / 2.0) for q in qs]


def main():
    R = load()
    days = [r["day"] for r in R]
    res = {"n_days": len(R), "first": days[0], "last": days[-1]}
    hist = {ln: np.zeros(1002, np.int64) for ln in LINES}
    cnt = {ln: {} for ln in LINES}
    rc = {ln: {} for ln in LINES}
    rt = {ln: 0 for ln in LINES}
    trips = []
    for r in R:
        for ln, h in r["hist"].items():
            hist[ln] += h
        for ln, c in r["cnt"].items():
            for k, v in c.items():
                cnt[ln][k] = cnt[ln].get(k, 0) + v
        for ln, c in r["rows_cnt"].items():
            for k, v in c.items():
                rc[ln][k] = rc[ln].get(k, 0) + v
        for ln, v in r["rows_total"].items():
            rt[ln] += v
        t = pd.DataFrame(r["trips"]); t["day"] = r["day"]; trips.append(t)
    T = pd.concat(trips, ignore_index=True)
    # 1. ruido
    qs = [0.5, 0.9, 0.95, 0.99]
    res["noise"] = {}
    for ln in LINES + ["TODAS"]:
        h = sum(hist.values()) if ln == "TODAS" else hist[ln]
        tot = int(h.sum())
        res["noise"][ln] = {"pings": tot, "frac_gt150": float(h[301:].sum() / max(tot, 1)),
                            "pct_valid": pct_from_hist(h, qs, 300),
                            "pct_all": pct_from_hist(h, qs, 1001)}
    # 2. contaminación
    def agg(d):
        return {k: sum(d[l].get(k, 0) for l in LINES) for k in set().union(*[d[l].keys() for l in LINES])}
    cnt["TODAS"] = agg(cnt); rc["TODAS"] = agg(rc); rt["TODAS"] = sum(rt[l] for l in LINES)
    res["pings"] = cnt; res["rows"] = rc; res["rows_total"] = rt
    # 3. ambigüedad
    T["gap"] = T.med2 - T.med1
    res["trips_n"] = len(T)
    res["amb"] = {}
    for ln in LINES + ["TODAS"]:
        g = T if ln == "TODAS" else T[T.line == ln]
        fin = np.isfinite(g.gap)
        res["amb"][ln] = {"trips": len(g), "frag20": float((g.gap < 20).mean()), "frag20_neg": float((g.gap < 0).mean()),
                          "frag10": float((g.gap < 10).mean()),
                          "second_opp": float(g.second_opp.mean()),
                          "frag20_and_opp": float(((g.gap < 20) & g.second_opp).mean()),
                          "gap_p50": float(g.gap[fin].median()) if fin.any() else None,
                          "med1_p50": float(g.med1.median()), "med1_p90": float(g.med1.quantile(0.9)),
                          "n_shapes_ge2": float(np.isfinite(g.med2).mean())}
    # 4. back150 en res["pings"] (back150/pairs)
    T.to_pickle(HERE / "_trips_all.pkl")
    # 5. simulación
    sim = [r["sim"] for r in R if "sim" in r]
    res["noise_frac_le"] = {str(m): float(sum(h[:int(m * 2) + 1].sum() for h in hist.values()) / sum(h[:301].sum() for h in hist.values())) for m in (10, 15, 20, 30, 45, 60, 100)}
    res["sim_days"] = [r["day"] for r in R if "sim" in r]
    if sim:
        from diag_asignacion import opposite_map  # noqa
        from prediccion.v2.shapes import LineShapes
        shapes = LineShapes()
        opp = {ln: opposite_map(shapes, ln) for ln in LINES}
        res["sim"] = {}
        for key in ["base", "s45"]:
            D = pd.concat([s[key] for s in sim], ignore_index=True)
            tr = transitions_fast(D, opp)
            rs = D.reason.value_counts().to_dict()
            res["sim"][key] = {"trips": len(D), "valid_pings": int(D.n_valid.sum()), "pings": int(D.n.sum()),
                               "start_unknown": float(D.start_unknown.mean()),
                               "start_unknown_w": float((D.start_unknown * D.n_valid).sum() / max(D.n_valid.sum(), 1)),
                               "reasons": rs, "transitions": tr,
                               "no_shape": int((D["shape"] == "").sum())}
        # corte partido / unido entre 150 y 45
        sp = mg = same = 0
        for s in sim:
            a, b = s["base"], s["s45"]
            sp_, mg_ = overlaps(a, b)
            sp += sp_; mg += mg_
        res["sim"]["split_150_into_multiple_45"] = sp
        res["sim"]["merge_multiple_150_into_one_45"] = mg
    json.dump(res, open(HERE / "resumen.json", "w"), indent=1, ensure_ascii=False)
    print("ok")


def transitions_fast(D, opp):
    D = D.sort_values(["line", "vid", "t0"]).reset_index(drop=True)
    nx = D.shift(-1)
    ok = (D.line == nx.line) & (D.vid == nx.vid) & ((nx.t0 - D.t1) <= 300) & ((nx.t0 - D.t1) >= -60)
    a, b = D[ok], nx[ok]
    out = {"same": 0, "opposite": 0, "other_ramal": 0, "no_shape": 0}
    for ln, sa, sb in zip(a.line, a["shape"], b["shape"]):
        if not sa or not sb:
            out["no_shape"] += 1
        elif sa == sb:
            out["same"] += 1
        elif sb in opp[ln].get(sa, set()):
            out["opposite"] += 1
        else:
            out["other_ramal"] += 1
    return out


def overlaps(a, b):
    """(# viajes de a que se parten en >=2 de b, # viajes de b que reúnen >=2 de a)."""
    def count(x, y):
        n = 0
        yg = {k: g for k, g in y.groupby(["line", "vid"])}
        for k, g in x.groupby(["line", "vid"]):
            yy = yg.get(k)
            if yy is None:
                continue
            y0, y1 = yy.t0.to_numpy(), yy.t1.to_numpy()
            for t0, t1 in zip(g.t0.to_numpy(), g.t1.to_numpy()):
                if ((np.minimum(y1, t1) - np.maximum(y0, t0)) >= 60).sum() >= 2:
                    n += 1
        return n
    return count(a, b), count(b, a)


if __name__ == "__main__":
    main()
