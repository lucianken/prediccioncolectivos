"""
D2: ¿dónde pierde el A3 contra A1 en la línea 39? Desglose por recorrido, sentido, posición, hora, más los tests
de las tres hipótesis (H-representación, H-identidad, H-pérdida). Solo inferencia/estadística sobre las
predicciones guardadas por d1 (diag/pred_*.npz); no entrena nada.

  PYTHONPATH=. python -m prediccion.v2.diag.d2_breakdown   (después de d1_train_vs_val)
"""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from prediccion.v2.diag import common as C

COL = {"A1": "#2a6fbb", "A3": "#d55e00", "obs": "#333333"}
SETS = {"train": ("train_sample_39.parquet", "pred_train_39.npz"), "eval": ("eval_seen_39.parquet", "pred_eval_39.npz")}
DIST_B = [("<500 m", 0, 500), ("0,5-2 km", 500, 2000), ("2-5 km", 2000, 5000), ("5+ km", 5000, 1e9)]
OUT = {}
MD = []


def _to_md(self, index=False, **kw):
    """to_markdown sin depender de tabulate."""
    d = self.reset_index() if index else self
    cols = [str(c) for c in d.columns]
    f = lambda v: f"{v:.3g}" if isinstance(v, float) and abs(v) < 1 else (f"{v:.1f}" if isinstance(v, float) else str(v))  # noqa: E731
    rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    rows += ["| " + " | ".join(f(v) for v in r) + " |" for r in d.itertuples(index=False)]
    return chr(10).join(rows)


pd.DataFrame.to_markdown = _to_md


def load(setname):
    pq, npz = SETS[setname]
    df = C.load_df(C.DIAG / pq)
    P = np.load(C.DIAG / npz)
    meta = C.shapes_meta()
    df["sid"] = df["shape_id"].astype(str)
    df["sentido"] = df["sid"].map(lambda s: meta[s]["sentido"].split()[0])
    df["short"] = df["sid"].map(lambda s: meta[s]["short"])
    df["hband"] = C.hour_band(C._hours(df))
    df["rem"] = df["dist_remaining_m"]
    df["true"] = df["observed_eta_s"]
    df["tgt"] = df["dist_along_m"] + df["rem"]
    df["a1"] = P["A1"]; df["a3"] = P["A3-K32"]; df["a3b"] = P["A3-K64"]
    for k in ("a1", "a3", "a3b"):
        df["ae_" + k] = (df[k] - df["true"]).abs()
        df["e_" + k] = df[k] - df["true"]
    df["d"] = df["ae_a3"] - df["ae_a1"]   # >0: A1 mejor
    return df


def agg(g):
    return pd.Series({"n": len(g), "MAE A1": g.ae_a1.mean(), "MAE A3": g.ae_a3.mean(), "MAE A3-K64": g.ae_a3b.mean(),
                      "Δ (A3-A1)": g.d.mean(), "ep Δ": g.d.std() / np.sqrt(max(len(g), 1)),
                      "A3 mejor %": 100 * (g.d < 0).mean(), "sesgo A1": g.e_a1.mean(), "sesgo A3": g.e_a3.mean()})


def table(df, by, title, setname):
    t = df.groupby(by, observed=True).apply(agg, include_groups=False).round(1)
    tot = df.d.sum()
    t["% del exceso total"] = (100 * df.groupby(by, observed=True).d.sum() / tot).round(0)
    MD.append(f"**{title} — {setname}**\n\n" + t.reset_index().to_markdown(index=False) + "\n")
    return t


def km_bins(x, cap=16):
    return np.minimum((x // 1000).astype(int), cap)


def divergence_info():
    from scipy.spatial import cKDTree
    with open(C.SHAPES_39, encoding="utf-8") as f:
        sh = {str(r["shapeId"]): np.array(r["points"], float) for r in json.load(f)["ramales"]}
    meta = C.shapes_meta()

    def xy(p):  # metros locales
        return np.c_[(p[:, 1] + 58.45) * 111320 * np.cos(np.radians(-34.6)), (p[:, 0] + 34.6) * 110540]
    XY = {k: xy(v) for k, v in sh.items()}
    cum = {k: np.r_[0, np.cumsum(np.hypot(*np.diff(v, axis=0).T))] for k, v in XY.items()}
    res = {}
    for k in XY:
        s = np.arange(0, cum[k][-1], 100.0)
        idx = np.searchsorted(cum[k], s).clip(0, len(cum[k]) - 1)
        pts = XY[k][idx]
        sib = [j for j in XY if j != k and meta[j]["sentido"] == meta[k]["sentido"]]
        d = np.max([cKDTree(XY[j]).query(pts)[0] for j in sib], axis=0)
        res[k] = {"s": s, "dmax_sib": d, "L": cum[k][-1]}

    def at(k, f):
        i = np.searchsorted(cum[k], f * cum[k][-1]).clip(0, len(cum[k]) - 1)
        return XY[k][i]
    f = np.linspace(0.02, 0.98, 49)
    same, opp = [], []
    for a in XY:
        for b in XY:
            if a >= b:
                continue
            dd = np.hypot(*(at(a, f) - at(b, f)).T)
            (same if meta[a]["sentido"] == meta[b]["sentido"] else opp).append(dd)
    same, opp = np.concatenate(same), np.concatenate(opp)
    info = {"same_dir_place_mismatch_m": [float(np.median(same)), float(np.percentile(same, 90))],
            "opp_dir_place_mismatch_m": [float(np.median(opp)), float(np.percentile(opp, 90))]}
    return res, info


def r2(y, groups):
    g = pd.Series(y, index=groups.index).groupby(groups).transform("mean")
    return 1 - ((y - g) ** 2).sum() / ((y - y.mean()) ** 2).sum(), groups.nunique()


def main():
    C.DIAG.mkdir(parents=True, exist_ok=True)
    meta = C.shapes_meta()
    div, div_info = divergence_info()
    OUT["geom"] = div_info
    MD.append("**Recorridos de la 39**\n\n" + pd.DataFrame(
        [{"shape_id": k, "shortName": v["short"], "nombre": v["name"], "sentido": v["sentido"],
          "largo m": round(div[k]["L"])} for k, v in meta.items()]).to_markdown(index=False) + "\n")
    MD.append(f"Desfase físico entre dos recorridos a igual fracción de largo: mismo sentido mediana "
              f"{div_info['same_dir_place_mismatch_m'][0]:.0f} m (P90 {div_info['same_dir_place_mismatch_m'][1]:.0f}); "
              f"sentido opuesto mediana {div_info['opp_dir_place_mismatch_m'][0]:.0f} m (P90 {div_info['opp_dir_place_mismatch_m'][1]:.0f}).\n")

    from prediccion.models.a1_baseline import A1Baseline
    a1m = A1Baseline.load(str(C.A1_PKL))
    with open(C.V2 / "shape_lengths.json", encoding="utf-8") as f:
        lengths = json.load(f)

    D = {s: load(s) for s in SETS}
    for s, df in D.items():
        MD.append(f"\n## Conjunto: {s} (n={len(df)})\n")
        table(df, "sid", "Por shape_id", s)
        table(df, "sentido", "Por sentido", s)
        table(df, "hband", "Por franja horaria", s)
        df["bin_veh"] = km_bins(df.dist_along_m)
        df["bin_tgt"] = km_bins(df.tgt)
        table(df, "bin_veh", "Por posición del coche (tramo de 1 km de dist_along; 16 = 16 km o más)", s)
        table(df, "bin_tgt", "Por posición del punto objetivo (tramo de 1 km)", s)
        df["dbk"] = pd.cut(df.rem, [0, 500, 2000, 5000, 1e9], labels=[d[0] for d in DIST_B], right=False)
        table(df, "dbk", "Por distancia restante", s)
        OUT[f"{s}_contrib_dist"] = {k: float(v) for k, v in (df.groupby("dbk", observed=True).d.sum() / len(df)).items()}
        cell = df.groupby(["sid", "bin_veh"]).d.agg(["sum", "count"])
        cell = cell[cell["count"] >= 20].sort_values("sum", ascending=False)
        pos = cell[cell["sum"] > 0]["sum"].sum()
        top = int(np.ceil(0.2 * len(cell)))
        OUT[f"{s}_concentration"] = {"cells": len(cell), "cells_A1_better": int((cell["sum"] > 0).sum()),
                                     "share_of_A1_advantage_in_top20pct_cells": float(cell["sum"].iloc[:top].clip(lower=0).sum() / pos)}

    # ── gráficos MAE por tramo ───────────────────────────────────────────────────────────────────────────────────
    df = D["train"]
    order = sorted(df.sid.unique(), key=lambda s: (meta[s]["sentido"], s))
    fig, axs = plt.subplots(2, 3, figsize=(15, 7), sharey=True)
    for ax, sid in zip(axs.ravel(), order):
        g = df[df.sid == sid]
        t = g.groupby("bin_veh")[["ae_a1", "ae_a3"]].mean()
        ax.plot(t.index, t.ae_a1, color=COL["A1"], lw=2, label="A1")
        ax.plot(t.index, t.ae_a3, color=COL["A3"], lw=2, label="A3-K32")
        ax.set_title(f"{meta[sid]['short']} {meta[sid]['sentido'].split()[0]} ({sid})", fontsize=10)
        ax.set_xlabel("posición del coche (km)")
        ax.grid(alpha=.2)
    axs[0, 0].set_ylabel("MAE (s)")
    axs[1, 0].set_ylabel("MAE (s)")
    axs[0, 0].legend()
    fig.suptitle("MAE por tramo de 1 km del coche, muestra de train (100k, estratificada por ETA)")
    fig.tight_layout()
    fig.savefig(C.DIAG / "d2_mae_por_tramo_train.png", dpi=110)
    plt.close(fig)

    fig, axs = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, (setn, col, ttl) in zip(axs, [("eval", "bin_veh", "eval_seen 39: tramo del coche"),
                                          ("eval", "bin_tgt", "eval_seen 39: tramo del objetivo"),
                                          ("train", "bin_tgt", "train: tramo del objetivo")]):
        t = D[setn].groupby(col)[["ae_a1", "ae_a3"]].mean()
        ax.plot(t.index, t.ae_a1, color=COL["A1"], lw=2, label="A1")
        ax.plot(t.index, t.ae_a3, color=COL["A3"], lw=2, label="A3-K32")
        ax.set_title(ttl, fontsize=10)
        ax.set_xlabel("km")
        ax.grid(alpha=.2)
    axs[0].set_ylabel("MAE (s)")
    axs[0].legend()
    fig.tight_layout()
    fig.savefig(C.DIAG / "d2_mae_por_tramo_agregado.png", dpi=110)
    plt.close(fig)

    # ── velocidad implícita vs observada (consultas de 1-3 km: fuera de la zona con q>0,5) ───────────────────────
    sub = df[(df.rem >= 1000) & (df.rem <= 3000)].copy()
    sub["mid"] = km_bins(sub.dist_along_m + sub.rem / 2)
    fig, axs = plt.subplots(2, 3, figsize=(15, 7), sharey=True)
    rows = []
    for ax, sid in zip(axs.ravel(), order):
        g = sub[sub.sid == sid]
        t = g.groupby("mid").apply(lambda h: pd.Series({"n": len(h), "obs": h.rem.sum() / h.true.sum(),
                                                       "A1": h.rem.sum() / h.a1.sum(), "A3": h.rem.sum() / h.a3.sum()}),
                                   include_groups=False)
        t = t[t.n >= 30]
        ax.plot(t.index, t.obs * 3.6, color=COL["obs"], lw=2, ls="--", label="observada")
        ax.plot(t.index, t.A1 * 3.6, color=COL["A1"], lw=2, label="A1")
        ax.plot(t.index, t.A3 * 3.6, color=COL["A3"], lw=2, label="A3-K32")
        ax.set_title(f"{meta[sid]['short']} {meta[sid]['sentido'].split()[0]} ({sid})", fontsize=10)
        ax.grid(alpha=.2)
        ax.set_xlabel("punto medio de la consulta (km)")
        sd = lambda a, b: 3.6 * np.sqrt((((a - a.mean()) - (b - b.mean())) ** 2).mean())  # noqa: E731
        rows.append({"shape_id": sid, "bins": len(t),
                     "corr A1": np.corrcoef(t.obs, t.A1)[0, 1], "corr A3": np.corrcoef(t.obs, t.A3)[0, 1],
                     "std A1/obs": t.A1.std() / t.obs.std(), "std A3/obs": t.A3.std() / t.obs.std(),
                     "RMSE A1 (km/h)": 3.6 * np.sqrt(((t.A1 - t.obs) ** 2).mean()),
                     "RMSE A3 (km/h)": 3.6 * np.sqrt(((t.A3 - t.obs) ** 2).mean()),
                     "RMSE A1 sin nivel": sd(t.A1, t.obs), "RMSE A3 sin nivel": sd(t.A3, t.obs)})
    axs[0, 0].set_ylabel("velocidad media (km/h)")
    axs[1, 0].set_ylabel("velocidad media (km/h)")
    axs[0, 0].legend()
    fig.suptitle("Velocidad implícita (Σdist/Σeta) por tramo, consultas de 1-3 km, muestra de train")
    fig.tight_layout()
    fig.savefig(C.DIAG / "d2_velocidad_implicita.png", dpi=110)
    plt.close(fig)
    pt = pd.DataFrame(rows).round(2)
    MD.append("**Perfil de velocidad por tramo (consultas de 1-3 km, train)**\n\n" + pt.to_markdown(index=False) + "\n")
    OUT["profile"] = {"mean_corr_A1": float(pt["corr A1"].mean()), "mean_corr_A3": float(pt["corr A3"].mean()),
                      "mean_std_ratio_A1": float(pt["std A1/obs"].mean()), "mean_std_ratio_A3": float(pt["std A3/obs"].mean()),
                      "mean_rmse_nolevel_A1": float(pt["RMSE A1 sin nivel"].mean()),
                      "mean_rmse_nolevel_A3": float(pt["RMSE A3 sin nivel"].mean())}

    # ── H-identidad ─────────────────────────────────────────────────────────────────────────────────────────────
    y = np.log(sub.rem / sub.true)
    sub["frac"] = ((sub.dist_along_m + sub.rem / 2) / sub.sid.map(lengths) * 20).astype(int).clip(0, 19)
    fs = sub.frac.astype(str)
    rr = {"fracción (20 bins)": r2(y, fs),
          "fracción x sentido": r2(y, fs + sub.sentido),
          "shape x tramo 1 km": r2(y, sub.sid + "_" + sub["mid"].astype(str)),
          "sentido x tramo 1 km": r2(y, sub.sentido + "_" + sub["mid"].astype(str)),
          "fracción x franja horaria": r2(y, fs + sub.hband),
          "fracción x sentido x franja": r2(y, fs + sub.sentido + sub.hband),
          "shape x tramo x franja": r2(y, sub.sid + "_" + sub["mid"].astype(str) + sub.hband)}
    r2t = pd.DataFrame([{"agrupación": k, "R² de log-velocidad (en muestra)": round(v[0], 3), "celdas": v[1]}
                        for k, v in rr.items()])
    MD.append("**Estructura de la velocidad (consultas 1-3 km, train)**\n\n" + r2t.to_markdown(index=False) + "\n")
    OUT["r2"] = {k: [float(v[0]), int(v[1])] for k, v in rr.items()}

    rat = {}
    for m in ("a1", "a3"):
        ts = {}
        for sen, g in sub.groupby("sentido"):
            ts[sen] = g.groupby("frac").apply(lambda h: h.true.sum() / h[m].sum(), include_groups=False)  # v_modelo/v_obs
        j = pd.concat(ts, axis=1).dropna()
        rat[m] = float(np.corrcoef(np.log(j.iloc[:, 0]), np.log(j.iloc[:, 1]))[0, 1])
        rat[m + "_std_log_ratio"] = float(np.log(j).stack().std())
    OUT["ida_vuelta_corr_error_nivel"] = rat

    hours = C._hours(df)
    dows = df["dow"].to_numpy().astype(int)
    d0 = df.dist_along_m.to_numpy()
    d1 = d0 + df.rem.to_numpy()
    L = df.sid.map(lengths).to_numpy()
    sids = list(meta)
    sen_arr = df.sid.map(lambda s: meta[s]["sentido"]).to_numpy()
    res = {"misma identidad (A1 normal)": float(df.ae_a1.mean())}
    for label, same in [("otro recorrido, mismo sentido (igual fracción)", True),
                        ("recorrido de sentido opuesto (igual fracción)", False)]:
        maes = []
        for alt in sids:
            msk = ((sen_arr == meta[alt]["sentido"]) == same) & (df.sid.to_numpy() != alt)
            idx = np.flatnonzero(msk)[:6000]
            if len(idx) == 0:
                continue
            La = lengths[alt]
            p = np.array([a1m.predict_direct(alt, d0[i] / L[i] * La, d1[i] / L[i] * La, int(hours[i]), int(dows[i]))[0]
                          for i in idx])
            maes.append(np.abs(p - df.true.to_numpy()[idx]).mean())
        res[label] = float(np.mean(maes))
    OUT["a1_identity_ablation_mae_train"] = res
    MD.append("**Ablación de identidad en A1 (train; A1 consultado con otro recorrido en la misma fracción)**\n\n" +
              pd.DataFrame([{"A1 consultado con": k, "MAE (s)": round(v, 1)} for k, v in res.items()] +
                           [{"A1 consultado con": "A3-K32 (referencia)", "MAE (s)": round(df.ae_a3.mean(), 1)}]
                           ).to_markdown(index=False) + "\n")

    rows = []
    for sid, g in df.groupby("sid"):
        dv = div[sid]
        i = np.clip((g.dist_along_m / 100).astype(int).to_numpy(), 0, len(dv["s"]) - 1)
        rows.append(g.assign(zona=np.where(dv["dmax_sib"][i] > 150, "separado (>150 m de algún hermano)", "compartido")))
    z = pd.concat(rows)
    table(z, "zona", "Por zona del coche: tramo compartido vs separado entre recorridos del mismo sentido", "train")
    OUT["zona_pct_separado"] = float((z.zona != "compartido").mean())

    # ── H-representación: baseline plano (nivel por hora, sin posición) ─────────────────────────────────────────
    def flat(df_):
        h = C._hours(df_)
        out = np.empty(len(df_))
        for i, (rid, hh, r) in enumerate(zip(df_.ramal_id, h, df_.rem)):
            v = a1m._fallback_l3.get((rid, int(hh)), a1m._fallback_global.get(rid, 7.0))
            out[i] = r / max(v, 0.5)
        return out
    cap = {}
    for s, d_ in D.items():
        d_["flat"] = flat(d_)
        d_["ae_flat"] = (d_.flat - d_.true).abs()
        cap[s] = {"MAE plano": float(d_.ae_flat.mean()), "MAE A1": float(d_.ae_a1.mean()), "MAE A3": float(d_.ae_a3.mean())}
        cap[s]["% de la ganancia de A1 sobre el plano que captura A3"] = float(
            100 * (cap[s]["MAE plano"] - cap[s]["MAE A3"]) / (cap[s]["MAE plano"] - cap[s]["MAE A1"]))
        r = np.log(d_.a1 / d_.flat)
        d_["score"] = pd.cut(np.abs(r), [0, .1, .2, .35, .6, 10], labels=["<0,1", "0,1-0,2", "0,2-0,35", "0,35-0,6", ">0,6"])
        t = d_.groupby("score", observed=True)[["ae_flat", "ae_a1", "ae_a3"]].mean().round(1)
        t.insert(0, "n", d_.groupby("score", observed=True).size())
        MD.append(f"**MAE según cuánto cambia el perfil posicional el ETA (|ln(ETA_A1/ETA_plano)|) — {s}**\n\n" +
                  t.reset_index().to_markdown(index=False) + "\n")
    OUT["capture"] = cap
    MD.append("**Captura de la ganancia posicional**\n\n" + pd.DataFrame(cap).T.round(1).reset_index().to_markdown(index=False) + "\n")
    fig, ax = plt.subplots(figsize=(7, 4))
    t = D["train"].groupby("score", observed=True)[["ae_flat", "ae_a1", "ae_a3"]].mean()
    x = np.arange(len(t))
    ax.plot(x, t.ae_flat, color="#888888", lw=2, label="plano (nivel hora/recorrido)")
    ax.plot(x, t.ae_a1, color=COL["A1"], lw=2, label="A1")
    ax.plot(x, t.ae_a3, color=COL["A3"], lw=2, label="A3-K32")
    ax.set_xticks(x, t.index)
    ax.set_xlabel("|ln(ETA A1 / ETA plano)|: cuánto importa el perfil")
    ax.set_ylabel("MAE (s)")
    ax.legend()
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(C.DIAG / "d2_captura_perfil.png", dpi=110)
    plt.close(fig)

    # ── H-pérdida ──────────────────────────────────────────────────────────────────────────────────────────────
    rows = []
    fit = D["train"]
    for s, d_ in D.items():
        for lab, lo, hi in [("<250 m", 0, 250), ("250-500 m", 250, 500), ("0,5-1 km", 500, 1000), ("1-2 km", 1000, 2000),
                            (">2 km", 2000, 1e9)]:
            m = (d_.rem >= lo) & (d_.rem < hi)
            mf = (fit.rem >= lo) & (fit.rem < hi)
            shift = np.median(fit.e_a3[mf])
            qm = 0.5 + 0.3 * np.clip(1 - (lo + min(hi, 2000)) / 2 / 1000, 0, 1)
            rows.append({"conjunto": s, "distancia": lab, "n": int(m.sum()), "q objetivo (centro)": round(float(qm), 2),
                         "cobertura A3": round(float((d_.true[m] <= d_.a3[m]).mean()), 2),
                         "cobertura A1": round(float((d_.true[m] <= d_.a1[m]).mean()), 2),
                         "sesgo A3": round(float(d_.e_a3[m].mean()), 1), "sesgo A1": round(float(d_.e_a1[m].mean()), 1),
                         "MAE A1": round(float(d_.ae_a1[m].mean()), 1), "MAE A3": round(float(d_.ae_a3[m].mean()), 1),
                         "MAE A3 recentrado": round(float((d_.e_a3[m] - shift).abs().mean()), 1),
                         "subest>60 A1 %": round(float(100 * ((d_.true[m] - d_.a1[m]) > 60).mean()), 1),
                         "subest>60 A3 %": round(float(100 * ((d_.true[m] - d_.a3[m]) > 60).mean()), 1)})
    MD.append("**H-pérdida: cobertura y sesgo a distancia corta (recentrado = restar la mediana del error de train de ese tramo)**\n\n" +
              pd.DataFrame(rows).to_markdown(index=False) + "\n")
    OUT["h_perdida"] = rows

    (C.DIAG / "d2_tables.md").write_text("\n".join(MD), encoding="utf-8")
    with open(C.DIAG / "d2_results.json", "w", encoding="utf-8") as f:
        json.dump(OUT, f, indent=1, ensure_ascii=False, default=float)
    keys = ["geom", "train_contrib_dist", "eval_contrib_dist", "train_concentration", "eval_concentration", "profile", "r2",
            "ida_vuelta_corr_error_nivel", "a1_identity_ablation_mae_train", "capture", "zona_pct_separado"]
    print(json.dumps({k: OUT[k] for k in keys}, indent=1))


if __name__ == "__main__":
    main()
