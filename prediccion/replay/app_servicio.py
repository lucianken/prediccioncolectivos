"""
Experimento B (APP_CON_SERVICIO.md): replay de producto con distinto historial por coche en cada instante.

  w1   app recién abierta sin servicio: cada coche trae solo su último ping (sin historial propio ni de los otros coches)
  w20  app con el servicio de historial de flota: cada coche trae los pings de los últimos 20 min (propio y de los otros)
  w15  control: ventana de 15 min, lo que asume el replay de siempre (debe reproducir v4prod)

  python -m prediccion.replay.app_servicio --lines 26,39 --days 2026-09-15 --out data/ml/replay/app_servicio [--workers 6]

Escribe {out}/{variante}/{dia}_{linea}.veh.parquet y .inst.parquet con variant = "base" (formato que lee porcoche/descomposicion.py).
No cambia el comportamiento por defecto de core/run; usa historial_ca.fast_last_bus (equivalente a path_reference.last_bus).
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from prediccion.replay import core, run
from prediccion.replay.historial_ca import Ctx, fast_last_bus
from prediccion.replay.pinned import path_reference as PR

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = {"w1": 1200.0, "w20": 1200.0, "w15": 900.0}
ONE_PING = ("w1",)


def run_day(a):
    day, lines, kw = a
    out = Path(kw["out"])
    names = kw["variants"]
    todo = [ln for ln in lines if not all((out / n / f"{day}_{ln}.inst.parquet").exists() for n in names)]
    if not todo:
        return day, 0.0
    if kw["idle"]:
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x00000040)
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
                                            others_windows={n: WINDOWS[n] for n in names},
                                            one_ping=tuple(n for n in names if n in ONE_PING))
            core.MEMO.clear()
        dv, di = pd.DataFrame(rv), pd.DataFrame(ri)
        for n in names:
            d = out / n
            d.mkdir(parents=True, exist_ok=True)
            x = dv[dv.variant == n].copy(); x["variant"] = "base"
            y = di[di.variant == n].copy(); y["variant"] = "base"
            x.to_parquet(d / f"{day}_{ln}.veh.parquet")
            y.to_parquet(d / f"{day}_{ln}.inst.parquet")
        print(f"{day} {ln}: {len(stops)} paradas, {len(vs)} coches, {time.time()-t0:.0f}s", flush=True)
    return day, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "data/ml/export/path_v4_l1_s1"))
    ap.add_argument("--days", default=run.DEFAULT_DAYS)
    ap.add_argument("--lines", required=True)
    ap.add_argument("--variants", default="w1,w20")
    ap.add_argument("--stops", type=int, default=40)
    ap.add_argument("--step-min", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", default="//192.168.0.18/buffer/grabaciones")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--chunk", type=int, default=5)
    ap.add_argument("--idle", action="store_true")
    a = ap.parse_args()
    kw = dict(model=a.model, out=a.out, data_dir=a.data_dir, label_map=str(ROOT / "LABEL_LINE_MAP.json"),
              shapes_dir=str(ROOT.parent / "proyectoconsola/data/line_shapes"), stops=a.stops, step_min=a.step_min,
              ts_offset=core.CABA_TS_OFFSET_S, variants=a.variants.split(","), idle=a.idle)
    lines = a.lines.split(",")
    with ProcessPoolExecutor(a.workers) as ex:
        chunks = [lines[i:i + a.chunk] for i in range(0, len(lines), a.chunk)]
        for day, el in ex.map(run_day, [(d, ch, kw) for ch in chunks for d in a.days.split(",")]):
            print("hecho", day, f"{el:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
