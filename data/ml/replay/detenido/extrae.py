"""Extraccion para el analisis de la regla "coche detenido" (COCHE_DETENIDO.md). Sin entrenar, sin tocar pinned/ ni v2/geo_assign.py.

Corre UNA vez el replay base (regla de sentido vigente trailing_run, la del pin) sobre (dia, linea) y guarda, para CADA coche con
prediccion en cada (parada, t) (no solo los listados): grupo, ETA, paso real y las variables causales de "avance" del coche sobre el
shape candidato (ventana N = 5, 10, 15 min: extension max(d) - min(d) de la racha final de pings a <= TOL del shape, la misma
proyeccion que usa la regla de sentido). Las variantes (ventana x avance minimo x tratamiento x cabecera/mitad) se derivan despues
(deriva.py) sin volver a predecir: descartar un coche o bajarlo de grupo no cambia las predicciones de los demas coches.
Uso: python extrae.py OUT_DIR [dias|-] [lineas|-] [workers] [paso_min]
"""
import sys, os, time, math
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
WINS = (300, 600, 900)       # ventanas N en s (5, 10, 15 min)
SPAN_SLACK_S = 90.0          # la racha debe cubrir la ventana salvo esta holgura (un ping de cadencia)
HZ = core.HORIZON_S
SHAPES_DIR = str(ROOT.parent / "proyectoconsola/data/line_shapes")


def run_feats(v, j, lo, shape):
    """Variables de avance del coche v (ping actual j; historial desde lo) sobre `shape`. Misma seleccion de pings y misma
    proyeccion que G.direction_from_history: pings pasados de <= HISTORY_WINDOW_S con ts < ts_actual, mas el actual; racha final
    de pings a <= TOL_M. Devuelve (d_actual, perp_actual, {N: extension_m o nan si la racha no cubre la ventana})."""
    ts_now = float(v.ts[j])
    idx = [i for i in range(lo, j) if v.ts[i] < ts_now and ts_now - v.ts[i] <= G.HISTORY_WINDOW_S] + [j]
    pr = [(float(v.ts[i]),) + tuple(shape.project(float(v.lat[i]), float(v.lon[i]))) for i in idx]
    d_now, perp_now = pr[-1][1], pr[-1][2]
    run = []
    for x in reversed(pr):
        if x[2] > G.TOL_M:
            break
        run.append(x)
    run.reverse()
    out = {}
    for N in WINS:
        w = [x for x in run if ts_now - x[0] <= N]
        if len(w) >= 2 and (ts_now - w[0][0]) >= N - SPAN_SLACK_S:
            ds = [x[1] for x in w]
            out[N] = max(ds) - min(ds)
        else:
            out[N] = np.nan
    return d_now, perp_now, out


def evaluate_multi(bundle, line, vehicles, stops, instants, day):
    shapes = bundle.lines[line]
    all_ids = list(shapes)
    by_id = {v.vid: v for v in vehicles}
    compat_cache = {}
    for v in vehicles:
        n = len(v.ts)
        perp = np.empty((len(all_ids), n)); dist = np.empty((len(all_ids), n))
        for k, sid in enumerate(all_ids):
            sh = shapes[sid]
            for i in range(n):
                dist[k, i], perp[k, i] = sh.project(float(v.lat[i]), float(v.lon[i]))
        lim = G.compat_limit(perp.min(axis=0))
        for k, sid in enumerate(all_ids):
            compat_cache[(v.vid, sid)] = (dist[k], perp[k] <= lim)
    passes, passes2 = core._passes(vehicles, stops, shapes, compat_cache)   # verdad anterior y corregida (core vigente)
    fcache = {}
    rows_veh, rows_inst = [], []
    for t in instants:
        live = {}
        for v in vehicles:
            j = int(np.searchsorted(v.ts, t, side="right")) - 1
            if j < 0 or t - v.ts[j] > core.HISTORY_S:
                continue
            lo = int(np.searchsorted(v.ts, t - core.HISTORY_S, side="left"))
            live[v.vid] = (j, lo)
        snap = max((float(by_id[vid].ts[j]) for vid, (j, _) in live.items()), default=float(t))
        others_by_vid = {vid: {"pings": [(float(by_id[vid].ts[i]), float(by_id[vid].lat[i]), float(by_id[vid].lon[i]))
                                          for i in range(lo, j + 1)]} for vid, (j, lo) in live.items()}
        # desplazamiento ex post en el horizonte (independiente de la parada)
        fut = {}
        for vid, (j, lo) in live.items():
            v = by_id[vid]
            k1 = int(np.searchsorted(v.ts, t + HZ, side="right"))
            if k1 > j + 1:
                dy = (v.lat[j + 1:k1] - v.lat[j]) * 111_320.0
                dx = (v.lon[j + 1:k1] - v.lon[j]) * 111_320.0 * math.cos(math.radians(v.lat[j]))
                fut[vid] = float(np.hypot(dx, dy).max())
            else:
                fut[vid] = np.nan
        for st in stops:
            tp_by, tp2_by, unv_by, past_by = core.truth_at(vehicles, live, passes, passes2, st.id, t)
            preds = {}
            for vid, (j, lo) in live.items():
                v = by_id[vid]
                if t - v.ts[j] > core.MAX_PING_AGE_S:
                    continue
                hist = [{"ts": float(v.ts[i]), "lat": float(v.lat[i]), "lon": float(v.lon[i])} for i in range(lo, j)]
                veh = {"lat": float(v.lat[j]), "lon": float(v.lon[j]), "speed_mps": float(v.speed[j]), "ts": float(v.ts[j])}
                others = [o for ovid, o in others_by_vid.items() if ovid != vid]
                preds[vid] = PR.predict_from_raw(bundle, line, veh, (st.lat, st.lon), float(t), history=hist, others=others,
                                                 only_shapes=None, user_kind="parada", stop_recorridos=st.recorridos,
                                                 snapshot_ts=snap, ts_offset_s=core.CABA_TS_OFFSET_S)
            lst = core.build_list(preds)
            grp = {x[0]: x for x in lst["seguro"] + lst["otros"]}
            real = sorted(tp_by.values())
            real2 = sorted(tp2_by.values())
            rows_inst.append({"line": line, "day": day, "stop_id": st.id, "stop_class": st.cls, "t": t, "n_vehicles": len(preds),
                              "real_next_s": real[0] if real else np.nan,
                              "n_pass_10": sum(1 for x in real if x <= 600), "n_pass_20": sum(1 for x in real if x <= 1200),
                              "real_next2_s": real2[0] if real2 else np.nan,
                              "n_pass2_10": sum(1 for x in real2 if x <= 600), "n_pass2_20": sum(1 for x in real2 if x <= 1200),
                              "unv_first_s": min(unv_by.values()) if unv_by else np.nan})
            for vid in list(preds) + [x for x in set(tp_by) | set(tp2_by) if x not in preds]:
                r = preds.get(vid)
                g = grp.get(vid)
                if g is None and vid not in tp_by and vid not in tp2_by:
                    continue
                row = {"line": line, "day": day, "stop_id": st.id, "t": t, "vehicle": vid, "visible": r is not None,
                       "group": g[1] if g else "", "eta_s": g[2] if g else np.nan,
                       "eta0_s": lst["eta0"].get(vid, np.nan) if g else np.nan, "tp_s": tp_by.get(vid, np.nan),
                       "tp2_s": tp2_by.get(vid, np.nan), "unv": vid in unv_by, "past": vid in past_by,
                       "fut_disp_m": fut.get(vid, np.nan) if vid in live else np.nan,
                       "d_p": np.nan, "rem_m": np.nan, "ext300": np.nan, "ext600": np.nan, "ext900": np.nan, "ref_shape": ""}
                if g is not None:
                    j, lo = live[vid]
                    v = by_id[vid]
                    sid = r.get("shape_id")
                    if sid is None:
                        cl = r["compatible"] if r["compatible"] else r["provisional"]
                        sid = next((k["shape_id"] for k in cl if k["passes"]), None)
                    if sid is not None:
                        key = (vid, j, sid)
                        f = fcache.get(key)
                        if f is None:
                            f = fcache[key] = run_feats(v, j, lo, shapes[sid])
                        row.update(d_p=f[0], ext300=f[2][300], ext600=f[2][600], ext900=f[2][900], ref_shape=sid)
                        bc = next((c for c in r["candidates"] if c["shape_id"] == sid), None)
                        row["rem_m"] = bc["rem_m"] if bc else 0.0
                rows_veh.append(row)
        if len(fcache) > 400_000:
            fcache.clear()
    return rows_veh, rows_inst


def lowprio():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass


_BUNDLE = None


def run_task(a):
    day, lines, out, step = a
    lowprio()
    global _BUNDLE
    out = Path(out)
    todo = [ln for ln in lines if not (out / f"{day}_{ln}.inst.parquet").exists()]
    if not todo:
        return day, 0
    t0 = time.time()
    if _BUNDLE is None:
        _BUNDLE = PR.load_bundle(MODEL)
    per_line = R.load_day(day, set(todo), "//192.168.0.18/buffer/grabaciones", str(ROOT / "LABEL_LINE_MAP.json"), SHAPES_DIR, with_trips=False)
    insts = core.instants_for_day(day, step_min=step)
    for ln in todo:
        vs = list(per_line.get(ln, {}).values())
        if not vs:
            continue
        stops = core.prepare_stops(_BUNDLE, ln, SHAPES_DIR, 40)
        with core.memoized():
            rv, ri = evaluate_multi(_BUNDLE, ln, vs, stops, insts, day)
            core.MEMO.clear()
        pd.DataFrame(rv).astype({"ext300": "float32", "ext600": "float32", "ext900": "float32", "d_p": "float32", "rem_m": "float32",
                                 "fut_disp_m": "float32"}).to_parquet(out / f"{day}_{ln}.veh.parquet")
        pd.DataFrame(ri).to_parquet(out / f"{day}_{ln}.inst.parquet")
        print(f"{day} {ln}: {len(stops)} paradas, {len(vs)} coches, {len(rv)} filas, {time.time()-t0:.0f}s", flush=True)
    return day, time.time() - t0


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    days = (sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else DAYS).split(",")
    lines = (sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else ",".join(LINES)).split(",")
    nw = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    step = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    G_SZ = int(os.environ.get("GROUP", "2"))
    groups = [lines[i:i + G_SZ] for i in range(0, len(lines), G_SZ)]
    tasks = [(d, g, str(out), step) for g in groups for d in days]
    with ProcessPoolExecutor(nw) as ex:
        for d, el in ex.map(run_task, tasks):
            print("hecho", d, f"{el:.0f}s", flush=True)
