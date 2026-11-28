"""Recalcula la verdad (tp2_s, unv, past) de los crudos de consistencia.py con la verdad vigente de core.py (cruce solo si el
viaje ex post del coche tiene la parada en su lista), SIN volver a predecir. Los ETA anunciados no dependen de la verdad.
python -m prediccion.replay.consistencia_verdad IN_DIR OUT_DIR [workers]"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.replay import core, run as RUN
from red import path_reference as PR

ROOT = Path(__file__).resolve().parents[2]
MODEL = str(ROOT / "data/ml/export/path_v3_l1_s1")
SHAPES = str(ROOT.parent / "proyectoconsola/data/line_shapes")
DATA = "//192.168.0.18/buffer/grabaciones"
LMAP = str(ROOT / "LABEL_LINE_MAP.json")


def do(a):
    f, out = a
    f, out = Path(f), Path(out)
    dst = out / f.name
    if dst.exists():
        return f.name, 0.0
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    t0 = time.time()
    df = pd.read_parquet(f)
    if df.empty:
        df.to_parquet(dst)
        return f.name, 0.0
    day, line = f.stem.split("_")
    bundle = PR.load_bundle(MODEL)
    per_line = RUN.load_day(day, {line}, DATA, LMAP, SHAPES)
    vs = list(per_line.get(line, {}).values())
    ids = set(df.stop.astype(str))
    stops = [s for s in core.prepare_stops(bundle, line, SHAPES, 10**6) if str(s.id) in ids]
    with core.memoized():
        cc = core.compat_for(vs, bundle.lines[line])
        stats = {}
        passes, passes2 = core._passes(vs, stops, bundle.lines[line], cc, stats)
        core.MEMO.clear()
    tp2 = np.full(len(df), np.nan)
    unv = np.zeros(len(df), bool)
    past = np.zeros(len(df), bool)
    for (sid, t), g in df.groupby(["stop", "t"]):
        live = {}
        for v in vs:
            j = int(np.searchsorted(v.ts, t, side="right")) - 1
            if j >= 0 and t - v.ts[j] <= core.HISTORY_S:
                live[v.vid] = (j, 0)
        a, b, u, p = core.truth_at(vs, live, passes, passes2, str(sid), t)
        for i, vid in zip(g.index, g.veh):
            tp2[i] = b.get(vid, np.nan)
            unv[i] = vid in u
            past[i] = vid in p
    df["tp2_s"], df["unv"], df["past"] = tp2, unv, past
    df.to_parquet(dst)
    stats["n_coches"] = len(vs)
    (out / f"{f.stem}.truth_stats.json").write_text(json.dumps(stats), encoding="utf-8")
    return f.name, time.time() - t0


if __name__ == "__main__":
    inp, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    files = sorted(p for p in inp.glob("*.parquet"))
    with ProcessPoolExecutor(w) as ex:
        for n, el in ex.map(do, [(p, out) for p in files]):
            print(n, f"{el:.0f}s", flush=True)
    print("FIN", flush=True)
