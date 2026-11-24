"""Comprueba que la base derivada de extrae.py reproduce core.evaluate_line (variante base): mismos listados y mismas metricas."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np, pandas as pd
import extrae as E
from deriva import derive
from prediccion.replay import core, run as R
from prediccion.replay.pinned import path_reference as PR

day, ln, step = sys.argv[1], sys.argv[2], int(sys.argv[3])
b = PR.load_bundle(E.MODEL)
pl = R.load_day(day, {ln}, "//192.168.0.18/buffer/grabaciones", str(E.ROOT / "LABEL_LINE_MAP.json"), E.SHAPES_DIR, with_trips=False)
vs = list(pl[ln].values())
stops = core.prepare_stops(b, ln, E.SHAPES_DIR, 10)
insts = core.instants_for_day(day, step_min=step)
with core.memoized():
    rv0, ri0 = core.evaluate_line(b, ln, vs, stops, insts, ("base",), day)
    rv, ri = E.evaluate_multi(b, ln, vs, stops, insts, day)
v0, i0 = pd.DataFrame(rv0), pd.DataFrame(ri0)
v, i = derive(pd.DataFrame(rv), pd.DataFrame(ri), dict(N=None))
k = ["stop_id", "t", "vehicle"]
a = v0[v0.listed].set_index(k)[["eta_s", "tp_s"]].sort_index()
c = v[v.listed].set_index(k)[["eta_s", "tp_s"]].sort_index()
print("listados", len(a), len(c), "iguales idx", a.index.equals(c.index))
print("tp2 nan iguales", bool((v0.set_index(k).loc[a.index].tp2_s.isna().to_numpy() == v.set_index(k).loc[a.index].tp2_s.isna().to_numpy()).all()), "unv", int(v0.unv.sum()), int(v.unv.sum()), "past", int(v0.past.sum()), int(v.past.sum()), "n_tp2", int(v0.tp2_s.notna().sum()), int(v.tp2_s.notna().sum()))
print("eta max diff", float((a.eta_s - c.eta_s).abs().max()), "tp nan iguales", bool((a.tp_s.isna() == c.tp_s.isna()).all()))
m = i0.set_index(["stop_id", "t"]).join(i.set_index(["stop_id", "t"]), rsuffix="_d")
for col in ["has_seguro", "ann0_any_s", "ann_any_s", "n_listed", "n_shown_status", "real_next_s"]:
    x, y = m[col], m[col + "_d"] if col + "_d" in m else None
    print(col, "OK" if y is not None and ((x == y) | (x.isna() & y.isna())).all() else "DIFF")
print("filas veh core", len(v0), "derivada", len(v))
print("flag ejemplo ext notna", float(pd.DataFrame(rv).ext600.notna().mean()))
