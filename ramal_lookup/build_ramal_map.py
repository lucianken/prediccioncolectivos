#!/usr/bin/env python
"""
build_ramal_map.py — Construye ramal_map.json desde cero.

Procesa archivos NDJSON en orden cronológico con I/O mínimo:
  - Cada día: scan rápido de route_ids presentes (sin GPS)
  - Solo acumula GPS para route_ids pendientes (no resueltos aún)
  - Al resolver un route_id lo bloquea: nunca más GPS para ese
  - Días donde todo está resuelto: solo scan de IDs para detectar rotaciones

Para N días con K períodos de rotación y R ramales por período:
  GPS leído ≈ K × (días para resolver) × R  <<  N días completos

Salida: ramal_map.json

Uso:
  python ramal_lookup/build_ramal_map.py --data-dir Z:\\grabaciones --line 39
  python ramal_lookup/build_ramal_map.py --data-dir Z:\\grabaciones  # todas las líneas con shapes
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from prediccion.pipeline.reader import (
    iter_daily_files,
    reconstruct_line_snapshots,
    reconstruct_snapshots,
)
from prediccion.pipeline.segmenter import segment_vehicle_history
from prediccion.pipeline.shapes_io import load_label_line_map, load_shapes

from ramal_lookup.route_lookup import (
    RouteEvidence,
    build_lookup,
    build_shape_entries,
    load_families,
)

RETIRE_GAP_DAYS  = 7
INTERVAL_S       = 30
SKIP_FIRST_DAYS  = 1   # día parcial al inicio del dataset (grabador arranca a mitad del día)
OUTPUT = Path(__file__).parent / "ramal_map.json"


# ── Scan rápido: solo route_ids, sin acumular GPS ─────────────────────────────

def scan_route_ids(fp: Path, line: str, label_line_map: dict) -> dict[str, int]:
    """Retorna {route_id: direction_id} para la línea, sin procesar GPS.

    Usa reconstruct_line_snapshots para mantener en memoria solo los vehículos
    de la línea (~50 vs ~4000), eliminando el overhead de filtrado en el loop.
    """
    rids: dict[str, int] = {}
    for ts, state in reconstruct_line_snapshots(fp, label_line_map, line, interval_s=INTERVAL_S):
        for vid, fields in state.items():
            rid = fields.get("route_id", "")
            if not rid or rid in rids:
                continue
            rids[rid] = fields.get("direction_id", 0)
    return rids


# ── Scan con GPS: acumula puntos solo para route_ids pendientes ───────────────

def scan_with_gps(
    fp: Path,
    line: str,
    label_line_map: dict,
    pending_rids: set[str],
) -> tuple[dict[str, int], dict[str, list], dict[str, int]]:
    """
    Retorna:
      active: {route_id: direction_id}  — todos los route_ids vistos
      points: {route_id: [(lat, lon)]}  — GPS solo para pending_rids
      n_trips: {route_id: int}

    Usa reconstruct_line_snapshots para iterar solo los ~50 vehículos de la
    línea (vs ~4000 de la flota completa), eliminando el 11% de CPU de filtrado.
    El filtrado de label ya fue aplicado en reader.py; no hace falta repetirlo aquí.
    """
    vehicle_obs: dict[str, list] = defaultdict(list)
    for ts, state in reconstruct_line_snapshots(fp, label_line_map, line, interval_s=INTERVAL_S):
        for vid, fields in state.items():
            rid = fields.get("route_id", "")
            if not rid:
                continue
            obs = dict(fields)
            obs["ts"] = obs.get("ts", ts)
            vehicle_obs[vid].append(obs)

    active: dict[str, int] = {}
    points: dict[str, list] = defaultdict(list)
    n_trips: dict[str, int] = defaultdict(int)

    for vid, observations in vehicle_obs.items():
        observations.sort(key=lambda o: o["ts"])
        for trip in segment_vehicle_history(vid, observations):
            rid = trip.route_id
            if not rid:
                continue
            active[rid] = trip.direction_id
            if rid in pending_rids:
                n_trips[rid] += 1
                for pt in trip.points:
                    points[rid].append((pt.lat, pt.lon))

    return active, dict(points), dict(n_trips)


# ── Runner por línea ──────────────────────────────────────────────────────────

def build_line(
    line: str,
    daily_files: list[Path],
    label_line_map: dict,
    shapes_data: dict,
    families_path: Path,
) -> list[dict]:
    """
    Procesa todos los días para una línea y retorna la lista de entradas
    para ramal_map["lines"][line]["entries"].
    """
    has_shapes = line in shapes_data and families_path.exists()
    if has_shapes:
        families = load_families(families_path)
        shape_entries = build_shape_entries(shapes_data, line, families)
    else:
        families = {}
        shape_entries = []

    # Estado por route_id
    pending: dict[str, dict] = {}   # rid → {first_seen, direction_id, points, n_trips, last_seen}
    resolved: dict[str, dict] = {}  # rid → {shape_key, confidence, …, first_seen, last_seen}
    retired_unresolved: list[dict] = []

    today_str = date.today().isoformat()

    for fp in daily_files:
        day = fp.name[:10]

        # ── Decidir si necesitamos GPS este día ───────────────────────────────
        if pending and has_shapes:
            # Scan completo: route_ids + GPS para pendientes
            active, gps_points, gps_trips = scan_with_gps(
                fp, line, label_line_map, set(pending.keys())
            )
            mode = "GPS"
        else:
            # Solo scan rápido
            active = scan_route_ids(fp, line, label_line_map)
            gps_points = {}
            gps_trips = {}
            mode = "scan"

        # ── Detectar route_ids nuevos ─────────────────────────────────────────
        known = set(pending) | set(resolved) | {e["route_id"] for e in retired_unresolved}
        new_rids = set(active) - known
        for rid in new_rids:
            pending[rid] = {
                "route_id": rid,
                "direction_id": active[rid],
                "first_seen": day,
                "last_seen": day,
                "points": [],
                "n_trips": 0,
                "days_inactive": 0,
            }

        # ── Acumular GPS para pendientes ──────────────────────────────────────
        for rid in list(pending.keys()):
            if rid in active:
                pending[rid]["last_seen"] = day
                pending[rid]["days_inactive"] = 0
                if rid in gps_points:
                    pending[rid]["points"].extend(gps_points[rid])
                    pending[rid]["n_trips"] += gps_trips.get(rid, 0)
            else:
                pending[rid]["days_inactive"] = pending[rid].get("days_inactive", 0) + 1

        # ── Retirar pendientes que llevan demasiado tiempo sin aparecer ────────
        for rid in list(pending.keys()):
            if pending[rid]["days_inactive"] >= RETIRE_GAP_DAYS:
                entry = pending.pop(rid)
                retired_unresolved.append({
                    "route_id": rid,
                    "direction_id": entry["direction_id"],
                    "first_seen": entry["first_seen"],
                    "last_seen": entry["last_seen"],
                    "status": "retired",
                    "assignment_status": "unresolved",
                    "shape_key": None,
                    "short_name": None,
                    "shape_id": None,
                    "name": None,
                    "confidence": None,
                    "method": None,
                })

        # ── Intentar resolver pendientes ──────────────────────────────────────
        if pending and has_shapes:
            evidence = {
                rid: RouteEvidence(
                    route_id=rid,
                    direction_id=data["direction_id"],
                    n_trips=data["n_trips"],
                    points=data["points"],
                )
                for rid, data in pending.items()
                if data["points"]
            }
            if evidence:
                lookup = build_lookup(evidence, shape_entries, families)
                for rid, result in lookup.items():
                    if result.status == "resolved":
                        entry = pending.pop(rid)
                        resolved[rid] = {
                            "route_id": rid,
                            "direction_id": entry["direction_id"],
                            "first_seen": entry["first_seen"],
                            "last_seen": entry["last_seen"],
                            "status": "active" if rid in active else "retired",
                            "assignment_status": "resolved",
                            "shape_key": result.assigned_shape_key,
                            "short_name": result.short_name,
                            "shape_id": result.shape_id,
                            "name": result.name,
                            "confidence": result.confidence,
                            "method": result.method,
                            "assignment_type": result.assignment_type,
                        }

        n_res = len(resolved)
        n_pend = len(pending)
        print(f"  {day} [{mode:4}]  active={len(active):3}  resolved={n_res:3}  pending={n_pend}")

    # ── Al final, resolver last_seen para activos y marcar status ─────────────
    last_day = daily_files[-1].name[:10] if daily_files else today_str
    last_active = scan_route_ids(daily_files[-1], line, label_line_map) if daily_files else {}

    entries = []

    for rid, data in resolved.items():
        if rid in last_active:
            data["last_seen"] = last_day
            data["status"] = "active"
        entries.append(data)

    for rid, data in pending.items():
        entries.append({
            "route_id": rid,
            "direction_id": data["direction_id"],
            "first_seen": data["first_seen"],
            "last_seen": data["last_seen"],
            "status": "active" if rid in last_active else "retired",
            "assignment_status": "pending",
            "shape_key": None,
            "short_name": None,
            "shape_id": None,
            "name": None,
            "confidence": None,
            "method": None,
        })

    entries.extend(retired_unresolved)

    return entries


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Construye ramal_map.json desde NDJSON")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--line", type=str, default=None,
                        help="Procesar solo esta línea (default: todas con shapes)")
    parser.add_argument(
        "--shapes", type=Path,
        default=Path(__file__).parent.parent / "prediccion" / "data" / "line_shapes.json",
    )
    parser.add_argument(
        "--label-map", type=Path,
        default=Path(__file__).parent.parent / "LABEL_LINE_MAP.json",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--skip-first", type=int, default=SKIP_FIRST_DAYS,
                        help=f"Días parciales a saltear al inicio (default {SKIP_FIRST_DAYS})")
    args = parser.parse_args()

    label_line_map = load_label_line_map(str(args.label_map))
    shapes_data = load_shapes(str(args.shapes))

    # Líneas a procesar: las que tienen shapes, o la indicada por --line
    if args.line:
        lines = [args.line]
    else:
        lines = [l for l in shapes_data if (Path(__file__).parent / f"families_{l}.json").exists()]

    daily_files = [
        f for f in iter_daily_files(args.data_dir)
        if f.name[:10] != date.today().isoformat()
    ]
    daily_files = daily_files[args.skip_first:]
    if not daily_files:
        print("ERROR: no hay archivos NDJSON en", args.data_dir, file=sys.stderr)
        sys.exit(1)

    print(f"Archivos: {len(daily_files)} días "
          f"({daily_files[0].name[:10]} → {daily_files[-1].name[:10]})")

    result: dict = {
        "generated_at": datetime.now().isoformat(),
        "lines": {}
    }

    total_start = time.time()
    for line in lines:
        families_path = Path(__file__).parent / f"families_{line}.json"
        print(f"\nLínea {line} {'(con shapes)' if line in shapes_data and families_path.exists() else '(sin shapes)'}")
        t0 = time.time()
        entries = build_line(line, daily_files, label_line_map, shapes_data, families_path)
        elapsed = time.time() - t0

        n_resolved = sum(1 for e in entries if e["assignment_status"] == "resolved")
        n_active = sum(1 for e in entries if e["status"] == "active")
        print(f"  → {len(entries)} route_ids | {n_resolved} resueltos | {n_active} activos | {elapsed:.0f}s")

        result["lines"][line] = {"entries": entries}

    print(f"\nTiempo total: {time.time()-total_start:.0f}s")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Escrito: {args.output}")


if __name__ == "__main__":
    main()
