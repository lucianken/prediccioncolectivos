"""Métricas de producto del replay de la 42 (viejo vs reexportado) por período y clase de parada, con IC bootstrap por
cluster (parada x ventana de 30 min). Salida: tablas markdown/json en la carpeta del run."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from prediccion.replay import metrics as M

DESPUES = ["2026-11-25", "2026-11-26", "2026-11-27"]
def load(run, tag):
    ii, vv = [], []
    for p in sorted(Path(run).glob(f"*_{tag}.inst.parquet")):
        day = p.name[:10]
        i = pd.read_parquet(p); v = pd.read_parquet(str(p).replace(".inst.", ".veh.")); i["day"] = day; v["day"] = day
        ii.append(i); vv.append(v)
    meta = pd.read_csv(Path(run) / "paradas.csv", dtype={"stop_id": str})
    inst, veh = pd.concat(ii, ignore_index=True), pd.concat(vv, ignore_index=True)
    for d in (inst, veh):
        d["stop_id"] = d.stop_id.astype(str)
    cls = meta.set_index("stop_id").cls
    inst["cls"] = inst.stop_id.map(cls); veh["cls"] = veh.stop_id.map(cls)
    for d in (inst, veh):
        d["cl"] = d.day + "|" + d.stop_id + "|" + (d.t // 1800).astype(str)
    return inst, veh

def one(inst, veh):
    real = inst.real_next2_s
    unv = M._unverifiable(inst, real)
    p10 = inst[(real <= 600) & ~unv]
    o = M.omissions(veh, corrected=True)
    f = M.false_alarms(veh, corrected=True)
    nb = M.next_bus(inst, "ann0_any_s", *M.BAND, corrected=True)
    return {"n_inst": len(inst), "n_paso10": len(p10), "listados_x_inst": float(inst.n_listed.mean()) if len(inst) else np.nan,
            "sin_lista_pct": float(100 * (p10.n_listed == 0).mean()) if len(p10) else np.nan,
            "sin_aviso_firme_pct": float(100 * (~p10.has_seguro).mean()) if len(p10) else np.nan,
            "no_anunciado_pct": o["omision_con_invisibles_pct"], "n_pasan10": o["pasan"],
            "fantasma_pct": f["falsa_alarma_pct"], "n_listados_eval": f["n_evaluados"],
            "mae_3_7_s": nb["mae_s"], "n_3_7": nb["n"], "sin_anuncio_3_7_pct": nb["sin_anuncio_pct"],
            "antes_pct": nb["antes_pct"], "despues_pct": nb["despues_pct"]}

def boot(inst, veh, B=300, seed=0):
    rng = np.random.default_rng(seed)
    gi = {k: g.index.values for k, g in inst.groupby("cl")}
    gv = {k: g.index.values for k, g in veh.groupby("cl")}
    keys = np.array(sorted(gi)); res = []
    for _ in range(B):
        ks = rng.choice(keys, len(keys))
        ii = np.concatenate([gi[k] for k in ks]); vi = np.concatenate([gv[k] for k in ks if k in gv] or [np.empty(0, int)])
        res.append(one(inst.loc[ii], veh.loc[vi]))
    r = pd.DataFrame(res)
    return {c: (float(r[c].quantile(.025)), float(r[c].quantile(.975))) for c in r.columns if not c.startswith("n_")}

def table(run, B=300):
    out = []
    for tag, nombre in (("old", "viejo"), ("new", "reexport")):
        inst, veh = load(run, tag)
        for per, days in (("desde 25/11", DESPUES), ("control 17-24/11", [d for d in inst.day.unique() if d not in DESPUES])):
            for grp, cl in (("tramo nuevo (15)", ["nueva_fuera", "nueva_cerca"]), ("  >45 m del viejo (9)", ["nueva_fuera"]),
                            ("  <=45 m del viejo (6)", ["nueva_cerca"]), ("resto (40)", ["resto"])):
                i = inst[inst.day.isin(days) & inst.cls.isin(cl)].reset_index(drop=True)
                v = veh[veh.day.isin(days) & veh.cls.isin(cl)].reset_index(drop=True)
                if not len(i): continue
                r = one(i, v); ci = boot(i, v, B) if len(i) else {}
                out.append(dict(bundle=nombre, periodo=per, grupo=grp, **r, ci=ci))
    return out

if __name__ == "__main__":
    run = sys.argv[1]; B = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    t = table(run, B)
    (Path(run) / "metricas.json").write_text(json.dumps(t, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    def f(x, nd=1): return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"
    for r in t:
        c = r["ci"]
        g = lambda k, nd=1: f"{f(r[k], nd)} [{f(c[k][0], nd)}, {f(c[k][1], nd)}]" if k in c else f(r[k], nd)
        print(f"{r['bundle']:8s} {r['periodo']:17s} {r['grupo']:22s} inst={r['n_inst']:5d} paso10={r['n_paso10']:4d} list/inst={g('listados_x_inst',2)} "
              f"sinlista={g('sin_lista_pct')} sinfirme={g('sin_aviso_firme_pct')} noanun={g('no_anunciado_pct')} (n={r['n_pasan10']}) "
              f"fant={g('fantasma_pct')} (n={r['n_listados_eval']}) mae37={g('mae_3_7_s',0)} (n={r['n_3_7']}) antes={f(r['antes_pct'])}")
