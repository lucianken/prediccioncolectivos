"""
Consistencia temporal del ETA anunciado (ARQUITECTURA.md §11 ítem 4a). Experimento de medición, no toca la app ni el modelo.
Para cada (línea, día): ventana aleatoria de WINDOW_H (2) horas, consultas cada 60 s, paradas = muestra aleatoria con semilla de
las paradas de la línea; variante base (ramal y sentido desconocidos, producción). Guarda los coches LISTADOS (top 5 de la app)
con su ETA anunciado, el último ping vigente y la verdad corregida. python -m prediccion.replay.consistencia --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.replay import core
from prediccion.replay.pinned import geo_assign as G
from prediccion.replay.pinned import path_reference as PR
from prediccion.replay.run import load_day

ROOT = Path(__file__).resolve().parents[2]
LINES = "26,39,42,50,92,106,107,108,124,132,151,168".split(",")
STEP_S = 60
WINDOW_H = 2
SEED = 20261116
N_STOPS = 150
N_DAYS = 12


def pick_days(seed=SEED):
    """12 días al azar de 2026-09-15..2026-10-14 (período de validación) con grabación, 4 de fin de semana."""
    import datetime as dt
    avail = sorted(p.name[:10] for p in Path("//192.168.0.18/buffer/grabaciones").glob("2026-*.ndjson.gz"))
    avail = [d for d in avail if "2026-09-15" <= d <= "2026-10-14"]
    wk = [d for d in avail if dt.date.fromisoformat(d).weekday() >= 5]
    wd = [d for d in avail if d not in wk]
    r = random.Random(seed)
    k = min(4, len(wk))
    return sorted(r.sample(wk, k) + r.sample(wd, N_DAYS - k))


def window_start_h(day, line):
    h = int(hashlib.md5(f"{SEED}{day}{line}".encode()).hexdigest(), 16)
    return 6 + h % (23 - WINDOW_H - 6 + 1)     # 6..21


def sample_stops(bundle, line, shapes_dir):
    allst = core.prepare_stops(bundle, line, shapes_dir, per_line=10**6)
    rng = np.random.default_rng(SEED + int(line))
    if len(allst) > N_STOPS:
        idx = np.sort(rng.choice(len(allst), N_STOPS, replace=False))
        allst = [allst[i] for i in idx]
    return allst


def run_task(a):
    day, line, kw = a
    out = Path(kw["out"])
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{day}_{line}.parquet"
    if f.exists():
        return day, line, 0, 0.0
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    t0 = time.time()
    bundle = PR.load_bundle(kw["model"])
    per_line = load_day(day, {line}, kw["data_dir"], kw["label_map"], kw["shapes_dir"], with_trips=False)
    vehicles = list(per_line.get(line, {}).values())
    if not vehicles:
        pd.DataFrame().to_parquet(f)
        return day, line, 0, time.time() - t0
    stops = sample_stops(bundle, line, kw["shapes_dir"])
    shapes = bundle.lines[line]
    from datetime import datetime, timezone
    base = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) + 3 * 3600
    h0 = window_start_h(day, line)
    instants = [base + h0 * 3600 + s for s in range(0, WINDOW_H * 3600 + 1, STEP_S)]
    by_id = {v.vid: v for v in vehicles}
    rows = []
    with core.memoized():
        compat = {}
        all_ids = list(shapes)
        for v in vehicles:
            n = len(v.ts)
            perp = np.empty((len(all_ids), n))
            dist = np.empty((len(all_ids), n))
            for k, sid in enumerate(all_ids):
                sh = shapes[sid]
                for i in range(n):
                    dist[k, i], perp[k, i] = sh.project(float(v.lat[i]), float(v.lon[i]))
            lim = G.compat_limit(perp.min(axis=0))
            for k, sid in enumerate(all_ids):
                compat[(v.vid, sid)] = (dist[k], perp[k] <= lim)
        passes, passes2 = core._passes(vehicles, stops, shapes, compat)
        for ti, t in enumerate(instants):
            live = {}
            for v in vehicles:
                j = int(np.searchsorted(v.ts, t, side="right")) - 1
                if j < 0 or t - v.ts[j] > core.HISTORY_S:
                    continue
                live[v.vid] = (j, int(np.searchsorted(v.ts, t - core.HISTORY_S, side="left")))
            snap = max((float(by_id[vid].ts[j]) for vid, (j, _) in live.items()), default=float(t))
            others_by_vid = {vid: {"pings": [(float(by_id[vid].ts[i]), float(by_id[vid].lat[i]), float(by_id[vid].lon[i]))
                                              for i in range(lo, j + 1)]} for vid, (j, lo) in live.items()}
            for st in stops:
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
                _, tp2_by, unv_by, past_by = core.truth_at(vehicles, live, passes, passes2, st.id, t)
                for rank, (vid, g, eta) in enumerate(lst["shown"]):
                    v = by_id[vid]
                    j = live[vid][0]
                    tp2 = tp2_by.get(vid, np.nan)
                    past = vid in past_by
                    unv = vid in unv_by
                    rows.append((line, day, st.id, t, vid, rank, g, eta, lst["eta0"][vid], float(v.ts[j]), tp2, past, unv))
            if ti % 10 == 9:
                core.MEMO.clear()
    cols = ["line", "day", "stop", "t", "veh", "rank", "group", "eta_s", "eta0_s", "ping_ts", "tp2_s", "past", "unv"]
    pd.DataFrame(rows, columns=cols).to_parquet(f)
    return day, line, len(stops), time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "data/ml/export/path_v3_l1_s1"))
    ap.add_argument("--out", default=str(ROOT / "data/ml/replay/consistencia/run"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--days", default="")
    ap.add_argument("--lines", default=",".join(LINES))
    ap.add_argument("--data-dir", default="//192.168.0.18/buffer/grabaciones")
    a = ap.parse_args()
    kw = dict(model=a.model, out=a.out, data_dir=a.data_dir, label_map=str(ROOT / "LABEL_LINE_MAP.json"),
              shapes_dir=str(ROOT.parent / "proyectoconsola/data/line_shapes"))
    days = a.days.split(",") if a.days else pick_days()
    print("dias", days, flush=True)
    tasks = [(d, ln, kw) for d in days for ln in a.lines.split(",")]
    with ProcessPoolExecutor(a.workers) as ex:
        for day, ln, ns, el in ex.map(run_task, tasks):
            print(f"{day} {ln}: {ns} paradas {el:.0f}s", flush=True)
    print("FIN", flush=True)


if __name__ == "__main__":
    sys.exit(main())
