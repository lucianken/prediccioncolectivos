"""C: feriados vs mismo dia de la semana no feriado vs domingos (muestra natural por dia, path_v4_l1_s1)."""
import sys, json
sys.path.insert(0, "data/ml/ruido_tramos_feriados/scripts"); sys.path.insert(0, ".")
from mdutil import to_md
import numpy as np, pandas as pd, pyarrow as pa, pyarrow.parquet as pq, psutil
p = psutil.Process(); p.nice(psutil.IDLE_PRIORITY_CLASS); p.cpu_affinity(list(range(8)))
O = "data/ml/ruido_tramos_feriados/"
M = pd.read_parquet(O + "muestra_dias.parquet", columns=["day", "line", "shape_id", "ts_p", "dow", "dist_along_m", "dist_remaining_m", "observed_eta_s", "pred", "n_valid_day"])
M["err"] = M.observed_eta_s - M.pred; M["ae"] = M.err.abs(); M["band"] = (M.observed_eta_s >= 180) & (M.observed_eta_s < 420)
M["hora"] = ((M.ts_p - 3 * 3600) % 86400) / 3600.0
M["dowd"] = pd.to_datetime(M.day).dt.dayofweek
FER = {"2026-08-17": "feriado (Paso a la Inmortalidad de San Martin, lunes)", "2026-10-12": "feriado (Dia del Respeto a la Diversidad Cultural, lunes)"}
VAL0, VAL1 = "2026-09-15", "2026-10-14"
M["fer"] = M.day.isin(FER)
M["tipo"] = np.where(M.fer, "FERIADO", np.select([M.dowd == 6, M.dowd == 5, M.dowd == 0], ["domingo", "sabado", "lunes no feriado"], "habil Mar-Vie"))
M["periodo"] = np.where((M.day >= VAL0) & (M.day <= VAL1), "val (fuera de muestra)", "train (en muestra)")


def stats(g):
    e = g.err.values
    return pd.Series(dict(n=len(g), MAE=g.ae.mean(), sesgo=e.mean(), P90=np.percentile(g.ae, 90), antes60=100 * (e < -60).mean(), despues60=100 * (e > 60).mean()))


pd_ = M.groupby("day").apply(stats).add_prefix("glob_").join(M[M.band].groupby("day").apply(stats).add_prefix("b37_"))
pd_["filas_validas_dia"] = M.groupby("day").n_valid_day.first(); pd_["dow"] = pd.to_datetime(pd_.index).dayofweek
pd_["tipo"] = M.groupby("day").tipo.first(); pd_["periodo"] = M.groupby("day").periodo.first()
pd_.to_csv(O + "C_por_dia.csv")
rows = []
for per, sub in M.groupby("periodo"):
    for tipo, g in sub.groupby("tipo"):
        for vara, gg in (("banda 3-7", g[g.band]), ("global", g)):
            s = stats(gg); rows.append(dict(periodo=per, tipo=tipo, dias=g.day.nunique(), vara=vara, **s.round(2).to_dict()))
T = pd.DataFrame(rows)
rng = np.random.default_rng(0)
B = M[M.band].copy(); B["cl"] = B.day + "|" + B.line.astype(str) + "|" + (B.ts_p // 1800).astype(str)


def boot(g1, g2, nrep=1000):
    parts = []
    for g in (g1, g2):
        c, u = pd.factorize(g.cl); k = len(u)
        parts.append((np.bincount(c, weights=g.ae.values, minlength=k), np.bincount(c, weights=g.err.values, minlength=k),
                      np.bincount(c, minlength=k).astype(float), k))
    out = []
    for _ in range(nrep):
        r = []
        for (sa, se, cn, k) in parts:
            i = rng.integers(0, k, k); n = cn[i].sum(); r.append((sa[i].sum() / n, se[i].sum() / n))
        out.append((r[0][0] - r[1][0], r[0][1] - r[1][1]))
    return np.percentile(np.array(out), [2.5, 50, 97.5], axis=0)


comps = []
for fd, nm in (("2026-10-12", "val"), ("2026-08-17", "train")):
    f = B[B.day == fd]
    refs = {"lunes no feriado": B[(B.tipo == "lunes no feriado") & (B.periodo.str.startswith(nm))],
            "domingos": B[(B.tipo == "domingo") & (B.periodo.str.startswith(nm))],
            "habiles Mar-Vie": B[(B.tipo == "habil Mar-Vie") & (B.periodo.str.startswith(nm))]}
    for rn, r in refs.items():
        if len(r) == 0:
            continue
        q = boot(f, r)
        comps.append(dict(feriado=fd, periodo=nm, contra=rn, dias_ref=r.day.nunique(), MAE_fer=f.ae.mean(), MAE_ref=r.ae.mean(), dif_MAE=f.ae.mean() - r.ae.mean(),
                          IC95_lo=q[0][0], IC95_hi=q[2][0], sesgo_fer=f.err.mean(), sesgo_ref=r.err.mean(), dif_sesgo=f.err.mean() - r.err.mean(),
                          IC_sesgo_lo=q[0][1], IC_sesgo_hi=q[2][1], antes60_fer=100 * (f.err < -60).mean(), antes60_ref=100 * (r.err < -60).mean(),
                          despues60_fer=100 * (f.err > 60).mean(), despues60_ref=100 * (r.err > 60).mean()))
C = pd.DataFrame(comps)
vd = pd_[pd_.periodo == "val (fuera de muestra)"]
vnf = vd[(vd.tipo != "FERIADO")]
vwk = vnf[vnf.dow < 5]


def estandarizar(fd, ref):
    f = B[B.day == fd].copy(); r = ref.copy()
    for d_ in (f, r):
        d_["cel"] = d_.line.astype(str) + "|" + (d_.hora // 4).astype(int).astype(str)
    w = f.cel.value_counts(normalize=True); rm = r.groupby("cel").ae.mean(); rb = r.groupby("cel").err.mean()
    common = w.index.intersection(rm.index); ww = w[common] / w[common].sum()
    fm = f[f.cel.isin(common)]
    return dict(cobertura=float(w[common].sum()), MAE_ref_estandarizado=float((ww * rm[common]).sum()), sesgo_ref_estandarizado=float((ww * rb[common]).sum()),
                MAE_fer_en_celdas=float(fm.ae.mean()), sesgo_fer_en_celdas=float(fm.err.mean()))


std = {}
for fd, nm in (("2026-10-12", "val"), ("2026-08-17", "train")):
    for rn, mask in (("lunes no feriado", B.tipo == "lunes no feriado"), ("domingos", B.tipo == "domingo")):
        r = B[mask & B.periodo.str.startswith(nm)]
        if len(r):
            std[f"{fd} vs {rn}"] = estandarizar(fd, r)
from prediccion.models.path_eta import predict_path
from prediccion.v2.make_eval import valid_mask
import torch
torch.set_num_threads(4)
CK = "data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt"; cf = {}
for fd in FER:
    t = pq.read_table(f"data/ml/v4/daily/{fd}.parquet")
    ok = np.flatnonzero(valid_mask(t)); sel = np.sort(np.random.default_rng(int(fd.replace("-", ""))).choice(ok, 100000, replace=False))
    s = t.take(pa.array(sel)); tmp = O + "_tmp/f.parquet"
    res = {}
    for nm, dowv in (("dow=lunes (como hoy)", None), ("dow=domingo", 6)):
        s2 = s if dowv is None else s.set_column(s.schema.get_field_index("dow"), "dow", pa.array(np.full(len(s), dowv, np.int8)))
        pq.write_table(s2, tmp); pr = predict_path(tmp, CK, len(s2))
        eta = np.asarray(s["observed_eta_s"]).astype(float); err = eta - pr; band = (eta >= 180) & (eta < 420)
        res[nm] = dict(MAE_global=float(np.abs(err).mean()), sesgo_global=float(err.mean()), antes60_global=float(100 * (err < -60).mean()), despues60_global=float(100 * (err > 60).mean()),
                       MAE_b37=float(np.abs(err[band]).mean()), sesgo_b37=float(err[band].mean()), antes60_b37=float(100 * (err[band] < -60).mean()), despues60_b37=float(100 * (err[band] > 60).mean()), n_b37=int(band.sum()))
    cf[fd] = res
out = dict(feriados=FER, comparaciones=C.round(2).to_dict("records"), estandarizado=std, contrafactual_dow=cf,
           variabilidad_val_dias_no_feriados=dict(MAE_b37_media=float(vnf.b37_MAE.mean()), sd=float(vnf.b37_MAE.std()), min=float(vnf.b37_MAE.min()), max=float(vnf.b37_MAE.max())),
           variabilidad_val_habiles=dict(MAE_b37_media=float(vwk.b37_MAE.mean()), sd=float(vwk.b37_MAE.std()), min=float(vwk.b37_MAE.min()), max=float(vwk.b37_MAE.max()), n=int(len(vwk))))
json.dump(out, open(O + "C_resultados.json", "w"), indent=1, default=float)
with open(O + "C_tablas.md", "w", encoding="utf-8") as f:
    f.write("### por dia\n\n" + to_md(pd_.reset_index().round(1)) + "\n\n### por tipo de dia\n\n" + to_md(T) + "\n\n### comparaciones\n\n" + to_md(C.round(2)) + "\n\n"
            + json.dumps({k: out[k] for k in ("estandarizado", "contrafactual_dow", "variabilidad_val_dias_no_feriados", "variabilidad_val_habiles")}, indent=1) + "\n")
print("ok")
