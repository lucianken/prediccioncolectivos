"""Tablas de V4_PRODUCCION.md. python data/ml/replay/v4prod/reporte.py  (desde prediccion colectivos/, PYTHONPATH=.)"""
import json, sys, glob
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from prediccion.replay import metrics as M
from prediccion.replay.report_vara import flat
R = Path("data/ml/replay")
DAYS = ["2026-09-15","2026-09-16","2026-09-17","2026-09-18","2026-09-19","2026-09-20","2026-10-03","2026-10-04","2026-10-06","2026-10-08"]
L118 = open(R/"v4prod/lines_118.txt").read().split(",")
OLD12, OLD46 = L118[:12], L118[:46]
NEW72 = L118[46:]
EXTRA = ["49","97","119","153","154","163","185","193","164"]
KEY = ["line","day","stop_id","t"]

def load_line(dirs, ln, days=DAYS):
    I, V = [], []
    for d in dirs:
        for day in days:
            pi, pv = Path(d)/f"{day}_{ln}.inst.parquet", Path(d)/f"{day}_{ln}.veh.parquet"
            if pi.exists() and pv.exists():
                I.append(pd.read_parquet(pi)); V.append(pd.read_parquet(pv))
    if not I: return None, None
    i = pd.concat(I, ignore_index=True); v = pd.concat(V, ignore_index=True)
    i = i[i.variant == "base"].drop_duplicates(KEY); v = v[v.variant == "base"].drop_duplicates(KEY + ["vehicle"])
    return i, v

def load_v3(ln):
    if ln in OLD12:
        # 12 líneas viejas: corrida con la vara vigente (verdad por recorrido ex post recalculada); 3 de oct. está en run_cs_xp
        i1, v1 = load_line([R/"vara/run_base_xp"], ln)
        i2, v2 = load_line([R/"vara/run_cs_xp"], ln, ["2026-10-03"])
        parts = [(i, v) for i, v in ((i1, v1), (i2, v2)) if i is not None]
        return pd.concat([p[0] for p in parts], ignore_index=True), pd.concat([p[1] for p in parts], ignore_index=True)
    return load_line([R/"v4prod/v3"], ln)

def pair(i3, v3, i4, v4):
    k3 = i3[KEY]; k4 = i4[KEY]
    com = k3.merge(k4, on=KEY)
    def cut(i, v):
        ii = i.merge(com, on=KEY); vv = v.merge(com, on=KEY)
        return ii, vv
    return cut(i3, v3) + cut(i4, v4)

def row(i, v):
    x = flat(i, v, True)
    return dict(n=x["n_band"], mae=x["mae"], antes=x["antes"], desp=x["desp"], fa=x["fa"], om=x["om"], vacio=x["vacio"],
                fa_seg=x["fa_seg"], listados=x["listados"], n_vacio=x["vacio_n"], sin_anuncio=x["sin_anuncio"])

if __name__ == "__main__":
    out = {}
    rows4, rows3, rowsp = {}, {}, {}
    pooled = {}   # para agregados
    LL = sys.argv[1].split(",") if len(sys.argv) > 1 else L118 + EXTRA
    for ln in LL:
        i4, v4 = load_line([R/"v4prod/v4"], ln)
        if i4 is None: print("sin datos v4", ln); continue
        rows4[ln] = row(i4, v4)
        rows4[ln]["n_inst"] = len(i4); rows4[ln]["n_dias"] = i4.day.nunique(); rows4[ln]["n_stops"] = i4.stop_id.nunique()
        if ln in OLD46:
            i3, v3 = load_v3(ln)
            if i3 is None: print("sin datos v3", ln); continue
            a3, b3, a4, b4 = pair(i3, v3, i4, v4)
            rowsp[ln] = (row(a3, b3), row(a4, b4), len(a3))
            # chequeo de alineación: la verdad no depende del modelo
            m = a3.merge(a4, on=KEY, suffixes=("3", "4"))
            rowsp[ln][1]["chk_real_dif"] = int((m.real_next2_s3.fillna(-1) != m.real_next2_s4.fillna(-1)).sum())
            pooled.setdefault("12" if ln in OLD12 else "34", []).append((a3, b3, a4, b4))
        print(ln, flush=True)
    agg = {}
    for g, lst in pooled.items():
        A3 = pd.concat([x[0] for x in lst]); B3 = pd.concat([x[1] for x in lst]); A4 = pd.concat([x[2] for x in lst]); B4 = pd.concat([x[3] for x in lst])
        agg[g] = (row(A3, B3), row(A4, B4), len(A3))
        if g == "12" and "34" in pooled:
            pass
    allp = [x for g in pooled.values() for x in g]
    A3 = pd.concat([x[0] for x in allp]); B3 = pd.concat([x[1] for x in allp]); A4 = pd.concat([x[2] for x in allp]); B4 = pd.concat([x[3] for x in allp])
    agg["46"] = (row(A3, B3), row(A4, B4), len(A3))
    pd.to_pickle(dict(rows4=rows4, rowsp=rowsp, agg=agg), R/"v4prod/resumen.pkl")
    print("listo")
