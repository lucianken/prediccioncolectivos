"""Punto 6: MAE del modelo por tramos en eval v2b, filas limpias vs contaminadas. Escribe eval_impacto.json."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
V2B = HERE.parents[1]
CLEAN_M = 45.0


def main():
    vr = pd.concat([pd.read_parquet(p) for p in sorted((HERE / "_days").glob("*.rows.parquet"))], ignore_index=True)
    vr = vr.drop_duplicates(["shape_id", "ts_p", "dist_along_m"])
    out = {"val_rows": len(vr)}
    for which in ["seen", "heldout"]:
        ev = pd.read_parquet(V2B / "eval" / f"eval_{which}.parquet",
                             columns=["line", "shape_id", "ts_p", "dist_along_m", "dist_remaining_m", "observed_eta_s"])
        pf = sorted((HERE / "eval").glob(f"*_{which}_*.pred.npy"))[-1]
        ev["pred"] = np.load(pf).astype(np.float64)
        m = ev.merge(vr[["shape_id", "ts_p", "dist_along_m", "perp_p", "perp_f", "oc_p", "oc_f", "oc_strict_p", "oc_strict_f"]],
                     on=["shape_id", "ts_p", "dist_along_m"], how="left")
        assert len(m) == len(ev)
        m["matched"] = m.perp_p.notna() & m.perp_f.notna()
        m["err"] = (m.pred - m.observed_eta_s).abs()
        m["bias"] = m.pred - m.observed_eta_s
        oc = m.oc_p.fillna(False).astype(bool) | m.oc_f.fillna(False).astype(bool)
        ocs = m.oc_strict_p.fillna(False).astype(bool) | m.oc_strict_f.fillna(False).astype(bool)
        mid = (m.perp_p > CLEAN_M) | (m.perp_f > CLEAN_M)
        mid_oc = mid & oc
        m["grp"] = np.select([~m.matched, ~mid & ~oc, mid & ~oc, ~mid & oc, mid & oc],
                             ["sin_dato", "limpia", "perp45_150", "otro_mas_cerca", "perp45_150+otro"], "x")
        m["band"] = (m.observed_eta_s >= 180) & (m.observed_eta_s <= 420)
        m["perp_max"] = np.maximum(m.perp_p, m.perp_f)
        res = {}
        for bname, sel in [("global", np.ones(len(m), bool)), ("3-7min", m.band.to_numpy())]:
            d = m[sel]
            r = {"n": len(d), "matched": int(d.matched.sum())}
            def stat(x):
                return {"n": int(len(x)), "frac": float(len(x) / max(d.matched.sum(), 1)),
                        "mae": float(x.err.mean()) if len(x) else None,
                        "bias": float(x.bias.mean()) if len(x) else None,
                        "p90": float(x.err.quantile(0.9)) if len(x) else None,
                        "late60": float((x.bias < -60).mean()) if len(x) else None,
                        "early60": float((x.bias > 60).mean()) if len(x) else None}
            dm = d[d.matched]
            r["grp"] = {g: stat(dm[dm.grp == g]) for g in ["limpia", "perp45_150", "otro_mas_cerca", "perp45_150+otro"]}
            r["limpia"] = stat(dm[dm.grp == "limpia"])
            r["contaminada"] = stat(dm[dm.grp != "limpia"])
            r["todas_matched"] = stat(dm)
            r["sin_dato_n"] = int((~d.matched).sum())
            # por perp max (cualquiera de P/F)
            bins = [0, 10, 20, 45, 75, 150]
            r["por_perp_max"] = {f"{a}-{b}": stat(dm[(dm.perp_max > a) & (dm.perp_max <= b)]) for a, b in zip(bins[:-1], bins[1:])}
            # otro más cerca con perp<=45 (calle paralela dentro del umbral)
            r["otro_estricto_limpias"] = stat(dm[(dm.grp == "limpia") & ocs[d.index][dm.index]])
            res[bname] = r
        out[which] = res
        m.to_pickle(HERE / f"_eval_{which}.pkl")
    json.dump(out, open(HERE / "eval_impacto.json", "w"), indent=1, ensure_ascii=False)
    print("ok")


if __name__ == "__main__":
    main()
