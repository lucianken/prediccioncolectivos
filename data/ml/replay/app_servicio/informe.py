"""Tablas de APP_CON_SERVICIO.md. Desde prediccion colectivos/: PYTHONPATH=. python data/ml/replay/app_servicio/informe.py
Antes: python data/ml/replay/porcoche/descomposicion.py --src data/ml/replay/app_servicio/w1 --out data/ml/replay/app_servicio/w1 (y w20)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "data/ml/replay/v4prod")
import reporte as RP
from prediccion.replay.report_vara import flat
R = Path("data/ml/replay"); A = R / "app_servicio"
L126 = open(A / "lines126.txt").read().split(",")
OLD = open(R / "v4prod/lines_118.txt").read().split(",")
G12 = L126[:12]; G34 = open(R / "v4prod/lines_v3_34.txt").read().split(",")
G80 = [l for l in L126 if l not in G12 and l not in G34]
assert len(G12) == 12 and len(G34) == 34 and len(G80) == 80
GROUPS = [("12 viejas", G12), ("34 de v3", G34), ("80 nuevas", G80), ("126 líneas", L126)]
VARS = [("w1", "1. sin servicio (1 ping)", A / "w1"), ("w15", "3. replay vigente (15 min)", R / "v4prod/v4"), ("w20", "2. con servicio (20 min)", A / "w20")]
KEY = RP.KEY
data = {}
for k, _, d in VARS:
    for ln in L126:
        i, v = RP.load_line([d], ln)
        if i is not None: data[(k, ln)] = (i, v)
miss = [(k, l) for k, _, _ in VARS for l in L126 if (k, l) not in data]
print("faltan", miss)
def row(k, lines):
    I = pd.concat([data[(k, l)][0] for l in lines if (k, l) in data]); V = pd.concat([data[(k, l)][1] for l in lines if (k, l) in data])
    return RP.row(I, V), len(I)
res = {}
for gn, ls in GROUPS:
    for k, _, _ in VARS: res[(gn, k)] = row(k, ls)
# descomposicion
def deco(k, lines):
    if k == "w15": df = pd.read_csv(R / "v4prod/descomposicion_lineas.csv", dtype={"line": str})
    else: df = pd.read_csv(A / k / "descomposicion_lineas.csv", dtype={"line": str})
    df = df[df.line.isin(lines)]
    n = df.n_con.sum()
    o = {"n_con": int(n), "mae": df.sum_abs.sum() / n, "sin_pct": 100 * df.n_sin.sum() / (n + df.n_sin.sum())}
    for c in "abcdef":
        o[f"n_{c}"] = 100 * df[f"n_{c}"].sum() / n; o[f"ap_{c}"] = df[f"abs_{c}"].sum() / n
        o[f"mae_{c}"] = df[f"abs_{c}"].sum() / max(df[f"n_{c}"].sum(), 1)
    return o
out = ["# tablas", ""]
f = lambda x, d=1: "—" if x is None or x != x else f"{x:.{d}f}"
out += ["## Métricas por variante y grupo", "", "| grupo | variante | n instantes banda | MAE próx. coche 3–7 (s) | llega antes >60 s % | llega después >60 s % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | sin anuncio % (banda) |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
for gn, ls in GROUPS:
    for k, nm, _ in VARS:
        r, n = res[(gn, k)]
        out.append(f"| {gn} | {nm} | {r['n']} | {f(r['mae'])} | {f(r['antes'])} | {f(r['desp'])} | {f(r['fa'])} | {f(r['om'])} | {f(r['vacio'])} | {f(r['sin_anuncio'])} |")
out += ["", "## Descomposición a–e (aporte al MAE en s; % de instantes con anuncio)", ""]
for gn, ls in GROUPS:
    out += [f"### {gn}", "", "| variante | MAE | sin anuncio % | a | b | c | d | e | f |", "|---|---:|---:|---|---|---|---|---|---|"]
    for k, nm, _ in VARS:
        o = deco(k, ls)
        out.append(f"| {nm} | {f(o['mae'])} | {f(o['sin_pct'])} | " + " | ".join(f"{f(o['ap_'+c])} s ({f(o['n_'+c])} %)" for c in "abcdef") + " |")
    out.append("")
# MAE por linea diferencia
rows = []
for ln in L126:
    r = {k: RP.row(*data[(k, ln)]) for k, _, _ in VARS if (k, ln) in data}
    if len(r) == 3: rows.append(dict(line=ln, **{f"{k}_{m}": r[k][m] for k in r for m in ("mae", "fa", "om", "vacio", "antes", "desp", "n")}))
pl = pd.DataFrame(rows); pl.to_csv(A / "por_linea.csv", index=False)
d = pl.w20_mae - pl.w15_mae; d1 = pl.w1_mae - pl.w20_mae
out += ["", f"MAE por línea w20 − w15: mediana {d.median():+.2f} s, rango {d.min():+.1f} a {d.max():+.1f} s; w20 mejor en {(d<0).sum()} de {len(d)}.",
        f"MAE por línea w1 − w20: mediana {d1.median():+.1f} s, rango {d1.min():+.1f} a {d1.max():+.1f} s; w20 mejor en {(d1>0).sum()} de {len(d1)}."]
Path(A / "tablas.md").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
