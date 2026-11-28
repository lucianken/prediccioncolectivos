"""Segunda pasada: para cada falsa alarma (base) calcula si el coche cruzo la parada (definicion estricta de la vara) entre su
ultimo ping y t, o en los 5 min previos a t. Escribe run_pasado/{dia}_{linea}.parquet con (stop_id, t, vehicle, cross_before_rel).
Uso: python pasado.py dias lineas workers"""
import sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
import falsas_diag as F
from prediccion.replay import core, run as R
from red import path_reference as PR

OUT = HERE / "run_pasado"


def task(a):
    day, ln = a
    F.lowprio()
    f = HERE / "run" / f"{day}_{ln}.parquet"
    o = OUT / f"{day}_{ln}.parquet"
    if o.exists() or not f.exists() or f.stat().st_size < 2000:
        return day, ln
    d = pd.read_parquet(f)
    fa = d[(d.variant == "base") & d.tp_s.isna()][["stop_id", "t", "vehicle"]].copy()
    bundle = PR.load_bundle(F.MODEL)
    shapes_dir = str(F.ROOT.parent / "proyectoconsola/data/line_shapes")
    per_line = R.load_day(day, {ln}, "//192.168.0.18/buffer/grabaciones", str(F.ROOT / "LABEL_LINE_MAP.json"), shapes_dir, with_trips=False)
    vs = list(per_line.get(ln, {}).values())
    stops = core.prepare_stops(bundle, ln, shapes_dir, 40)
    with core.memoized():
        ctx = F.Ctx(bundle.lines[ln], vs, stops)
        rel = []
        for r in fa.itertuples():
            st = ctx.stops[r.stop_id]
            v = ctx.by_id[r.vehicle]
            s = ctx.passes(st, r.vehicle)[0]
            j = int(np.searchsorted(v.ts, r.t, side="right")) - 1
            # cruce estricto en (ts_j - 300, t]
            m = s[(s > v.ts[j] - 300) & (s <= r.t)]
            rel.append(float(r.t - m.max()) if len(m) else np.nan)
        core.MEMO.clear()
    fa["cross_before_rel"] = rel
    fa.to_parquet(o)
    return day, ln


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    days = F.DAYS_ORDER.split(",")
    lines = F.LINES
    nw = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    with ProcessPoolExecutor(nw) as ex:
        for d, l in ex.map(task, [(d, l) for d in days for l in lines]):
            print("hecho", d, l, flush=True)
