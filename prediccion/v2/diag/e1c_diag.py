"""
E1c: chequeo del diagnóstico A3 vs A1 con el modelo con grilla de ciudad (solo inferencia, reusa common.py y las
predicciones A1 / A3-K32 que guardó d1 en diag/pred_*.npz).

  PYTHONPATH=. python -m prediccion.v2.diag.e1c_diag [--ckpt data/ml/v2_39_k32_geo/models/eta_a3_best.pt]

Mide lo mismo que d2: (1) correlación ida/vuelta del error de nivel de velocidad (consultas de 1-3 km, por fracción
del recorrido; era -0,60 en A3 y -0,02 en A1), (2) MAE a más de 2 km. Escribe diag/e1c_results.json y e1c_tables.md.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from prediccion.eval import compute_metrics
from prediccion.v2.diag import common as C

SETS = {"train": ("train_sample_39.parquet", "pred_train_39.npz"), "eval": ("eval_seen_39.parquet", "pred_eval_39.npz")}
MODELS = ["A1", "A3-K32", "A3-E1c"]


def level_error_corr(df: pd.DataFrame, lengths: dict, meta: dict, col: str) -> dict:
    """Correlación entre sentidos de log(v_modelo / v_obs) por bin de fracción (misma definición que d2)."""
    sub = df[(df.rem >= 1000) & (df.rem <= 3000)].copy()
    sub["sentido"] = sub.sid.map(lambda s: meta[s]["sentido"].split()[0])
    sub["frac"] = ((sub.dist_along_m + sub.rem / 2) / sub.sid.map(lengths) * 20).astype(int).clip(0, 19)
    ts = {sen: g.groupby("frac").apply(lambda h: h.true.sum() / h[col].sum(), include_groups=False)
          for sen, g in sub.groupby("sentido")}
    j = pd.concat(ts, axis=1).dropna()
    return {"corr": float(np.corrcoef(np.log(j.iloc[:, 0]), np.log(j.iloc[:, 1]))[0, 1]),
            "std_log_ratio": float(np.log(j).stack().std()), "bins": int(len(j)), "n": int(len(sub))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=str(C.REPO_ROOT / "data/ml/v2_39_k32_geo/models/eta_a3_best.pt"))
    a = ap.parse_args(argv)
    meta = C.shapes_meta()
    with open(C.V2 / "shape_lengths.json", encoding="utf-8") as f:
        lengths = json.load(f)
    out, md = {}, ["# E1c: chequeo del diagnóstico (A1 / A3-K32 / A3-E1c con grilla de ciudad)\n"]
    for name, (pq, npz) in SETS.items():
        path = C.DIAG / pq
        df = C.load_df(path)
        P = dict(np.load(C.DIAG / npz))
        P["A3-E1c"] = C.a3_predict(path, len(df), C.Path(a.ckpt))
        df["sid"] = df["shape_id"].astype(str)
        df["rem"] = df["dist_remaining_m"]
        df["true"] = df["observed_eta_s"]
        res = {}
        for m in MODELS:
            df[m] = P[m]
            met = compute_metrics(P[m], df.true, df.rem)
            far = df[df.rem >= 2000]
            res[m] = {"mae": met["global"]["mae"], "bias": met["global"]["bias"],
                      "mae_by_eta": {k: v["mae"] for k, v in met["by_eta"].items()},
                      "mae_by_dist": {k: v["mae"] for k, v in met["by_dist"].items()},
                      "pct_under_60_0_5min": met["by_eta"]["0-5 min"]["pct_under_60s"],
                      "mae_over_2km": float((far[m] - far.true).abs().mean()),
                      "level_corr": level_error_corr(df, lengths, meta, m)}
        out[name] = {"n": int(len(df)), "models": res}
        rows = [{"modelo": m, "MAE": round(r["mae"], 1), "MAE >2 km": round(r["mae_over_2km"], 1),
                 "<500 m": round(r["mae_by_dist"]["<500 m"], 1), "0,5-2 km": round(r["mae_by_dist"]["0,5-2 km"], 1),
                 "2-5 km": round(r["mae_by_dist"]["2-5 km"], 1), "5+ km": round(r["mae_by_dist"]["5+ km"], 1),
                 "corr ida/vuelta": round(r["level_corr"]["corr"], 2),
                 "desvío log(v/v_obs)": round(r["level_corr"]["std_log_ratio"], 3)} for m, r in res.items()]
        d = pd.DataFrame(rows)
        cols = [str(c) for c in d.columns]
        md += [f"\n## {name} (n={len(df)})\n", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        md += ["| " + " | ".join(str(v) for v in r) + " |" for r in d.itertuples(index=False)]
    with open(C.DIAG / "e1c_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    (C.DIAG / "e1c_tables.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
