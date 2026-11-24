"""
Experimento HISTORIAL_COCHE_ADELANTE.md: variantes del replay que solo cambian la ventana de historial de los OTROS coches
que recibe "coche de adelante" (last_bus). Todo lo demas (sentido 900 s, historial propio, verdad) queda igual.

  python -m prediccion.replay.historial_ca --model data/ml/export/path_v4_l1_s1 --lines 26,39 --days 2026-09-15 \
      --windows w20=1200,w60=3600,wdia=none --out data/ml/replay/histca/run [--workers 2]

`install_fast_last_bus(ctx)` reemplaza PR.last_bus (dentro de core.memoized()) por una version numpy con los pings de cada
coche proyectados una vez; da el mismo resultado que `path_reference.last_bus` (ver `check_equivalence`).
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.replay import core, run
from prediccion.replay.pinned import geo_assign as G
from prediccion.replay.pinned import path_reference as PR

ROOT = Path(__file__).resolve().parents[2]


class Ctx:
    def __init__(self, vehicles):
        self.by_id = {v.vid: v for v in vehicles}
        self.proj = {}      # (id(shape), vid) -> (d, perp)
        self.valid = {}     # (id(shape), vid, lo, j) -> (ts, d) | False
        self.scan = {}      # (id(shape), vid, lo, j, d_t) -> (tp, near)
        self.t = None

    def arrays(self, shape, vid):
        k = (id(shape), vid)
        r = self.proj.get(k)
        if r is None:
            v = self.by_id[vid]
            pp = [shape.project(float(la), float(lo)) for la, lo in zip(v.lat, v.lon)]
            r = self.proj[k] = (np.array([x[0] for x in pp]), np.array([x[1] for x in pp]))
        return r


def make_last_bus(ctx: Ctx):
    def pieces(shape, o):
        """(vid, lo, j) a evaluar para el otro coche: la ventana tal cual, o (modo viaje) cada viaje ex post del coche sobre
        este recorrido, con los pings hasta t (análogo a `_find_prev_trip` del entrenamiento)."""
        if not o.get("trip"):
            return [(o["vid"], o["lo"], o["j"])]
        key = ("trips", id(shape), o["vid"], o["j"])
        r = ctx.valid.get(key)
        if r is None:
            v = ctx.by_id[o["vid"]]
            r = []
            for a, b, sid in v.trips:
                if str(sid) != str(shape.id) or a > v.ts[o["j"]]:
                    continue
                lo = int(np.searchsorted(v.ts, a, side="left"))
                j = min(int(np.searchsorted(v.ts, b, side="right")) - 1, o["j"])
                if j > lo:
                    r.append((o["vid"], lo, j))
            ctx.valid[key] = r
        return r

    def last_bus(c, shape, others, d_t, ts_ping):
        best = None
        for o in others:
            if o["t"] != ctx.t:
                ctx.valid.clear(); ctx.scan.clear(); ctx.t = o["t"]
            for vid, lo, j in pieces(shape, o):
                tp = one(c, shape, vid, lo, j, d_t, ts_ping)
                if tp is not None and (best is None or tp > best):
                    best = tp
        if best is None:
            return PR.STATE_FALLBACK_TLB_S, False
        return min(ts_ping - best, c["tlb_cap_s"]), True

    def one(c, shape, vid, lo, j, d_t, ts_ping):
        kv = (id(shape), vid, lo, j)
        v = ctx.valid.get(kv)
        if v is None:
            d, perp = ctx.arrays(shape, vid)
            ts = ctx.by_id[vid].ts[lo:j + 1]
            dd, pp = d[lo:j + 1], perp[lo:j + 1]
            m = pp <= G.TOL_M
            if m.sum() < 2 or G.forward_fraction(dd[m], pp[m], G.TOL_M) < G.MIN_FORWARD_FRAC:
                v = False
            else:
                v = (ts[m].astype(np.float64), dd[m])
            ctx.valid[kv] = v
        if v is False:
            return None
        ks = kv + (d_t,)
        sc = ctx.scan.get(ks)
        if sc is None:
            ts, d = v
            d0, d1 = d[:-1], d[1:]
            mk = (d1 > d0) & (d0 <= d_t) & (d_t < d1)
            tp = None
            if mk.any():
                i = int(np.argmax(mk))
                tp = float(ts[i] + (d_t - d0[i]) / (d1[i] - d0[i]) * (ts[i + 1] - ts[i]))
            near = ts[np.abs(d - d_t) <= PR.FALLBACK_M]
            sc = ctx.scan[ks] = (tp, near)
        tp, near = sc
        if tp is None or tp >= ts_ping:
            nr = near[near < ts_ping]
            tp = float(nr.max()) if len(nr) else None
        return tp if (tp is not None and tp < ts_ping) else None
    return last_bus


@contextmanager
def fast_last_bus(ctx: Ctx):
    """Dentro de core.memoized(): PR.last_bus = version rapida (restaura al salir)."""
    prev = PR.last_bus
    PR.last_bus = make_last_bus(ctx)
    try:
        yield
    finally:
        PR.last_bus = prev


def parse_windows(s: str) -> dict:
    out = {}
    for it in s.split(","):
        k, v = it.split("=")
        out[k] = None if v == "none" else v if v == "trip" else float(v)
    return out


def run_day(a):
    day, lines, kw = a
    out = Path(kw["out"])
    out.mkdir(parents=True, exist_ok=True)
    todo = [ln for ln in lines if not (out / f"{day}_{ln}.inst.parquet").exists()]
    if not todo:
        return day, 0.0
    k = ctypes.windll.kernel32
    k.SetPriorityClass(k.GetCurrentProcess(), 0x00000040)   # Idle
    t0 = time.time()
    bundle = PR.load_bundle(kw["model"])
    per_line = run.load_day(day, set(todo), kw["data_dir"], kw["label_map"], kw["shapes_dir"])
    insts = core.instants_for_day(day, step_min=kw["step_min"])
    for ln in todo:
        vs = list(per_line.get(ln, {}).values())
        if not vs:
            continue
        stops = core.prepare_stops(bundle, ln, kw["shapes_dir"], kw["stops"])
        with core.memoized():
            ctx = Ctx(vs)
            with fast_last_bus(ctx):
                rv, ri = core.evaluate_line(bundle, ln, vs, stops, insts, ("base",), day, ts_offset_s=kw["ts_offset"],
                                            others_windows=kw["windows"])
            core.MEMO.clear()
        pd.DataFrame(rv).to_parquet(out / f"{day}_{ln}.veh.parquet")
        pd.DataFrame(ri).to_parquet(out / f"{day}_{ln}.inst.parquet")
        print(f"{day} {ln}: {len(stops)} paradas, {len(vs)} coches, {time.time()-t0:.0f}s", flush=True)
    return day, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "data/ml/export/path_v4_l1_s1"))
    ap.add_argument("--days", default=run.DEFAULT_DAYS)
    ap.add_argument("--lines", required=True)
    ap.add_argument("--windows", default="w20=1200,w60=3600,wdia=none,wviaje=trip")
    ap.add_argument("--stops", type=int, default=40)
    ap.add_argument("--step-min", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", default="//192.168.0.18/buffer/grabaciones")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--chunk", type=int, default=5, help="líneas por tarea (cada tarea carga el día una vez)")
    a = ap.parse_args()
    k = ctypes.windll.kernel32
    k.SetPriorityClass(k.GetCurrentProcess(), 0x00000040)
    kw = dict(model=a.model, out=a.out, data_dir=a.data_dir, label_map=str(ROOT / "LABEL_LINE_MAP.json"),
              shapes_dir=str(ROOT.parent / "proyectoconsola/data/line_shapes"), stops=a.stops, step_min=a.step_min,
              ts_offset=core.CABA_TS_OFFSET_S, windows=parse_windows(a.windows))
    lines = a.lines.split(",")
    with ProcessPoolExecutor(a.workers) as ex:
        chunks = [lines[i:i + a.chunk] for i in range(0, len(lines), a.chunk)]
        for day, el in ex.map(run_day, [(d, ch, kw) for ch in chunks for d in a.days.split(",")]):
            print("hecho", day, f"{el:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
