"""
Validación del segmentador geométrico contra el de trip_id/start_time, para una línea y un día.

  python -m prediccion.v2.compare_segmenters --line 39 --day 2026-09-16 [--line 151 ...]

Reporta: cantidad de viajes, duración mediana, % de viajes de trip_id que tienen un viaje geométrico con
inicio y fin dentro de +-3 min (y a la inversa), cuántos viajes geométricos nacen de pings sin trip_id, y
la distribución de duración y largo recorrido de los viajes geométricos (sanity check en líneas sin trip_id).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from red.label_map import load_label_line_data, resolve_label_line_index
from prediccion.v2.day import geometry_for_trip, read_day, segment_vehicles
from prediccion.v2.shapes import DEFAULT_DATA_DIR, DEFAULT_LABEL_MAP, LineShapes

TOL_S = 180


def _pct(a, q):
    return float(np.percentile(a, q)) if len(a) else None


def compare(line: str, day: str, data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    ld = load_label_line_data(DEFAULT_LABEL_MAP)
    index = resolve_label_line_index(ld, on_date=day)
    lmap = {s: v["line"] for s, v in index.items()}
    vehicles, stats, _ = read_day(Path(data_dir) / f"{day}.ndjson.gz", lmap, {line})
    shapes = LineShapes()
    geo = segment_vehicles(vehicles, index, shapes, "geo")
    old = segment_vehicles(vehicles, index, shapes, "trip_id")

    has_tid = {}                                # (vehicle, ts) -> bool, para saber qué pings tenían trip_id
    for vid, rec in vehicles.items():
        for o in rec["obs"]:
            has_tid[(vid, o[0])] = o[9]

    def span(t):
        return t.points[0].ts, t.points[-1].ts

    def by_vehicle(trips):
        d = {}
        for t in trips:
            d.setdefault(t.vehicle_id, []).append(span(t))
        return d

    gv, ov = by_vehicle(geo), by_vehicle(old)

    def matched(src, dst):
        n = 0
        for vid, spans in src.items():
            cand = dst.get(vid, [])
            for s0, s1 in spans:
                if any(abs(s0 - c0) <= TOL_S and abs(s1 - c1) <= TOL_S for c0, c1 in cand):
                    n += 1
        return n

    def contained(src, dst):
        n = 0
        for vid, spans in src.items():
            cand = dst.get(vid, [])
            for s0, s1 in spans:
                if any(s0 >= c0 - TOL_S and s1 <= c1 + TOL_S for c0, c1 in cand):
                    n += 1
        return n

    n_old, n_geo = len(old), len(geo)
    # viajes "del trip_id" que son reales: >= 5 pings y progreso (ya filtrado en el viejo por 5 pings)
    dur_geo = np.array([t.points[-1].ts - t.points[0].ts for t in geo]) / 60.0
    dur_old = np.array([t.points[-1].ts - t.points[0].ts for t in old]) / 60.0

    # largo recorrido por viaje geométrico (rango de dist_along sobre el recorrido elegido, puntos <=150 m)
    lens, ratios = [], []
    for t in geo:
        g = geometry_for_trip(t, shapes.indices(line))
        if g is None or g["valid"].sum() < 2:
            continue
        d = g["dist"][g["valid"]]
        lens.append(float(d.max() - d.min()) / 1000.0)
        L = shapes.indices(line)[g["shape_id"]].total_length_m
        ratios.append(float(d.max() - d.min()) / L)

    no_tid_geo = 0
    for t in geo:
        flags = [has_tid.get((t.vehicle_id, p.ts), False) for p in t.points]
        if np.mean(flags) < 0.5:
            no_tid_geo += 1
    old_empty = sum(1 for t in old if not any(has_tid.get((t.vehicle_id, p.ts), False) for p in t.points))
    st = stats.get(line, [0, 0, 0])
    return {
        "line": line, "day": day, "pings": st[0], "trip_id_coverage": round(st[1] / st[0], 3) if st[0] else None,
        "trip_id_segmenter": {"trips": n_old, "median_dur_min": _pct(dur_old, 50), "trips_without_any_trip_id": old_empty},
        "geo_segmenter": {"trips": n_geo, "median_dur_min": _pct(dur_geo, 50),
                          "dur_min_p10_p50_p90_p99": [_pct(dur_geo, q) for q in (10, 50, 90, 99)],
                          "pct_trips_longer_than_3h": float(100 * np.mean(dur_geo > 180)) if len(dur_geo) else None,
                          "route_len_km_p10_p50_p90": [_pct(np.array(lens), q) for q in (10, 50, 90)],
                          "route_len_over_shape_len_p10_p50_p90": [_pct(np.array(ratios), q) for q in (10, 50, 90)],
                          "trips_born_from_pings_without_trip_id": no_tid_geo},
        "match_pm3min": {
            "trip_id_trips_with_geo_match_pct": round(100 * matched(ov, gv) / n_old, 1) if n_old else None,
            "geo_trips_with_trip_id_match_pct": round(100 * matched(gv, ov) / n_geo, 1) if n_geo else None,
            "trip_id_trips_contained_in_a_geo_trip_pct": round(100 * contained(ov, gv) / n_old, 1) if n_old else None},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--line", action="append", required=True)
    ap.add_argument("--day", default="2026-09-16")
    a = ap.parse_args(argv)
    for ln in a.line:
        print(json.dumps(compare(ln, a.day), indent=1, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
