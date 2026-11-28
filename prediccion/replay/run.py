"""
Lanzador del replay: python -m prediccion.replay.run --model data/ml/export/path_v2c_l1_s1 --days 2026-09-15,... \
    --lines 26,39,... --variants base,sentido,ramal,cs --cs-days d1,d2 --out data/ml/replay/run1 [--workers 3]
Escribe por (día, línea): {out}/{day}_{line}.veh.parquet y .inst.parquet (se salta lo ya hecho), y {out}/meta.json con la
versión de `red` (reglas y referencia de la app, bondi/red) y los parámetros de cada invocación.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

import red
from prediccion.replay import core, prior_ramal
from red import path_reference as PR

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LINES = "26,39,42,50,92,106,107,108,124,132,151,168"
DEFAULT_DAYS = "2026-09-15,2026-09-16,2026-09-17,2026-09-18,2026-09-19,2026-09-20,2026-10-03,2026-10-04,2026-10-06,2026-10-08"


def load_day(day, lines, data_dir, label_map, shapes_dir, with_trips=True):
    """Pings por coche y recorrido ex post de sus viajes (segmentador geo2 + geo3: variante oráculo y verdad por recorrido).
    `with_trips` se conserva por compatibilidad y se ignora: desde 2026-11-16 los viajes se calculan siempre, porque la verdad
    (core._passes) cuenta un cruce solo si el recorrido ex post del coche tiene la parada en su lista."""
    from red.label_map import load_label_line_data, resolve_label_line_index
    from prediccion.v2.day import geometry_for_trip, read_day, segment_vehicles
    from prediccion.v2.shapes import LineShapes
    label_index = resolve_label_line_index(load_label_line_data(label_map), on_date=day)
    lm = {s: v["line"] for s, v in label_index.items()}
    vehicles, _, _ = read_day(Path(data_dir) / f"{day}.ndjson.gz", lm, set(lines), None, 30, False)
    shapes = LineShapes(shapes_dir)
    trips = segment_vehicles(vehicles, label_index, shapes, "geo2")
    per_line: dict[str, dict[str, core.Veh]] = {}
    for vid, rec in vehicles.items():
        ln = lm.get(rec["label"].split("-")[-1]) if rec["label"] else None
        if ln in lines and rec["obs"]:
            per_line.setdefault(ln, {})[vid] = core._veh_arrays(vid, rec["obs"])
            per_line[ln][vid].expost = True
    for tr in trips:
        ln = tr.line_number
        if ln not in lines or tr.vehicle_id not in per_line.get(ln, {}):
            continue
        idx = shapes.indices(ln)
        g = geometry_for_trip(tr, idx, assign="geo3") if idx else None
        per_line[ln][tr.vehicle_id].trips.append((float(tr.points[0].ts), float(tr.points[-1].ts), g["shape_id"] if g else ""))
    for d in per_line.values():
        for v in d.values():
            v.trips.sort()
    return per_line


def build_cs_rid(map_path, table_path) -> dict:
    """{route_id: (terna, [shape_ids] | None)} como la app: csRamalOf (route_id -> terna 'longName|shortName|description' con
    espacios colapsados, en ROUTE_AGENCY_MAP) y config/ramal_cuandosubo.json (terna -> shape_ids). Solo la variante cs."""
    routes = json.loads(Path(map_path).read_text(encoding="utf-8"))["routes"]
    table = json.loads(Path(table_path).read_text(encoding="utf-8"))["ramales"]
    n = lambda x: re.sub(r"\s+", " ", str("" if x is None else x)).strip()   # noqa: E731
    out = {}
    for rid, r in routes.items():
        k = "|".join(n(r.get(f)) for f in ("longName", "shortName", "description"))
        if k == "||":
            continue
        ids = table.get(k, {}).get("shape_ids") if k in table else None
        out[str(rid)] = (k, [str(i) for i in ids] if ids else None)
    return out


def run_day(a):
    day, lines, kw = a
    out = Path(kw["out"])
    out.mkdir(parents=True, exist_ok=True)
    todo = [ln for ln in lines if not (out / f"{day}_{ln}.inst.parquet").exists()]
    if not todo:
        return day, 0.0
    try:
        os.nice(10)
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    t0 = time.time()
    bundle = PR.load_bundle(kw["model"])
    variants = kw["variants"]
    cs_rid = build_cs_rid(kw["cs_map"], kw["cs_table"]) if "cs" in variants and day in kw["cs_days"] else None
    if cs_rid is None:
        variants = tuple(v for v in variants if v != "cs")
    per_line = load_day(day, set(todo), kw["data_dir"], kw["label_map"], kw["shapes_dir"], with_trips=variants != ("base",))
    insts = core.instants_for_day(day, step_min=kw["step_min"])
    for ln in todo:
        vs = list(per_line.get(ln, {}).values())
        if not vs:
            continue
        stops = core.prepare_stops(bundle, ln, kw["shapes_dir"], kw["stops"])
        cs_out = [] if cs_rid is not None else None
        pctx = None
        if any(v in prior_ramal.VARIANTS for v in variants):
            pctx = prior_ramal.PriorCtx.load(day, ln, bundle.lines[ln], kw["prior_dir"])
        with core.memoized():
            rv, ri = core.evaluate_line(bundle, ln, vs, stops, insts, variants, day, ts_offset_s=kw["ts_offset"],
                                        cs_rid=cs_rid, cs_out=cs_out, prior_ctx=pctx)
            core.MEMO.clear()
        if cs_out:
            pd.DataFrame(cs_out).to_parquet(out / f"{day}_{ln}.cs.parquet")
        pd.DataFrame(rv).to_parquet(out / f"{day}_{ln}.veh.parquet")
        pd.DataFrame(ri).to_parquet(out / f"{day}_{ln}.inst.parquet")
        print(f"{day} {ln}: {len(stops)} paradas, {len(vs)} coches, {time.time()-t0:.0f}s", flush=True)
    return day, time.time() - t0


def write_run_meta(out, info: dict) -> dict:
    """{out}/meta.json de la corrida: `red_version` (versión de `red` con que corre la lógica de la app) y los parámetros de
    cada invocación (se agregan al reanudar). Una carpeta no mezcla versiones de `red`: si ya tiene salidas de otra versión,
    o salidas sin meta.json (corridas anteriores a importar `red`), falla y hay que usar otro --out."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "meta.json"
    if p.exists():
        meta = json.loads(p.read_text(encoding="utf-8"))
        if meta.get("red_version") != red.__version__:
            raise ValueError(f"{out} tiene corridas con red {meta.get('red_version')} y está instalado red {red.__version__}: "
                             "usar otro --out")
    elif any(out.glob("*.inst.parquet")):
        raise ValueError(f"{out} tiene salidas sin meta.json (corrida anterior a registrar la versión de red): usar otro --out")
    else:
        meta = {"red_version": red.__version__, "invocaciones": []}
    meta["invocaciones"].append(info)
    p.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "data/ml/export/path_v2c_l1_s1"))
    ap.add_argument("--days", default=DEFAULT_DAYS)
    ap.add_argument("--lines", default=DEFAULT_LINES)
    ap.add_argument("--variants", default="base,sentido,ramal")
    ap.add_argument("--stops", type=int, default=40)
    ap.add_argument("--step-min", type=int, default=10)
    ap.add_argument("--out", default=str(ROOT / "data/ml/replay/run1"))
    ap.add_argument("--data-dir", default="//192.168.0.18/buffer/grabaciones")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cs-map", default=str(ROOT.parent / "proyectoconsola/ROUTE_AGENCY_MAP.json"),
                    help="copia de ROUTE_AGENCY_MAP vigente en los días de --cs-days (variante cs)")
    ap.add_argument("--cs-table", default=str(ROOT.parent / "proyectoconsola/public/config/ramal_cuandosubo.json"))
    ap.add_argument("--cs-days", default="", help="días en que --cs-map resuelve los route_id (ver FILTRO_RAMAL_CS.md); la variante cs solo corre ahí")
    ap.add_argument("--shapes-dir", default=str(ROOT.parent / "proyectoconsola/data/line_shapes"),
                    help="line_shapes/{linea}.json con ramales[].stops (paradas); para v4 usar data/backup_line_shapes_2026-11-26 (= shapes del export)")
    ap.add_argument("--prior-dir", default=str(ROOT / "data/ml/replay/prior"), help="P_eventos.parquet y meta.json del prior causal (variantes prior_*)")
    ap.add_argument("--ts-offset", type=float, default=core.CABA_TS_OFFSET_S, help="corrimiento del sello de CABA descontado del ETA anunciado (s)")
    a = ap.parse_args()
    kw = dict(model=a.model, out=a.out, data_dir=a.data_dir, label_map=str(ROOT / "LABEL_LINE_MAP.json"),
              shapes_dir=a.shapes_dir, prior_dir=a.prior_dir, variants=tuple(a.variants.split(",")),
              stops=a.stops, step_min=a.step_min, ts_offset=a.ts_offset,
              cs_map=a.cs_map, cs_table=a.cs_table, cs_days=set(filter(None, a.cs_days.split(","))))
    days = a.days.split(",")
    lines = a.lines.split(",")
    man = Path(a.model) / "manifest.json"
    write_run_meta(a.out, {"fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": a.model,
                           "model_version": json.loads(man.read_text(encoding="utf-8")).get("model_version") if man.exists() else None,
                           "days": days, "lines": lines, "variants": list(kw["variants"]), "stops": a.stops,
                           "step_min": a.step_min, "ts_offset_s": a.ts_offset, "shapes_dir": a.shapes_dir,
                           "prior_dir": a.prior_dir, "cs_days": sorted(kw["cs_days"])})
    with ProcessPoolExecutor(a.workers) as ex:
        for day, el in ex.map(run_day, [(d, lines, kw) for d in days]):
            print("hecho", day, f"{el:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
