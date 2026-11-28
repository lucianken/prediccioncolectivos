"""Tablas de PRIOR_RAMAL.md desde prior_lineas.csv / prior_dias.csv (reporte_prior.py). Imprime markdown en tablas_prior.md.
Uso: python data/ml/replay/prior/tablas_prior.py [variante_mejor]"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

R = Path(__file__).resolve().parent
L = pd.read_csv(R / "prior_lineas.csv", dtype={"line": str}); D = pd.read_csv(R / "prior_dias.csv", dtype={"line": str})
METS = [("mae", "MAE 3–7 (s)", 1, -1), ("d120", "±120 s %", 1, 1), ("antes", "llega antes >60 s %", 1, -1), ("desp", "llega después >60 s %", 1, -1),
        ("fa", "bondi fantasma %", 1, -1), ("om", "bondi no anunciado %", 1, -1), ("vacio", "sin aviso firme %", 1, -1)]
variants = [v for v in L.variant.unique()]
best = sys.argv[1] if len(sys.argv) > 1 else None
out = []; w = out.append
base_all = L[(L.variant == "base") & (L.line == "TODAS")].iloc[0]
days = sorted(x[4:] for x in L.line.unique() if x.startswith("DIA:"))


def per_day(v, m):
    a = np.array([L[(L.variant == v) & (L.line == "DIA:" + d)][m].iloc[0] - L[(L.variant == "base") & (L.line == "DIA:" + d)][m].iloc[0] for d in days])
    return a


w("### Agregado (14 líneas, 10 días, pareado en los mismos (línea, día, parada, t))\n")
w("| variante | " + " | ".join(n for _, n, _, _ in METS) + " |"); w("|---|" + "---:|" * len(METS))
w("| base | " + " | ".join(f"{base_all[m]:.1f}" for m, _, _, _ in METS) + " |")
for v in variants:
    if v == "base":
        continue
    r = L[(L.variant == v) & (L.line == "TODAS")].iloc[0]
    cells = []
    for m, _, _, sgn in METS:
        dd = per_day(v, m); good = int(((dd * sgn) > 0).sum())
        cells.append(f"{r[m]:.1f} ({r[m] - base_all[m]:+.2f}; {good}/{len(days)} días mejor)")
    w(f"| {v} | " + " | ".join(cells) + " |")
w("\nEntre paréntesis: diferencia contra `base` del agregado y días (de 10) en que la variante mejora a `base` en el agregado del día.\n")
w("Diferencia pareada día por día (media ± desvío de las 10 diferencias diarias de `variante − base`, agregado de las 14 líneas):\n")
w("| variante | " + " | ".join(n for _, n, _, _ in METS) + " |"); w("|---|" + "---:|" * len(METS))
for v in variants:
    if v == "base":
        continue
    w(f"| {v} | " + " | ".join(f"{per_day(v, m).mean():+.2f} ± {per_day(v, m).std(ddof=1):.2f}" for m, _, _, _ in METS) + " |")
if best:
    w(f"\n### Por línea: base contra `{best}` (agregado de los 10 días; Δ = variante − base; días mejor = de 10 diferencias diarias de la línea)\n")
    w("| línea | n banda | MAE base → prior (s) | Δ MAE | días mejor MAE | ±120 s % | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % |"); w("|---|---:|---|---:|---:|---|---|---|---|---|---|")
    rows = []
    for ln in sorted({x for x in L.line.unique() if not x.startswith("DIA:") and x != "TODAS"}, key=int):
        b = L[(L.variant == "base") & (L.line == ln)].iloc[0]; p = L[(L.variant == best) & (L.line == ln)].iloc[0]
        db = D[(D.variant == "base") & (D.line == ln)].set_index("day"); dp = D[(D.variant == best) & (D.line == ln)].set_index("day")
        good = int((dp.mae < db.mae).sum()); rows.append((ln, b, p, good, p.mae - b.mae))
    for ln, b, p, good, dm in sorted(rows, key=lambda x: x[4]):
        c = lambda m: f"{b[m]:.1f} → {p[m]:.1f}"
        w(f"| {ln} | {int(b.n_band)} | {b.mae:.0f} → {p.mae:.0f} | {dm:+.1f} | {good}/10 | {c('d120')} | {c('antes')} | {c('desp')} | {c('fa')} | {c('om')} | {c('vacio')} |")
    w(f"\nOrdenadas por Δ MAE (mejor primero). Mejoran el MAE {sum(1 for r in rows if r[4] < 0)} de {len(rows)} líneas.\n")
open(R / "tablas_prior.md", "w", encoding="utf8").write("\n".join(out) + "\n"); print("\n".join(out))
