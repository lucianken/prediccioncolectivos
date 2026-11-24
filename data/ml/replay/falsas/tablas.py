"""Tablas markdown de falsas alarmas a partir de clasif.parquet y run/. Uso: python tablas.py RUN_DIR > tablas.md"""
import sys
import numpy as np
import pandas as pd
sys.argv = [sys.argv[0], sys.argv[1]]
import clasifica as C

run = sys.argv[1]
d = C.load(run)
b = d[d.variant == "base"].copy()
ram = d[d.variant == "ramal"]
b["fa"] = b.tp_s.isna()
b["band"] = b.eta0_s.map(C.band)
fa = b[b.fa].copy()
import glob, os
ps = []
for f in glob.glob(run + "/../run_pasado/*.parquet"):
    x = pd.read_parquet(f); dd, ll = os.path.basename(f)[:-8].split("_"); x["day"] = dd; x["line"] = ll; ps.append(x)
ps = pd.concat(ps)
fa = fa.merge(ps, on=["day", "line", "stop_id", "t", "vehicle"], how="left")
fa["cause"] = [C.classify(r) for r in fa.itertuples()]
fa["res"] = fa.listed_ramal.astype(bool).map(lambda x: not x)
fa.to_parquet(run + "/../clasif.parquet")
short = {c: c.split(" ")[0] for c in C.CAUSES}
fa["c"] = fa.cause.map(short)
order = [short[c] for c in C.CAUSES]
N, NF = len(b), len(fa)
bands = [x[2] for x in C.BANDS]
print(f"dias {b.day.nunique()}, pares (dia,linea) {b.groupby(['day','line']).ngroups}; listados {N}; falsas alarmas {NF} ({100*NF/N:.1f} %); "
      f"FA con oraculo de ramal {100*ram.tp_s.isna().mean():.1f} % de {len(ram)} listados\n")
print("## causas\n")
print("| causa | n | % de las FA | pp de los listados | % FA banda 3-7 | oraculo la saca % | provisional % | puede venir % |")
print("|---|---|---|---|---|---|---|---|")
f37 = fa[fa.band.isin(["3-5", "5-7"])]
for cc, c in zip(C.CAUSES, order):
    x = fa[fa.c == c]
    print(f"| {cc} | {len(x)} | {100*len(x)/NF:.1f} | {100*len(x)/N:.2f} | {100*(f37.c==c).sum()/len(f37):.1f} | {100*x.res.mean() if len(x) else 0:.0f} | "
          f"{100*(x.group=='provisional').mean() if len(x) else 0:.0f} | {100*(x.group=='puede_venir').mean() if len(x) else 0:.0f} |")
print(f"\nBanda 3-7: {len(b[b.band.isin(['3-5','5-7'])])} listados, FA {100*b[b.band.isin(['3-5','5-7'])].fa.mean():.1f} % ({len(f37)})\n")
print("## por banda de ETA anunciada\n")
g = b.groupby("band").agg(n=("fa", "size"), fa=("fa", "mean")).reindex(bands)
ct = pd.crosstab(fa.c, fa.band, normalize="columns").reindex(order).fillna(0) * 100
print("| causa | " + " | ".join(bands) + " |")
print("|---|" + "---|" * len(bands))
print("| listados | " + " | ".join(str(int(g.loc[k, 'n'])) for k in bands) + " |")
print("| FA % | " + " | ".join(f"{100*g.loc[k,'fa']:.1f}" for k in bands) + " |")
for c in order:
    print(f"| {c} | " + " | ".join(f"{ct.loc[c, k]:.1f}" if k in ct.columns else "0" for k in bands) + " |")
print("\n## por linea\n")
gl = b.groupby("line").agg(n=("fa", "size"), fa=("fa", "mean"))
ctl = pd.crosstab(fa.line, fa.c, normalize="index").reindex(columns=order).fillna(0) * 100
b37 = b[b.band.isin(["3-5", "5-7"])].groupby("line").fa.mean() * 100
print("| linea | FA % | FA % 3-7 | " + " | ".join(order) + " |")
print("|---|---|---|" + "---|" * len(order))
for ln in sorted(gl.index, key=int):
    print(f"| {ln} | {100*gl.loc[ln,'fa']:.1f} | {b37.get(ln, float('nan')):.1f} | " + " | ".join(f"{ctl.loc[ln, c]:.1f}" for c in order) + " |")
print("\n## por linea: FA con oraculo de ramal\n")
r = ram.copy(); r["fa"] = r.tp_s.isna()
print("| linea | base % | oraculo % |\n|---|---|---|")
for ln in sorted(gl.index, key=int):
    print(f"| {ln} | {100*gl.loc[ln,'fa']:.1f} | {100*r[r.line==ln].fa.mean():.1f} |")
print("\n## por grupo y clase de parada\n")
for col in ("group", "stop_class"):
    gg = b.groupby(col).agg(n=("fa", "size"), fa=("fa", "mean"))
    for k, row in gg.iterrows():
        print(f"- {col} {k}: {int(row.n)} listados, FA {100*row.fa:.1f} %")
print("\n## que tan lejos esta el coche listado en FA (rem_m a la parada), mediana por causa\n")
print(fa.groupby("c").agg(rem_med=("rem_m", "median"), eta_med=("eta0_s", "median")).reindex(order).round(0).to_string())
# oraculo: FA que quedan por causa
print("\n## FA que el oraculo no saca, por causa (% del total de FA)\n")
rem = fa[~fa.res]
print((100 * rem.c.value_counts() / NF).reindex(order).fillna(0).round(2).to_string())
