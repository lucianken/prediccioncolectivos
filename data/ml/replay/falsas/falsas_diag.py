"""Diagnostico de falsas alarmas del replay de produccion (variantes base y ramal-oraculo), modelo path_v3_l1_s1,
regla de sentido racha final (k=2, avance 40 m, frac 0,6) puesta en memoria como en barrido_sentido.py.
No toca pinned/ ni v2/geo_assign.py. Uso: python falsas_diag.py OUT_DIR dias lineas workers
Por (dia, linea) escribe OUT/{dia}_{linea}.parquet: una fila por coche listado (variante base: con atributos ex post si es
falsa alarma; variante ramal: solo lo minimo)."""
import sys, os, time, json
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
DAYS_ORDER = "2026-09-15,2026-09-17,2026-09-19,2026-09-20,2026-10-04,2026-10-06,2026-09-16,2026-09-18,2026-10-03,2026-10-08"
TOL, FRAC_MIN, NET_MIN, K, WIN = 45.0, 0.6, 40.0, 2, 900
HZ = core.HORIZON_S


def trailing_rule(pings, shape, tol_m=TOL):
    ps = [G._as_tuple(p) for p in pings]
    if not ps:
        return False, "sin_sentido"
    t_now = ps[-1][0]
    ps = [p for p in ps[:-1] if t_now - p[0] <= WIN and p[0] < t_now] + [ps[-1]]
    pr = [shape.project(la, lo) for _, la, lo in ps]
    run = []
    for x in reversed(pr):
        if x[1] > tol_m:
            break
        run.append(x)
    run.reverse()
    if len(run) < K:
        return False, "sin_sentido"
    if G.forward_fraction([x[0] for x in run], [x[1] for x in run], tol_m) < FRAC_MIN:
        return False, "sentido_incoherente"
    net = run[-1][0] - run[0][0]
    if net <= -NET_MIN:
        return False, "sentido_incoherente"
    if net < NET_MIN:
        return False, "sin_sentido"
    return True, None


REC = {}
_ORIG_PRED = PR.predict_from_raw


def _rec_pred(bundle, line, vehicle, user, now_ts, *a, **k):
    r = _ORIG_PRED(bundle, line, vehicle, user, now_ts, *a, **k)
    if k.get("only_shapes") is None and r and r.get("status") in core.SHOWN_STATUS and r.get("eta_s") is not None:
        best = None
        for c in r["candidates"]:
            if c["shape_id"] == r["shape_id"]:
                best = c
        REC[(vehicle["ts"], vehicle["lat"], vehicle["lon"], user[0], user[1], float(now_ts))] = (
            r["status"], r["group"], r["sense"], r["shape_id"], "|".join(c["shape_id"] for c in r["candidates"]),
            "|".join(r["depends_on"]), best["d_p"] if best else np.nan, best["rem_m"] if best else np.nan,
            "|".join(sorted({d["reason"] for d in r["discarded"]})))
    return r


def lowprio():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass


class Ctx:
    def __init__(self, shapes, vehicles, stops):
        self.shapes = shapes
        self.ids = list(shapes)
        self.sidx = {s: i for i, s in enumerate(self.ids)}
        self.dirs = core.direction_groups(shapes)
        self.by_id = {v.vid: v for v in vehicles}
        self.stops = {s.id: s for s in stops}
        self.info = {}
        self.pass_c = {}
        self.stopproj = {}

    def vinfo(self, vid):
        r = self.info.get(vid)
        if r is None:
            v = self.by_id[vid]
            n = len(v.ts)
            dist = np.empty((len(self.ids), n)); perp = np.empty((len(self.ids), n))
            for k, sid in enumerate(self.ids):
                sh = self.shapes[sid]
                for i in range(n):
                    dist[k, i], perp[k, i] = sh.project(float(v.lat[i]), float(v.lon[i]))
            lim = G.compat_limit(perp.min(axis=0))
            ok = perp <= lim[None, :]
            r = self.info[vid] = (dist, perp, ok)
        return r

    def sproj(self, st, sid):
        k = (st.id, sid)
        r = self.stopproj.get(k)
        if r is None:
            r = self.stopproj[k] = self.shapes[sid].project(st.lat, st.lon)
        return r

    def passes(self, st, vid):
        k = (st.id, vid)
        r = self.pass_c.get(k)
        if r is not None:
            return r
        v = self.by_id[vid]
        dist, perp, ok = self.vinfo(vid)
        strict = []
        loose = []     # (tcross, gap, jump, noncompat)
        geo = []       # cruce estricto sobre shapes NO asociados a la parada pero a <= 50 m de ella
        ts = v.ts
        for sid, ds in st.serving.items():
            kk = self.sidx[sid]
            strict.append(core.crossing_times(ts, dist[kk], ok[kk], ds))
            d0, d1, t0, t1 = dist[kk][:-1], dist[kk][1:], ts[:-1], ts[1:]
            m = (perp[kk][:-1] <= 100) & (perp[kk][1:] <= 100) & (d0 <= ds) & (ds < d1)
            for i in np.nonzero(m)[0]:
                tc = t0[i] + (ds - d0[i]) / (d1[i] - d0[i]) * (t1[i] - t0[i])
                loose.append((tc, t1[i] - t0[i], d1[i] - d0[i], not (ok[kk][i] and ok[kk][i + 1])))
        for sid in self.ids:
            if sid in st.serving:
                continue
            ds, pp = self.sproj(st, sid)
            if pp > 50:
                continue
            kk = self.sidx[sid]
            c = core.crossing_times(ts, dist[kk], ok[kk], ds)
            geo.extend(c.tolist())
        s = np.sort(np.concatenate(strict)) if strict else np.empty(0)
        r = self.pass_c[k] = (s, sorted(loose), sorted(geo))
        return r


def first_after(arr, t):
    for x in arr:
        if x > t:
            return x
    return np.nan


def enrich(ctx, row, rec):
    """Atributos ex post de una falsa alarma. row: dict base listado sin paso en 40 min."""
    vid, t = row["vehicle"], float(row["t"])
    st = ctx.stops[row["stop_id"]]
    v = ctx.by_id[vid]
    dist, perp, ok = ctx.vinfo(vid)
    j = int(np.searchsorted(v.ts, t, side="right")) - 1
    lo = int(np.searchsorted(v.ts, t - core.HISTORY_S, side="left"))
    o = {"age_s": t - v.ts[j], "speed": float(v.speed[j]), "n_hist": j - lo + 1,
         "minperp": float(perp[:, j].min()), "n_compat_t": int(ok[:, j].sum())}
    best = rec[3] if rec else None
    o["best_shape"] = best or ""
    o["n_serving"] = len(st.serving)
    o["n_cands"] = len(rec[4].split("|")) if rec and rec[4] else 0
    o["cand_shapes"] = rec[4] if rec else ""
    o["depends_on"] = rec[5] if rec else ""
    o["d_p"] = rec[6] if rec else np.nan
    o["rem_m"] = rec[7] if rec else np.nan
    o["disc"] = rec[8] if rec else ""
    o["sense"] = (rec[2] or "") if rec else ""
    tH = t + HZ
    fut = np.nonzero((v.ts > t) & (v.ts <= tH))[0]
    o["n_fut"] = len(fut)
    o["last_data_rel"] = float(v.ts[-1] - t)
    seq = v.ts[j:(fut[-1] + 1 if len(fut) else j + 1)]
    gaps = np.diff(seq) if len(seq) > 1 else np.array([0.0])
    o["max_gap_fut"] = float(max(gaps.max(), (tH - seq[-1]) if v.ts[-1] < tH else 0.0))
    strict, loose, geo = ctx.passes(st, vid)
    o["tp_any_rel"] = first_after(strict, t) - t
    lz = [x for x in loose if x[0] > t]
    o["loose_rel"] = (lz[0][0] - t) if lz else np.nan
    o["loose_gap"] = lz[0][1] if lz else np.nan
    o["loose_jump"] = lz[0][2] if lz else np.nan
    o["loose_noncompat"] = bool(lz[0][3]) if lz else False
    o["geo_rel"] = first_after(geo, t) - t
    if best:
        kb = ctx.sidx[best]
        ds_b = ctx.sproj(st, best)[0]
        o["ds_best"] = ds_b; o["len_best"] = ctx.shapes[best].length_m
        o["perp_best_t"] = float(perp[kb, j]); o["d_best_t"] = float(dist[kb, j])
        fk = fut[ok[kb, fut]] if len(fut) else fut
        o["prog_best_m"] = float(dist[kb, fk].max() - dist[kb, j]) if len(fk) else np.nan
        o["dmax_best"] = float(dist[kb, fk].max()) if len(fk) else np.nan
        o["d_last_best"] = float(dist[kb, fk[-1]]) if len(fk) else np.nan
        o["reach_best"] = bool(len(fk) and dist[kb, fk].max() >= ds_b)
        pm = (perp[kb, fut] <= 100) if len(fut) else np.zeros(0, bool)
        o["near_best_min_m"] = float(np.abs(dist[kb, fut] - ds_b)[pm].min()) if pm.any() else np.nan
    tr = None
    for a, b, sid in v.trips:
        if a <= v.ts[j] <= b:
            tr = (a, b, sid, True); break
        if v.ts[j] < a:
            tr = (a, b, sid, False); break
    o["in_trip"] = bool(tr and tr[3]); o["true_shape"] = (tr[2] if tr else "") or ""
    o["trip_wait_s"] = float(tr[0] - v.ts[j]) if tr and not tr[3] else 0.0
    o["trip_start_rel"] = float(tr[0] - t) if tr else np.nan
    o["trip_end_rel"] = float(tr[1] - t) if tr else np.nan
    o["n_trips_fut"] = sum(1 for a, b, s in v.trips if a > t and a <= tH)
    nxt = [x for x in v.trips if tr and x[0] > tr[1]]
    o["next_trip_rel"] = float(nxt[0][0] - t) if nxt else np.nan
    o["next_trip_shape"] = (nxt[0][2] if nxt else "") or ""
    ts_id = o["true_shape"]
    if ts_id and ts_id in ctx.sidx:
        kt = ctx.sidx[ts_id]
        o["true_serves"] = ts_id in st.serving
        o["true_dir_ne_best"] = bool(best and ctx.dirs[ts_id] != ctx.dirs[best])
        o["true_dir_ne_serving"] = bool(st.serving) and all(ctx.dirs[s] != ctx.dirs[ts_id] for s in st.serving)
        o["len_true"] = ctx.shapes[ts_id].length_m
        o["d_true_t"] = float(dist[kt, j])
        o["perp_true_t"] = float(perp[kt, j])
        ds_t = st.serving.get(ts_id)
        o["ds_true"] = ds_t if ds_t is not None else np.nan
        ie = int(np.searchsorted(v.ts, tr[1], side="right")) - 1
        o["d_true_end"] = float(dist[kt, ie]); o["perp_true_end"] = float(perp[kt, ie])
        o["min_perp_end"] = float(perp[:, ie].min())
    else:
        o["true_serves"] = False; o["true_dir_ne_best"] = False; o["true_dir_ne_serving"] = False
    ie2 = (fut[-1] if len(fut) else j)
    o["min_perp_h_end"] = float(perp[:, ie2].min())
    o["speed_h_end"] = float(v.speed[ie2])
    o["slow_frac_fut"] = float((v.speed[fut] < 1.0).mean()) if len(fut) else np.nan
    return o


def run_task(a):
    day, ln, out = a
    lowprio()
    out = Path(out)
    f = out / f"{day}_{ln}.parquet"
    if f.exists():
        return day, ln, 0.0
    t0 = time.time()
    bundle = PR.load_bundle(MODEL)
    G.direction_from_history = trailing_rule
    PR.predict_from_raw = _rec_pred
    shapes_dir = str(ROOT.parent / "proyectoconsola/data/line_shapes")
    per_line = R.load_day(day, {ln}, "//192.168.0.18/buffer/grabaciones", str(ROOT / "LABEL_LINE_MAP.json"), shapes_dir, with_trips=True)
    insts = core.instants_for_day(day, step_min=10)
    vs = list(per_line.get(ln, {}).values())
    if not vs:
        pd.DataFrame().to_parquet(f)
        return day, ln, 0.0
    stops = core.prepare_stops(bundle, ln, shapes_dir, 40)
    REC.clear()
    with core.memoized():
        rv, ri = core.evaluate_line(bundle, ln, vs, stops, insts, ("base", "ramal"), day, ts_offset_s=core.CABA_TS_OFFSET_S)
        df = pd.DataFrame(rv)
        ctx = Ctx(bundle.lines[ln], vs, stops)
        ram = df[(df.variant == "ramal") & df.listed][["stop_id", "t", "vehicle", "tp_s", "group", "eta0_s", "variant"]].copy()
        b = df[(df.variant == "base") & df.listed].copy()
        key = set(zip(ram.stop_id, ram.t, ram.vehicle))
        b["listed_ramal"] = [(s, t, v) in key for s, t, v in zip(b.stop_id, b.t, b.vehicle)]
        recs = []
        for r in b.itertuples():
            if not np.isnan(r.tp_s):
                recs.append({})
                continue
            v = ctx.by_id[r.vehicle]
            j = int(np.searchsorted(v.ts, r.t, side="right")) - 1
            st = ctx.stops[r.stop_id]
            rc = REC.get((float(v.ts[j]), float(v.lat[j]), float(v.lon[j]), st.lat, st.lon, float(r.t)))
            recs.append(enrich(ctx, r._asdict(), rc))
        ex = pd.DataFrame(recs, index=b.index)
        b = pd.concat([b, ex], axis=1)
        b["stop_class"] = b.stop_id.map({s.id: s.cls for s in stops})
        core.MEMO.clear()
    allr = pd.concat([b, ram], ignore_index=True)
    allr["line"] = ln; allr["day"] = day
    allr.to_parquet(f)
    return day, ln, time.time() - t0


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    days = (sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else DAYS_ORDER).split(",")
    lines = (sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else ",".join(LINES)).split(",")
    nw = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    tasks = [(d, l, str(out)) for d in days for l in lines]
    with ProcessPoolExecutor(nw) as ex:
        for d, l, el in ex.map(run_task, tasks):
            print("hecho", d, l, f"{el:.0f}s", flush=True)
