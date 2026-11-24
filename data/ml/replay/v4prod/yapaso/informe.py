"""Tablas de YA_PASO.md desde variantes.csv. Uso (desde prediccion colectivos/): python data/ml/replay/v4prod/yapaso/informe.py > tablas.md"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
d = pd.read_csv(HERE / "variantes.csv", dtype={"line": str})
L118 = open(ROOT / "data/ml/replay/v4prod/lines_118.txt").read().split(",")
EXTRA8 = ["49", "97", "119", "153", "154", "163", "185", "193"]
GROUPS = {"12 viejas": L118[:12], "34 de v3": L118[12:46], "80 nuevas habilitadas": L118[46:] + EXTRA8}
GROUPS["126 agregado"] = sum(GROUPS.values(), [])
enabled = [e["line"] for e in json.load(open(ROOT.parent / "proyectoconsola/public/config/prediccion.json", encoding="utf-8"))["enabledLines"]]
assert sorted(enabled) == sorted(GROUPS["126 agregado"]) and set(d.line) == set(enabled), "grupos != habilitadas"
NM = {"base": "base (sin regla)", "app_dem": "app: ETA consumido, baja", "app_rem": "app: ETA consumido, saca"}
for t in (30, 50, 70, 90):
    NM[f"p{t}_dem"] = f"P > {t/100:.1f}, baja"; NM[f"p{t}_rem"] = f"P > {t/100:.1f}, saca"
ORDER = list(NM)
num = [c for c in d.columns if c not in ("line", "variant")]


def agg(g, var):
    s = d[(d.variant == var) & d.line.isin(GROUPS[g])][num].sum()
    r = {"n_band": s.n_band, "mae": s.sum_abs / s.n_con, "antes": 100 * s.n_antes / s.n_con, "desp": 100 * s.n_desp / s.n_con,
         "sin": 100 * s.n_sin / s.n_band, "fa": 100 * s.n_fa / s.n_eval, "om": 100 * s.n_om / s.n_vis, "vac": 100 * s.n_vac / s.n_vac_den,
         "mae03": s.abs_0_3 / s.con_0_3, "antes03": 100 * s.antes_0_3 / s.con_0_3, "desp03": 100 * s.desp_0_3 / s.con_0_3,
         "mae715": s.abs_7_15 / s.con_7_15, "antes715": 100 * s.antes_7_15 / s.con_7_15, "desp715": 100 * s.desp_7_15 / s.con_7_15,
         "n_rule": s.n_rule, "prec": 100 * s.n_rule_past / s.n_rule if s.n_rule else np.nan,
         "pasa10": 100 * s.n_rule_pasa10 / s.n_rule if s.n_rule else np.nan, "n_listados": s.n_listados,
         "n_om": s.n_om, "n_vac": s.n_vac, "n_vis": s.n_vis}
    for k in "abcdef":
        r[f"ap_{k}"] = s[f"abs_{k}"] / s.n_con; r[f"pc_{k}"] = 100 * s[f"n_{k}"] / s.n_con
    return r


f = lambda x, k=1: "-" if x is None or x != x else f"{x:.{k}f}"
out = []
for g in GROUPS:
    R = {v: agg(g, v) for v in ORDER}
    b = R["base"]
    out += [f"### {g} (n banda 3-7 min: {int(b['n_band']):,})", "",
            "| variante | MAE 3-7 (s) | llega antes > 60 s % | llega despues > 60 s % | sin anuncio % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | MAE 0-3 (s) | antes/despues 0-3 % | MAE 7-15 (s) | coches movidos | % que ya habia pasado | % que pasa en <= 10 min |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|"]
    for v in ORDER:
        r = R[v]
        out.append(f"| {NM[v]} | {f(r['mae'])} | {f(r['antes'])} | {f(r['desp'])} | {f(r['sin'],2)} | {f(r['fa'],2)} | {f(r['om'],2)} | {f(r['vac'],2)} | {f(r['mae03'])} | {f(r['antes03'])} / {f(r['desp03'])} | {f(r['mae715'])} | {int(r['n_rule']):,} | {f(r['prec'])} | {f(r['pasa10'])} |")
    out.append("")
    out += [f"Descomposicion a-e, aporte al MAE en s (% de instantes), {g}:", "",
            "| variante | (a) | (b) ya habia pasado | (c) fantasma | (d) otro listado | (e) no anunciado | (f) | total |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for v in ORDER:
        r = R[v]
        out.append(f"| {NM[v]} | " + " | ".join(f"{f(r['ap_'+k])} ({f(r['pc_'+k])})" for k in "abcdef") + f" | {f(r['mae'])} |")
    out.append("")
# por linea: la mejor variante candidata
print("\n".join(out))
# chequeo baseline contra descomposicion_lineas.csv
dl = pd.read_csv(ROOT / "data/ml/replay/v4prod/descomposicion_lineas.csv", dtype={"line": str}).set_index("line")
bb = d[d.variant == "base"].set_index("line")
com = [l for l in bb.index if l in dl.index]
print("<!-- chequeo base: max dif n_con", int((bb.loc[com, "n_con"] - dl.loc[com, "n_con"]).abs().max()), "; max dif |sum_abs| (s)",
      round(float((bb.loc[com, "sum_abs"] - dl.loc[com, "sum_abs"]).abs().max()), 2), "; MAE 126 desc.", round(dl.loc[com, "sum_abs"].sum() / dl.loc[com, "n_con"].sum(), 2), "-->")
# lineas donde empeora el MAE con la regla P>0.5 baja
for v in ("p50_dem", "p70_dem", "app_dem"):
    x = d[d.variant == v].set_index("line"); m = x.sum_abs / x.n_con - bb.sum_abs / bb.n_con
    print(f"<!-- {v}: MAE por linea delta mediana {m.median():.1f}, mejora {int((m<0).sum())} lineas, empeora {int((m>0).sum())}, peor {m.max():.1f} -->")
