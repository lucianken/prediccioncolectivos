"""
D1: ¿el A3 generaliza mal o no logra representar lo que sabe la tabla A1? (línea 39)

  1. Evalúa A1, A3-K32 y A3-K64 sobre ~100k filas de ENTRENAMIENTO de la 39 (estratificadas por ETA real) y sobre
     eval_seen filtrado a la 39, con las métricas y buckets de prediccion/eval.py.
  2. Explica "train 48 s > val 41 s" del log: recomputa la pérdida (pinball) y el MAE real en muestras naturales
     de train y de val, con dropout activo y en modo eval.

  PYTHONPATH=. python -m prediccion.v2.diag.d1_train_vs_val
"""
from __future__ import annotations

import json
import time

import numpy as np

from prediccion.v2.diag import common as C


def main():
    C.DIAG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    tr_pq = C.make_stratified_sample(C.TRAIN_PQ, C.DIAG / "train_sample_39.parquet")
    ev_pq = C.filter_eval_39(C.DIAG / "eval_seen_39.parquet")
    nat_tr = C.make_natural_sample(C.TRAIN_PQ, C.DIAG / "nat_train_39.parquet", per_group=2000)
    nat_va = C.make_natural_sample(C.VAL_PQ, C.DIAG / "nat_val_39.parquet", per_group=12000)
    print(f"muestras listas {time.time()-t0:.0f}s")

    from prediccion.models.a1_baseline import A1Baseline
    a1 = A1Baseline.load(str(C.A1_PKL))
    out, preds = {}, {}
    md = []
    for setname, path in [("train (muestra)", tr_pq), ("eval_seen 39", ev_pq)]:
        df = C.load_df(path)
        n = len(df)
        P = {"A1": C.predict_a1(df, a1)}
        for k, ck in C.A3_CKPTS.items():
            P[k] = C.a3_predict(path, n, ck)
        true = df["observed_eta_s"].to_numpy(float)
        dist = df["dist_remaining_m"].to_numpy(float)
        out[setname] = {}
        for m, p in P.items():
            met = C.compute_metrics(p, true, dist)
            out[setname][m] = met
            md.append(C.metrics_to_markdown(f"{m} sobre {setname} (n={n})", met))
        preds[setname] = P
        np.savez_compressed(C.DIAG / ("pred_" + ("train" if "train" in setname else "eval") + "_39.npz"), **P)
        print(setname, {m: round(out[setname][m]["global"]["mae"], 1) for m in P}, f"{time.time()-t0:.0f}s")

    # ── pérdida de entrenamiento vs val: ¿por qué 48 > 41? ───────────────────────────────────────────────────────
    loss = {}
    for k, ck in C.A3_CKPTS.items():
        loss[k] = {}
        for sname, path in [("train", nat_tr), ("val", nat_va)]:
            df = C.load_df(path)
            n = len(df)
            true = df["observed_eta_s"].to_numpy(float)
            dist = df["dist_remaining_m"].to_numpy(float)
            for mode, dr in [("eval", False), ("dropout", True)]:
                p = C.a3_predict(path, n, ck, dropout=dr)
                pb = C.pinball(p, true, dist)
                ae = np.abs(p - np.clip(true, 1, 7200))
                loss[k][f"{sname}/{mode}"] = {"n": n, "pinball": float(pb.mean()), "mae": float(ae.mean()),
                                              "pinball_by_dist": {}, "mae_by_dist": {}}
                for lab, lo, hi in [("<500 m", 0, 500), ("0,5-2 km", 500, 2000), ("2-5 km", 2000, 5000),
                                    ("5+ km", 5000, 1e9)]:
                    m = (dist >= lo) & (dist < hi)
                    loss[k][f"{sname}/{mode}"]["pinball_by_dist"][lab] = float(pb[m].mean())
                    loss[k][f"{sname}/{mode}"]["mae_by_dist"][lab] = float(ae[m].mean())
                if mode == "eval" and k == "A3-K32":
                    # por mes (¿estacionalidad?) y composición
                    ts = df["ts_p"].to_numpy(float)
                    month = np.array([time.strftime("%Y-%m", time.gmtime(x)) for x in ts])
                    loss[k][f"{sname}/eval"]["pinball_by_month"] = {
                        mm: [float(pb[month == mm].mean()), int((month == mm).sum())] for mm in sorted(set(month))}
        print(k, {a: round(b["pinball"], 1) for a, b in loss[k].items()}, f"{time.time()-t0:.0f}s")

    comp = {}
    for sname, path in [("train", nat_tr), ("val", nat_va)]:
        df = C.load_df(path)
        dist = df["dist_remaining_m"].to_numpy(float)
        true = df["observed_eta_s"].to_numpy(float)
        comp[sname] = {"n": len(df), "mean_eta_s": float(np.clip(true, 1, 7200).mean()),
                       "mean_dist_km": float(dist.mean() / 1000),
                       "share_dist": {lab: float(((dist >= lo) & (dist < hi)).mean())
                                      for lab, lo, hi in [("<500 m", 0, 500), ("0,5-2 km", 500, 2000),
                                                          ("2-5 km", 2000, 5000), ("5+ km", 5000, 1e9)]},
                       "mean_speed_ms": float((dist / np.clip(true, 1, 7200)).mean())}
    # A1 (una tabla, sin dropout) sobre las mismas muestras naturales: aísla el efecto del período
    loss["A1"] = {}
    for sname, path in [("train", nat_tr), ("val", nat_va)]:
        df = C.load_df(path)
        true = df["observed_eta_s"].to_numpy(float)
        dist = df["dist_remaining_m"].to_numpy(float)
        p = C.predict_a1(df, a1)
        loss["A1"][sname] = {"n": len(df), "pinball": float(C.pinball(p, true, dist).mean()),
                             "mae": float(np.abs(p - np.clip(true, 1, 7200)).mean())}
    print("A1", loss["A1"])
    hist = json.load(open(C.REPO_ROOT / "data/ml/v2_39_k32/models/eta_a3_metrics.json"))["history"]
    log = {"k32_best_epoch_train_loss": hist[15]["train_mae_s"], "k32_best_epoch_val_loss": hist[15]["val_mae_s"]}
    res = {"metrics": out, "loss": loss, "composition": comp, "log": log}
    with open(C.DIAG / "d1_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    (C.DIAG / "d1_tables.md").write_text("\n\n".join(md), encoding="utf-8")
    print(json.dumps({"composition": comp, "log": log}, indent=1))
    print(f"listo {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
