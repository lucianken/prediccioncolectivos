"""Clasifica las falsas alarmas (variante base listadas sin paso en 40 min) por causa y arma las tablas.
Uso: python clasifica.py RUN_DIR [salida_md_tablas]"""
import sys, glob
from pathlib import Path
import numpy as np
import pandas as pd

HZ = 2400.0
BANDS = [(0, 120, "0-2"), (120, 180, "2-3"), (180, 300, "3-5"), (300, 420, "5-7"), (420, 600, "7-10"), (600, 1200, "10-20"),
         (1200, 2400, "20-40"), (2400, 1e9, ">40")]
CAUSES = [
    "X0 ETA anunciado > 40 min (fuera del horizonte)",
    "X3 parada en el ultimo tramo del shape: el coche llega pero el cruce no existe por construccion",
    "X2a pasa en 40 min durante un hueco de GPS > 10 min (la vara no interpola)",
    "X2b pasa en 40 min con salto > 5 km entre pings (la vara lo descarta)",
    "X2c pasa en 40 min con pings no compatibles (> 45 m) en el cruce",
    "X2d pasa en 40 min por un shape no asociado a la parada",
    "X1 pasa despues de 40 min en el mismo viaje (ETA subestimado)",
    "X4 alcanza la parada sobre el shape elegido pero ningun par de pings consecutivos compatibles la cruza",
    "P el coche ya cruzo la parada antes de t (ping desactualizado)",
    "S sentido contrario (el recorrido ex post va en el otro sentido)",
    "R1 otro ramal: no sirve la parada (tramo compartido y diverge)",
    "T1 el viaje termina antes de la parada, a mitad de recorrido (fraccionado / corta / se pierde)",
    "T2 el viaje termina antes de la parada, a < 1,5 km del final del recorrido",
    "C coche en cabecera / sin viaje: arranca despues de 40 min o nunca",
    "G hueco de GPS > 10 min en el horizonte (no se sabe)",
    "D desvio / fuera de shape cerca de la parada",
    "O otro: sirve la parada, sigue el viaje y no llega en 40 min",
]
CX0, CX3, CX2a, CX2b, CX2c, CX2d, CX1, CX4, CP, CS, CR1, CT1, CT2, CC, CG, CD, CO = CAUSES


def classify(r):
    if r.eta0_s > HZ:
        return CX0
    tp = r.tp_any_rel
    L, ds, dm = (r.len_best, r.ds_best, r.dmax_best) if not np.isnan(r.ds_best) else (r.len_true, r.ds_true, r.d_true_end)
    if not np.isnan(L) and not np.isnan(ds) and L - ds <= 100 and not np.isnan(dm) and dm >= ds - 100:
        return CX3
    lr = r.loose_rel
    if not np.isnan(lr) and lr <= HZ:
        if r.loose_gap > 600:
            return CX2a
        if r.loose_jump > 5000:
            return CX2b
        return CX2c
    if not np.isnan(r.geo_rel) and r.geo_rel <= HZ:
        return CX2d
    if not np.isnan(tp) and HZ < tp <= 5400 and (np.isnan(r.trip_end_rel) or tp <= r.trip_end_rel or not r.in_trip):
        return CX1
    if not np.isnan(r.cross_before_rel) and r.cross_before_rel <= 300:
        return CP
    if r.true_shape and r.true_dir_ne_serving:
        return CS
    if r.true_shape and not r.true_serves:
        return CR1
    if (r.reach_best is True or r.reach_best == 1.0) and not np.isnan(r.near_best_min_m) and r.near_best_min_m <= 250:
        return CX4
    if r.true_shape and r.trip_wait_s > 0 and (np.isnan(r.trip_start_rel) or r.trip_start_rel > HZ):
        return CC
    if r.true_shape and r.trip_end_rel <= HZ and not np.isnan(r.ds_true) and r.d_true_end < r.ds_true - 50:
        return CT1 if (r.len_true - r.d_true_end) > 1500 else CT2
    if not r.true_shape:
        return CC
    if r.max_gap_fut > 600:
        return CG
    if r.min_perp_h_end > 100 or (not np.isnan(r.near_best_min_m) and r.near_best_min_m > 300) or r.n_fut == 0:
        return CD
    return CO



def band(x):
    for lo, hi, n in BANDS:
        if lo <= x < hi:
            return n
    return ">40"


def load(run):
    fs = sorted(glob.glob(str(Path(run) / "*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs if Path(f).stat().st_size > 2000], ignore_index=True)
    return d


def main():
    run = sys.argv[1]
    d = load(run)
    b = d[d.variant == "base"].copy()
    ram = d[d.variant == "ramal"]
    b["fa"] = b.tp_s.isna()
    b["band"] = b.eta0_s.map(band)
    fa = b[b.fa].copy()
    fa["cause"] = [classify(r) for r in fa.itertuples()]
    fa["resuelve_ramal"] = fa.listed_ramal.astype(bool).map(lambda x: not x)
    fa["n_hist1"] = fa.n_hist <= 1
    b.loc[fa.index, "cause"] = fa.cause
    out = Path(run).parent / "clasif.parquet"
    fa.to_parquet(out)
    n_l, n_fa = len(b), len(fa)
    pr = []
    pr.append(f"listados base: {n_l}; falsas alarmas: {n_fa} ({100*n_fa/n_l:.2f}%); pares (dia,linea): {b.groupby(['day','line']).ngroups}; dias: {b.day.nunique()}")
    pr.append(f"listados ramal: {len(ram)}; FA ramal: {ram.tp_s.isna().sum()} ({100*ram.tp_s.isna().mean():.2f}%)")
    t = fa.groupby("cause").agg(n=("fa", "size"), ram=("resuelve_ramal", "mean"), prov=("group", lambda s: (s == "provisional").mean()),
                                  pv=("group", lambda s: (s == "puede_venir").mean()), h1=("n_hist1", "mean")).reindex(CAUSES).fillna(0)
    t["pct_fa"] = 100 * t.n / n_fa
    t["pp_listados"] = 100 * t.n / n_l
    f37 = fa[fa.band.isin(["3-5", "5-7"])]
    t["pct_fa_3_7"] = (100 * f37.groupby("cause").size() / len(f37)).reindex(CAUSES).fillna(0)
    print("\n".join(pr))
    print(t.round(2).to_string())
    print("\nFA por banda (eta anunciada):")
    g = b.groupby("band").agg(n=("fa", "size"), fa=("fa", "mean"))
    g = g.reindex([x[2] for x in BANDS])
    g["fa"] *= 100
    print(g.round(1).to_string())
    print("\ncausas por banda (% de las FA de la banda):")
    ct = pd.crosstab(fa.cause, fa.band, normalize="columns").reindex(CAUSES).fillna(0)[[x[2] for x in BANDS if x[2] in fa.band.unique()]] * 100
    print(ct.round(1).to_string())
    print("\nFA % por linea y causas (% de las FA de la linea):")
    gl = b.groupby("line").agg(n=("fa", "size"), fa=("fa", "mean"))
    gl["fa"] *= 100
    ctl = pd.crosstab(fa.line, fa.cause, normalize="index") * 100
    ctl.columns = [c.split(" ")[0] for c in ctl.columns]
    print(pd.concat([gl, ctl], axis=1).round(1).to_string())
    print("\nFA % por grupo:")
    gg = b.groupby("group").agg(n=("fa", "size"), fa=("fa", "mean"))
    gg["fa"] *= 100
    print(gg.round(1).to_string())
    print("\nFA % por clase de parada:")
    gs = b.groupby("stop_class").agg(n=("fa", "size"), fa=("fa", "mean"))
    gs["fa"] *= 100
    print(gs.round(1).to_string())
    print("\nFA % por n_hist==1 / <=2 / resto:")
    bb = b.copy()
    bb["h"] = np.where(bb.n_hist <= 1, "1 ping", np.where(bb.n_hist <= 2, "2 pings", ">2"))
    # n_hist solo esta en FA; para el denominador no sirve -> solo composicion en FA
    print(fa.assign(h=np.where(fa.n_hist <= 1, "1 ping", np.where(fa.n_hist <= 2, "2 pings", ">2"))).h.value_counts(normalize=True).round(3).to_string())


if __name__ == "__main__":
    main()
