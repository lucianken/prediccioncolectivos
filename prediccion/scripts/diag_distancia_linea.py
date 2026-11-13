"""
Diagnóstico A (sin entrenar): ¿la diferencia de error seen vs heldout es distribución de distancia / de línea?
Lee las predicciones por fila de data/ml/v2b_sub/runs/eval2/ (prediccion.eval --save-preds) y el eval congelado de
data/ml/v2b/eval, y escribe data/ml/v2b_sub/runs/diag/_body.md y distancia_linea.json.
  python -m prediccion.scripts.diag_distancia_linea
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from prediccion.eval import DIST_FINE_M, ETA_BUCKETS_S

RUNS = Path("data/ml/v2b_sub/runs")
EVAL = Path("data/ml/v2b/eval")
OUT = RUNS / "diag"
MODELS = {"A3 s0": "a3_lr1e-3_s0", "A3 s1": "a3_lr1e-3_s1", "Por tramos s0": "path_lr2e-3_s0",
          "Por tramos s1": "path_lr2e-3_s1", "A1": "a1"}
FAMILIES = {"A3 (media de 2 semillas)": ["A3 s0", "A3 s1"],
            "Por tramos (media de 2 semillas)": ["Por tramos s0", "Por tramos s1"]}
D_COARSE = [("<0,5 km", 0, 500), ("0,5-2 km", 500, 2000), ("2-5 km", 2000, 5000), ("5+ km", 5000, math.inf)]


def bin_idx(x, bins):
    out = np.full(len(x), -1, int)
    for i, (_, lo, hi) in enumerate(bins):
        out[(x >= lo) & (x < hi)] = i
    return out


def load(which):
    import pyarrow.parquet as pq
    df = pq.read_table(EVAL / f"eval_{which}.parquet",
                       columns=["line", "dist_remaining_m", "observed_eta_s"]).to_pandas()
    preds = {}
    for name, d in MODELS.items():
        f = next((RUNS / "eval2" / d).glob(f"*_{which}_*.pred.npy"))
        p = np.load(f).astype(np.float64)
        assert len(p) == len(df)
        preds[name] = p
    return df, preds


def fmt(v, nd=0):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{nd}f}"


def table(header, rows):
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|"]
                     + ["| " + " | ".join(map(str, r)) + " |" for r in rows]) + "\n"


def wmean(x, w):
    return float((x * w).sum() / w.sum()) if w.sum() > 0 else float("nan")


def lsort(vals):
    return sorted(vals, key=lambda x: (len(x), x))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    S, Ps = load("seen")
    H, Ph = load("heldout")
    tS, tH = S["observed_eta_s"].to_numpy(), H["observed_eta_s"].to_numpy()
    xS, xH = S["dist_remaining_m"].to_numpy(), H["dist_remaining_m"].to_numpy()
    res = {}
    md = []

    # ---- 1. sobreestimación / subestimación ----
    md += ["## 1. Sobreestimación y subestimación por modelo", "",
           "Tablas completas (por ETA, distancia, distancia fina, línea, fase) en `runs/eval2/<modelo>/*.md`. Resumen "
           "(sobreest. = pred − real > 60 s; subest. = real − pred > 60 s):", ""]
    for tag, sel in (("ETA real 0-5 min", lambda t, x: t < 300), ("distancia < 1 km", lambda t, x: x < 1000),
                     ("global", lambda t, x: np.ones(len(t), bool))):
        rows = []
        for name in MODELS:
            r = [name]
            for t, x, P in ((tS, xS, Ps), (tH, xH, Ph)):
                m = sel(t, x)
                e = P[name][m] - t[m]
                r += [int(m.sum()), fmt(np.abs(e).mean()), fmt(100 * np.mean(e > 60), 1), fmt(100 * np.mean(e < -60), 1)]
            rows.append(r)
        md += [f"**{tag}**", "", table(["modelo", "n seen", "MAE seen", "sobreest. seen %", "subest. seen %", "n held",
                                         "MAE held", "sobreest. held %", "subest. held %"], rows)]

    # ---- 2. histogramas ----
    dS, dH = bin_idx(xS, DIST_FINE_M), bin_idx(xH, DIST_FINE_M)
    eS, eH = bin_idx(tS, ETA_BUCKETS_S), bin_idx(tH, ETA_BUCKETS_S)
    md += ["## 2. Distribuciones de distancia y de ETA real (% de filas)", ""]
    md += [table(["distancia", "seen %", "heldout %"],
                 [[b[0], fmt(100 * np.mean(dS == i), 1), fmt(100 * np.mean(dH == i), 1)] for i, b in enumerate(DIST_FINE_M)])]
    md += [table(["ETA real", "seen %", "heldout %"],
                 [[b[0], fmt(100 * np.mean(eS == i), 1), fmt(100 * np.mean(eH == i), 1)] for i, b in enumerate(ETA_BUCKETS_S)])]
    md += ["Por línea (% de filas de la línea por distancia fina; mediana de distancia y de ETA real):", ""]
    hdr = ["conjunto", "línea", "n"] + [b[0] for b in DIST_FINE_M] + ["med dist km", "med ETA min"]
    rows = []
    for nm, d, di, x, t in (("seen", S, dS, xS, tS), ("heldout", H, dH, xH, tH)):
        for ln in lsort(d["line"].unique()):
            m = (d["line"] == ln).to_numpy()
            rows.append([nm, ln, int(m.sum())] + [fmt(100 * np.mean(di[m] == i), 0) for i in range(8)]
                        + [fmt(np.median(x[m]) / 1000, 2), fmt(np.median(t[m]) / 60, 1)])
    md += [table(hdr, rows)]

    # ---- 3. reponderación ----
    md += ["## 3. Seen re-ponderado a la distribución de heldout", "",
           "Peso de cada fila seen = P_heldout(celda) / P_seen(celda). (a) celda = bin de distancia fino (8); (b) celda = "
           "distancia fina × bucket de ETA (32). Las celdas con heldout > 0 y seen = 0 no se pueden cubrir: se informa la masa "
           "de heldout sin cobertura y el MAE de heldout se calcula solo sobre las celdas cubiertas, para comparar igual con igual.", ""]
    cS2, cH2 = dS * 4 + eS, dH * 4 + eH
    rows, rw = [], {}
    for name in MODELS:
        a_s, a_h = np.abs(Ps[name] - tS), np.abs(Ph[name] - tH)
        r = [name, fmt(a_s.mean()), fmt(a_h.mean())]
        for cs, ch, nc in ((dS, dH, 8), (cS2, cH2, 32)):
            ps = np.bincount(cs, minlength=nc) / len(cs)
            ph = np.bincount(ch, minlength=nc) / len(ch)
            cover = ps > 0
            w = np.where(cover, ph / np.where(cover, ps, 1), 0.0)[cs]
            hv = a_h[cover[ch]].mean()
            r += [fmt(wmean(a_s, w)), fmt(hv), fmt(100 * ph[~cover].sum(), 1)]
            rw[f"{name}|{nc}"] = [wmean(a_s, w), float(hv), float(100 * ph[~cover].sum())]
        rows.append(r)
    md += [table(["modelo", "MAE seen", "MAE heldout", "(a) seen repond. dist", "heldout cubierto", "sin cubrir %",
                  "(b) seen repond. dist×ETA", "heldout cubierto", "sin cubrir %"], rows)]
    res["reweight"] = rw
    md += ["Seen re-ponderado a la distribución de distancia fina de **cada línea heldout** por separado:", ""]
    rows = []
    ps = np.bincount(dS, minlength=8) / len(dS)
    cover = ps > 0
    for fam, names in FAMILIES.items():
        for ln in ("12", "15", "128"):
            mH = (H["line"] == ln).to_numpy()
            ph = np.bincount(dH[mH], minlength=8) / mH.sum()
            w = np.where(cover, ph / np.where(cover, ps, 1), 0.0)[dS]
            sv = np.mean([wmean(np.abs(Ps[n] - tS), w) for n in names])
            hv = np.mean([np.abs(Ph[n] - tH)[mH & cover[dH]].mean() for n in names])
            rows.append([fam, ln, int(mH.sum()), fmt(sv), fmt(hv), fmt(hv - sv)])
    md += [table(["familia", "línea heldout", "n", "seen repond.", "heldout de la línea", "brecha"], rows)]

    # ---- 4. línea y línea × distancia ----
    md += ["## 4. MAE por línea y por línea × distancia", ""]
    dcS, dcH = bin_idx(xS, D_COARSE), bin_idx(xH, D_COARSE)
    for fam, names in FAMILIES.items():
        md += [f"### {fam}", ""]
        eSm = np.mean([np.abs(Ps[n] - tS) for n in names], axis=0)
        eHm = np.mean([np.abs(Ph[n] - tH) for n in names], axis=0)
        rows = []
        for nm, d, e, dc in (("seen", S, eSm, dcS), ("heldout", H, eHm, dcH)):
            for ln in lsort(d["line"].unique()):
                m = (d["line"] == ln).to_numpy()
                row = [nm, ln, int(m.sum()), fmt(e[m].mean())]
                for i in range(4):
                    mm = m & (dc == i)
                    row.append(f"{fmt(e[mm].mean())} ({int(mm.sum())})" if mm.any() else "- (0)")
                rows.append(row)
        md += [table(["conjunto", "línea", "n", "MAE", "<0,5 km (n)", "0,5-2 km (n)", "2-5 km (n)", "5+ km (n)"], rows)]
        is15 = (H["line"] == "15").to_numpy()
        rows = []
        for i, b in enumerate(D_COARSE):
            m = dcH == i
            rows.append([b[0], int(m.sum()), fmt(eHm[m].mean()), int((m & is15).sum()), fmt(eHm[m & is15].mean()) if (m & is15).any() else "-",
                         int((m & ~is15).sum()), fmt(eHm[m & ~is15].mean()) if (m & ~is15).any() else "-", fmt(eSm[dcS == i].mean())])
        md += ["¿La 15 sola explica la cola? Heldout con y sin la 15 (seen de referencia):", "",
               table(["distancia", "n heldout", "MAE heldout", "n (15)", "MAE (15)", "n (12+128)", "MAE (12+128)", "MAE seen"], rows)]
    md += ["### MAE por bucket de ETA real y línea (media de los 4 modelos A3 y por tramos)", ""]
    allm = ["A3 s0", "A3 s1", "Por tramos s0", "Por tramos s1"]
    rows = []
    for nm, d, P, t, ei in (("seen", S, Ps, tS, eS), ("heldout", H, Ph, tH, eH)):
        e = np.mean([np.abs(P[n] - t) for n in allm], axis=0)
        for ln in lsort(d["line"].unique()):
            m = (d["line"] == ln).to_numpy()
            rows.append([nm, ln] + [f"{fmt(e[m & (ei == i)].mean())} ({int((m & (ei == i)).sum())})" if (m & (ei == i)).any() else "-" for i in range(4)])
    md += [table(["conjunto", "línea", "0-5 min (n)", "5-10 (n)", "10-20 (n)", "20+ (n)"], rows)]
    (OUT / "distancia_linea.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (OUT / "_body.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
