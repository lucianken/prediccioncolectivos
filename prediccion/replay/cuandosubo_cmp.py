"""
Comparación CuandoSubo vs modelo vs llegada real en las paradas del panel del grabador de CuandoSubo.
Módulo aparte: no cambia `core.py` ni `run.py`; parchea en memoria (solo en este proceso) `core.compat_for` y `core._passes`
para reusar el cálculo por (línea, día) entre paradas.

Uso (desde la raíz del repo, PYTHONPATH=.):
  python -m prediccion.replay.cuandosubo_cmp --model data/ml/export/path_v4_l1_s1 --days 2026-11-18 --lines 39 \
      --out data/ml/replay/cuandosubo/run --workers 2

Por (día, línea) escribe {out}/{día}_{línea}.veh.parquet y .inst.parquet (replay del modelo, columnas de core.evaluate_line,
solo en las paradas e instantes de las consultas de CuandoSubo) y .cs.parquet (un registro por coche listado por CuandoSubo,
con la verdad de CABA del mismo coche y parada).
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.replay import core
from prediccion.replay.pinned import path_reference as PR

ROOT = Path(__file__).resolve().parents[2]
CS_DIR = "//192.168.0.18/buffer/grabaciones_cuandosubo"
BA = -3 * 3600

# Parada OBA (panel de arrival_stops.json) -> parada OSM de `line_shapes/{línea}.json` (ramales[].stops).
# Criterio: la parada OSM más cercana (<= 11 m) cuyos ramales van en el sentido del headsign de OBA. Revisado a mano (2026-11-22);
# ninguna quedó dudosa. Distancias (m): 39: 8, 11, 7; 42: 4, 17, 5; 92: 7, 5, 16; 168: 6, 9, 5; 152: 3, 7, 5.
# 42 medio (Guzmán y Newbery, 17 m): única candidata a < 80 m. 92 final (Av. General Paz, 16 m): la otra candidata (Eva Perón y
# Gral.Paz, 23 m) es del sentido opuesto. 152 medio: 9 de Julio (7 m) y no Santa Fe y Suipacha (36 m).
PANEL = {
    "39": [("14_206600", "n1493476757"), ("14_203270", "n2719439787"), ("14_201063", "n3909887526")],
    "42": [("14_204691", "n2747920157"), ("14_20796", "n2892599806"), ("14_206135", "n13148755645")],
    "92": [("14_205731", "n5076531539"), ("14_201704", "n3713013093"), ("14_203994", "n3048390056")],
    "168": [("14_S00094695", "n3606354766"), ("14_S00094827", "n7727258306"), ("14_S00094902", "n4704721415")],
    "152": [("14_S00081644", "n3646859385"), ("14_S00081575", "n3447885521"), ("14_S00081526", "n4911904604")],
}

# huecos de CABA > 3 min y reinicios (unix s), medidos 2026-11-22; se excluyen +-10 min
EXCLUDE = [(1794691356, 1794693396), (1794834420, 1794834662), (1794838982, 1794839702), (1794897522, 1794901906),
           (1794919320, 1794919558), (1794963098, 1794963338), (1795065636, 1795065876), (1795076268, 1795076450),
           (1795175860, 1795176842), (1794603532, 1794604372), (1794604221, 1794604221 + 619), (1794839606, 1794839606 + 617),
           (1794901732, 1794901732 + 4165)]
EXCL_PAD = 600
WIN = (6, 23)   # horas BA


def _bounds(day: str) -> tuple[int, int]:
    base = core.instants_for_day(day, WIN[0], WIN[0], 10)[0]
    return base, base + (WIN[1] - WIN[0]) * 3600


def _excluded(t: int) -> bool:
    return any(a - EXCL_PAD <= t <= b + EXCL_PAD for a, b in EXCLUDE)


def load_arribos(day: str, line: str) -> pd.DataFrame:
    """Consultas de arribos de las paradas del panel de `line` en `day` -> una fila por (consulta, entrada)."""
    ids = {a: o for a, o in PANEL[line]}
    rows, queries = [], []
    with gzip.open(f"{CS_DIR}/arribos/{day}.ndjson.gz", "rt") as f:
        for l in f:
            fr = json.loads(l)
            if fr["stop"] not in ids or fr["line"] != line:
                continue
            queries.append((fr["stop"], fr["t"]))
            for a in fr["arrivals"]:
                rows.append({"stop_oba": fr["stop"], "t": fr["t"], "vehicle": a.get("vehicle"), "label": a.get("label"),
                             "veh_line": a.get("veh_line"), "route": a.get("route"), "trip": a.get("trip"),
                             "predicted": bool(a.get("predicted")), "pred_arr": a.get("pred_arr"),
                             "stops_away": a.get("stops_away"), "sched_dev": a.get("sched_dev"), "veh_ts": a.get("veh_ts")})
    return pd.DataFrame(queries, columns=["stop_oba", "t"]), pd.DataFrame(rows)


def make_stops(bundle, line: str, shapes_dir: str) -> tuple[list, list]:
    """Paradas OSM del panel como core.Stop (misma construcción que core.prepare_stops, sin muestreo). Devuelve (stops, excluidas)."""
    d = json.loads((Path(shapes_dir) / f"{line}.json").read_text(encoding="utf-8"))
    want = {osm: oba for oba, osm in PANEL[line]}
    by_id: dict[str, core.Stop] = {}
    for r in d.get("ramales", []):
        for s in r.get("stops", []):
            if s["id"] in want:
                st = by_id.setdefault(s["id"], core.Stop(s["id"], s.get("name", ""), s["lat"], s["lng"], []))
                if r["name"] not in st.recorridos:
                    st.recorridos.append(r["name"])
    shapes = bundle.lines[line]
    dirs = core.direction_groups(shapes)
    out, excl = [], []
    for osm, st in by_id.items():
        us = PR.user_shapes(bundle, line, (st.lat, st.lon), "parada", st.recorridos)
        st.serving = {sid: shapes[sid].project(st.lat, st.lon)[0] for sid, (ok, _) in us.items() if ok}
        if not st.serving:
            excl.append((want[osm], osm, "ningún shape la sirve"))
            continue
        st.cls = core.classify_stop(list(st.serving), dirs)
        out.append(st)
    for osm, oba in want.items():
        if osm not in by_id:
            excl.append((oba, osm, "no está en ramales[].stops"))
    return out, excl


def run_day(a):
    day, lines, kw = a
    out = Path(kw["out"])
    out.mkdir(parents=True, exist_ok=True)
    todo = [ln for ln in lines if not (out / f"{day}_{ln}.cs.parquet").exists()]
    if not todo:
        return day, 0.0
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00000040)   # Idle
    from prediccion.replay.run import load_day
    t0 = time.time()
    bundle = PR.load_bundle(kw["model"])
    per_line = load_day(day, set(todo), kw["data_dir"], kw["label_map"], kw["shapes_dir"])
    print(f"{day} carga {time.time()-t0:.0f}s", flush=True)
    lo, hi = _bounds(day)
    orig_compat, orig_passes = core.compat_for, core._passes
    for ln in todo:
        vs = list(per_line.get(ln, {}).values())
        if not vs:
            continue
        t1 = time.time()
        shapes = bundle.lines[ln]
        stops, excl = make_stops(bundle, ln, kw["shapes_dir"])
        queries, arr = load_arribos(day, ln)
        cc = orig_compat(vs, shapes)
        pcache: dict = {}

        def passes_cached(vehicles, stops_, shapes_, compat_cache, stats=None, expost=None, _c=pcache):
            k = tuple(s.id for s in stops_)
            if k not in _c:
                _c[k] = orig_passes(vehicles, stops_, shapes_, compat_cache, stats, expost)
            return _c[k]

        core.compat_for = lambda v, s, _cc=cc: _cc
        core._passes = passes_cached
        by_id = {v.vid: v for v in vs}
        rv_all, ri_all, cs_rows, meta = [], [], [], {"excluidas": excl, "paradas": [s.id for s in stops]}
        try:
            for st in stops:
                oba = next(o for o, osm in PANEL[ln] if osm == st.id)
                ts = sorted({int(t) for t in queries[queries.stop_oba == oba].t if lo <= t <= hi and not _excluded(int(t))})
                if not ts:
                    continue
                with core.memoized():
                    rv, ri = core.evaluate_line(bundle, ln, vs, [st], ts, kw["variants"], day, ts_offset_s=kw["ts_offset"])
                    core.MEMO.clear()
                rv_all += rv
                ri_all += ri
                passes, passes2 = pcache[(st.id,)]
                a_st = arr[arr.stop_oba == oba] if len(arr) else arr
                g = {t: x for t, x in a_st.groupby("t")} if len(a_st) else {}
                for t in ts:
                    live = {}
                    for v in vs:
                        j = int(np.searchsorted(v.ts, t, side="right")) - 1
                        if j < 0 or t - v.ts[j] > core.HISTORY_S:
                            continue
                        live[v.vid] = (j, int(np.searchsorted(v.ts, t - core.HISTORY_S, side="left")))
                    _, tp2_by, unv_by, past_by = core.truth_at(vs, live, passes, passes2, st.id, t)
                    x = g.get(t)
                    if x is None:
                        continue
                    for r in x.itertuples():
                        if not r.vehicle:
                            continue
                        cs_rows.append({"day": day, "line": ln, "stop_oba": oba, "stop_id": st.id, "t": t, "vehicle": r.vehicle,
                                        "label": r.label, "veh_line": r.veh_line, "route": r.route, "trip": r.trip,
                                        "predicted": r.predicted, "pred_arr": r.pred_arr, "stops_away": r.stops_away,
                                        "sched_dev": r.sched_dev, "veh_ts": r.veh_ts,
                                        "cs_eta_s": (r.pred_arr - t) if r.pred_arr else np.nan,
                                        "in_caba": r.vehicle in by_id, "live": r.vehicle in live,
                                        "tp2_s": tp2_by.get(r.vehicle, np.nan), "unv": r.vehicle in unv_by,
                                        "past": r.vehicle in past_by})
        finally:
            core.compat_for, core._passes = orig_compat, orig_passes
        # consultas del panel sin coche (para "sin predicción de CuandoSubo")
        qn = queries.assign(n=1).groupby("stop_oba").n.sum().to_dict()
        meta["consultas"] = {k: int(v) for k, v in qn.items()}
        if len(arr):
            m = arr[arr.vehicle.notna()]
            meta["entradas_con_coche"] = int(len(m))
            meta["entradas_otra_linea"] = int((m.veh_line.notna() & (m.veh_line != ln)).sum())
            meta["entradas_sin_linea"] = int(m.veh_line.isna().sum())
            meta["entradas_solo_horario"] = int((~arr.predicted).sum())
        pd.DataFrame(rv_all).to_parquet(out / f"{day}_{ln}.veh.parquet")
        pd.DataFrame(ri_all).to_parquet(out / f"{day}_{ln}.inst.parquet")
        pd.DataFrame(cs_rows).to_parquet(out / f"{day}_{ln}.cs.parquet")
        (out / f"{day}_{ln}.meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        print(f"{day} {ln}: {len(stops)} paradas, {len(vs)} coches, {len(ri_all)} instantes-variante, {len(cs_rows)} entradas CS, "
              f"{time.time()-t1:.0f}s (acum {time.time()-t0:.0f}s)", flush=True)
    return day, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "data/ml/export/path_v4_l1_s1"))
    ap.add_argument("--days", default="2026-11-18")
    ap.add_argument("--lines", default="39,42,92,168,152")
    ap.add_argument("--variants", default="base")
    ap.add_argument("--out", default=str(ROOT / "data/ml/replay/cuandosubo/run"))
    ap.add_argument("--data-dir", default="//192.168.0.18/buffer/grabaciones")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--ts-offset", type=float, default=core.CABA_TS_OFFSET_S)
    a = ap.parse_args()
    kw = dict(model=a.model, out=a.out, data_dir=a.data_dir, label_map=str(ROOT / "LABEL_LINE_MAP.json"),
              shapes_dir=str(ROOT.parent / "proyectoconsola/data/line_shapes"), variants=tuple(a.variants.split(",")),
              ts_offset=a.ts_offset)
    days, lines = a.days.split(","), a.lines.split(",")
    with ProcessPoolExecutor(a.workers) as ex:
        for day, el in ex.map(run_day, [(d, lines, kw) for d in days]):
            print(f"día {day} listo {el:.0f}s", flush=True)


if __name__ == "__main__":
    main()
