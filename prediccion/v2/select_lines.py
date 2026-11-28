"""
Selección de líneas (ARQUITECTURA.md §4.4).

Dos pasos:
  1) measure: sobre una muestra de días mide, por línea AMBA 1-199 con recorrido en line_shapes/:
       viajes/día, cobertura de trip_id (y start_time, que es lo que usa el segmentador),
       error perpendicular mediano al mejor recorrido, fracción de puntos <= 150 m, agencia(s).
     -> data/ml/v2/line_metrics.json
  2) propose: elige train/heldout a partir de las métricas -> data/ml/v2/lines.json

Uso:
  python -m prediccion.v2.select_lines measure --days 2026-07-15,2026-08-18,2026-09-17,2026-10-07,2026-08-22 --workers 3
  python -m prediccion.v2.select_lines propose
"""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date as _date
from pathlib import Path

import numpy as np

from red.label_map import load_label_line_data, resolve_label_line_index
from prediccion.v2.day import read_day, segment_vehicles, geometry_for_trip
from prediccion.v2.shapes import (DEFAULT_DATA_DIR, DEFAULT_LABEL_MAP, DEFAULT_LINE_SHAPES_DIR,
                                  DEFAULT_V2_DIR, LineShapes)

CURRENT_LINES = ["26", "39", "42", "92", "124", "151", "168"]

# Criterios de elegibilidad (ver propose)
# Nota: la cobertura de trip_id "normal" ronda 0,85-0,92 (el resto son pings de coches sin viaje asignado);
# las líneas sin trip_id real están en ~0 (4, 25, 124, 84, 102), por eso el corte es 0,60 y no 0,90.
MIN_TRIPS_WEEKDAY = 300
MIN_TRIP_ID_COV = 0.60
MIN_START_TIME_COV = 0.60
MAX_MEDIAN_PERP_M = 15.0
MIN_FRAC_WITHIN_150 = 0.92
MIN_FRAC_TRIPS_PERP_LE_50 = 0.80   # fracción de viajes cuyo error mediano al mejor recorrido es <= 50 m
N_EXTRA_TRAIN = 29
N_HELDOUT = 8


def amba_lines(shapes: LineShapes) -> list[str]:
    return [ln for ln in shapes.available_lines() if ln.isdigit() and 1 <= int(ln) <= 199]


def _measure_day(args) -> tuple[str, dict]:
    day, shapes_dir, data_dir, label_map_path, only_lines = args
    t0 = time.time()
    shapes = LineShapes(shapes_dir)
    label_data = load_label_line_data(label_map_path)
    index = resolve_label_line_index(label_data, on_date=day)
    label_map = {s: v["line"] for s, v in index.items()}
    lines = set(amba_lines(shapes)) & set(label_map.values())
    if only_lines:
        lines &= set(only_lines)
    vehicles, stats, _ = read_day(Path(data_dir) / f"{day}.ndjson.gz", label_map, lines)
    mstats: dict = {}
    trips = segment_vehicles(vehicles, index, shapes, "geo", stats=mstats)
    del vehicles
    agg: dict[str, dict] = {}
    for trip in trips:
        ln = trip.line_number
        if ln not in lines:
            continue
        a = agg.setdefault(ln, {"trips": 0, "medians": [], "valid": 0, "points": 0, "agencies": {}})
        a["trips"] += 1
        if trip.agency_id:
            a["agencies"][trip.agency_id] = a["agencies"].get(trip.agency_id, 0) + 1
        idx = shapes.indices(ln)
        g = geometry_for_trip(trip, idx) if idx else None
        if g is None:
            continue
        a["medians"].append(g["median_perp"])
        a["valid"] += int(g["valid"].sum())
        a["points"] += len(g["valid"])
    out = {}
    for ln, a in agg.items():
        s = stats.get(ln, [0, 0, 0])
        med = np.array(a["medians"]) if a["medians"] else np.array([np.nan])
        out[ln] = {
            "trips": a["trips"], "pings": s[0],
            "trip_id_cov": s[1] / s[0] if s[0] else 0.0,
            "start_time_cov": s[2] / s[0] if s[0] else 0.0,
            "median_perp_m": float(np.nanmedian(med)),
            "p90_perp_m": float(np.nanpercentile(med, 90)),
            "frac_within_150": a["valid"] / a["points"] if a["points"] else 0.0,      # sobre pings dentro de viajes
            "depot_frac": mstats[ln]["depot"] / mstats[ln]["pings"] if ln in mstats and mstats[ln]["pings"] else 0.0,
            "frac_within_150_moving": (mstats[ln]["moving_valid"] / mstats[ln]["moving_total"]
                                       if ln in mstats and mstats[ln]["moving_total"] else 0.0),
            "frac_trips_perp_le_50": float(np.mean(med <= 50.0)),
            "agencies": a["agencies"],
        }
    out["_elapsed_s"] = round(time.time() - t0, 1)
    return day, out


def measure(days: list[str], workers: int, out_path: Path, shapes_dir, data_dir, label_map, only_lines=None) -> dict:
    jobs = [(d, str(shapes_dir), str(data_dir), str(label_map), only_lines) for d in days]
    results = {}
    if workers <= 1:
        for j in jobs:
            d, r = _measure_day(j)
            results[d] = r
            print(f"  {d}: {len(r) - 1} líneas, {r['_elapsed_s']} s", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for d, r in ex.map(_measure_day, jobs):
                results[d] = r
                print(f"  {d}: {len(r) - 1} líneas, {r['_elapsed_s']} s", flush=True)
    data = {"days": days, "weekday": [d for d in days if _date.fromisoformat(d).weekday() < 5],
            "per_day": {d: {k: v for k, v in r.items() if k != "_elapsed_s"} for d, r in results.items()}}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


# ── propose ──────────────────────────────────────────────────────────────────

def _centroid(shapes: LineShapes, ln: str) -> tuple[float, float]:
    pts = np.concatenate([s.index._pts for s in shapes.get(ln)])
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def _km(a, b) -> float:
    dlat = (a[0] - b[0]) * 111.32
    dlon = (a[1] - b[1]) * 111.32 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dlat, dlon)


def summarize(metrics: dict) -> dict[str, dict]:
    """Agrega las métricas por día en una fila por línea."""
    weekday = set(metrics["weekday"])
    lines: dict[str, dict] = {}
    for day, per_line in metrics["per_day"].items():
        for ln, m in per_line.items():
            r = lines.setdefault(ln, {"days": {}, "agencies": {}})
            r["days"][day] = m
            for ag, n in m["agencies"].items():
                r["agencies"][ag] = r["agencies"].get(ag, 0) + n
    out = {}
    for ln, r in lines.items():
        ds = r["days"]
        wk = [m for d, m in ds.items() if d in weekday]
        allm = list(ds.values())
        def med(key, ms):
            return float(np.median([m.get(key, float("nan")) for m in ms])) if ms else float("nan")
        pings = sum(m["pings"] for m in allm)
        out[ln] = {
            "trips_weekday": med("trips", wk),
            "trips_all_days": {d: m["trips"] for d, m in ds.items()},
            "trip_id_cov": med("trip_id_cov", allm),
            "start_time_cov": med("start_time_cov", allm),
            "median_perp_m": med("median_perp_m", allm),
            "p90_perp_m": med("p90_perp_m", allm),
            "frac_within_150": med("frac_within_150", allm),
            "frac_within_150_moving": med("frac_within_150_moving", allm),
            "depot_frac": med("depot_frac", allm),
            "frac_trips_perp_le_50": med("frac_trips_perp_le_50", allm),
            "agencies": sorted(r["agencies"], key=lambda a: -r["agencies"][a]),
            "n_days_seen": len(ds), "pings": pings,
        }
    return out


def _reject_reason(s: dict) -> str | None:
    why = []
    if not (s["trips_weekday"] >= MIN_TRIPS_WEEKDAY):
        why.append(f"pocos viajes ({s['trips_weekday']:.0f}/día hábil < {MIN_TRIPS_WEEKDAY})")
    if s["trip_id_cov"] < MIN_TRIP_ID_COV:
        why.append(f"trip_id {s['trip_id_cov']*100:.0f}% < {MIN_TRIP_ID_COV*100:.0f}%")
    if s["start_time_cov"] < MIN_START_TIME_COV:
        why.append(f"start_time {s['start_time_cov']*100:.0f}% (el segmentador corta por start_time)")
    if not (s["median_perp_m"] <= MAX_MEDIAN_PERP_M):
        why.append(f"perp mediano {s['median_perp_m']:.0f} m > {MAX_MEDIAN_PERP_M:.0f} m")
    if s["frac_within_150"] < MIN_FRAC_WITHIN_150:
        why.append(f"solo {s['frac_within_150']*100:.0f}% de puntos <=150 m")
    if s["frac_trips_perp_le_50"] < MIN_FRAC_TRIPS_PERP_LE_50:
        why.append(f"solo {s['frac_trips_perp_le_50']*100:.0f}% de viajes con perp mediano <=50 m (recorrido incompleto/ramales faltantes)")
    return "; ".join(why) if why else None


def propose(metrics_path: Path, out_path: Path, shapes_dir) -> dict:
    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)
    shapes = LineShapes(shapes_dir)
    summ = summarize(metrics)
    all_lines = amba_lines(shapes)
    cent = {ln: _centroid(shapes, ln) for ln in all_lines}

    excluded = {}
    eligible = []
    for ln in all_lines:
        if ln in CURRENT_LINES:
            continue
        s = summ.get(ln)
        if s is None:
            excluded[ln] = "sin vehículos en la muestra (label map / sin servicio)"
            continue
        why = _reject_reason(s)
        if why:
            excluded[ln] = why
        else:
            eligible.append(ln)

    # Farthest-point sampling desde las 7 actuales, bonificando agencias nuevas. Cada línea elegida
    # recibe un rank; cada ~5ª va a heldout para que el control tenga la misma dispersión geográfica.
    chosen = list(CURRENT_LINES)
    agencies_seen = {a for ln in CURRENT_LINES for a in summ.get(ln, {}).get("agencies", [])[:1]}
    order = []
    pool = set(eligible)
    n_pick = N_EXTRA_TRAIN + N_HELDOUT
    while pool and len(order) < n_pick:
        best, best_score = None, -1.0
        for ln in sorted(pool, key=lambda x: int(x)):
            dmin = min(_km(cent[ln], cent[c]) for c in chosen)
            ag = summ[ln]["agencies"][:1]
            bonus = 1.25 if ag and ag[0] not in agencies_seen else 1.0
            quality = summ[ln]["frac_trips_perp_le_50"]                    # 0.8..1.0
            score = dmin * bonus * quality
            if score > best_score:
                best, best_score = ln, score
        order.append(best)
        chosen.append(best)
        pool.discard(best)
        agencies_seen.update(summ[best]["agencies"][:1])
    stride = max(1, len(order) // N_HELDOUT)
    heldout = [ln for i, ln in enumerate(order) if (i + 1) % stride == 0][:N_HELDOUT]
    train_extra = [ln for ln in order if ln not in heldout]
    train = sorted(CURRENT_LINES + train_extra, key=int)
    heldout = sorted(heldout, key=int)
    not_picked = sorted(set(eligible) - set(order), key=int)

    def row(ln):
        s = summ.get(ln, {})
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items() if k != "trips_all_days"} | {
            "centroid": [round(c, 4) for c in cent.get(ln, (0, 0))]}

    warnings = {}
    for ln in CURRENT_LINES:
        s = summ.get(ln)
        why = _reject_reason(s) if s else "sin datos en la muestra"
        if why:
            warnings[ln] = "línea actual que se mantiene pese a no cumplir: " + why
    no_shape = [str(n) for n in range(1, 200) if str(n) not in set(all_lines)]

    out = {
        "train": train, "heldout": heldout,
        "criteria": {
            "min_trips_weekday": MIN_TRIPS_WEEKDAY, "min_trip_id_cov": MIN_TRIP_ID_COV,
            "min_start_time_cov": MIN_START_TIME_COV, "max_median_perp_m": MAX_MEDIAN_PERP_M,
            "min_frac_within_150": MIN_FRAC_WITHIN_150,
            "min_frac_trips_perp_le_50": MIN_FRAC_TRIPS_PERP_LE_50,
            "selection": "7 actuales + farthest-point sampling por centroide del recorrido entre las elegibles "
                         "(bonus x1.25 por agencia no representada, ponderado por calidad); cada ~5ª elegida va a heldout",
            "sample_days": metrics["days"], "weekday_days": metrics["weekday"],
        },
        "metrics": {ln: row(ln) for ln in train + heldout},
        "warnings_current_lines": warnings,
        "eligible_not_picked": not_picked,
        "excluded": excluded,
        "lines_1_199_without_shape": no_shape,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--days", required=True, help="YYYY-MM-DD separados por coma")
    m.add_argument("--workers", type=int, default=3)
    m.add_argument("--lines", default=None, help="medir solo estas líneas (coma)")
    m.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    m.add_argument("--shapes-dir", type=Path, default=DEFAULT_LINE_SHAPES_DIR)
    m.add_argument("--label-map", type=Path, default=DEFAULT_LABEL_MAP)
    m.add_argument("--out", type=Path, default=DEFAULT_V2_DIR / "line_metrics.json")
    p = sub.add_parser("propose")
    p.add_argument("--metrics", type=Path, default=DEFAULT_V2_DIR / "line_metrics.json")
    p.add_argument("--shapes-dir", type=Path, default=DEFAULT_LINE_SHAPES_DIR)
    p.add_argument("--out", type=Path, default=DEFAULT_V2_DIR / "lines_first_pass.json")  # la lista final sale de lines_final.py
    a = ap.parse_args()
    if a.cmd == "measure":
        measure(a.days.split(","), a.workers, a.out, a.shapes_dir, a.data_dir, a.label_map,
                a.lines.split(",") if a.lines else None)
        print("OK ->", a.out)
    else:
        out = propose(a.metrics, a.out, a.shapes_dir)
        print("train:", len(out["train"]), out["train"])
        print("heldout:", out["heldout"])
        print("excluidas:", len(out["excluded"]))


if __name__ == "__main__":
    main()
