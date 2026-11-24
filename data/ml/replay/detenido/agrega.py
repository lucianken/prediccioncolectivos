"""Deriva todas las variantes de la tabla de extrae.py y guarda sumas suficientes por (dia, linea, cfg) en stats.csv, y la matriz de
confusion de los coches marcados (listados en la base) en flags.csv. Uso: python agrega.py RUN_DIR OUT_DIR [workers]"""
import sys, itertools
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
import deriva as D

HERE = Path(__file__).parent
CLASIF = HERE.parent / "falsas" / "clasif.parquet"
KEY5 = ["day", "line", "stop_id", "t", "vehicle"]
NS, AS, TREATS, LOCS = (300, 600, 900), (20, 50, 100), ("a", "b1", "b2"), ("all", "cab", "mid")


def cfg_name(s):
    return "base" if s.get("N") is None else f"N{s['N']//60}_A{s['A']}_{s['treat']}_{s['loc']}"


def specs():
    out = [dict(N=None)]
    for N, A, tr, lc in itertools.product(NS, AS, TREATS, LOCS):
        out.append(dict(N=N, A=A, treat=tr, loc=lc))
    return out


def load_clasif():
    c = pd.read_parquet(CLASIF, columns=["day", "line", "stop_id", "t", "vehicle", "cause"])
    c["t"] = c.t.astype("int64"); c["vehicle"] = c.vehicle.astype(str)
    c["isC"] = c.cause.str.startswith("C ")
    return c[KEY5 + ["isC"]]


def prep(veh, clasif):
    veh = veh.copy()
    veh["t"] = veh.t.astype("int64"); veh["vehicle"] = veh.vehicle.astype(str)
    m = veh[KEY5].merge(clasif, on=KEY5, how="left")
    veh["inclas"] = m.isC.notna().to_numpy()
    veh["isC"] = m.isC.fillna(False).astype(bool).to_numpy()
    return veh


def stats(v, i):
    """Sumas suficientes de un (dia, linea) con la VARA CORREGIDA (metrics.py corrected=True): paso = tp2_s; falsas alarmas sobre los
    listados con ETA anunciado (eta0) <= 40 min, sin no verificables, sin los que ya pasaron; omision con tp2_s; vacio y proximo coche
    con real_next2_s excluyendo instantes no verificables. Las de la vara anterior van con sufijo _old."""
    s = {}
    l = v[v.listed]
    fa0 = l.tp_s.isna()
    s["fa_old_n"], s["fa_old_k"] = len(l), int(fa0.sum())
    fuera = l.eta0_s > 2400
    unv = ~fuera & l.tp2_s.isna() & l.unv
    e = l[~fuera & ~unv]
    fa = e.tp2_s.isna() & ~e.past
    s["fa_n"], s["fa_k"] = len(e), int(fa.sum())
    s["fa_fuera"], s["fa_unv"], s["fa_past"] = int(fuera.sum()), int(unv.sum()), int((e.tp2_s.isna() & e.past).sum())
    s["faC_k"] = int((fa & e.isC).sum())
    s["faI_k"] = int((fa & (e.fut_disp_m < 300)).sum())
    s["faUnk_k"] = int((fa & ~e.inclas).sum())
    for g in ("seguro", "puede_venir", "provisional"):
        s[f"lst_{g}"] = int((l.group == g).sum())
    s["seg_fa_k"] = int((fa & (e.group == "seguro")).sum())
    s["seg_n"] = int((e.group == "seguro").sum())
    p = v[v.tp2_s <= 600]
    vis = p[p.visible]
    s["om_n"], s["om_k"] = len(vis), int((~vis.listed).sum())
    b = vis[(vis.tp2_s >= 180) & (vis.tp2_s <= 420)]
    s["omb_n"], s["omb_k"] = len(b), int((~b.listed).sum())
    if len(p):
        first = p.loc[p.groupby(["stop_id", "t"]).tp2_s.idxmin()]
        fv = first[first.visible]
    else:
        fv = p
    s["om1_n"], s["om1_k"] = len(fv), int((~fv.listed).sum())
    r = i.real_next2_s
    u = i.unv_first_s
    unvi = u.notna() & (u < r.fillna(np.inf)) & (u <= 1200)
    ii = i[~unvi & (r <= 600)]
    s["vac_n"], s["vac_k"] = len(ii), int((~ii.has_seguro).sum())
    sb = i[~unvi & (r >= 180) & (r <= 420)]
    ann = sb.ann0_any_s
    has = ann.notna()
    err = (sb.real_next2_s - ann)[has]
    s["nb_n"], s["nb_has"] = len(sb), int(has.sum())
    s["nb_abs"] = float(err.abs().sum())
    s["nb_antes"], s["nb_desp"] = int((err < -60).sum()), int((err > 60).sum())
    s["inst_listed_sum"], s["inst_n"] = int(i.n_listed.sum()), len(i)
    return s


def flag_stats(v, spec):
    """Coches listados en la base que la regla marca: cuanto pasa realmente (costo) y cuanto es falsa alarma (beneficio)."""
    f = D.flags(v, spec) & v.listed.to_numpy()
    x = v[f]
    s = dict(n=len(x), pass10=int((x.tp2_s <= 600).sum()), pass37=int(((x.tp2_s >= 180) & (x.tp2_s <= 420)).sum()),
             pass40=int(x.tp2_s.notna().sum()), fa=int((x.tp2_s.isna() & ~x.past).sum()), faC=int((x.tp2_s.isna() & ~x.past & x.isC).sum()),
             immobile=int((x.fut_disp_m < 300).sum()), seguro=int((x.group == "seguro").sum()),
             seg_pass10=int(((x.group == "seguro") & (x.tp_s <= 600)).sum()))
    # los que pasan en <= 10 min: ¿cuanto antes/despues del paso real tardan? (nada: solo conteo)
    s["rem_lt500"] = int((x.rem_m < 500).sum())
    return s


def run_day(a):
    run_dir, day = a
    clasif = load_clasif()
    veh, inst = D.load(run_dir, days={day})
    veh = prep(veh, clasif)
    inst["t"] = inst.t.astype("int64")
    rows, frows = [], []
    for sp in specs():
        name = cfg_name(sp)
        v, i = D.derive(veh, inst, sp, name)
        for ln, vg in v.groupby("line"):
            ig = i[i.line == ln]
            rows.append(dict(day=day, line=ln, cfg=name, **stats(vg, ig)))
    return rows


def flags_day(a):
    run_dir, day = a
    clasif = load_clasif()
    veh, inst = D.load(run_dir, days={day})
    veh = prep(veh, clasif)
    inst["t"] = inst.t.astype("int64")
    vb, _ = D.derive(veh, inst, dict(N=None), "base")
    out = []
    for N, A, lc in itertools.product(NS, AS, LOCS):
        sp = dict(N=N, A=A, loc=lc, treat="a")
        for ln, vg in vb.groupby("line"):
            vg2 = vg.copy()
            out.append(dict(day=day, line=ln, N=N // 60, A=A, loc=lc, **flag_stats(vg2, sp)))
    return out


if __name__ == "__main__":
    run_dir, out_dir = sys.argv[1], Path(sys.argv[2])
    nw = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    days = sorted({p.name.split("_")[0] for p in Path(run_dir).glob("*.veh.parquet")})
    out_dir.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(nw) as ex:
        rs = list(ex.map(run_day, [(run_dir, d) for d in days]))
        pd.DataFrame([r for x in rs for r in x]).to_csv(out_dir / "stats.csv", index=False)
        fs = list(ex.map(flags_day, [(run_dir, d) for d in days]))
        pd.DataFrame([r for x in fs for r in x]).to_csv(out_dir / "flags.csv", index=False)
    print("listo", len(days), "dias")
