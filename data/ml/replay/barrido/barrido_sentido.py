"""Barrido de la regla de sentido (racha final) sobre el replay de produccion, variante base, modelo path_v3_l1_s1.
Reemplaza en memoria pinned.geo_assign.direction_from_history; no toca pinned/ ni v2/geo_assign.py.
Uso: python barrido_sentido.py OUT_DIR "cfg1;cfg2;..." [dias] [lineas] [workers]
cfg: base | t{minpings}n{netforward_m}f{frac}  y opcional @N (historial recortado a los ultimos N pings, incluido el actual).
Guarda por (dia, linea) un JSON con sumas suficientes por cfg (se reanuda: salta lo hecho).
"""
import sys, os, re, json, time
from pathlib import Path
ROOT = Path(r"c:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos")
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
from prediccion.replay import core, run as R
from red import path_reference as PR, geo_assign as G

MODEL = str(ROOT / "data/ml/export/path_v3_l1_s1")
LINES = "26,39,42,50,92,106,107,108,124,132,151,168".split(",")
DAYS = R.DEFAULT_DAYS
_ORIG_DFH = G.direction_from_history


def parse_cfg(name):
    trunc = None
    if "@" in name:
        name, n = name.split("@")
        trunc = int(n)
    if name == "base":
        return dict(kind="base", trunc=trunc)
    m = re.fullmatch(r"t(\d+)n(\d+(?:\.\d+)?)f(\d+(?:\.\d+)?)", name)
    return dict(kind="trail", k=int(m.group(1)), net=float(m.group(2)), frac=float(m.group(3)), trunc=trunc)


def make_rule(c):
    trunc = c["trunc"]
    if c["kind"] == "base":
        def f(pings, shape, tol_m=G.TOL_M):
            ps = list(pings)
            if trunc:
                ps = ps[-trunc:]
            return _ORIG_DFH(ps, shape, tol_m)
        return f
    k, net_min, frac_min = c["k"], c["net"], c["frac"]

    def f(pings, shape, tol_m=G.TOL_M):
        ps = [G._as_tuple(p) for p in pings]
        if not ps:
            return False, G.REASON_NO_DIRECTION
        t_now = ps[-1][0]
        ps = [p for p in ps[:-1] if t_now - p[0] <= G.HISTORY_WINDOW_S and p[0] < t_now] + [ps[-1]]
        if trunc:
            ps = ps[-trunc:]
        pr = [shape.project(la, lo) for _, la, lo in ps]
        run = []
        for x in reversed(pr):
            if x[1] > tol_m:
                break
            run.append(x)
        run.reverse()
        if len(run) < k:
            return False, G.REASON_NO_DIRECTION
        if G.forward_fraction([x[0] for x in run], [x[1] for x in run], tol_m) < frac_min:
            return False, G.REASON_INCOHERENT
        net = run[-1][0] - run[0][0]
        if net <= -net_min:
            return False, G.REASON_INCOHERENT
        if net < net_min:
            return False, G.REASON_NO_DIRECTION
        return True, None
    return f


def stats(inst, veh):
    s = {}
    p = veh[veh.tp_s <= 600]
    vis = p[p.visible]
    s["om_n"], s["om_k"] = len(vis), int((~vis.listed).sum())
    s["desc_k"] = int((vis.group == "").sum())            # ni lista ni siquiera en la cola (sin_sentido / sin_candidatos / ...)
    b = vis[(vis.tp_s >= 180) & (vis.tp_s <= 420)]
    s["omb_n"], s["omb_k"] = len(b), int((~b.listed).sum())
    if len(p):
        first = p.loc[p.groupby(["stop_id", "t"]).tp_s.idxmin()]
        fv = first[first.visible]
    else:
        fv = p
    s["om1_n"], s["om1_k"] = len(fv), int((~fv.listed).sum())
    l = veh[veh.listed]
    s["fa_n"], s["fa_k"] = len(l), int(l.tp_s.isna().sum())
    for g in ("seguro", "puede_venir", "provisional"):
        s[f"lst_{g}"] = int((l.group == g).sum())
    i = inst[inst.real_next_s <= 600]
    s["vac_n"], s["vac_k"] = len(i), int((~i.has_seguro).sum())
    sb = inst[(inst.real_next_s >= 180) & (inst.real_next_s <= 420)]
    ann = sb.ann0_any_s
    has = ann.notna()
    err = (sb.real_next_s - ann)[has]
    s["nb_n"], s["nb_has"] = len(sb), int(has.sum())
    s["nb_abs"] = float(err.abs().sum())
    s["nb_antes"], s["nb_desp"] = int((err < -60).sum()), int((err > 60).sum())
    s["inst_listed_sum"] = int(inst.n_listed.sum()); s["inst_n"] = len(inst)
    return s


_BUNDLE = None


def run_task(a):
    day, lines, out, cfgs = a
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00000040)
    except Exception:
        pass
    global _BUNDLE
    out = Path(out)
    todo = [ln for ln in lines if not (out / f"{day}_{ln}.json").exists()]
    if not todo:
        return day, 0
    t0 = time.time()
    if _BUNDLE is None:
        _BUNDLE = PR.load_bundle(MODEL)
    shapes_dir = str(ROOT.parent / "proyectoconsola/data/line_shapes")
    per_line = R.load_day(day, set(todo), "//192.168.0.18/buffer/grabaciones", str(ROOT / "LABEL_LINE_MAP.json"), shapes_dir, with_trips=False)
    insts = core.instants_for_day(day, step_min=10)
    for ln in todo:
        vs = list(per_line.get(ln, {}).values())
        res = {}
        if vs:
            stops = core.prepare_stops(_BUNDLE, ln, shapes_dir, 40)
            with core.memoized():
                for name in cfgs:
                    G.direction_from_history = make_rule(parse_cfg(name))
                    core.MEMO.sense.clear(); core.MEMO.lb_valid.clear(); core.MEMO.lb_scan.clear()
                    rv, ri = core.evaluate_line(_BUNDLE, ln, vs, stops, insts, ("base",), day, ts_offset_s=core.CABA_TS_OFFSET_S)
                    res[name] = stats(pd.DataFrame(ri), pd.DataFrame(rv))
                    print(day, ln, name, f"{time.time()-t0:.0f}s", flush=True)
                core.MEMO.clear()
            G.direction_from_history = _ORIG_DFH
        (out / f"{day}_{ln}.json").write_text(json.dumps(res))
    return day, time.time() - t0


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    a2 = sys.argv[2]
    cfgs = (open(a2[1:], encoding="utf-8").read().strip() if a2.startswith("@") else a2).split(";")
    days = (sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else DAYS).split(",")
    lines = (sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "-" else ",".join(LINES)).split(",")
    nw = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    G_SZ = int(os.environ.get("GROUP", "3"))
    groups = [lines[i:i + G_SZ] for i in range(0, len(lines), G_SZ)]
    tasks = [(d, g, str(out), cfgs) for g in groups for d in days]
    with ProcessPoolExecutor(nw) as ex:
        for d, el in ex.map(run_task, tasks):
            print("hecho", d, f"{el:.0f}s", flush=True)
