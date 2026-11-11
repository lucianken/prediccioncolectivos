"""
D3: fuga de información por el shape ex post (diagnóstico, no toca el pipeline).

En producción no se sabe en qué recorrido (shape_id) va el coche; el pipeline v2 lo elige DESPUÉS, con el viaje completo
(`best_shape_for_trip` en `geometry_for_trip`). A1 indexa toda su tabla por shape; A3 usa el largo del shape (normalización de
la posición y de la distancia restante) y las medianas de schedule_dev por shape. Este script mide:
  1. qué fracción de las filas de eval de la 39 tiene a P en un tramo ambiguo (>= 2 recorridos compatibles con los pings hasta P);
  2. el error de A1 y A3 en filas ambiguas / no ambiguas (y T compartido / T tras la divergencia);
  3. A1 y A3 "sin fuga": el modelo se consulta con cada candidato compatible con los pings hasta P (y que contiene a T,
     porque el usuario elige una parada y esa parada pertenece a ciertos ramales) y se promedia, o se usa el de mejor ajuste hasta P.

Compatible con P: perp < 30 m en los últimos N pings hasta P (N = 5) y avance hacia adelante (fracción de avance >= 0,5, misma
función del proyector) en los últimos 10 pings.

  PYTHONPATH=. python -m prediccion.v2.diag.d3_leak     (después de d1 y d3_extract_hist)
"""
from __future__ import annotations

import json
import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from prediccion.pipeline.projector import _forward_fraction
from prediccion.v2.diag import common as C
from prediccion.v2.diag.d2_breakdown import _to_md  # noqa: F401  (parchea DataFrame.to_markdown sin tabulate)
from prediccion.v2.shapes import DEFAULT_LINE_SHAPES_DIR, LineShapes

PERP_M = 30.0
N_WIN = 5
MD, OUT = [], {}


def md(df):
    return df.to_markdown(index=False)


def at_dist(ix, d):
    d = float(np.clip(d, 0, ix._cum_dist[-1]))
    return np.interp(d, ix._cum_dist, ix._pts[:, 0]), np.interp(d, ix._cum_dist, ix._pts[:, 1])


def candidates(h, idx, n_win=N_WIN, perp_m=PERP_M):
    """shapes compatibles con los pings hasta P (solo información disponible en tiempo real)."""
    out = []
    for sid, ix in idx.items():
        d, p = ix.project_many(h["lat"][-n_win:], h["lon"][-n_win:])
        if not np.all(p < perp_m):
            continue
        d10, p10 = ix.project_many(h["lat"][-10:], h["lon"][-10:])
        if _forward_fraction(d10, p10, 150.0) < 0.5:
            continue
        out.append(sid)
    return out


def best_fit(h, idx, among):
    """el de menor error perp. mediano sobre todo el historial hasta P (mismo criterio que best_shape_for_trip)."""
    sc = []
    for sid in among:
        d, p = idx[sid].project_many(h["lat"], h["lon"])
        sc.append((round(float(np.median(p)) / 10.0), float(np.minimum(p, 150).mean()), sid))
    return min(sc)[2]


def a3_swapped(df, cand_per_row, idx, lengths, ckpt):
    """
    A3 consultado con otro recorrido (aproximado: se recalculan posición, distancia restante, normalización y la columna
    de distancia de la trayectoria asumiendo el mismo desplazamiento en metros). Devuelve {fila: {sid: pred}}.
    """
    t = pq.read_table(C.DIAG / "eval_seen_39.parquet")
    n = len(t)
    traj = np.asarray(t["traj_flat"].combine_chunks().flatten(), dtype=np.float32).reshape(n, 30).copy()
    d0 = df.dist_along_m.to_numpy()
    Lt = df.shape_id.astype(str).map(lengths).to_numpy()
    preds: dict[int, dict] = {}
    for sid in idx:
        rows = [i for i in range(n) if sid in cand_per_row[i] and cand_per_row[i][sid] is not None]
        if not rows:
            continue
        rows = np.array(rows)
        a = np.array([cand_per_row[i][sid][0] for i in rows])
        b = np.array([cand_per_row[i][sid][1] for i in rows])
        L = lengths[sid]
        ok = (b - a >= 100) & (a / L >= 0) & (a / L <= 1)
        rows, a, b = rows[ok], a[ok], b[ok]
        if len(rows) == 0:
            continue
        # tabla modificada: todas las filas (para conservar el orden), solo las de `rows` usan el candidato
        cols = {name: t[name].to_numpy(zero_copy_only=False) for name in
                ["shape_id", "ramal_id", "dist_along_m", "dist_remaining_m", "dist_along_norm"]}
        cols = {k: v.copy() for k, v in cols.items()}
        tr = traj.copy()
        cols["shape_id"][rows] = sid
        cols["ramal_id"][rows] = sid
        cols["dist_along_m"][rows] = a
        cols["dist_remaining_m"][rows] = b - a
        cols["dist_along_norm"][rows] = a / L
        for j in range(10):
            m = (tr[rows, 3 * j] * Lt[rows] - d0[rows]) + a      # metros de la trayectoria desplazados al nuevo origen
            tr[rows, 3 * j] = np.clip(m / L, 0, 1)
        t2 = t
        for k, v in cols.items():
            t2 = t2.set_column(t2.schema.get_field_index(k), t2.schema.field(k), pa.array(v, type=t2.schema.field(k).type))
        t2 = t2.set_column(t2.schema.get_field_index("traj_flat"), t2.schema.field("traj_flat"),
                           pa.FixedSizeListArray.from_arrays(pa.array(tr.ravel(), type=pa.float32()), 30))
        tmp = C.DIAG / "_tmp_swap.parquet"
        pq.write_table(t2, str(tmp), row_group_size=100_000)
        p = C.a3_predict(tmp, n, ckpt)
        tmp.unlink()
        for i in rows:
            preds.setdefault(int(i), {})[sid] = float(p[i])
    return preds


def main():
    C.DIAG.mkdir(parents=True, exist_ok=True)
    meta = C.shapes_meta()
    shapes = LineShapes(DEFAULT_LINE_SHAPES_DIR)
    idx = shapes.indices("39")
    with open(C.V2 / "shape_lengths.json", encoding="utf-8") as f:
        lengths = json.load(f)
    df = C.load_df(C.DIAG / "eval_seen_39.parquet")
    P = np.load(C.DIAG / "pred_eval_39.npz")
    df["a1"], df["a3"] = P["A1"], P["A3-K32"]
    df["true"] = df.observed_eta_s
    df["rem"] = df.dist_remaining_m
    df["sid"] = df.shape_id.astype(str)
    hist = pickle.load(open(C.DIAG / "eval_hist_39.pkl", "rb"))
    n = len(df)
    hours = C._hours(df)
    dows = df.dow.to_numpy().astype(int)
    from prediccion.models.a1_baseline import A1Baseline
    a1m = A1Baseline.load(str(C.A1_PKL))

    # ── 1. qué shape se usa ──────────────────────────────────────────────────────────────────────────────────────
    MD.append("## 1. Qué shape usan la evaluación, A1 y A3\n\n"
              "`eval_seen` toma `shape_id` del parquet diario; ese valor sale de `process_day` -> `geometry_for_trip` -> "
              "`best_shape_for_trip(lats, lons, ...)` aplicado a **todos los puntos del viaje completo** (también los posteriores a P) y "
              "`dist_along_m`, `dist_remaining_m`, `dist_along_norm` (÷ largo de ese shape) y la trayectoria salen de proyectar el viaje sobre ese shape. "
              "A1 recibe `ramal_id` = ese shape_id (`predict_a1`, tabla indexada por `(ramal_id, tramo, hora, día)`). A3 no recibe el id, pero las "
              "medianas de `schedule_dev_norm` se buscan por `ramal_id`, y `dist_remaining_norm` / `dist_along_norm` se normalizan por el largo de ese shape. "
              "Además el segmentador geométrico corta viajes usando los shapes de la línea (fuga menor y común a todos los modelos). "
              "**Confirmado: es el shape ex post del viaje completo para A1 y A3.**\n")

    # ── 2. ambigüedad ────────────────────────────────────────────────────────────────────────────────────────────
    rows = []
    cls = np.array(["sin historial"] * n, dtype=object)
    ncand = np.zeros(n, int)
    true_in = np.zeros(n, bool)
    cand_sets, K_sets, tin = [], [], []
    for i in range(n):
        h = hist.get(i)
        if h is None:
            cand_sets.append([])
            K_sets.append([df.sid[i]])
            tin.append({})
            continue
        c = candidates(h, idx)
        cand_sets.append(c)
        true = df.sid[i]
        true_in[i] = true in c
        ncand[i] = len(c)
        d0, dT = float(df.dist_along_m[i]), float(df.dist_along_m[i] + df.rem[i])
        latT, lonT = at_dist(idx[true], dT)
        ti = {}
        for s in idx:
            dd, pp = idx[s].project_many(np.array([h["lat"][-1], latT]), np.array([h["lon"][-1], lonT]))
            ti[s] = (float(dd[0]), float(dd[1]), bool(pp[1] < PERP_M and dd[1] > dd[0]))
        tin.append(ti)
        K = [s for s in c if ti[s][2]]
        K_sets.append(K if K else [true])
        if len(c) <= 1:
            cls[i] = "no ambiguo"
        elif all(ti[s][2] for s in c):
            cls[i] = "ambiguo, T compartido"
        else:
            cls[i] = "ambiguo, T tras la divergencia"
    df["cls"], df["ncand"] = cls, ncand
    df["resuelto_por_parada"] = [len(K) == 1 and len(c) >= 2 for K, c in zip(K_sets, cand_sets)]
    amb = df.ncand >= 2
    OUT["share_ambiguous"] = float(amb.mean())
    OUT["true_in_candidates"] = float(true_in[df.cls != "sin historial"].mean())
    dist_tab = pd.DataFrame({"candidatos": df.ncand.value_counts().sort_index().index,
                             "filas": df.ncand.value_counts().sort_index().values})
    dist_tab["%"] = (100 * dist_tab["filas"] / n).round(1)
    MD.append("## 2. Filas con P en tramo ambiguo\n\n"
              f"Definición: shapes con perp < {PERP_M:.0f} m en los últimos {N_WIN} pings hasta P y avance hacia adelante. "
              f"Filas con historial recuperado: {(df.cls != 'sin historial').sum()} de {n}.\n\n" + md(dist_tab) +
              f"\n\n**Ambiguas (>= 2 candidatos): {100*amb.mean():.1f} %** de las filas. El shape ex post está entre los candidatos en "
              f"{100*OUT['true_in_candidates']:.1f} % de las filas. De las ambiguas, {100*df.resuelto_por_parada[amb].mean():.1f} % quedan resueltas "
              "por la parada objetivo (solo un candidato contiene a T).\n")
    sens = []
    for nw, pm in [(3, 30), (5, 30), (10, 30), (5, 50), (5, 15)]:
        a = np.mean([len(candidates(hist[i], idx, nw, pm)) >= 2 for i in range(n) if i in hist])
        sens.append({"N pings": nw, "perp (m)": pm, "% ambiguas": round(100 * a, 1)})
    OUT["sensitivity"] = sens
    MD.append("Sensibilidad de la definición:\n\n" + md(pd.DataFrame(sens)) + "\n")
    by_dir = df[amb].groupby("sid").size()
    MD.append("Ambiguas por shape ex post (n): " + ", ".join(f"{meta[k]['short']} {meta[k]['sentido'].split()[0]}: {v}" for k, v in by_dir.items()) + ".\n")

    # ── 3. error por clase ──────────────────────────────────────────────────────────────────────────────────────
    df["ae_a1"] = (df.a1 - df.true).abs()
    df["ae_a3"] = (df.a3 - df.true).abs()
    df["d"] = df.ae_a3 - df.ae_a1
    g = df.groupby("cls").apply(lambda x: pd.Series({"n": len(x), "MAE A1": x.ae_a1.mean(), "MAE A3": x.ae_a3.mean(),
                                                    "Δ (A3-A1)": x.d.mean(), "ep Δ": x.d.std() / np.sqrt(len(x)),
                                                    "sesgo A1": (x.a1 - x.true).mean(), "sesgo A3": (x.a3 - x.true).mean(),
                                                    "rem media (km)": x.rem.mean() / 1000}), include_groups=False).round(1)
    g.loc["TOTAL"] = [n, df.ae_a1.mean(), df.ae_a3.mean(), df.d.mean(), df.d.std() / np.sqrt(n), (df.a1 - df.true).mean(),
                      (df.a3 - df.true).mean(), df.rem.mean() / 1000]
    OUT["by_class"] = g.reset_index().round(2).to_dict("records")
    MD.append("## 3. Error por clase de ambigüedad (A1 y A3 con shape ex post)\n\n" + md(g.round(1).reset_index()) + "\n")
    df["amb2"] = np.where(amb, "ambiguo", "no ambiguo")
    g2 = df.groupby(["amb2", pd.cut(df.rem, [0, 2000, 5000, 1e9], labels=["<2 km", "2-5 km", "5+ km"])], observed=True).apply(
        lambda x: pd.Series({"n": len(x), "MAE A1": x.ae_a1.mean(), "MAE A3": x.ae_a3.mean(), "Δ": x.d.mean()}), include_groups=False).round(1)
    MD.append("Mismo corte controlando por distancia restante:\n\n" + md(g2.reset_index()) + "\n")

    # ── 4. A1 y A3 sin fuga ─────────────────────────────────────────────────────────────────────────────────────
    cand_args = []   # por fila: {sid: (d0_s, d1_s)}
    for i in range(n):
        if i not in hist:
            cand_args.append({})
            continue
        d = {}
        for s in K_sets[i]:
            if s == df.sid[i]:
                d[s] = (float(df.dist_along_m[i]), float(df.dist_along_m[i] + df.rem[i]))
            elif s in tin[i]:
                d[s] = (tin[i][s][0], tin[i][s][1])
        cand_args.append(d)
    a1_all = np.full(n, np.nan)
    a1_best = np.full(n, np.nan)
    a1_mean = np.full(n, np.nan)
    for i in range(n):
        args = cand_args[i]
        if not args:
            a1_mean[i] = a1_best[i] = df.a1[i]
            continue
        pr = {s: a1m.predict_direct(s, a, b, int(hours[i]), int(dows[i]))[0] for s, (a, b) in args.items()
              if b - a > 0}
        if not pr:
            a1_mean[i] = a1_best[i] = df.a1[i]
            continue
        a1_mean[i] = np.mean(list(pr.values()))
        bs = best_fit(hist[i], idx, list(pr)) if len(pr) > 1 else next(iter(pr))
        a1_best[i] = pr[bs]
    df["a1_mean"], df["a1_best"] = a1_mean, a1_best
    # A3 (aproximado) con los mismos candidatos
    cand_for_a3 = [{s: v for s, v in cand_args[i].items()} for i in range(n)]
    swapped = a3_swapped(df, cand_for_a3, idx, lengths, C.A3_CKPTS["A3-K32"])
    a3_mean = np.array([np.mean(list(swapped[i].values())) if i in swapped and len(swapped[i]) > 0 else df.a3[i] for i in range(n)])
    a3_best = np.array([swapped[i][best_fit(hist[i], idx, list(swapped[i]))] if i in swapped and i in hist and len(swapped[i]) > 1
                        else (next(iter(swapped[i].values())) if i in swapped and len(swapped[i]) == 1 else df.a3[i]) for i in range(n)])
    df["a3_mean"], df["a3_best"] = a3_mean, a3_best
    for k in ("a1_mean", "a1_best", "a3_mean", "a3_best"):
        df["ae_" + k] = (df[k] - df.true).abs()
    df["multi"] = [len(a) >= 2 for a in cand_args]   # filas donde el candidato importa (>= 2 candidatos que contienen P y T)

    def row(x, lab):
        return {"filas": lab, "n": len(x), "A1 ex post": x.ae_a1.mean(), "A1 sin fuga (prom.)": x.ae_a1_mean.mean(),
                "A1 sin fuga (mejor ajuste)": x.ae_a1_best.mean(), "A3 ex post": x.ae_a3.mean(),
                "A3 sin fuga (prom., aprox.)": x.ae_a3_mean.mean(), "A3 sin fuga (mejor ajuste, aprox.)": x.ae_a3_best.mean()}
    tab = [row(df, "todas"), row(df[df.multi], ">= 2 candidatos con P y T"), row(df[~df.multi], "resto")]
    for c in ["no ambiguo", "ambiguo, T compartido", "ambiguo, T tras la divergencia"]:
        tab.append(row(df[df.cls == c], c))
    t4 = pd.DataFrame(tab)
    OUT["leak_table"] = t4.round(2).to_dict("records")
    MD.append("## 4. Modelos sin fuga (diagnóstico)\n\nA1 se consulta con cada candidato compatible con los pings hasta P que además contiene al punto objetivo T, "
              "y se promedia o se elige el de mejor ajuste hasta P (menor perp mediano en el historial). A3: misma idea pero la sustitución es aproximada "
              "(se recalculan posición, distancia restante y la columna de distancia de la trayectoria; el resto de las entradas queda igual).\n\n" + md(t4.round(1)) + "\n")
    # pareado A1 sin fuga vs A3
    for lab, m in [("todas", np.ones(n, bool)), ("ambiguas (>=2 cand. con P y T)", df.multi.to_numpy())]:
        x = df[m]
        OUT.setdefault("paired", {})[lab] = {
            "n": int(m.sum()),
            "A1_expost_minus_A1_lf_mean": float((x.ae_a1 - x.ae_a1_mean).mean()),
            "A3_minus_A1_expost": float((x.ae_a3 - x.ae_a1).mean()),
            "A3_minus_A1_leakfree_mean": float((x.ae_a3 - x.ae_a1_mean).mean()),
            "A3lf_minus_A1lf_mean": float((x.ae_a3_mean - x.ae_a1_mean).mean()),
            "se_A3_minus_A1_leakfree_mean": float((x.ae_a3 - x.ae_a1_mean).std() / np.sqrt(len(x)))}
    MD.append("Pareado (diferencia de MAE en s):\n\n" + md(pd.DataFrame(OUT["paired"]).T.round(2).reset_index()) + "\n")

    # gráfico
    fig, ax = plt.subplots(figsize=(9, 4.2))
    names = [r["filas"] for r in tab]
    x = np.arange(len(names))
    w = 0.2
    for j, (k, lab, col) in enumerate([("A1 ex post", "A1 ex post", "#2a6fbb"), ("A1 sin fuga (prom.)", "A1 sin fuga (prom.)", "#8fb8e8"),
                                       ("A3 ex post", "A3 ex post", "#d55e00"), ("A3 sin fuga (prom., aprox.)", "A3 sin fuga (aprox.)", "#f0a878")]):
        ax.bar(x + (j - 1.5) * w, [r[k] for r in tab], w, label=lab, color=col)
    ax.set_xticks(x, [f"{a}\n(n={r['n']})" for a, r in zip(names, tab)], fontsize=7)
    ax.set_ylabel("MAE (s)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=.2)
    ax.set_title("eval_seen 39: MAE con shape ex post vs sin fuga", fontsize=10)
    fig.tight_layout()
    fig.savefig(C.DIAG / "d3_fuga.png", dpi=110)
    plt.close(fig)

    (C.DIAG / "d3_tables.md").write_text("\n".join(MD), encoding="utf-8")
    with open(C.DIAG / "d3_results.json", "w", encoding="utf-8") as f:
        json.dump(OUT, f, indent=1, ensure_ascii=False, default=float)
    print("\n".join(MD))


if __name__ == "__main__":
    main()
