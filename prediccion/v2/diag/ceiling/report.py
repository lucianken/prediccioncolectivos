"""
Junta las filas de ceiling_days/*.parquet con la vara (eval) y arma tablas + PNG del informe
data/ml/v2/diag/TECHO_TRANSITO.md. La narrativa (resumen/conclusión) sale de ceiling/narrativa.md.

  PYTHONPATH=. python -m prediccion.v2.diag.ceiling.report
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.eval import compute_metrics, predict_a1, load_eval_df, ETA_BUCKETS_S, DIST_BUCKETS_M
from prediccion.models.a1_baseline import A1Baseline
from prediccion.v2.diag.ceiling import common as C
from prediccion.v2.diag.ceiling.run_ceiling import NCLS

OUT = C.DIAG / "TECHO_TRANSITO.md"
HOUR_BANDS = [("0-5", 0, 6), ("6-9", 6, 10), ("10-15", 10, 16), ("16-19", 16, 20), ("20-23", 20, 24)]
METHODS = [
    ("a1", "A1 (vara)"), ("eta_a1sim", "A1 simulado"),
    ("eta_or_raw", "Oraculo crudo"), ("eta_or_adj", "Oraculo ajustado por detenidos"),
    ("eta_or_mix", "Oraculo mezcla con A1"), ("eta_or_rel", "Oraculo relativo (A1 x obs/tipica)"),
    ("eta_or_relmix", "Oraculo relativo + mezcla"),
    ("eta_re_raw", "Realista crudo"), ("eta_re_adj", "Realista ajustado por detenidos"),
    ("eta_re_mix", "Realista mezcla con A1"), ("eta_re_rel", "Realista relativo"),
    ("eta_re_relmix", "Realista relativo + mezcla"),
]


def load() -> pd.DataFrame:
    df = C.load_eval_subset()
    parts = [pd.read_parquet(p) for p in sorted((C.DIAG / "ceiling_days").glob("ceiling_*.parquet"))]
    df = df.merge(pd.concat(parts, ignore_index=True), on="row_id", how="inner")
    df["a1"] = predict_a1(df, A1Baseline.load(C.A1_PKL))
    df["true"] = df.observed_eta_s
    df["dist"] = df.dist_remaining_m
    return df


def fmt(x, nd=1):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def method_table(df, cols_labels):
    txt = []
    for g in ("train", "control"):
        s = df[df.group == g]
        rows = []
        for col, lab in cols_labels:
            m = compute_metrics(s[col].to_numpy(), s.true.to_numpy(), s.dist.to_numpy())
            gl = m["global"]
            be = [fmt(m["by_eta"][k]["mae"]) for k, *_ in ETA_BUCKETS_S]
            under = [fmt(m["by_eta"][k]["pct_under_60s"]) for k, *_ in ETA_BUCKETS_S[:2]]
            rows.append([lab, *be, fmt(gl["mae"]), fmt(gl["p50"]), fmt(gl["p90"]), fmt(gl["bias"]),
                         fmt(gl["pct_under_60s"]), *under])
        txt.append(f"**{g}** (n={len(s)})\n\n" + md_table(
            ["metodo", "MAE 0-5", "5-10", "10-20", "20+", "MAE global", "P50", "P90", "sesgo",
             "subest.>60s %", "subest. 0-5 %", "subest. 5-10 %"], rows))
    return "\n".join(txt)


def dist_table(df, cols_labels):
    txt = []
    for g in ("train", "control"):
        s = df[df.group == g]
        rows = []
        for col, lab in cols_labels:
            m = compute_metrics(s[col].to_numpy(), s.true.to_numpy(), s.dist.to_numpy())
            rows.append([lab, *[fmt(m["by_dist"][k]["mae"]) for k, *_ in DIST_BUCKETS_M]])
        m0 = compute_metrics(s.a1.to_numpy(), s.true.to_numpy(), s.dist.to_numpy())
        n = [m0["by_dist"][k]["n"] for k, *_ in DIST_BUCKETS_M]
        txt.append(f"**{g}** (n por bucket: {n})\n\n" + md_table(["metodo"] + [k for k, *_ in DIST_BUCKETS_M], rows))
    return "\n".join(txt)


def a1_full_check() -> str:
    p = C.V2 / "eval" / "a1_a1_v1794415690_seen_20261111.json"
    d = load_eval_df(C.V2 / "eval" / "eval_seen.parquet")
    pred = predict_a1(d, A1Baseline.load(C.A1_PKL))
    m = compute_metrics(pred, d.observed_eta_s.to_numpy(), d.dist_remaining_m.to_numpy())
    ref = json.loads(p.read_text(encoding="utf-8"))["metrics"]
    s = "Reproduccion sobre todo `eval_seen` (100k filas), MAE por bucket de ETA " + " / ".join(
        fmt(m["by_eta"][k]["mae"]) for k, *_ in ETA_BUCKETS_S)
    s += " vs vara guardada " + " / ".join(fmt(ref["by_eta"][k]["mae"]) for k, *_ in ETA_BUCKETS_S)
    s += f"; global {fmt(m['global']['mae'])} vs {fmt(ref['global']['mae'])}.\n"
    return s


def main():
    df = load()
    out = []
    narr = Path(__file__).with_name("narrativa.md")
    out.append(narr.read_text(encoding="utf-8") if narr.exists() else "# Techo del transito\n")

    out.append("## 1. Verificacion de A1\n")
    out.append(a1_full_check())
    for g in ("train", "control"):
        s = df[df.group == g]
        d = (s.a1 - s.eta_a1sim).abs()
        out.append(f"- {g}: A1 vara MAE {fmt((s.a1 - s.true).abs().mean())} s, sesgo {fmt((s.a1 - s.true).mean())}; "
                   f"A1 simulado paso a paso (100 m) MAE {fmt((s.eta_a1sim - s.true).abs().mean())} s, "
                   f"sesgo {fmt((s.eta_a1sim - s.true).mean())}; |vara - simulado| media {fmt(d.mean())} s, "
                   f"P50 {fmt(d.quantile(.5))}, P90 {fmt(d.quantile(.9))}, P99 {fmt(d.quantile(.99))}.")
    out.append("\nLa diferencia viene de la discretizacion: A1 recorre bloques de 500 m desde la posicion de P (no alineados "
               "a la grilla de segmentos); el simulador usa pasos de ~100 m y toma el segmento de A1 del punto medio de cada paso.\n")
    out.append("**Control:** A1 no tiene tabla para las lineas de control (nunca entraron al train), asi que cae al fallback de "
               "7 m/s en todo (RESULTADOS.md). En control, 'A1' es un naive de 7 m/s, no una tabla: la comparacion con el "
               "transito ahi mide otra cosa (el transito reemplaza a un naive, no a una tabla).\n")
    out.append("**Fuga comun:** todos los metodos usan el shape ex post que ya trae el eval (elegido con el viaje completo). Es la misma para todos.\n")

    ln = C.DIAG / "ceiling_label_noise.json"
    out.append("## 2. Ruido de etiqueta\n")
    if ln.exists():
        j = json.loads(ln.read_text(encoding="utf-8"))
        a, b = j["loo_120s"], j["estimate_60s_gap_(x1/3)"]
        out.append(f"Leave-one-out sobre {j['n']:,} tripletas de pings consecutivos (hueco total ~120 s, punto del medio "
                   f"interpolado por distancia como la etiqueta): MAE {fmt(a['mae'])} s, P50 {fmt(a['p50'])}, P90 {fmt(a['p90'])}, "
                   f"sesgo {fmt(a['bias'])} (cota superior para un hueco de 60 s). Estimacion para el hueco real de 60 s con T "
                   f"uniforme dentro del hueco (x1/3, ver docstring de `label_noise.py`): MAE ~{fmt(b['mae'])} s, "
                   f"P50 ~{fmt(b['p50'])}, P90 ~{fmt(b['p90'])}. Antecedente del plan historico: P50 ~24 s, P90 ~52 s. "
                   "Es una estimacion, no una medicion directa de la etiqueta.\n")

    out.append("## 3. Error por metodo\n")
    out.append("MAE en segundos por bucket de ETA real (0-5, 5-10, 10-20, 20+ min), global y % de subestimaciones > 60 s "
               "(pred - real < -60). Sesgo = pred - real (+ sobreestima).\n")
    out.append(method_table(df, METHODS))
    out.append("### Por distancia restante (MAE, s)\n")
    out.append(dist_table(df, METHODS))

    out.append("## 4. Exclusion del propio coche\n")
    rows = []
    for g in ("train", "control"):
        s = df[df.group == g]
        rows.append([g, fmt((s.eta_or_raw - s.true).abs().mean()), fmt((s.eta_or_approx - s.true).abs().mean()),
                     fmt((s.eta_or_raw - s.eta_or_approx).abs().mean()), fmt((s.eta_or_raw - s.eta_or_approx).mean()),
                     fmt(100 * s.cov_or.mean()), fmt(100 * s.cov_or_approx.mean())])
    out.append("Se uso la exclusion exacta (recalculada del NDJSON, un dia por vez). Coche propio identificado por "
               "(linea, shape_id, start_ts = ts_p - time_since_start) en `daily/<dia>.trips.parquet`: "
               f"{100 * (df.own_dt <= 60).mean():.1f} % de las filas casan y {100 * (df.own_n >= 1).mean():.1f} % tienen el coche "
               "propio en el NDJSON; con empates se excluyen todos los coches empatados. La tabla recomputada coincide con la "
               "diaria (celdas halladas y n iguales: 100 %).\n")
    out.append(md_table(["grupo", "MAE oraculo exacto", "MAE oraculo aprox. (sin excluir, n>=2)", "|dif| media",
                         "dif. media (exacto - aprox.)", "cobertura exacto %", "cobertura aprox. %"], rows))

    out.append("## 5. Cobertura\n")
    out.append("Cobertura = fraccion de pasos de ~100 m del camino P->T con dato observado de **otros** coches en movimiento "
               "(oraculo: ventana del paso simulado, luego +1 y -1; realista: 5 ventanas completas previas a la de t). "
               "'Una linea' = celdas recorridas solo por la linea de la fila entre las 60 de la mascara (entre parentesis, "
               "lo mismo con las 129 lineas de proyectoconsola).\n")
    df["sg_share"] = df.nsteps_single / df.nsteps
    df["sg129_share"] = df.nsteps_single129 / df.nsteps
    rows = []
    for ln_, s in df.groupby("line"):
        rows.append([ln_, s.group.iloc[0], len(s), fmt(100 * s.cov_or.mean()), fmt(100 * s.cov_re.mean()),
                     fmt(100 * s.cov_re_same.mean()), fmt(100 * s.cov_re_other.mean()), fmt(100 * s.sg_share.mean()),
                     fmt(100 * s.sg129_share.mean()), fmt(s.dist.mean() / 1000)])
    out.append("### Por linea (%)\n")
    out.append(md_table(["linea", "grupo", "n", "oraculo", "realista", "realista: misma linea", "realista: otras lineas",
                         "pasos en celda de una linea (60)", "(129)", "dist. media km"], rows))
    rows = []
    for nm, lo, hi in HOUR_BANDS:
        s = df[(df.hour >= lo) & (df.hour < hi)]
        rows.append([nm, len(s), fmt(100 * s.cov_or.mean()), fmt(100 * s.cov_re.mean()), fmt(100 * s.cov_re_same.mean()),
                     fmt(100 * s.cov_re_other.mean()), fmt(100 * s.tfrac_or.mean())])
    out.append("### Por franja horaria (%)\n")
    out.append(md_table(["hora", "n", "oraculo", "realista", "realista misma linea", "realista otras lineas",
                         "oraculo: % del tiempo en pasos con dato"], rows))
    rows = []
    for k, lo, hi in DIST_BUCKETS_M:
        s = df[(df.dist >= lo) & (df.dist < hi)]
        rows.append([k, len(s), fmt(100 * s.cov_or.mean()), fmt(100 * s.cov_re.mean()), fmt(100 * s.cov_re_same.mean()),
                     fmt(100 * s.cov_re_other.mean())])
    out.append("### Por distancia (%)\n")
    out.append(md_table(["distancia", "n", "oraculo", "realista", "realista misma linea", "realista otras lineas"], rows))
    out.append("### Distribucion de n (coches distintos por celda-ventana, otros coches) en los pasos con dato\n")
    labs = ["1", "2", "3", "4-5", "6-10", "11+"]
    rows = []
    for meth in ("or", "re"):
        for cls in ("single", "shared"):
            tot = np.array([df[f"hist_{meth}_{cls}_{b}"].sum() for b in range(NCLS)], dtype=float)
            rows.append([("oraculo" if meth == "or" else "realista (suma de 5 ventanas)") + " / " +
                         ("una linea" if cls == "single" else "compartido"), int(tot.sum())] +
                        [fmt(100 * x / max(tot.sum(), 1)) for x in tot])
    out.append(md_table(["", "pasos con dato"] + labs, rows))
    out.append("(% de los pasos con dato; el realista suma 5 ventanas, asi que su n esta inflado respecto del oraculo.)\n")
    tot_steps = df.nsteps.sum()
    out.append(f"Pasos en celdas de una sola linea: {100 * df.nsteps_single.sum() / tot_steps:.1f} % del total (60 lineas), "
               f"{100 * df.nsteps_single129.sum() / tot_steps:.1f} % con las 129.\n")

    out.append("## 6. Error segun cobertura\n")
    for g in ("train", "control"):
        s = df[df.group == g]
        rows = []
        for covcol, nm in (("cov_or", "oraculo"), ("cov_re", "realista")):
            for lo, hi in [(-0.01, 0.5), (0.5, 0.9), (0.9, 0.99), (0.99, 1.01)]:
                x = s[(s[covcol] > lo) & (s[covcol] <= hi)]
                if len(x) == 0:
                    continue
                best_o = "eta_or_adj" if nm == "oraculo" else "eta_re_adj"
                best_r = "eta_or_rel" if nm == "oraculo" else "eta_re_rel"

                def ae(c_):
                    return (x[c_] - x.true).abs().mean()
                rows.append([nm, f"({lo:.2f}, {hi:.2f}]", len(x), fmt(ae("a1")), fmt(ae(best_o)), fmt(ae(best_r)),
                             fmt(ae("a1") - ae(best_o)), fmt(ae("a1") - ae(best_r)),
                             fmt(100 * (((x[best_r] - x.true).abs()) < ((x.a1 - x.true).abs())).mean())])
        out.append(f"**{g}**\n\n" + md_table(["version", "cobertura", "n", "MAE A1", "MAE ajustado", "MAE relativo",
                                              "A1 - ajustado", "A1 - relativo", "% filas donde relativo < A1"], rows))
    out.append("(ajustado = velocidad observada en mov. x fraccion de coches en mov.; relativo = A1 x (velocidad observada / "
               "tipica de esa celda y hora, de dias de train); ver seccion 9.)\n")

    out.append("## 7. Tramos de una linea vs compartidos\n")
    out.append("Se usa el dato observado **solo** en celdas de un tipo (donde no hay dato, A1), variante relativa. "
               "'pasos %' = fraccion de pasos de ese tipo.\n")
    rows = []
    for g in ("train", "control"):
        s = df[df.group == g]
        for nm, ocol, rcol, share in (("solo celdas de una linea", "eta_or_only_single", "eta_re_only_single", s.sg_share),
                                      ("solo celdas compartidas", "eta_or_only_shared", "eta_re_only_shared", 1 - s.sg_share)):
            def mae(c_):
                return (s[c_] - s.true).abs().mean()
            rows.append([g, nm, fmt(100 * share.mean()), fmt(mae("a1")), fmt(mae(ocol)), fmt(mae("a1") - mae(ocol)),
                         fmt(mae(rcol)), fmt(mae("a1") - mae(rcol))])
    out.append(md_table(["grupo", "dato usado en", "pasos %", "MAE A1", "MAE oraculo", "ganancia oraculo", "MAE realista",
                         "ganancia realista"], rows))

    out.append("## 8. Realista: coches de la misma linea vs de otras lineas\n")
    out.append("Cobertura y error usando solo coches de los ultimos 10 min de la **misma linea** (coche propio excluido) o solo "
               "de **otras lineas** (variante relativa; el resto, A1). La linea de cada coche sale de sus viajes del dia en "
               "`trips.parquet` (60 lineas); un coche sin viajes en esas 60 lineas cuenta como 'otra linea'. Corrido sobre "
               "todo el eval (sin muestreo).\n")
    rows = []
    for g in ("train", "control"):
        s = df[df.group == g]

        def mae(c_):
            return (s[c_] - s.true).abs().mean()
        rows.append([g, len(s), fmt(100 * s.cov_re_same.mean()), fmt(100 * s.cov_re_other.mean()), fmt(mae("a1")),
                     fmt(mae("eta_re_same")), fmt(mae("a1") - mae("eta_re_same")), fmt(mae("eta_re_other")),
                     fmt(mae("a1") - mae("eta_re_other")), fmt(mae("eta_re_rel")), fmt(mae("a1") - mae("eta_re_rel"))])
    out.append(md_table(["grupo", "n", "cob. misma linea %", "cob. otras lineas %", "MAE A1", "MAE solo misma", "ganancia",
                         "MAE solo otras", "ganancia", "MAE todos", "ganancia"], rows))

    out.append("## 9. Que no explica el transito\n")
    out.append("**Variantes de velocidad.** La tabla de transito guarda la velocidad media *solo de los intervalos en movimiento* "
               "(>= 1 m/s) y `n_stopped` aparte; los tiempos de parada y dwell no estan en esa velocidad, asi que usada cruda "
               "**subestima** el tiempo (sesgo negativo). 'ajustado' multiplica por la fraccion de coches en movimiento (piso 1 "
               "m/s); 'mezcla' pondera con A1 (A1 pesa como 2 coches); 'relativo' usa A1 x (v observada / v tipica de la celda a esa "
               "hora y tipo de dia, de la tabla de dias de train; cociente acotado a [0,25; 3]) y aisla la *desviacion respecto de "
               "lo habitual* sin el sesgo de las paradas.\n")
    s = df[df.group == "train"].copy()
    s["parado_P"] = s.speed_mps < 1.0
    s["cabecera"] = s.time_since_start < 300
    rows = []
    for nm, mask in (("P en movimiento", ~s.parado_P), ("P detenido (<1 m/s)", s.parado_P),
                     ("a <5 min de la salida de cabecera", s.cabecera), ("resto", ~s.cabecera)):
        x = s[mask]
        rows.append([nm, len(x), fmt((x.a1 - x.true).abs().mean()), fmt((x.eta_or_adj - x.true).abs().mean()),
                     fmt((x.eta_or_rel - x.true).abs().mean()), fmt((x.eta_re_rel - x.true).abs().mean())])
    out.append("MAE (s), lineas de train:\n\n" + md_table(["subconjunto", "n", "A1", "oraculo ajustado", "oraculo relativo",
                                                          "realista relativo"], rows))
    rows = []
    for k, lo, hi in ETA_BUCKETS_S:
        x = s[(s.true >= lo) & (s.true < hi)]
        e = x.a1 - x.true
        rows.append([k, len(x), fmt(e.abs().mean()), fmt(e.mean()), fmt(e.abs().quantile(.9)),
                     fmt((x.eta_or_rel - x.true).abs().mean()), fmt((x.eta_or_adj - x.true).abs().mean())])
    out.append("Error de A1 por bucket (train) y el mejor oraculo:\n\n" + md_table(
        ["ETA real", "n", "MAE A1", "sesgo A1", "P90 abs. A1", "MAE oraculo relativo", "MAE oraculo ajustado"], rows))

    out.append("### Mezcla lineal optima A1 + transito\n")
    out.append("Para saber cuanto se aprovecha con un uso simple del transito, se busca el peso lambda en pred = A1 + lambda x (metodo - A1) "
               "(lambda en [0, 1.5], paso 0,05) que minimiza el MAE en los dias pares y se evalua en los dias impares (y viceversa; se promedian). "
               "lambda = 0 es A1; lambda = 1 es el metodo solo.\n")
    rows = []
    days = np.array(sorted(df.day.unique()))
    fold = df.day.map({d: i % 2 for i, d in enumerate(days)}).to_numpy()
    lam_grid = np.arange(0, 1.501, 0.05)
    for g in ("train", "control"):
        sg = df.group.to_numpy() == g
        for col, lab in (("eta_or_rel", "oraculo relativo"), ("eta_re_rel", "realista relativo"),
                         ("eta_or_adj", "oraculo ajustado"), ("eta_re_adj", "realista ajustado"),
                         ("eta_re_same", "realista solo misma linea"), ("eta_re_other", "realista solo otras lineas")):
            tot_a1 = tot_new = 0.0
            lams = []
            for f in (0, 1):
                tr = sg & (fold == f)
                te = sg & (fold != f)
                maes = [np.abs(df.a1[tr] + l * (df[col][tr] - df.a1[tr]) - df.true[tr]).mean() for l in lam_grid]
                l_best = lam_grid[int(np.argmin(maes))]
                lams.append(l_best)
                tot_a1 += np.abs(df.a1[te] - df.true[te]).sum()
                tot_new += np.abs(df.a1[te] + l_best * (df[col][te] - df.a1[te]) - df.true[te]).sum()
            n_ = sg.sum()
            rows.append([g, lab, fmt(lams[0], 2) + " / " + fmt(lams[1], 2), fmt(tot_a1 / n_), fmt(tot_new / n_), fmt((tot_a1 - tot_new) / n_),
                         fmt(100 * (tot_a1 - tot_new) / tot_a1)])
    out.append(md_table(["grupo", "metodo", "lambda (fold 0 / fold 1)", "MAE A1", "MAE mezcla", "ganancia s", "ganancia %"], rows))

    plots(df)
    out.append("## 10. Graficos\n\n![error vs cobertura](TECHO_TRANSITO_error_vs_cobertura.png)\n\n"
               "![cobertura por hora](TECHO_TRANSITO_cobertura_por_hora.png)\n")
    OUT.write_text("\n".join(out), encoding="utf-8")
    print("escrito", OUT)


def plots(df):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    for a, g in zip(ax, ("train", "control")):
        s = df[df.group == g]
        s = s.assign(b=pd.cut(s.cov_re, [0, 0.5, 0.8, 0.9, 0.95, 0.99, 1.0001], include_lowest=True))
        grp = s.groupby("b", observed=True)
        x = np.arange(len(grp))
        for col, lab, st in (("a1", "A1", "k-o"), ("eta_or_adj", "oraculo ajustado", "b--s"),
                             ("eta_or_rel", "oraculo relativo", "c--s"), ("eta_re_adj", "realista ajustado", "r-^"),
                             ("eta_re_rel", "realista relativo", "m-^")):
            a.plot(x, [(v[col] - v.true).abs().mean() for _, v in grp], st, label=lab, ms=4)
        a.set_xticks(x)
        a.set_xticklabels([f"{i.left:.2f}-{i.right:.2f}\n(n={len(v)})" for i, v in grp], fontsize=7)
        a.set_xlabel("cobertura del realista (fraccion del camino con dato)")
        a.set_ylabel("MAE (s)")
        a.set_title(g)
        a.grid(alpha=.3)
    ax[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(C.DIAG / "TECHO_TRANSITO_error_vs_cobertura.png", dpi=110)
    plt.close(fig)
    fig, a = plt.subplots(figsize=(7, 4))
    hh = np.arange(24)
    for col, lab, st in (("cov_or", "oraculo", "b-o"), ("cov_re", "realista (todos)", "r-o"),
                         ("cov_re_same", "realista misma linea", "g-o"), ("cov_re_other", "realista otras lineas", "m-o")):
        a.plot(hh, [100 * df[df.hour == h][col].mean() if (df.hour == h).any() else np.nan for h in hh], st, label=lab, ms=3)
    a.set_xlabel("hora del dia (BA)")
    a.set_ylabel("cobertura del camino (%)")
    a.grid(alpha=.3)
    a.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(C.DIAG / "TECHO_TRANSITO_cobertura_por_hora.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main()
