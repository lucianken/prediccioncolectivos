import sys
from pathlib import Path
ROOT = Path(r"c:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos")
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from prediccion.replay import run as R
from red import path_reference as PR
S = Path(r"C:\Users\LK\AppData\Local\Temp\claude\586fec94495e776d\a0d2e010-c63d-45d0-842b-630e83e620e9\scratchpad")
LINES = "26,39,42,50,92,106,107,108,124,132,151,168".split(",")


def job(day):
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    d = pd.read_pickle(S / "detail.pkl")
    d = d[d.day == day]
    bundle = PR.load_bundle(str(ROOT / "data/ml/export/path_v2c_l1_s1"))
    per_line = R.load_day(day, set(LINES), "//192.168.0.18/buffer/grabaciones", str(ROOT / "LABEL_LINE_MAP.json"),
                          str(ROOT.parent / "proyectoconsola/data/line_shapes"))
    res = []
    for ln, g in d.groupby("line"):
        shapes = bundle.lines[ln]
        vs = per_line[ln]
        for r in g.itertuples():
            v = vs[r.vid]
            sh = shapes[r.cross_shape]
            j = int(np.searchsorted(v.ts, r.t, side="right")) - 1
            ps = [(float(v.ts[i]), float(v.lat[i]), float(v.lon[i])) for i in range(int(np.searchsorted(v.ts, v.ts[j] - 900)), j + 1)]
            perpS = np.array([sh.project(p[1], p[2])[1] for p in ps])
            anyp = np.array([min(s_.project(p[1], p[2])[1] for s_ in shapes.values()) for p in ps])
            offS = perpS > 45
            o = dict(idx=r.Index, w_n=len(ps), w_offS=int(offS.sum()), w_off_any=int((offS & (anyp > 45)).sum()),
                     w_off_other=int((offS & (anyp <= 45)).sum()))
            fn = int(np.argmax(~offS)) if (~offS).any() else len(ps)
            o["pat_prefix"] = bool(fn < len(ps) and offS[:fn].all() and not offS[fn:].any())
            o["n_prefix_off"] = fn
            tr = [a for a, b, s_ in v.trips if a <= ps[-1][0] <= b]
            o["tss"] = float(ps[-1][0] - tr[0]) if tr else np.nan
            o["first_ping_of_day_s"] = float(ps[-1][0] - v.ts[0])
            o["t_on_S_s"] = float(ps[-1][0] - ps[fn][0]) if fn < len(ps) else 0.0
            res.append(o)
    return d.join(pd.DataFrame(res).set_index("idx"))


if __name__ == "__main__":
    days = ["2026-09-15", "2026-09-17", "2026-09-19", "2026-09-20", "2026-10-04", "2026-10-06"]
    with ProcessPoolExecutor(2) as ex:
        parts = list(ex.map(job, days))
    pd.concat(parts).to_pickle(S / "detail2.pkl")
    print("ok")
