"""Ejemplos concretos por causa: traza de pings del coche alrededor del instante t. Uso: python ejemplos.py > ejemplos.txt"""
import sys, json, datetime as dt
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd
import falsas_diag as F
from prediccion.replay import core, run as R
from prediccion.replay.pinned import path_reference as PR

fa = pd.read_parquet(HERE / "clasif.parquet")
fa["c"] = fa.cause.str.split(" ").str[0]
bundle = PR.load_bundle(F.MODEL)
shapes_dir = str(F.ROOT.parent / "proyectoconsola/data/line_shapes")
PICK = [("R1", "39"), ("X2a", "124"), ("P", "106"), ("S", "92"), ("T1", "108"), ("C", "42"), ("X3", "106"), ("D", "124"), ("X2d", "132")]
hm = lambda ts: dt.datetime.utcfromtimestamp(ts - 3 * 3600).strftime("%H:%M:%S")
rng = np.random.default_rng(7)
for c, ln in PICK:
    x = fa[(fa.c == c) & (fa.line == ln) & (fa.eta0_s >= 120) & (fa.eta0_s <= 480)]
    if c == "P":
        x = fa[(fa.c == c) & (fa.line == ln) & (fa.eta0_s <= 120)]
    if x.empty:
        x = fa[(fa.c == c) & (fa.line == ln)]
    if x.empty:
        print("sin ejemplo", c, ln); continue
    r = x.iloc[int(rng.integers(len(x)))]
    per = R.load_day(r.day, {ln}, "//192.168.0.18/buffer/grabaciones", str(F.ROOT / "LABEL_LINE_MAP.json"), shapes_dir, with_trips=True)
    vs = list(per[ln].values())
    stops = core.prepare_stops(bundle, ln, shapes_dir, 40)
    with core.memoized():
        ctx = F.Ctx(bundle.lines[ln], vs, stops)
        st = ctx.stops[r.stop_id]
        v = ctx.by_id[r.vehicle]
        dist, perp, ok = ctx.vinfo(r.vehicle)
        info = json.loads((Path(shapes_dir) / f"{ln}.json").read_text(encoding="utf-8"))
        names = {s["id"]: s.get("name", "") for s in info.get("shapes", [])} if isinstance(info.get("shapes"), list) else {}
        sh = ctx.shapes
        print(f"\n### {c} linea {ln} {r.day} t={hm(r.t)} coche {r.vehicle} parada {r.stop_id} «{st.name}» ({st.cls})")
        print(f"grupo {r.group}, ETA anunciada {r.eta0_s:.0f} s, forma elegida {r.best_shape} ({sh[r.best_shape].name if r.best_shape in sh else ''}), forma ex post {r.true_shape} ({sh[r.true_shape].name if r.true_shape in sh else ''}), "
              f"recorridos que sirven la parada: {[(s, sh[s].name, round(d)) for s, d in st.serving.items()]}, trip_end_rel {r.trip_end_rel}, tp_any_rel {r.tp_any_rel}")
        kb = ctx.sidx.get(r.best_shape); kt = ctx.sidx.get(r.true_shape)
        j = int(np.searchsorted(v.ts, r.t, side="right")) - 1
        lo, hi = max(0, j - 3), min(len(v.ts), j + 14)
        print("hora | d elegida (m) | perp elegida | d ex post | perp ex post | vel")
        for i in range(lo, hi):
            mark = " <- ultimo ping <= t" if i == j else ""
            print(f"{hm(v.ts[i])} | {dist[kb, i]:.0f} | {perp[kb, i]:.0f} | " + (f"{dist[kt, i]:.0f} | {perp[kt, i]:.0f}" if kt is not None else "- | -") + f" | {v.speed[i]:.1f}{mark}")
        print("posicion de la parada sobre la forma elegida:", round(ctx.sproj(st, r.best_shape)[0]) if r.best_shape else "-")
        core.MEMO.clear()
