"""Generalización de recorridos_nuevos_42/replay42.py a varias líneas (2026-11-27). Mismo diseño; cambia: línea por argumento,
instantes solo en horas con pings >= 25 % de la mediana horaria 08-20 h de la línea ese día (huecos de grabación), y tag de salida por línea.
  python -m experiments.recorridos_nuevos_lineas.replay_lineas --lines 84,7 --days 2026-11-25,2026-11-26 --out <dir> [--workers 3]
Replay `base` de la 42 con dos bundles de predicción sobre la MISMA verdad (recorridos nuevos).
  python -m experiments.recorridos_nuevos_42.replay42 --days 2026-11-26 --out <dir> [--workers 3]
- Verdad: bundle nuevo (path_v4_l1_s1_shapes20261126), paradas de line_shapes actuales, viajes ex post con line_shapes actuales.
- Predicción viejo: bundle path_v4_l1_s1. Paradas 'nueva_*' (sin parada vieja a <= 25 m): el punto se resuelve como la app con
  GPS/mapa (snap_to_route a <= T = 45 m, user_kind 'punto'); si no engancha: no se puede predecir (ningún coche). Paradas 'resto':
  por nombre de recorrido, como siempre.
- Predicción nuevo: todas por nombre de recorrido.
Se reutiliza core.evaluate_line parcheando solo (a) la verdad con otro bundle y (b) cómo se resuelve el punto del usuario."""
from __future__ import annotations
import argparse, inspect, json, re, sys, textwrap
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parents[1] / "recorridos_nuevos_42"))
import core_head as core
from prediccion.replay import run as RUN
from prediccion.replay.pinned import path_reference as PR
from diff_shapes import densify, xy
OLD = ROOT / "data/ml/export/path_v4_l1_s1"
NEW = ROOT / "data/ml/export/path_v4_l1_s1_r20261126"
SHAPES = ROOT.parent / "proyectoconsola/data/line_shapes"

def _patched():
    src = textwrap.dedent(inspect.getsource(core.evaluate_line))
    def sub(a, b, n=1):
        nonlocal src
        assert src.count(a) == n, (a, src.count(a)); src = src.replace(a, b)
    sub("def evaluate_line(", "def evaluate_line_x(")
    sub("one_ping: tuple = ()):", "one_ping: tuple = (), truth_bundle=None, pred_user=None):")
    sub("compat_cache = compat_for(vehicles, shapes)\n    passes, passes2 = _passes(vehicles, stops, shapes, compat_cache, truth_stats)",
        "tshapes = (truth_bundle or bundle).lines[line]\n    compat_cache = compat_for(vehicles, tshapes)\n    passes, passes2 = _passes(vehicles, stops, tshapes, compat_cache, truth_stats)")
    sub("preds[vid] = PR.predict_from_raw(bundle, line, veh, (st.lat, st.lon), float(t), history=hist,",
        "_pu = pred_user(st) if pred_user else ((st.lat, st.lon), 'parada', st.recorridos)\n                    if _pu is None:\n                        continue\n                    preds[vid] = PR.predict_from_raw(bundle, line, veh, _pu[0], float(t), history=hist,")
    sub('user_kind="parada",', "user_kind=_pu[1],")
    sub("stop_recorridos=st.recorridos,", "stop_recorridos=_pu[2],")
    ns = core.__dict__
    exec(compile(src, "evaluate_line_x", "exec"), ns)
    return ns["evaluate_line_x"]


def hours_ok(vs, day):
    ts = np.concatenate([v.ts for v in vs]) if vs else np.empty(0)
    h = (((ts - 3 * 3600) % 86400) // 3600).astype(int)
    c = np.bincount(h, minlength=24)
    ref = np.median(c[8:21]) if c[8:21].size else 0
    return {k for k in range(24) if c[k] >= 0.25 * ref and ref > 0}

def run_day(a):
    day, LINE, out, per_resto, step = a
    out = Path(out) / LINE; out.mkdir(parents=True, exist_ok=True)
    if (out / f"{day}_old.inst.parquet").exists() and (out / f"{day}_new.inst.parquet").exists():
        return day
    import ctypes
    try: ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00000040)
    except Exception: pass
    ev = _patched()
    B_new, B_old = PR.load_bundle(NEW), PR.load_bundle(OLD)
    # paradas
    allst = core.prepare_stops(B_new, LINE, SHAPES, per_line=1000)
    old_ll = []
    for sh in B_old.lines[LINE].values():
        for d in sh.stops_m:
            old_ll.append(sh.latlon_at(d))
    KX, KY = 111320.0 * np.cos(np.radians(-34.6)), 111320.0
    tree_old_stops = cKDTree(xy(old_ll))
    d_old_stop = tree_old_stops.query(xy([(s.lat, s.lon) for s in allst]))[0]
    snap = {s.id: PR.snap_to_route(B_old, LINE, s.lat, s.lon) for s in allst}
    for s, d in zip(allst, d_old_stop):
        s.cls_orig = s.cls
        s.nueva = bool(d > 25.0)
        s.snap_perp = snap[s.id]["perp"]
    nuevas = [s for s in allst if s.nueva]
    rest = [s for s in allst if not s.nueva]
    rng = np.random.default_rng(0)
    rest = [rest[i] for i in sorted(rng.choice(len(rest), min(per_resto, len(rest)), replace=False))]
    stops = nuevas + rest
    for s in stops:
        s.cls = ("nueva_fuera" if s.snap_perp > 45.0 else "nueva_cerca") if s.nueva else "resto"
    def user_old(st):
        if not st.nueva:
            return (st.lat, st.lon), "parada", st.recorridos
        sn = snap[st.id]
        if not sn["on_route"]:
            return None
        return (sn["lat"], sn["lon"]), "punto", None
    per_line = RUN.load_day(day, {LINE}, "Z:/grabaciones", str(ROOT / "LABEL_LINE_MAP.json"), str(SHAPES))
    vs = list(per_line.get(LINE, {}).values())
    hok = hours_ok(vs, day)
    insts = [t for t in core.instants_for_day(day, step_min=step)
             if ((t - 3 * 3600) // 3600 % 24) in hok and (((t + 2400) - 3 * 3600) // 3600 % 24) in hok]
    meta = pd.DataFrame([dict(stop_id=s.id, name=s.name, cls=s.cls, snap_perp=s.snap_perp, lat=s.lat, lon=s.lon,
                              serving=len(s.serving)) for s in stops])
    meta.to_csv(out / "paradas.csv", index=False)
    for tag, B, pu in (("old", B_old, user_old), ("new", B_new, None)):
        with core.memoized():
            rv, ri = ev(B, LINE, vs, stops, insts, ("base",), day, truth_bundle=B_new, pred_user=pu)
            core.MEMO.clear()
        pd.DataFrame(rv).to_parquet(out / f"{day}_{tag}.veh.parquet")
        pd.DataFrame(ri).to_parquet(out / f"{day}_{tag}.inst.parquet")
        print(day, tag, len(stops), "paradas", len(insts), "instantes", len(vs), "coches", flush=True)
    return day

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", required=True); ap.add_argument("--days", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--resto", type=int, default=40); ap.add_argument("--step", type=int, default=10)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    days = a.days.split(","); lines = a.lines.split(",")
    with ProcessPoolExecutor(a.workers) as ex:
        for d in ex.map(run_day, [(d, l, a.out, a.resto, a.step) for l in lines for d in days]):
            print("hecho", d, flush=True)

if __name__ == "__main__":
    main()
