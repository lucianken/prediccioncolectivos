"""
Validación del segmentador v2b (segmenter_version=2, segmentation="geo2") contra el v2 de siempre ("geo").
ARQUITECTURA.md §6.2 paso 5. No construye datos de entrenamiento: trabaja sobre algunos días y líneas.

  python -m prediccion.v2.validate_segmenter_v2 --days 2026-07-14,2026-08-12,2026-09-16,2026-10-07,2026-09-12 \
      --lines 26,39,42,92,124,151,168,50,106,107,108,132,12,15,128 --out-dir data/ml/v2b/validation

Escribe en --out-dir: summary.json, summary.md, cars.md (coches revisados a mano) y work/{geo,geo2}/ (los
process_day de cada versión, K=32, sin carry). Corre en CPU, un solo proceso, en prioridad baja.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from red.label_map import load_label_line_data, resolve_label_line_index
from prediccion.v2.build import set_low_priority
from prediccion.v2.day import geometry_for_trip, process_day, read_day, segment_vehicles
from prediccion.v2.segmenter import START_UNKNOWN_M
from prediccion.v2.shapes import DEFAULT_DATA_DIR, DEFAULT_LABEL_MAP, DEFAULT_V2_DIR, LineShapes

GAP_BINS = [(300, 420), (420, 600), (600, 900), (900, 1800), (1800, 3600), (3600, 10 ** 9)]
VMAX_MPS = 60 / 3.6


def _pct(a, q):
    a = np.asarray(a, dtype=float)
    return [round(float(x), 1) for x in np.percentile(a, q)] if len(a) else None


def trip_records(trips, shapes: LineShapes) -> list[dict]:
    recs = []
    for t in trips:
        idx = shapes.indices(t.line_number)
        g = geometry_for_trip(t, idx) if idx else None
        if g is None or g["valid"].sum() < 2:
            continue
        v = g["valid"]
        ts = np.array([p.ts for p in t.points], dtype=np.int64)[v]
        d = g["dist"][v]
        L = idx[g["shape_id"]].total_length_m
        recs.append({"line": t.line_number, "vid": t.vehicle_id, "start_ts": int(t.start_time), "shape": g["shape_id"],
                     "L": float(L), "n": int(v.sum()), "t0": int(ts[0]), "t1": int(ts[-1]),
                     "d0": float(d[0]), "d1": float(d[-1]),
                     "nj": len(getattr(t, "joined_gaps", [])), "wait": getattr(t, "waiting", None)})
    return recs


def analyze_day(day: str, lines: list[str], data_dir: Path, work: Path, shapes: LineShapes, label_data: dict,
                k_pairs: int = 32) -> dict:
    label_index = resolve_label_line_index(label_data, on_date=day)
    lmap = {s: v["line"] for s, v in label_index.items()}
    vehicles, _, _ = read_day(Path(data_dir) / f"{day}.ndjson.gz", lmap, set(lines))
    out = {"day": day}
    for name, method in (("v1", "geo"), ("v2", "geo2")):
        st: dict = {}
        trips = segment_vehicles(vehicles, label_index, shapes, method, st)
        recs = trip_records(trips, shapes)
        w = work / method
        process_day(day, lines, data_dir=data_dir, out_dir=w, shapes=shapes, label_data=label_data, k_pairs=k_pairs,
                    use_carry=False, force=True, segmentation=method)
        import pyarrow.parquet as pq
        tp = pq.read_table(w / "daily" / f"{day}.trips.parquet").to_pandas()
        rows = pq.read_table(w / "daily" / f"{day}.parquet", columns=["line", "dist_along_m", "time_since_start"]
                             ).to_pandas()
        nrows = {(r.vehicle_id, int(r.start_ts)): int(r.n_rows) for r in tp.itertuples()}
        for r in recs:
            r["rows"] = nrows.get((r["vid"], r["start_ts"]), 0)
        gaps = [g for a in st.values() for g in a.get("gaps", [])]
        out[name] = {"trips": recs, "gaps": gaps, "rows_df": rows}
    return out


def summarize(days_out: list[dict]) -> dict:
    s: dict = {}
    for name in ("v1", "v2"):
        recs = [r for d in days_out for r in d[name]["trips"]]
        rows_all = sum(r["rows"] for r in recs)
        far = [r for r in recs if r["d0"] > START_UNKNOWN_M]
        far_rows = sum(r["rows"] for r in far)
        sec: dict = {"trips": len(recs), "rows": rows_all, "trips_start_gt1km": len(far),
                     "pct_trips_start_gt1km": round(100 * len(far) / max(len(recs), 1), 2),
                     "pct_rows_start_gt1km": round(100 * far_rows / max(rows_all, 1), 2)}
        if name == "v2":
            joined = [r for r in recs if r["nj"] > 0]
            jr = sum(r["rows"] for r in joined)
            sec["trips_with_joined_gap"] = len(joined)
            sec["pct_rows_in_joined_trips"] = round(100 * jr / max(rows_all, 1), 2)
            sec["pct_rows_start_unknown"] = sec["pct_rows_start_gt1km"]
            sec["joined_trips_start_unknown"] = sum(1 for r in joined if r["d0"] > START_UNKNOWN_M)
        # coherencia de time_since_start con la distancia desde el inicio del recorrido
        rdf = [d[name]["rows_df"] for d in days_out]
        import pandas as pd
        rdf = pd.concat(rdf, ignore_index=True)
        tss = rdf["time_since_start"].to_numpy(dtype=float)
        dist = rdf["dist_along_m"].to_numpy(dtype=float)
        nan = np.isnan(tss)
        ok = ~nan & (tss >= 300)
        v = dist[ok] / tss[ok]
        sec["rows_total_parquet"] = int(len(rdf))
        sec["rows_tss_nan"] = int(nan.sum())
        sec["coherence"] = {"rows_tss>=300s": int(ok.sum()), "v_implicita_mps_p10_50_90": _pct(v, [10, 50, 90]),
                            "pct_gt_60kmh": round(100 * float((v > VMAX_MPS).mean()), 2) if len(v) else None,
                            "pct_gt_40kmh": round(100 * float((v > 40 / 3.6).mean()), 2) if len(v) else None}
        # duración por línea de los viajes completos (arrancan en cabecera y llegan al último km del recorrido)
        per_line = {}
        for ln in sorted({r["line"] for r in recs}, key=int):
            rr = [r for r in recs if r["line"] == ln]
            full = [r for r in rr if r["d0"] <= START_UNKNOWN_M and r["d1"] >= r["L"] - 1000]
            durs = [(r["t1"] - r["t0"]) / 60 for r in full]
            Ls = [r["L"] / 1000 for r in rr]
            per_line[ln] = {"trips": len(rr), "completos": len(full), "L_km_mediana": round(float(np.median(Ls)), 1),
                            "dur_min_p10_50_90": _pct(durs, [10, 50, 90]),
                            "vel_kmh_mediana": round(float(np.median([r["L"] / 1000 / max((r["t1"] - r["t0"]) / 3600, 1e-6)
                                                                      for r in full])), 1) if full else None}
        sec["por_linea"] = per_line
        s[name] = sec
    # huecos (solo v2 los mide; en v1 todo hueco dentro de un viaje corta)
    allg = [g for d in days_out for g in d["v2"]["gaps"]]
    gl = [g for g in allg if g["kind"] == "gap"]
    ex = [g for g in allg if g["kind"] == "off"]
    hist = []
    for lo, hi in GAP_BINS:
        sel = [g for g in gl if lo < g["dur"] <= hi]
        hist.append({"dur_s": f"{lo}-{hi if hi < 10 ** 9 else 'inf'}", "n": len(sel),
                     "unidos": sum(g["joined"] for g in sel),
                     "no_unidos": sum(not g["joined"] for g in sel)})
    s["huecos"] = {"total": len(gl), "unidos": sum(g["joined"] for g in gl),
                   "no_unidos": sum(not g["joined"] for g in gl), "por_duracion": hist,
                   "dur_s_p10_50_90": _pct([g["dur"] for g in gl], [10, 50, 90]),
                   "v_implicita_mps_p10_50_90_unidos": _pct([g["v"] for g in gl if g["joined"]], [10, 50, 90]),
                   "no_unidos_por_parado(v<1.4)": sum(1 for g in gl if not g["joined"] and g["v"] < 1.4),
                   "no_unidos_por_retroceso(adv<-150)": sum(1 for g in gl if not g["joined"] and g["adv"] < -150)}
    s["excursiones"] = {"total": len(ex), "unidas": sum(g["joined"] for g in ex),
                        "no_unidas": sum(not g["joined"] for g in ex),
                        "dur_s_p10_50_90": _pct([g["dur"] for g in ex], [10, 50, 90])}
    # esperas en cabecera
    waits = [r["wait"] for d in days_out for r in d["v2"]["trips"] if r["wait"]]
    ws = [w["end_ts"] - w["start_ts"] for w in waits]
    v1_pings = sum(r["n"] for d in days_out for r in d["v1"]["trips"])
    s["esperas"] = {"n": len(waits), "pings_en_espera": int(sum(w["n_pings"] for w in waits)),
                    "pct_de_pings_de_viaje_v1": round(100 * sum(w["n_pings"] for w in waits) / max(v1_pings, 1), 2),
                    "dur_s_p10_50_90_max": (_pct(ws, [10, 50, 90]) + [int(max(ws))]) if ws else None,
                    "n_mayor_5min": int(sum(x > 300 for x in ws)), "n_mayor_10min": int(sum(x > 600 for x in ws))}
    return s


def to_markdown(s: dict, days: list[str], lines: list[str]) -> str:
    L = [f"# Validación segmentador v2b vs v2 (días {', '.join(days)}; {len(lines)} líneas)", ""]
    a, b = s["v1"], s["v2"]
    L += ["| | v2 actual (v1 del segmentador) | v2b (segmenter_version=2) |", "|---|---|---|",
          f"| viajes | {a['trips']} | {b['trips']} |", f"| filas (K=32) | {a['rows']} | {b['rows']} |",
          f"| % viajes que arrancan a >1 km del inicio | {a['pct_trips_start_gt1km']} | {b['pct_trips_start_gt1km']} |",
          f"| % filas de viajes que arrancan a >1 km | {a['pct_rows_start_gt1km']} | {b['pct_rows_start_gt1km']} (start_unknown) |",
          f"| % filas en viajes con hueco unido | - | {b['pct_rows_in_joined_trips']} |",
          f"| filas con time_since_start NaN | {a['rows_tss_nan']} | {b['rows_tss_nan']} |", ""]
    h = s["huecos"]
    L += [f"## Huecos > 5 min dentro de un viaje: {h['total']} (unidos {h['unidos']}, no unidos {h['no_unidos']})", "",
          "| duración (s) | n | unidos | no unidos |", "|---|---|---|---|"]
    L += [f"| {x['dur_s']} | {x['n']} | {x['unidos']} | {x['no_unidos']} |" for x in h["por_duracion"]]
    L += ["", f"Velocidad implícita de los unidos (m/s, p10/p50/p90): {h['v_implicita_mps_p10_50_90_unidos']}. "
          f"No unidos por coche parado en el hueco: {h['no_unidos_por_parado(v<1.4)']}, por retroceso: "
          f"{h['no_unidos_por_retroceso(adv<-150)']}.", "", "## Coherencia de time_since_start (dist_along / time_since_start, filas con tss >= 300 s)", "",
          "| | v1 | v2b |", "|---|---|---|"]
    ca, cb = a["coherence"], b["coherence"]
    L += [f"| filas evaluadas | {ca['rows_tss>=300s']} | {cb['rows_tss>=300s']} |",
          f"| velocidad implícita m/s p10/p50/p90 | {ca['v_implicita_mps_p10_50_90']} | {cb['v_implicita_mps_p10_50_90']} |",
          f"| % filas > 60 km/h | {ca['pct_gt_60kmh']} | {cb['pct_gt_60kmh']} |",
          f"| % filas > 40 km/h | {ca['pct_gt_40kmh']} | {cb['pct_gt_40kmh']} |", "",
          "## Excursiones fuera del recorrido (>= 5 pings fuera) que vuelven al recorrido", "",
          json.dumps(s["excursiones"], ensure_ascii=False), "",
          "## Esperas en cabecera (v2b)", "", json.dumps(s["esperas"], ensure_ascii=False), "",
          "## Duración de viajes completos por línea (min p10/p50/p90; largo del recorrido en km)", "",
          "| línea | L km | v1 completos | v1 dur | v1 km/h | v2b completos | v2b dur | v2b km/h |", "|---|---|---|---|---|---|---|---|"]
    for ln, x in a["por_linea"].items():
        y = b["por_linea"].get(ln, {})
        L.append(f"| {ln} | {x['L_km_mediana']} | {x['completos']} | {x['dur_min_p10_50_90']} | {x['vel_kmh_mediana']} | "
                 f"{y.get('completos')} | {y.get('dur_min_p10_50_90')} | {y.get('vel_kmh_mediana')} |")
    return "\n".join(L) + "\n"


def _hms(t):
    import time
    return time.strftime("%H:%M:%S", time.gmtime(int(t) - 3 * 3600))


def car_timeline(day: str, vid: str, lines: list[str], data_dir: Path, shapes: LineShapes, label_data: dict,
                 vehicles=None, label_index=None) -> str:
    """Pings de un coche con su avance sobre el recorrido y a qué viaje pertenecen en v1 y v2b."""
    if vehicles is None:
        label_index = resolve_label_line_index(label_data, on_date=day)
        lmap = {s: v["line"] for s, v in label_index.items()}
        vehicles, _, _ = read_day(Path(data_dir) / f"{day}.ndjson.gz", lmap, set(lines))
    rec = {vid: vehicles[vid]}
    res = {}
    for name, method in (("v1", "geo"), ("v2b", "geo2")):
        res[name] = segment_vehicles(rec, label_index, shapes, method)
    obs = rec[vid]["obs"]
    ln = label_index[rec[vid]["label"].split("-")[-1]]["line"]
    out = [f"### coche {vid} (línea {ln}), día {day}", ""]
    for name, trips in res.items():
        for i, t in enumerate(trips):
            g = geometry_for_trip(t, shapes.indices(ln))
            d0 = float(g["dist"][g["valid"]][0]) if g and g["valid"].any() else float("nan")
            extra = (f" start_unknown={t.start_unknown} huecos_unidos={[(_hms(a), _hms(b)) for a, b in t.joined_gaps]}"
                     if name == "v2b" else "")
            wait = (f" espera={_hms(t.waiting['start_ts'])}..{_hms(t.waiting['end_ts'])} "
                    f"({(t.waiting['end_ts'] - t.waiting['start_ts']) / 60:.1f} min, sale {_hms(t.waiting['depart_ts'])})"
                    if name == "v2b" and t.waiting else "")
            out.append(f"- {name} viaje {i + 1}: {_hms(t.points[0].ts)} -> {_hms(t.points[-1].ts)} "
                       f"({len(t.points)} pings, {(t.points[-1].ts - t.points[0].ts) / 60:.1f} min), shape {g['shape_id'] if g else '?'}, "
                       f"dist al arrancar {d0:.0f} m{extra}{wait}")
    return "\n".join(out) + "\n"


def pick_cars(days_out: list[dict]) -> dict:
    """Un coche con hueco unido, uno con espera larga, uno con hueco no unido (start_unknown) y uno que v1 arrancaba lejos."""
    best: dict = {}
    for d in days_out:
        for r in d["v2"]["trips"]:
            c = (d["day"], r["vid"], r["line"])
            if r["nj"] > 0 and r["d0"] <= START_UNKNOWN_M and r["n"] >= 40:
                if "hueco_unido" not in best or r["nj"] > best["hueco_unido"][1]:
                    best["hueco_unido"] = (c, r["nj"])
            if r["wait"]:
                w = r["wait"]["end_ts"] - r["wait"]["start_ts"]
                if w <= 1500 and ("espera_larga" not in best or w > best["espera_larga"][1]):
                    best["espera_larga"] = (c, w)
            if r["d0"] > START_UNKNOWN_M and r["n"] >= 40 and "start_unknown" not in best:
                best["start_unknown"] = (c, r["d0"])
    return {k: v[0] for k, v in best.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", required=True)
    ap.add_argument("--lines", required=True)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_V2_DIR.parent / "v2b" / "validation")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--label-map", type=Path, default=DEFAULT_LABEL_MAP)
    a = ap.parse_args(argv)
    set_low_priority()
    days, lines = a.days.split(","), a.lines.split(",")
    a.out_dir.mkdir(parents=True, exist_ok=True)
    shapes = LineShapes()
    ld = load_label_line_data(a.label_map)
    outs = []
    for d in days:
        print("día", d, flush=True)
        outs.append(analyze_day(d, lines, a.data_dir, a.out_dir / "work", shapes, ld))
    s = summarize(outs)
    s["cars"] = {k: list(v) for k, v in pick_cars(outs).items()}
    with open(a.out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)
    with open(a.out_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write(to_markdown(s, days, lines))
    cars_md = []
    for kind, (day, vid, ln) in pick_cars(outs).items():
        cars_md.append(f"## {kind}\n\n" + car_timeline(day, vid, lines, a.data_dir, shapes, ld))
    with open(a.out_dir / "cars.md", "w", encoding="utf-8") as f:
        f.write("\n".join(cars_md))
    print(to_markdown(s, days, lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
