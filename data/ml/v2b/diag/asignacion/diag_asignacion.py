"""
Diagnóstico de asignación de recorrido en v2b (solo lectura de v2b; escribe en data/ml/v2b/diag/asignacion/_days).

Por día: relee el NDJSON, vuelve a segmentar con el segmentador v2b (geo2, mismo carry que el build) y mide:
  - perp de cada ping al shape asignado (histograma 0,5 m por línea),
  - pings con perp 45-150 m y si otro shape de la línea está más cerca,
  - ambigüedad del viaje (mediana perp del elegido vs el segundo mejor),
  - retrocesos de distancia a lo largo > 150 m entre pings válidos consecutivos,
  - flags por fila de entrenamiento (P y F) leyendo el parquet del día (solo lectura),
  - en días de muestra, simulación del segmentador con FIT_M = 45 m.
Uso: python diag_asignacion.py --workers 3 [--days a:b]
"""
from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]            # .../prediccion colectivos
sys.path.insert(0, str(ROOT))
V2B = ROOT / "data" / "ml" / "v2b"
OUT = V2B / "diag" / "asignacion" / "_days"
DATA_DIR = Path("//192.168.0.18/buffer/grabaciones")
LINES = ["26", "39", "42", "92", "124", "151", "168", "50", "106", "107", "108", "132", "12", "15", "128"]
HBIN = 2.0            # bins de 0,5 m: idx = ceil(2*perp)
HMAX = 1000           # 500 m
CLEAN_M = 45.0
OC_MARGIN = 10.0      # "otro más cerca" = perp_otro < perp_asignado - OC_MARGIN
BACK_M = 150.0
SIM_EVERY = 5         # simulación FIT_M=45 en 1 de cada SIM_EVERY días


def _parts(name: str):
    s = name.split(":", 1)[1] if ":" in name else name
    if ":" in s:
        s = s.split(":", 1)[1]
    ps = [re.sub(r"^x\s+", "", p.strip()) for p in s.split("→")]
    return ps


def opposite_map(shapes, line):
    infos = shapes.get(line)
    parts = {i.shape_id: _parts(i.name) for i in infos}
    opp = {}
    for a in infos:
        opp[a.shape_id] = {b.shape_id for b in infos
                           if b.shape_id != a.shape_id and len(parts[a.shape_id]) > 1
                           and parts[a.shape_id] == parts[b.shape_id][::-1]}
    return opp


def trip_geom_full(trip, idx, sids, max_perp):
    from prediccion.v2.day import geometry_for_trip
    n = len(trip.points)
    lats = np.fromiter((p.lat for p in trip.points), dtype=np.float64, count=n)
    lons = np.fromiter((p.lon for p in trip.points), dtype=np.float64, count=n)
    g = geometry_for_trip(trip, idx, max_perp=max_perp)
    if g is None:
        return None
    Dall = np.empty((len(sids), n)); Pall = np.empty((len(sids), n))
    for k, s in enumerate(sids):
        Dall[k], Pall[k] = idx[s].project_many(lats, lons)
    g["lats"], g["lons"], g["Dall"], g["Pall"] = lats, lons, Dall, Pall
    return g


def sim_summary(trips, shapes, max_perp):
    """Resumen de viajes para comparar segmentaciones (150 vs 45)."""
    recs = []
    for t in trips:
        idx = shapes.indices(t.line_number)
        g = geometry_for_trip_safe(t, idx, max_perp)
        recs.append({"line": t.line_number, "vid": t.vehicle_id, "t0": int(t.points[0].ts), "t1": int(t.points[-1].ts),
                     "n": len(t.points), "shape": g[0], "n_valid": g[1], "start_unknown": g[2],
                     "reason": getattr(t, "end_reason", ""), "seg_su": bool(getattr(t, "start_unknown", False))})
    return pd.DataFrame(recs)


def geometry_for_trip_safe(trip, idx, max_perp):
    from prediccion.v2.day import geometry_for_trip
    from prediccion.v2.segmenter import START_UNKNOWN_M
    if not idx:
        return ("", 0, False)
    g = geometry_for_trip(trip, idx, max_perp=max_perp)
    if g is None:
        return ("", 0, False)
    v = g["valid"]
    su = bool(v.sum() >= 1 and g["dist"][v][0] > START_UNKNOWN_M)
    return (g["shape_id"], int(v.sum()), su)


def transitions(df, opp):
    """Clasifica el paso entre viajes consecutivos del mismo coche (hueco <= 300 s)."""
    out = {"same": 0, "opposite": 0, "other_ramal": 0, "no_shape": 0}
    ex = []
    for (line, vid), g in df.sort_values("t0").groupby(["line", "vid"]):
        a = g.iloc[:-1]; b = g.iloc[1:]
        for (_, r0), (_, r1) in zip(a.iterrows(), b.iterrows()):
            if r1.t0 - r0.t1 > 300:
                continue
            if not r0["shape"] or not r1["shape"]:
                out["no_shape"] += 1
            elif r0["shape"] == r1["shape"]:
                out["same"] += 1
            elif r1["shape"] in opp.get(line, {}).get(r0["shape"], set()):
                out["opposite"] += 1
            else:
                out["other_ramal"] += 1
    return out


def process_one(day, shapes, label_data, opp_maps, do_sim, val_days):
    from prediccion.v2.day import read_day, segment_vehicles, prev_day
    from prediccion.pipeline.shapes_io import resolve_label_line_index
    import prediccion.v2.segmenter as sg
    import pyarrow.parquet as pq

    t0 = time.time()
    label_index = resolve_label_line_index(label_data, on_date=day)
    label_map = {s: v["line"] for s, v in label_index.items()}
    carry = None
    pc = V2B / "daily" / f"{prev_day(day)}.carry.json"
    if pc.exists():
        carry = json.load(open(pc, encoding="utf-8"))
    vehicles, _, _ = read_day(DATA_DIR / f"{day}.ndjson.gz", label_map, set(LINES), carry, 30, False)
    trips = segment_vehicles(vehicles, label_index, shapes, "geo2", {})
    trips.sort(key=lambda t: t.start_time)

    res = {"day": day, "hist": {}, "cnt": {}, "trips": [], "pings_val": []}
    cnt = res["cnt"]
    tr = res["trips"]
    pv = []
    for trip in trips:
        ln = trip.line_number
        idx = shapes.indices(ln)
        if not idx:
            continue
        sids = list(idx)
        g = trip_geom_full(trip, idx, sids, 150.0)
        if g is None:
            continue
        c = cnt.setdefault(ln, dict.fromkeys(
            ["trips", "pings", "valid", "low", "mid", "mid_oc", "mid_oc_strict", "mid_oc_opp", "mid_oc_otherramal",
             "low_oc", "low_oc_strict", "pairs", "back150", "back150_trips", "trips_valid2"], 0))
        h = res["hist"].setdefault(ln, np.zeros(HMAX + 2, dtype=np.int64))
        a = sids.index(g["shape_id"])
        pa = g["Pall"][a]
        n = len(pa)
        h += np.bincount(np.minimum(np.ceil(pa * HBIN).astype(np.int64), HMAX + 1), minlength=HMAX + 2)
        valid = g["valid"]
        # otros recorridos
        if len(sids) > 1:
            Po = np.delete(g["Pall"], a, axis=0)
            oidx = [s for s in sids if s != g["shape_id"]]
            po = Po.min(axis=0)
            on = np.array(oidx, dtype=object)[Po.argmin(axis=0)]
            opp_set = opp_maps[ln].get(g["shape_id"], set())
            near_opp = np.fromiter((x in opp_set for x in on), dtype=bool, count=n)
        else:
            po = np.full(n, np.inf); near_opp = np.zeros(n, bool)
        oc_strict = po < pa
        oc = po < pa - OC_MARGIN
        low = valid & (pa <= CLEAN_M)
        mid = valid & (pa > CLEAN_M)
        c["trips"] += 1; c["pings"] += n; c["valid"] += int(valid.sum())
        c["low"] += int(low.sum()); c["mid"] += int(mid.sum())
        c["mid_oc"] += int((mid & oc).sum()); c["mid_oc_strict"] += int((mid & oc_strict).sum())
        c["mid_oc_opp"] += int((mid & oc & near_opp).sum()); c["mid_oc_otherramal"] += int((mid & oc & ~near_opp).sum())
        c["low_oc"] += int((low & oc).sum()); c["low_oc_strict"] += int((low & oc_strict).sum())
        # retrocesos entre válidos consecutivos
        vi = np.flatnonzero(valid)
        nb = 0; first_back = -1
        if len(vi) >= 2:
            step = np.diff(g["dist"][vi])
            bk = step < -BACK_M
            c["pairs"] += len(step); nb = int(bk.sum()); c["back150"] += nb
            if nb:
                c["back150_trips"] += 1
                first_back = int(vi[1:][bk][0])
        if valid.sum() >= 2:
            c["trips_valid2"] += 1
        # ambigüedad del viaje
        med = np.median(g["Pall"], axis=1)
        med1 = float(med[a])
        if len(sids) > 1:
            mo = np.delete(med, a)
            j = int(mo.argmin()); oidx2 = [s for s in sids if s != g["shape_id"]]
            sec, med2 = oidx2[j], float(mo[j])
            sec_opp = sec in opp_maps[ln].get(g["shape_id"], set())
        else:
            sec, med2, sec_opp = "", float("inf"), False
        first_oc = int(np.flatnonzero(mid & oc)[0]) if (mid & oc).any() else -1
        def ll(i):
            return (float(g["lats"][i]), float(g["lons"][i]), int(trip.points[i].ts)) if i >= 0 else (None, None, None)
        tr.append({"line": ln, "vid": trip.vehicle_id, "t0": int(trip.points[0].ts), "n": n, "shape": g["shape_id"],
                   "med1": med1, "med2": med2, "second": sec, "second_opp": sec_opp,
                   "n_valid": int(valid.sum()), "n_mid": int(mid.sum()), "n_mid_oc": int((mid & oc).sum()),
                   "n_back": nb, "su": bool(valid.sum() >= 1 and g["dist"][valid][0] > 1000.0),
                   "first_oc": ll(first_oc), "first_back": ll(first_back),
                   "reason": getattr(trip, "end_reason", "")})
        if valid.sum() >= 2:
            v = valid
            ts_ = np.array([p.ts for p in trip.points], dtype=np.int64)[v]
            pv.append(pd.DataFrame({"shape_id": g["shape_id"], "ts": ts_, "dist": g["dist"][v], "perp": pa[v],
                                    "oc": oc[v], "oc_strict": oc_strict[v], "opp": near_opp[v]}))
    # filas de entrenamiento del día
    rows = pq.read_table(V2B / "daily" / f"{day}.parquet",
                         columns=["line", "shape_id", "ts_p", "dist_along_m", "dist_remaining_m", "observed_eta_s"]).to_pandas()
    pdf = pd.concat(pv, ignore_index=True) if pv else pd.DataFrame(columns=["shape_id", "ts", "dist", "perp", "oc", "oc_strict", "opp"])
    rows["ri"] = np.arange(len(rows))
    rows["ts_f"] = rows["ts_p"] + rows["observed_eta_s"].round().astype(np.int64)
    rows["dist_f"] = rows["dist_along_m"].astype(np.float64) + rows["dist_remaining_m"]

    def join(rows, tcol, dcol, sfx):
        m = rows[["ri", "shape_id", tcol, dcol]].merge(pdf, left_on=["shape_id", tcol], right_on=["shape_id", "ts"], how="left")
        m = m[(m["dist"] - m[dcol]).abs() < 2.0].drop_duplicates("ri")
        return m.set_index("ri")[["perp", "oc", "oc_strict", "opp"]].add_suffix(sfx)
    jp = join(rows, "ts_p", "dist_along_m", "_p")
    jf = join(rows, "ts_f", "dist_f", "_f")
    rows = rows.set_index("ri").join(jp).join(jf)
    res["rows_matched"] = float((rows["perp_p"].notna() & rows["perp_f"].notna()).mean()) if len(rows) else 0.0
    rr = rows[["line", "shape_id", "ts_p", "dist_along_m", "dist_remaining_m", "observed_eta_s",
               "perp_p", "perp_f", "oc_p", "oc_f", "oc_strict_p", "oc_strict_f"]].copy()
    ok = rr["perp_p"].notna() & rr["perp_f"].notna()
    rc = {}
    for ln, gdf in rr[ok].groupby("line"):
        pmax = np.maximum(gdf.perp_p, gdf.perp_f)
        mid_p = gdf.perp_p > CLEAN_M; mid_f = gdf.perp_f > CLEAN_M
        any_mid = mid_p | mid_f
        oc_any = (gdf.oc_p.astype(bool) | gdf.oc_f.astype(bool))
        rc[ln] = {"rows": len(gdf), "mid_p": int(mid_p.sum()), "mid_f": int(mid_f.sum()), "mid_any": int(any_mid.sum()),
                  "mid_any_oc": int((any_mid & oc_any).sum()),
                  "oc_any_all": int(oc_any.sum()),
                  "clean": int((~any_mid & ~oc_any).sum()), "dirty": int((any_mid | oc_any).sum())}
    res["rows_cnt"] = rc
    res["rows_total"] = {ln: int(v) for ln, v in rows.groupby("line").size().items()}
    if day in val_days:
        rr[ok].to_parquet(OUT / f"{day}.rows.parquet")
    # simulación FIT_M = 45
    if do_sim:
        sim = {}
        base = sim_summary([t for t in trips if t.line_number in set(LINES)], shapes, 150.0)
        old = sg.FIT_M
        try:
            sg.FIT_M = 45.0
            trips45 = segment_vehicles(vehicles, label_index, shapes, "geo2", {})
            trips45.sort(key=lambda t: t.start_time)
        finally:
            sg.FIT_M = old
        s45 = sim_summary(trips45, shapes, 45.0)
        s45b = sim_summary(trips45, shapes, 150.0)
        sim["base"], sim["s45"], sim["s45_valid150"] = base, s45, s45b
        res["sim"] = sim
    res["elapsed"] = round(time.time() - t0, 1)
    res["n_trips_total"] = len(trips)
    return res


def chunk(args):
    days, sim_days, val_days, low = args
    if low:
        try:
            import psutil, os
            psutil.Process(os.getpid()).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except Exception:
            pass
    from prediccion.v2.shapes import LineShapes
    from prediccion.pipeline.shapes_io import load_label_line_data
    shapes = LineShapes()
    label_data = load_label_line_data(ROOT / "LABEL_LINE_MAP.json")
    opp_maps = {ln: opposite_map(shapes, ln) for ln in LINES}
    out = []
    for d in days:
        p = OUT / f"{d}.pkl"
        if p.exists():
            out.append((d, "skip")); continue
        try:
            r = process_one(d, shapes, label_data, opp_maps, d in sim_days, val_days)
            with open(str(p) + ".tmp", "wb") as f:
                pickle.dump(r, f)
            Path(str(p) + ".tmp").replace(p)
            out.append((d, f"ok {r['elapsed']}s trips={r['n_trips_total']}"))
        except Exception as e:  # noqa
            import traceback
            out.append((d, "ERR " + traceback.format_exc()[-600:]))
        print(out[-1], flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--days", default=None)
    ap.add_argument("--sim-every", type=int, default=SIM_EVERY)
    a = ap.parse_args()
    manifest = json.load(open(V2B / "manifest.json"))
    days = sorted(manifest["days"])
    if a.days:
        lo, hi = a.days.split(":")
        days = [d for d in days if lo <= d <= hi]
    ev = json.load(open(V2B / "eval" / "eval_meta.json"))
    val_days = set(ev["val_days"])
    sim_days = set(days[::a.sim_every]) | set(d for d in days if d in {"2026-07-14", "2026-08-12", "2026-09-16", "2026-10-07"})
    # reparto intercalado: cada worker toma días no consecutivos (carry viene del build, no hay dependencia)
    chunks = [(days[i::a.workers], sim_days, val_days, True) for i in range(a.workers)]
    with ProcessPoolExecutor(a.workers) as ex:
        for r in ex.map(chunk, chunks):
            pass


if __name__ == "__main__":
    main()
