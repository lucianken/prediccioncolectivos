#!/usr/bin/env python
"""
build_lookup.py — Construye la lookup route_id → shape para una línea (Enfoque C).

Lee todos los NDJSON diarios, segmenta en trips, acumula evidencia por route_id
y corre el algoritmo de voto-por-punto + containment/coverage.

Salida: lookup_results_{LINE}.json en el directorio de trabajo.

Uso:
  python ramal_lookup/build_lookup.py --data-dir Z:\\grabaciones --line 39
  python ramal_lookup/build_lookup.py --data-dir Z:\\grabaciones --line 39 --max-days 14
  python ramal_lookup/build_lookup.py --data-dir Z:\\grabaciones --line 39 --vote-margin 0.10
"""

import argparse
import json
import sys
import time
sys.stdout.reconfigure(encoding="utf-8")
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

# Importar desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from prediccion.pipeline.reader import iter_daily_files, reconstruct_snapshots
from prediccion.pipeline.segmenter import segment_vehicle_history
from prediccion.pipeline.shapes_io import load_label_line_map, load_shapes

from ramal_lookup.route_lookup import (
    CONTAINED_PERP_M,
    CONTAINMENT_THRESHOLD,
    COVERAGE_GAP_THRESHOLD,
    MIN_TRIPS,
    QUANTILE_MARGIN,
    QUANTILE_P,
    VOTE_MARGIN_THRESHOLD,
    VOTE_TIE_TOLERANCE_M,
    RouteEvidence,
    build_lookup,
    build_shape_entries,
    load_families,
)

INTERVAL_S = 30
SKIP_FIRST_DAYS = 3   # días parciales al inicio del dataset que se descartan por defecto


def main() -> None:
    parser = argparse.ArgumentParser(description="Lookup route_id → shape por Enfoque C")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--line", type=str, default="39")
    parser.add_argument(
        "--shapes", type=Path,
        default=Path(__file__).parent.parent / "prediccion" / "data" / "line_shapes.json",
    )
    parser.add_argument(
        "--families", type=Path,
        default=Path(__file__).parent / "families_39.json",
    )
    parser.add_argument(
        "--label-map", type=Path,
        default=Path(__file__).parent.parent / "LABEL_LINE_MAP.json",
    )
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--skip-first", type=int, default=SKIP_FIRST_DAYS,
                        help=f"Días parciales a saltear al inicio (default {SKIP_FIRST_DAYS})")
    parser.add_argument("--min-trips", type=int, default=MIN_TRIPS)
    parser.add_argument("--vote-margin", type=float, default=VOTE_MARGIN_THRESHOLD,
                        help=f"Margen mínimo de voto para resolver completo (default {VOTE_MARGIN_THRESHOLD})")
    parser.add_argument("--coverage-gap", type=float, default=COVERAGE_GAP_THRESHOLD,
                        help=f"Gap mínimo de coverage para resolver fraccionado (default {COVERAGE_GAP_THRESHOLD})")
    parser.add_argument("--containment-threshold", type=float, default=CONTAINMENT_THRESHOLD)
    parser.add_argument("--contained-perp-m", type=float, default=CONTAINED_PERP_M)
    parser.add_argument("--vote-tie-m", type=float, default=VOTE_TIE_TOLERANCE_M,
                        help=f"Tolerancia de empate en votos en metros (default {VOTE_TIE_TOLERANCE_M})")
    parser.add_argument("--quantile-p", type=float, default=QUANTILE_P,
                        help=f"Percentil alto del perp para discriminar completos (default {QUANTILE_P})")
    parser.add_argument("--quantile-margin", type=float, default=QUANTILE_MARGIN,
                        help=f"Margen relativo mínimo del cuantil (default {QUANTILE_MARGIN})")
    parser.add_argument("--output", type=Path, default=None,
                        help="Ruta de salida JSON (default: ramal_lookup/lookup_results_{line}.json)")
    args = parser.parse_args()

    # ── Cargar shapes y families ──────────────────────────────────────────────
    shapes = load_shapes(str(args.shapes))
    if args.line not in shapes:
        print(f"ERROR: línea {args.line} no encontrada en {args.shapes}", file=sys.stderr)
        sys.exit(1)

    families = load_families(args.families)
    shape_entries = build_shape_entries(shapes, args.line, families)
    label_line_map = load_label_line_map(str(args.label_map))

    print(f"Línea {args.line}: {len(shape_entries)} shapes")
    for e in shape_entries:
        frac_note = f"  [fraccionado de {e.parent_short_name}]" if e.is_fraccionado else ""
        print(f"  {e.key}  {e.index.total_length_m/1000:.1f}km{frac_note}")

    # ── Archivos a procesar ───────────────────────────────────────────────────
    daily_files = list(iter_daily_files(args.data_dir))
    today_name = f"{date.today().isoformat()}.ndjson.gz"
    daily_files = [f for f in daily_files if f.name != today_name]
    if args.skip_first:
        daily_files = daily_files[args.skip_first:]
    if args.max_days:
        daily_files = daily_files[: args.max_days]
    if not daily_files:
        print("ERROR: No hay archivos NDJSON.gz en", args.data_dir, file=sys.stderr)
        sys.exit(1)

    mb_total = sum(f.stat().st_size for f in daily_files) / 1024 / 1024
    print(f"\nProcesando {len(daily_files)} días "
          f"({daily_files[0].name[:10]} → {daily_files[-1].name[:10]}) — {mb_total:.0f} MB\n")

    # ── Acumulación de evidencia por route_id ─────────────────────────────────
    route_points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    route_trips: dict[str, int] = defaultdict(int)
    route_direction: dict[str, int] = {}
    route_first_seen: dict[str, str] = {}
    route_last_seen: dict[str, str] = {}

    total_start = time.time()

    for i, fp in enumerate(daily_files):
        t0 = time.time()
        day_str = fp.name[:10]

        vehicle_obs: dict[str, list] = defaultdict(list)
        snap_count = 0

        for ts, state in reconstruct_snapshots(fp, interval_s=INTERVAL_S):
            snap_count += 1
            for vid, fields in state.items():
                obs = dict(fields)
                obs["ts"] = obs.get("ts", ts)
                raw_label = obs.get("label", "")
                suffix = raw_label.split("-")[-1] if raw_label else ""
                if label_line_map.get(suffix) != args.line:
                    continue
                vehicle_obs[vid].append(obs)

        day_trips = 0
        for vid, observations in vehicle_obs.items():
            observations.sort(key=lambda o: o["ts"])
            for trip in segment_vehicle_history(vid, observations):
                rid = trip.route_id or ""
                if not rid:
                    continue

                if rid not in route_first_seen:
                    route_first_seen[rid] = day_str
                route_last_seen[rid] = day_str
                route_direction[rid] = trip.direction_id
                route_trips[rid] += 1
                day_trips += 1

                for pt in trip.points:
                    route_points[rid].append((pt.lat, pt.lon))

        elapsed = time.time() - t0
        print(f"  [{i+1:2d}/{len(daily_files)}] {day_str}  "
              f"{snap_count} snaps | {len(vehicle_obs)} veh | {day_trips} trips  "
              f"[{elapsed:.0f}s]")

    elapsed_total = time.time() - total_start
    print(f"\nTotal route_ids acumulados: {len(route_points)}  "
          f"(tiempo: {elapsed_total/60:.1f} min)")

    # ── Construir RouteEvidence ───────────────────────────────────────────────
    evidence: dict[str, RouteEvidence] = {
        rid: RouteEvidence(
            route_id=rid,
            direction_id=route_direction.get(rid, -1),
            n_trips=route_trips[rid],
            points=route_points[rid],
        )
        for rid in route_points
    }

    # ── Correr el algoritmo ───────────────────────────────────────────────────
    print("\nCorriendo Enfoque C...")
    t0 = time.time()
    lookup = build_lookup(
        evidence,
        shape_entries,
        families,
        contained_perp_m=args.contained_perp_m,
        containment_threshold=args.containment_threshold,
        vote_margin_threshold=args.vote_margin,
        coverage_gap_threshold=args.coverage_gap,
        min_trips=args.min_trips,
        vote_tie_tolerance_m=args.vote_tie_m,
        quantile_p=args.quantile_p,
        quantile_margin_threshold=args.quantile_margin,
    )
    print(f"Tiempo de cómputo: {time.time()-t0:.1f}s")

    # ── Resumen ───────────────────────────────────────────────────────────────
    resolved = {rid: e for rid, e in lookup.items() if e.status == "resolved"}
    pending = {rid: e for rid, e in lookup.items() if e.status == "pending"}

    n_total = len(lookup)
    n_resolved = len(resolved)
    n_pending = len(pending)

    sep = "=" * 64
    print(f"\n{sep}")
    print(f"RESUMEN — Línea {args.line} — Enfoque C")
    print(sep)

    print(f"\nRoute_ids procesados: {n_total}")
    print(f"  Resueltos: {n_resolved} ({n_resolved/n_total*100:.0f}%)")
    print(f"  Pendientes: {n_pending} ({n_pending/n_total*100:.0f}%)")

    # Resueltos por shape
    print("\nResueltos por shape:")
    shape_counts: dict[str, list[str]] = defaultdict(list)
    for rid, entry in resolved.items():
        shape_counts[entry.assigned_shape_key or "?"].append(rid)

    for shape_key in sorted(shape_counts):
        rids = shape_counts[shape_key]
        entry0 = resolved[rids[0]]
        atype = entry0.assignment_type
        method_counts: dict[str, int] = defaultdict(int)
        for r in rids:
            method_counts[resolved[r].method or "?"] += 1
        methods_str = ", ".join(f"{m}:{c}" for m, c in sorted(method_counts.items()))
        print(f"  {shape_key:12}  {atype:12}  {len(rids)} route_ids  [{methods_str}]")
        for rid in sorted(rids):
            e = resolved[rid]
            print(f"    {rid}  conf={e.confidence:.2f}  trips={e.total_trips}  pts={e.total_points}")

    # Pendientes agrupados por razón
    if pending:
        print("\nPendientes por razón:")
        by_reason: dict[str, list[str]] = defaultdict(list)
        for rid, e in pending.items():
            by_reason[e.reason or "?"].append(rid)
        for reason, rids in sorted(by_reason.items()):
            print(f"  {reason}: {len(rids)} route_ids")
            for rid in sorted(rids)[:10]:
                e = pending[rid]
                print(f"    {rid}  trips={e.total_trips}  pts={e.total_points}")
            if len(rids) > 10:
                print(f"    ... y {len(rids)-10} más")

    # Shapes sin ningún route_id resuelto
    all_shape_keys = {e.key for e in shape_entries}
    covered_shapes = set(shape_counts.keys())
    uncovered = all_shape_keys - covered_shapes
    if uncovered:
        print(f"\nShapes SIN route_id resuelto: {sorted(uncovered)}")

    print(sep)

    # ── Escribir output ───────────────────────────────────────────────────────
    output_path = args.output or Path(__file__).parent / f"lookup_results_{args.line}.json"

    output = {
        "generated_at": datetime.now().isoformat(),
        "line": args.line,
        "days_analyzed": len(daily_files),
        "date_range": {
            "from": daily_files[0].name[:10],
            "to": daily_files[-1].name[:10],
        },
        "params": {
            "contained_perp_m": args.contained_perp_m,
            "containment_threshold": args.containment_threshold,
            "vote_margin_threshold": args.vote_margin,
            "coverage_gap_threshold": args.coverage_gap,
            "vote_tie_tolerance_m": args.vote_tie_m,
            "quantile_p": args.quantile_p,
            "quantile_margin": args.quantile_margin,
            "min_trips": args.min_trips,
        },
        "summary": {
            "total_route_ids": n_total,
            "resolved": n_resolved,
            "pending": n_pending,
            "resolved_pct": round(n_resolved / n_total * 100, 1) if n_total else 0,
        },
        "lookup": {
            rid: entry.to_dict()
            for rid, entry in sorted(
                lookup.items(),
                key=lambda x: (x[1].status != "resolved", x[0])
            )
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nEscrito: {output_path}")


if __name__ == "__main__":
    main()
