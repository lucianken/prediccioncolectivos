"""Replay base con la regla nueva (racha final k=2/40 m/frac 0,6, en memoria) guardando inst y veh por (dia, linea).
Uso: python run_nueva.py OUT [workers]. Reanudable."""
import sys, time
from pathlib import Path
B = r"c:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos\data\ml\replay\barrido"
sys.path.insert(0, B)
import barrido_sentido as BS
from barrido_sentido import *   # noqa
from concurrent.futures import ProcessPoolExecutor
import pandas as pd

CFG = "t2n40f0.6"

def task(a):
    day, lines, out = a
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    out = Path(out)
    todo = [ln for ln in lines if not (out / f"{day}_{ln}.inst.parquet").exists()]
    if not todo:
        return day, 0
    t0 = time.time()
    bundle = PR.load_bundle(MODEL)
    shapes_dir = str(ROOT.parent / "proyectoconsola/data/line_shapes")
    per_line = R.load_day(day, set(todo), "//192.168.0.18/buffer/grabaciones", str(ROOT / "LABEL_LINE_MAP.json"), shapes_dir, with_trips=False)
    insts = core.instants_for_day(day, step_min=10)
    G.direction_from_history = make_rule(parse_cfg(CFG))
    for ln in todo:
        vs = list(per_line.get(ln, {}).values())
        if not vs:
            continue
        stops = core.prepare_stops(bundle, ln, shapes_dir, 40)
        with core.memoized():
            core.MEMO.sense.clear(); core.MEMO.lb_valid.clear(); core.MEMO.lb_scan.clear()
            rv, ri = core.evaluate_line(bundle, ln, vs, stops, insts, ("base",), day, ts_offset_s=core.CABA_TS_OFFSET_S)
            core.MEMO.clear()
        pd.DataFrame(rv).to_parquet(out / f"{day}_{ln}.veh.parquet")
        pd.DataFrame(ri).to_parquet(out / f"{day}_{ln}.inst.parquet")
        print(day, ln, f"{time.time()-t0:.0f}s", flush=True)
    return day, time.time() - t0

if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    nw = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    groups = [LINES[i:i + 2] for i in range(0, len(LINES), 2)]
    tasks = [(d, g, str(out)) for g in groups for d in DAYS.split(",")]
    with ProcessPoolExecutor(nw) as ex:
        for d, el in ex.map(task, tasks):
            print("hecho", d, f"{el:.0f}s", flush=True)
