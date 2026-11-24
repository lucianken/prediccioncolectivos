import json, numpy as np, pandas as pd, psutil
psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
O = "data/ml/ruido_tramos_feriados/"
tot = json.load(open(O + "A_totales.json"))
R = pd.read_parquet(O + "_errores_interp.parquet", columns=["mode", "k", "e"]); R = R[R.k == 2]
d = pd.read_parquet("data/ml/v4/eval/eval_seen.parquet", columns=["observed_eta_s"])
pred = np.load("data/ml/v4_sub/runs/eval/full_s1_v4/path_path_eta_best_seen_20261121.pred.npy").astype(float)
r = d.observed_eta_s.values - pred; band = (d.observed_eta_s.values >= 180) & (d.observed_eta_s.values < 420)
rng = np.random.default_rng(1)
out = {}
def inc(res, noise):
    n = rng.choice(noise, size=len(res)); return float(np.abs(res + n).mean() - np.abs(res).mean())
for mode in ("obj", "ping"):
    e2 = R[R["mode"] == mode].e.values.astype(float); mae2 = np.abs(e2).mean()
    sc = tot[mode]["mae_ext"] / mae2; en = e2 * sc
    out[mode] = dict(escala_a_1_intervalo=sc, MAE_ruido=float(np.abs(en).mean()), P90_ruido=float(np.quantile(np.abs(en), .9)),
                     inc_banda=np.mean([inc(r[band], en) for _ in range(5)]), inc_global=np.mean([inc(r, en) for _ in range(5)]))
# hipotetico: lag de estampado por lote U[0,60) independiente en P y F
lag = rng.uniform(0, 60, 2_000_000) - rng.uniform(0, 60, 2_000_000)
out["hipotetico_lote_U0_60"] = dict(MAE_ruido=float(np.abs(lag).mean()), inc_banda=np.mean([inc(r[band], lag) for _ in range(5)]), inc_global=np.mean([inc(r, lag) for _ in range(5)]))
for s in (10, 20, 30):
    z = rng.normal(0, s / 0.7979, 2_000_000)
    out[f"gauss_MAE{s}"] = dict(MAE_ruido=float(np.abs(z).mean()), inc_banda=np.mean([inc(r[band], z) for _ in range(5)]), inc_global=np.mean([inc(r, z) for _ in range(5)]))
out["MAE_banda"] = float(np.abs(r[band]).mean()); out["MAE_global"] = float(np.abs(r).mean())
json.dump(out, open(O + "A_ruido_vs_mae.json", "w"), indent=1)
print(json.dumps(out, indent=1)); print(json.dumps({m: {k: v for k, v in tot[m].items() if k != "per"} for m in tot}, indent=1))
