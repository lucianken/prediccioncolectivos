"""B: distribucion del error del modelo por tramo (eval congelado v4 seen + checkpoint de produccion)."""
import sys, json
sys.path.insert(0, "data/ml/ruido_tramos_feriados/scripts")
from mdutil import to_md
import numpy as np, pandas as pd, psutil
psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
O = "data/ml/ruido_tramos_feriados/"
d = pd.read_parquet("data/ml/v4/eval/eval_seen.parquet")
pred = np.load("data/ml/v4_sub/runs/eval/full_s1_v4/path_path_eta_best_seen_20261121.pred.npy").astype(float)
assert len(pred) == len(d)
VAR = sys.argv[1] if len(sys.argv) > 1 else ""
d["pred"] = pred; d["err"] = d.observed_eta_s - d.pred; d["ae"] = d.err.abs()   # negativo = llega antes de lo anunciado
d["band"] = (d.observed_eta_s >= 180) & (d.observed_eta_s < 420)
n_impl = int((d.dist_remaining_m / d.observed_eta_s > 25).sum())
if VAR == "plaus":
    keep_ = (d.dist_remaining_m / d.observed_eta_s <= 25).to_numpy(); d = d[keep_].reset_index(drop=True); pred = pred[keep_]
L = (d.dist_along_m / d.dist_along_norm.replace(0, np.nan)).astype(float)
tr = np.stack(d.traj_flat.to_numpy()); n = len(d)
hl = d.traj_len.to_numpy().astype(int)
dist_tr = tr[:, 0::3] * L.to_numpy()[:, None]
dP = dist_tr[np.arange(n), hl - 1]
# pings consecutivos finales a < 30 m de P (cuenta de pings detenido, incluyendo P)
still = np.zeros(n, int); alive = np.ones(n, bool)
for j in range(10):
    idx = hl - 1 - j; ok = idx >= 0
    dj = np.where(ok, dist_tr[np.arange(n), np.clip(idx, 0, 9)], np.inf)
    alive &= ok & (np.abs(dj - dP) < 30.0) if j > 0 else np.ones(n, bool)
    still += alive
d["still"] = still
d["det"] = pd.cut(still, [0, 1, 3, 6, 11], labels=["en movimiento (0 pings previos quietos)", "quieto 1-2 pings previos", "quieto 3-5 pings previos", "quieto >=6 pings previos"], right=False)
d["det"] = np.where((still <= 1) | (d.speed_mps > 0.5), "en movimiento", np.where(still < 4, "detenido 2-3 pings (~1-3 min)", "detenido >=4 pings (>=3 min)"))
def stats(g):
    e = g.err.values
    return pd.Series(dict(n=len(g), MAE=g.ae.mean(), sesgo=e.mean(), P90=np.percentile(g.ae, 90), antes60=100 * (e < -60).mean(), despues60=100 * (e > 60).mean()))
def tabla(col, edges=None, labels=None, df=d):
    x = df[col] if edges is None else pd.cut(df[col], edges, labels=labels, right=False)
    out = {}
    for nm, sub in (("banda 3-7 min", df.band), ("global", pd.Series(True, index=df.index))):
        t = df[sub.values].groupby(x[sub.values], observed=True).apply(stats)
        out[nm] = t
    r = out["banda 3-7 min"].add_prefix("b37_").join(out["global"].add_prefix("glob_"), how="outer")
    return r
bins_along = ([0, 300, 600, 1000, 2000, 5000, 1e9], ["0-300 m", "300-600 m", "600-1000 m", "1-2 km", "2-5 km", ">5 km"])
bins_rem = ([0, 500, 1000, 2000, 5000, 10000, 1e9], ["<0,5 km", "0,5-1 km", "1-2 km", "2-5 km", "5-10 km", ">10 km"])
bins_tss = ([0, 60, 180, 420, 900, 1800, 1e9], ["0-1 min", "1-3 min", "3-7 min", "7-15 min", "15-30 min", ">30 min"])
d["tss_c"] = pd.cut(d.time_since_start, bins_tss[0], labels=bins_tss[1], right=False).astype(object).fillna("sin dato (start_unknown)")
d["su"] = np.where(d.start_unknown, "start_unknown=1", "start_unknown=0")
T = {"dist_along": tabla("dist_along_m", *bins_along), "start_unknown": tabla("su"), "time_since_start": tabla("tss_c"),
     "dist_remaining": tabla("dist_remaining_m", *bins_rem)}
# cruce start_unknown x dist_along
d["along_c"] = pd.cut(d.dist_along_m, bins_along[0], labels=bins_along[1], right=False)
T["su_x_along"] = tabla("su", df=d[d.dist_along_m < 1000]).iloc[:0]
sx = []
for su in (False, True):
    for lab in bins_along[1][:3]:
        g = d[(d.start_unknown == su) & (d.along_c == lab)]
        for nm, gg in (("b37", g[g.band]), ("glob", g)):
            s = stats(gg); sx.append(dict(start_unknown=int(su), dist_along=lab, vara=nm, **s.round(1).to_dict()))
T["su_x_along"] = pd.DataFrame(sx)
# detenido en cabecera (dist_along < 600)
head = d[d.dist_along_m < 600]
T["detenido_cabecera"] = pd.concat([head.groupby("det").apply(stats).add_prefix("glob_"), head[head.band].groupby("det").apply(stats).add_prefix("b37_")], axis=1)
T["detenido_resto"] = pd.concat([d[d.dist_along_m >= 600].groupby("det").apply(stats).add_prefix("glob_"), d[(d.dist_along_m >= 600) & d.band].groupby("det").apply(stats).add_prefix("b37_")], axis=1)
# techo de modelo especifico de cabecera
def techo(df, hmax):
    h = df.dist_along_m < hmax; res = {}
    for nm, m in (("banda 3-7 min", df.band), ("global", pd.Series(True, index=df.index))):
        s = df[m.values]; hh = h[m.values]
        mae_all = s.ae.mean(); mae_head = s.ae[hh].mean(); mae_rest = s.ae[~hh].mean()
        naive = (s.ae[~hh].sum() + mae_rest * hh.sum()) / len(s)
        # emparejado por ETA real (bins de 60 s) y distancia restante
        key = pd.cut(s.observed_eta_s, [0, 60, 120, 180, 240, 300, 360, 420, 600, 900, 1200, 1800, 1e9], right=False).astype(str) + "|" + pd.cut(s.dist_remaining_m, [0, 500, 1000, 2000, 5000, 1e9], right=False).astype(str)
        ref = s.ae[~hh].groupby(key[~hh]).mean()
        rep = key[hh].map(ref).fillna(mae_rest)
        matched = (s.ae[~hh].sum() + rep.sum()) / len(s)
        # emparejado solo por ETA real
        key2 = pd.cut(s.observed_eta_s, [0, 60, 120, 180, 240, 300, 360, 420, 600, 900, 1200, 1800, 1e9], right=False).astype(str)
        ref2 = s.ae[~hh].groupby(key2[~hh]).mean(); rep2 = key2[hh].map(ref2).fillna(mae_rest)
        m2 = (s.ae[~hh].sum() + rep2.sum()) / len(s)
        res[nm] = dict(n=len(s), n_cab=int(hh.sum()), peso_filas=100 * hh.mean(), peso_error=100 * s.ae[hh].sum() / s.ae.sum(), MAE=mae_all, MAE_cab=mae_head, MAE_resto=mae_rest,
                       techo_simple=naive, techo_por_eta=m2, techo_por_eta_y_dist=matched)
    return res
TE = {str(h): techo(d, h) for h in (300, 600, 1000)}
# misma cuenta sobre la muestra natural de dias de val (peso en el trafico real)
M = pd.read_parquet(O + "muestra_dias.parquet", columns=["day", "dist_along_m", "dist_remaining_m", "observed_eta_s", "pred"])
M = M[(M.day >= "2026-09-15") & (M.day <= "2026-10-14")].copy()
if VAR == "plaus": M = M[M.dist_remaining_m / M.observed_eta_s <= 25].copy()
M["ae"] = (M.observed_eta_s - M.pred).abs(); M["band"] = (M.observed_eta_s >= 180) & (M.observed_eta_s < 420)
TEnat = {str(h): techo(M, h) for h in (300, 600, 1000)}
nat = {}
for nm, m in (("banda 3-7 min", M.band), ("global", pd.Series(True, index=M.index))):
    s = M[m.values]; x = pd.cut(s.dist_along_m, bins_along[0], labels=bins_along[1], right=False)
    t = s.groupby(x, observed=True).agg(n=("ae", "size"), MAE=("ae", "mean")); t["pct_filas"] = 100 * t.n / t.n.sum(); nat[nm] = t
res = {"tablas": {k: v.round(2).reset_index().to_dict("records") for k, v in T.items()}, "techo": TE, "techo_natural": TEnat,
       "natural": {k: v.round(2).reset_index().to_dict("records") for k, v in nat.items()},
       "n_implausibles_removidos": n_impl if VAR else 0, "n": len(d), "n_band": int(d.band.sum()), "MAE_band": d.ae[d.band].mean(), "MAE_glob": d.ae.mean()}
json.dump(res, open(O + f"B_resultados{VAR}.json", "w"), indent=1, default=float)
with open(O + f"B_tablas{VAR}.md", "w", encoding="utf-8") as f:
    for k, v in T.items():
        f.write(f"\n### {k}\n\n" + to_md(v.round(1), index=(k not in ("su_x_along",))) + "\n")
    f.write("\n### techo (eval congelado)\n\n" + json.dumps(TE, indent=1, default=float) + "\n\n### techo (muestra natural val)\n\n" + json.dumps(TEnat, indent=1, default=float) + "\n")
    for k, v in nat.items(): f.write(f"\n### natural {k}\n\n" + to_md(v.round(1), index=True) + "\n")
print(open(O + f"B_tablas{VAR}.md", encoding="utf-8").read())
