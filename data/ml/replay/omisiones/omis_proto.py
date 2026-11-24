"""Diagnostico de omisiones del replay (variante base). Escribe parquet por (dia, linea)."""
import sys, os, time, json
from pathlib import Path
ROOT = Path(r"c:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos")
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
from prediccion.replay import core, run as R
from prediccion.replay.pinned import path_reference as PR, geo_assign as G

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
LINES = "26,39,42,50,92,106,107,108,124,132,151,168".split(",")



def _dir_hist_trailing(pings, shape, tol_m=G.TOL_M):
    """PROTOTIPO: sentido con la racha final de pings cercanos al shape (en vez de >=80 % de toda la ventana)."""
    ps = [G._as_tuple(p) for p in pings]
    if not ps:
        return False, G.REASON_NO_DIRECTION
    t_now = ps[-1][0]
    ps = [p for p in ps[:-1] if t_now - p[0] <= G.HISTORY_WINDOW_S and p[0] < t_now] + [ps[-1]]
    pr = [shape.project(la, lo) for _, la, lo in ps]
    run = []
    for x in reversed(pr):
        if x[1] > tol_m:
            break
        run.append(x)
    run.reverse()
    if len(run) < G.MIN_NEAR_PINGS:
        return False, G.REASON_NO_DIRECTION
    if G.forward_fraction([x[0] for x in run], [x[1] for x in run], tol_m) < G.MIN_FORWARD_FRAC:
        return False, G.REASON_INCOHERENT
    net = run[-1][0] - run[0][0]
    if net <= -G.MIN_NET_FORWARD_M:
        return False, G.REASON_INCOHERENT
    if net < G.MIN_NET_FORWARD_M:
        return False, G.REASON_NO_DIRECTION
    return True, None


def crossings(ts, d, ok, d_stop):
    """lista (tcross, t0, t1, d0, d1) de cruces validos."""
    d0, d1, t0, t1 = d[:-1], d[1:], ts[:-1], ts[1:]
    m = ok[:-1] & ok[1:] & (d0 <= d_stop) & (d_stop < d1) & ((t1 - t0) <= core.PASS_MAX_DT_S) & ((d1 - d0) <= G.STEP_JUMP_M)
    idx = np.nonzero(m)[0]
    return [(t0[i] + (d_stop - d0[i]) / (d1[i] - d0[i]) * (t1[i] - t0[i]), t0[i], t1[i], d0[i], d1[i]) for i in idx]


def eval_line(bundle, line, vehicles, stops, instants, day):
    shapes = bundle.lines[line]
    ids = list(shapes)
    dirs = core.direction_groups(shapes)
    by_id = {v.vid: v for v in vehicles}
    info = {}
    for v in vehicles:
        n = len(v.ts)
        perp = np.empty((len(ids), n)); dist = np.empty((len(ids), n))
        for k, sid in enumerate(ids):
            for i in range(n):
                dist[k, i], perp[k, i] = shapes[sid].project(float(v.lat[i]), float(v.lon[i]))
        lim = G.compat_limit(perp.min(axis=0))
        info[v.vid] = (dist, perp, perp <= lim[None, :], perp.min(axis=0))
    cross = {}
    for st in stops:
        for v in vehicles:
            dist, perp, ok, _ = info[v.vid]
            lst = []
            for sid, ds in st.serving.items():
                k = ids.index(sid)
                for c in crossings(v.ts, dist[k], ok[k], ds):
                    lst.append((*c, sid))
            lst.sort()
            cross[(st.id, v.vid)] = lst
    rows = []
    inst = []
    for t in instants:
        live = {}
        for v in vehicles:
            j = int(np.searchsorted(v.ts, t, side="right")) - 1
            if j < 0 or t - v.ts[j] > core.HISTORY_S:
                continue
            lo = int(np.searchsorted(v.ts, t - core.HISTORY_S, side="left"))
            live[v.vid] = (j, lo)
        others_by = {vid: {"pings": [(float(by_id[vid].ts[i]), float(by_id[vid].lat[i]), float(by_id[vid].lon[i])) for i in range(lo, j + 1)]} for vid, (j, lo) in live.items()}
        for st in stops:
            tp_by = {}
            for v in vehicles:
                lst = cross[(st.id, v.vid)]
                nxt = [c for c in lst if c[0] > t and c[0] - t <= core.HORIZON_S]
                if nxt:
                    tp_by[v.vid] = nxt[0]
            preds = {}
            for vid, (j, lo) in live.items():
                v = by_id[vid]
                age = t - v.ts[j]
                if age > core.MAX_PING_AGE_S:
                    continue
                hist = [{"ts": float(v.ts[i]), "lat": float(v.lat[i]), "lon": float(v.lon[i])} for i in range(lo, j)]
                veh = {"lat": float(v.lat[j]), "lon": float(v.lon[j]), "speed_mps": float(v.speed[j]), "ts": float(v.ts[j])}
                others = [o for ov, o in others_by.items() if ov != vid]
                preds[vid] = PR.predict_from_raw(bundle, line, veh, (st.lat, st.lon), float(t), history=hist, others=others,
                                                 only_shapes=None, user_kind="parada", stop_recorridos=st.recorridos)
            lst = core.build_list(preds)
            order = [x[0] for x in lst["seguro"]] + [x[0] for x in lst["otros"]]
            shown = {x[0] for x in lst["shown"]}
            inst.append(dict(line=line, day=day, stop_id=st.id, t=t, n_listed=len(shown), n_false=sum(1 for x in shown if x not in tp_by), n_pass10=sum(1 for c in tp_by.values() if c[0]-t<=600), n_order=len(order)))
            n_pass10 = sum(1 for c in tp_by.values() if c[0] - t <= 600)
            for vid, c in tp_by.items():
                tp = c[0] - t
                if tp > 600:
                    continue
                v = by_id[vid]
                j = int(np.searchsorted(v.ts, t, side="right")) - 1
                r = preds.get(vid)
                # ping anterior (ultimo <= t)
                dist, perp, ok, minperp = info[vid]
                rec = dict(line=line, day=day, stop_id=st.id, cls=st.cls, t=t, vid=vid, tp=tp, n_pass10=n_pass10,
                           n_listed_pass=sum(1 for x in tp_by if x in shown and tp_by[x][0] - t <= 600),
                           in_live=vid in live, visible=r is not None, listed=vid in shown,
                           rank=(order.index(vid) + 1 if vid in order else 0), n_order=len(order), n_shown_status=len(order),
                           last_ping_age=(t - v.ts[j]) if j >= 0 else np.nan,
                           cross_t0=c[1] - t, cross_t1=c[2] - t, cross_gap=c[2] - c[1], cross_shape=c[5], cross_d0=c[3], cross_d1=c[4],
                           d_stop=st.serving[c[5]], n_serving=len(st.serving))
                if j >= 0:
                    k = ids.index(c[5])
                    rec.update(minperp=float(minperp[j]), perp_cross_shape=float(perp[k, j]), compat_cross_shape=bool(ok[k, j]),
                               d_p_cross=float(dist[k, j]), n_compat=int(ok[:, j].sum()),
                               compat_serving=int(sum(ok[ids.index(s), j] for s in st.serving)),
                               speed=float(v.speed[j]), n_pings_hist=int(j - np.searchsorted(v.ts, t - core.HISTORY_S) + 1))
                    ts_true = v.true_shape(float(v.ts[j]))
                    rec["true_shape_now"] = ts_true or ""
                    inx = [(a, b) for a, b, s in v.trips if a <= v.ts[j] <= b]
                    rec["in_trip"] = bool(inx)
                    nxt_trip = [a for a, b, s in v.trips if a > t]
                    rec["next_trip_start"] = (min(nxt_trip) - t) if nxt_trip else np.nan
                    rec["first_ping_s"] = float(v.ts[0] - t)
                    # el coche aun no habia empezado a moverse sobre el shape de cruce?
                if r is not None:
                    rec.update(status=r["status"], group=r["group"] or "", eta_s=r["eta_s"] if r["eta_s"] is not None else np.nan,
                               sense=r["sense"] or "", n_cands=len(r["candidates"]),
                               disc="|".join(sorted({d["reason"] for d in r["discarded"]})),
                               disc_n=len(r["discarded"]), n_compat_pred=len(r["compatible"]), n_prov=len(r["provisional"]),
                               prov_reasons="|".join(sorted({str(k.get("reason")) for k in r["provisional"]})),
                               compat_reasons="|".join(sorted({str(k.get("reason")) for k in r["compatible"]})),
                               # razon del descarte para el shape de cruce
                               disc_cross="|".join(d["reason"] for d in r["discarded"] if d["shape_id"] == c[5]),
                               cands_on_cross=any(x["shape_id"] == c[5] for x in r["candidates"]),
                               eta_err=(tp - r["eta_s"]) if r["eta_s"] is not None else np.nan)
                else:
                    rec.update(status="", group="")
                rows.append(rec)
    return rows, inst


def run_day(a):
    day, lines = a
    try:
        os.nice(10)
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    if os.environ.get('PROTO'):
        G.direction_from_history = _dir_hist_trailing
    t0 = time.time()
    bundle = PR.load_bundle(str(ROOT / "data/ml/export/path_v2c_l1_s1"))
    shapes_dir = str(ROOT.parent / "proyectoconsola/data/line_shapes")
    per_line = R.load_day(day, set(lines), "//192.168.0.18/buffer/grabaciones", str(ROOT / "LABEL_LINE_MAP.json"), shapes_dir)
    insts = core.instants_for_day(day, step_min=10)
    for ln in lines:
        f = OUT / f"{day}_{ln}.parquet"
        if f.exists():
            continue
        vs = list(per_line.get(ln, {}).values())
        if not vs:
            continue
        stops = core.prepare_stops(bundle, ln, shapes_dir, 40)
        with core.memoized():
            rows, inst = eval_line(bundle, ln, vs, stops, insts, day)
            core.MEMO.clear()
        pd.DataFrame(inst).to_parquet(OUT / f'{day}_{ln}.inst.parquet')
        pd.DataFrame(rows).to_parquet(f)
        print(day, ln, len(rows), f"{time.time()-t0:.0f}s", flush=True)
    return day


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    days = sys.argv[2].split(",")
    lines = sys.argv[3].split(",") if len(sys.argv) > 3 else LINES
    nw = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    with ProcessPoolExecutor(nw) as ex:
        for d in ex.map(run_day, [(d, lines) for d in days]):
            print("hecho", d, flush=True)
