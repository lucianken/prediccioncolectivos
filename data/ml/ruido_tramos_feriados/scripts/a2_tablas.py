import sys; sys.path.insert(0,"data/ml/ruido_tramos_feriados/scripts")
from mdutil import to_md
import pandas as pd, numpy as np, json
import psutil; psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
O = "data/ml/ruido_tramos_feriados/"
R = pd.read_parquet(O + "_errores_interp.parquet")
R["ae"] = R.e.abs(); R["dlt"] = R.S / R.k; R["dpi"] = R.D / R.k; R["v"] = R.D / R.S
loc = R.hour
wk = R.dow < 5
R["franja"] = np.select([~wk, wk & (loc >= 7) & (loc < 10), wk & (loc >= 17) & (loc < 20), wk & (loc >= 10) & (loc < 17), True],
                        ["fin de semana", "pico manana 7-10", "pico tarde 17-20", "valle 10-17 (habil)", "noche/madrugada (habil)"], "x")
def cut(col, edges, labels):
    return pd.cut(R[col], edges, labels=labels, right=False)
R["s_dlt"] = cut("dlt", [0, 50, 65, 90, 130, 1e9], ["<50 s", "50-65 s", "65-90 s", "90-130 s", ">=130 s"])
R["s_dpi"] = cut("dpi", [0, 150, 300, 500, 1e9], ["<150 m", "150-300 m", "300-500 m", ">=500 m"])
R["s_v"] = cut("v", [0, 1.5, 3, 5, 8, 1e9], ["<1,5 m/s", "1,5-3 m/s", "3-5 m/s", "5-8 m/s", ">=8 m/s"])
g = R.gap_paradas
R["s_gap"] = pd.cut(g, [0, 250, 400, 700, 1500, 1e9], labels=["<250 m", "250-400 m", "400-700 m", "0,7-1,5 km", ">=1,5 km"], right=False).astype(object).fillna("sin paradas/dato")
npk = R.n_paradas_tramo / (R.D / 1000.0)
R["s_np"] = pd.cut(npk, [0, 1e-9, 2, 4, 1e9], labels=["0 paradas en el tramo", "<2 por km", "2-4 por km", ">=4 por km"], right=False).astype(object).fillna("sin dato")
R["s_franja"] = R["franja"]
R["s_dn"] = pd.cut(R.dn, [0, 50, 100, 200, 1e9], labels=["<50 m", "50-100 m", "100-200 m", ">=200 m"], right=False)
def fit(x, y):
    m = (x > 0) & (y > 0)
    if m.sum() < 3: return np.nan, np.nan
    b, a = np.polyfit(np.log(x[m]), np.log(y[m]), 1); return a, b
def table(mode, col, minn=300):
    D = R[R["mode"] == mode]; rows = []
    for lab, d in D.groupby(col, observed=True):
        per = d.groupby("k").agg(S=("S", "mean"), mae=("ae", "mean"), p90=("ae", lambda x: x.quantile(.9)), n=("ae", "size"))
        per = per[per.n >= minn]
        if 2 not in per.index: continue
        sstar = float((d.S / d.k).mean())
        am, bm = fit(per.S.values, per.mae.values); ap, bp = fit(per.S.values, per.p90.values)
        k2 = d[d.k == 2]
        rows.append(dict(estrato=lab, n_k2=len(k2), mae_k2=k2.ae.mean(), p90_k2=k2.ae.quantile(.9), pct30_k2=100 * (k2.ae > 30).mean(),
                         mae_k4=d[d.k == 4].ae.mean(), b=bm, S_real=sstar, mae_ext=np.exp(am) * sstar ** bm, p90_ext=np.exp(ap) * sstar ** bp))
    return pd.DataFrame(rows)
out = {}
for col, nm in [("s_dlt", "espaciado temporal entre pings"), ("s_dpi", "distancia entre pings"), ("s_v", "velocidad media del tramo"),
                ("s_gap", "separacion entre paradas del shape alrededor del objetivo"), ("s_np", "paradas por km en el tramo"),
                ("s_franja", "franja horaria (proxy de transito)"), ("s_dn", "distancia del objetivo al ping usado mas cercano")]:
    for mode in ("obj", "ping"):
        out[(nm, mode)] = table(mode, col)
tot = {}
for mode in ("obj", "ping"):
    D = R[R["mode"] == mode]
    per = D.groupby("k").agg(S=("S", "mean"), mae=("ae", "mean"), p50=("ae", "median"), p90=("ae", lambda x: x.quantile(.9)), p99=("ae", lambda x: x.quantile(.99)), n=("ae", "size"))
    am, bm = fit(per.S.values, per.mae.values); ap, bp = fit(per.S.values, per.p90.values); a5, b5 = fit(per.S.values, per.p50.values)
    sst = float((D.S / D.k).mean()); sst_med = 60.0
    tot[mode] = dict(per=per.round(2).reset_index().to_dict("records"), b_mae=bm, b_p90=bp, S_real_media=sst,
                     mae_ext=np.exp(am) * sst ** bm, p90_ext=np.exp(ap) * sst ** bp, p50_ext=np.exp(a5) * sst ** b5,
                     mae_ext_S60=np.exp(am) * 60 ** bm, p90_ext_S60=np.exp(ap) * 60 ** bp)
json.dump(tot, open(O + "A_totales.json", "w"), indent=1)
def md(df):
    d = df.copy()
    d.columns = ["estrato", "n (k=2)", "MAE k=2 (s)", "P90 k=2 (s)", "% >30 s (k=2)", "MAE k=4 (s)", "exponente b", "intervalo real medio (s)", "MAE extrap. 1 intervalo (s)", "P90 extrap. 1 intervalo (s)"]
    return to_md(d.round(1))
with open(O + "A_tablas.md", "w", encoding="utf-8") as f:
    f.write("TOTALES\n" + json.dumps(tot, indent=1) + "\n")
    for (nm, mode), df in out.items():
        f.write(f"\n### {nm} | modo {mode}\n\n" + md(df) + "\n")
# cruce velocidad x separacion de paradas (modo ping y obj), extrapolado simple: MAE k=2 y escalado por el exponente global
for mode in ("obj", "ping"):
    D = R[(R["mode"] == mode) & (R.k == 2)]
    pv = D.pivot_table(index="s_v", columns="s_gap", values="ae", aggfunc="mean", observed=True).round(1)
    pn = D.pivot_table(index="s_v", columns="s_gap", values="ae", aggfunc="size", observed=True)
    with open(O + "A_tablas.md", "a", encoding="utf-8") as f:
        f.write(f"\n### cruce velocidad x separacion de paradas, MAE k=2 (s), modo {mode}\n\n" + to_md(pv,index=True) + "\n\nn:\n\n" + to_md(pn.astype(float),index=True,nd=0) + "\n")
print(open(O + "A_tablas.md", encoding="utf-8").read())
