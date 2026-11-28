"""Recalcula la verdad corregida (tp2_s, unv, past; real_next2_s, n_pass2_*, unv_first_s) de corridas ya hechas, SIN volver a predecir.
La verdad no depende de la variante ni de la predicción: se recomputa con core.truth_at y se reescriben solo esas columnas.
Uso: python recalcula_verdad.py IN_RUN OUT_RUN [dias|-] [workers]
Verdad = solo los shapes que sirven la parada por nombre (ramales[].stops) Y, desde 2026-11-16 (segunda corrección), solo los cruces
de coches cuyo recorrido ex post del viaje (geo2 + geo3, `core._expost_filter`) tiene la parada en su lista; cruce sin viaje ex post =
no verificable. Necesita los pings crudos (//192.168.0.18/buffer/grabaciones) para segmentar. Escribe además {day}_{line}.truth_stats.json
(cruces firmes, descartados por recorrido sin la parada, firmes sin viaje ex post, huecos). Ejemplo, 3 workers, prioridad baja:
  python recalcula_verdad.py run_base_sg run_base_xp - 3 ; python recalcula_verdad.py run_cs_sg run_cs_xp 2026-09-23,...,2026-10-03 3
Validado el 2026-11-16: con la asociación por geometría (definición retirada) reproducía columna por columna los crudos originales.
"""
from __future__ import annotations
import sys, os, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from prediccion.replay import core, run as RUN  # noqa: E402
from red import path_reference as PR  # noqa: E402

MODEL = str(ROOT / "data/ml/export/path_v3_l1_s1")
SHAPES = str(ROOT.parent / "proyectoconsola/data/line_shapes")
DATA = "//192.168.0.18/buffer/grabaciones"
LMAP = str(ROOT / "LABEL_LINE_MAP.json")


def do_day(a):
    day, inp, out = a
    inp, out = Path(inp), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lines = sorted({p.name.split("_")[1].split(".")[0] for p in inp.glob(f"{day}_*.inst.parquet")})
    todo = [ln for ln in lines if not (out / f"{day}_{ln}.inst.parquet").exists()]
    if not todo:
        return day, 0.0
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    t0 = time.time()
    bundle = PR.load_bundle(MODEL)
    per_line = RUN.load_day(day, set(todo), DATA, LMAP, SHAPES, with_trips=False)
    for ln in todo:
        inst = pd.read_parquet(inp / f"{day}_{ln}.inst.parquet")
        veh = pd.read_parquet(inp / f"{day}_{ln}.veh.parquet")
        vs = list(per_line.get(ln, {}).values())
        stops = {s.id: s for s in core.prepare_stops(bundle, ln, SHAPES, 40)}
        with core.memoized():
            cc = core.compat_for(vs, bundle.lines[ln])
            stats = {}
            passes, passes2 = core._passes(vs, list(stops.values()), bundle.lines[ln], cc, stats)
            core.MEMO.clear()
        ts = sorted(inst.t.unique())
        ik, vk = {}, {}
        for t in ts:
            live = {}
            for v in vs:
                j = int(np.searchsorted(v.ts, t, side="right")) - 1
                if j >= 0 and t - v.ts[j] <= core.HISTORY_S:
                    live[v.vid] = (j, 0)
            for sid in inst[inst.t == t].stop_id.unique():
                tp, tp2, unv, past = core.truth_at(vs, live, passes, passes2, sid, t)
                r = sorted(tp2.values())
                ik[(sid, t)] = (r[0] if r else np.nan, sum(x <= 600 for x in r), sum(x <= 1200 for x in r), min(unv.values()) if unv else np.nan)
                for vid in set(tp2) | set(unv) | past:
                    vk[(sid, t, vid)] = (tp2.get(vid, np.nan), vid in unv, vid in past)
        k = list(zip(inst.stop_id, inst.t))
        inst["real_next2_s"] = [ik[x][0] for x in k]
        inst["n_pass2_10"] = [ik[x][1] for x in k]
        inst["n_pass2_20"] = [ik[x][2] for x in k]
        inst["unv_first_s"] = [ik[x][3] for x in k]
        kv = list(zip(veh.stop_id, veh.t, veh.vehicle))
        d = [vk.get(x, (np.nan, False, False)) for x in kv]
        veh["tp2_s"] = [x[0] for x in d]
        veh["unv"] = [x[1] for x in d]
        veh["past"] = [x[2] for x in d]
        if "extra" in veh:
            veh = veh.drop(columns="extra")
        lst = veh.listed if "listed" in veh else veh.group.fillna("") != ""   # tablas de data/ml/replay/detenido: listado = tiene grupo
        veh = veh[lst | veh.tp_s.notna() | veh.tp2_s.notna()]   # filas que existían solo por un paso por geometría ya no corresponden
        veh.to_parquet(out / f"{day}_{ln}.veh.parquet")
        if (inp / f"{day}_{ln}.cs.parquet").exists():
            pd.read_parquet(inp / f"{day}_{ln}.cs.parquet").to_parquet(out / f"{day}_{ln}.cs.parquet")
        inst.to_parquet(out / f"{day}_{ln}.inst.parquet")
        import json
        stats["n_coches"] = len(vs)
        stats["n_coches_sin_viajes"] = sum(1 for v in vs if not v.trips)
        (out / f"{day}_{ln}.truth_stats.json").write_text(json.dumps(stats), encoding="utf-8")
        print(f"{day} {ln}: {len(vs)} coches {time.time()-t0:.0f}s", flush=True)
    return day, time.time() - t0


if __name__ == "__main__":
    inp, out = sys.argv[1], sys.argv[2]
    days = sorted({p.name[:10] for p in Path(inp).glob("*.inst.parquet")})
    if len(sys.argv) > 3 and sys.argv[3] != "-":
        days = [d for d in sys.argv[3].split(",") if d in days]
    w = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    with ProcessPoolExecutor(w) as ex:
        for d, el in ex.map(do_day, [(d, inp, out) for d in days]):
            print("hecho", d, f"{el:.0f}s", flush=True)
