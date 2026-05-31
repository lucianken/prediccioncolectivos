#!/usr/bin/env python
"""
run_daily.py — Runner incremental que mantiene ramal_map.json día a día.

Por cada línea:
  1. Lee el NDJSON del día actual → detecta route_ids activos
  2. Marca como retired los route_ids que dejaron de aparecer (> RETIRE_GAP_DAYS)
  3. Detecta route_ids nuevos → los agrega como pending
  4. Para route_ids pending: corre el algoritmo sobre los días desde su first_seen
     (normalmente 1-5 días, no los 40 del período completo)
  5. Bloquea los que resuelven → nunca se vuelven a procesar
  6. Actualiza ramal_map.json

Solo lee NDJSON del día actual + los días necesarios para resolver pendientes.
Los route_ids ya resueltos nunca generan I/O.

Uso:
  python ramal_lookup/run_daily.py --data-dir Z:\\grabaciones
  python ramal_lookup/run_daily.py --data-dir Z:\\grabaciones --day 2026-05-31
  python ramal_lookup/run_daily.py --data-dir Z:\\grabaciones --all-lines
"""

import argparse
import json
import sys
import time
sys.stdout.reconfigure(encoding="utf-8")
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from prediccion.pipeline.reader import reconstruct_snapshots
from prediccion.pipeline.segmenter import segment_vehicle_history
from prediccion.pipeline.shapes_io import load_label_line_map, load_shapes

from ramal_lookup.route_lookup import (
    RouteEvidence,
    build_lookup,
    build_shape_entries,
    load_families,
)

# ── Configuración ─────────────────────────────────────────────────────────────

RAMAL_MAP   = Path(__file__).parent / "ramal_map.json"
STATE_DIR   = Path(__file__).parent / "lookup_state"
SHAPES_PATH = Path(__file__).parent.parent / "prediccion" / "data" / "line_shapes.json"
LABEL_MAP   = Path(__file__).parent.parent / "LABEL_LINE_MAP.json"

RETIRE_GAP_DAYS = 7    # días sin aparecer → retired
INTERVAL_S      = 30
LINES_WITH_SHAPES = {"39"}   # líneas con shapes disponibles para resolver


# ── I/O de estado ────────────────────────────────────────────────────────────

def load_state(line: str) -> dict:
    STATE_DIR.mkdir(exist_ok=True)
    p = STATE_DIR / f"state_{line}.json"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"line": line, "last_processed_day": None, "resolved": {}, "pending": {}}


def save_state(line: str, state: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    p = STATE_DIR / f"state_{line}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_ramal_map() -> dict:
    with open(RAMAL_MAP, encoding="utf-8") as f:
        return json.load(f)


def save_ramal_map(data: dict) -> None:
    with open(RAMAL_MAP, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Lectura de snapshots ──────────────────────────────────────────────────────

def get_active_rids(fp: Path, line: str, label_line_map: dict) -> dict[str, int]:
    """Lee un NDJSON y retorna {route_id: direction_id} para la línea."""
    vehicle_obs: dict[str, list] = defaultdict(list)
    for ts, state in reconstruct_snapshots(fp, interval_s=INTERVAL_S):
        for vid, fields in state.items():
            obs = dict(fields); obs["ts"] = obs.get("ts", ts)
            suffix = obs.get("label", "").split("-")[-1]
            if label_line_map.get(suffix) == line:
                vehicle_obs[vid].append(obs)

    rids: dict[str, int] = {}
    for vid, observations in vehicle_obs.items():
        observations.sort(key=lambda o: o["ts"])
        for trip in segment_vehicle_history(vid, observations):
            if trip.route_id and trip.route_id not in rids:
                rids[trip.route_id] = trip.direction_id
    return rids


def accumulate_evidence(
    data_dir: Path,
    days: list[str],
    rids: set[str],
    line: str,
    label_line_map: dict,
) -> dict[str, RouteEvidence]:
    """Acumula GPS de los días indicados para los route_ids en rids."""
    points: dict[str, list] = defaultdict(list)
    n_trips: dict[str, int] = defaultdict(int)
    direction: dict[str, int] = {}

    for day in days:
        fp = data_dir / f"{day}.ndjson.gz"
        if not fp.exists():
            continue
        vehicle_obs: dict[str, list] = defaultdict(list)
        for ts, state in reconstruct_snapshots(fp, interval_s=INTERVAL_S):
            for vid, fields in state.items():
                obs = dict(fields); obs["ts"] = obs.get("ts", ts)
                suffix = obs.get("label", "").split("-")[-1]
                if label_line_map.get(suffix) == line:
                    vehicle_obs[vid].append(obs)
        for vid, observations in vehicle_obs.items():
            observations.sort(key=lambda o: o["ts"])
            for trip in segment_vehicle_history(vid, observations):
                if trip.route_id not in rids:
                    continue
                direction[trip.route_id] = trip.direction_id
                n_trips[trip.route_id] += 1
                for pt in trip.points:
                    points[trip.route_id].append((pt.lat, pt.lon))

    return {
        rid: RouteEvidence(rid, direction.get(rid, -1), n_trips[rid], points[rid])
        for rid in rids
        if points[rid]
    }


# ── Actualizar ramal_map ──────────────────────────────────────────────────────

def update_map_entry(map_line: list, rid: str, updates: dict) -> None:
    """Actualiza in-place la entrada de un route_id en la lista de entradas."""
    for entry in map_line:
        if entry["route_id"] == rid:
            entry.update(updates)
            return
    # Si no existe, agregarlo
    map_line.append({"route_id": rid, **updates})


# ── Runner por línea ──────────────────────────────────────────────────────────

def run_line(line: str, data_dir: Path, day: str, label_line_map: dict) -> None:
    print(f"\n── Línea {line} ──────────────────────────────")
    state = load_state(line)
    ramal_map = load_ramal_map()
    map_entries: list = ramal_map["lines"].get(line, {}).get("entries", [])

    # 1. Route_ids activos hoy
    fp_today = data_dir / f"{day}.ndjson.gz"
    if not fp_today.exists():
        print(f"  AVISO: no existe {fp_today.name}, saltando")
        return

    t0 = time.time()
    active_today = get_active_rids(fp_today, line, label_line_map)
    print(f"  {len(active_today)} route_ids activos hoy ({time.time()-t0:.0f}s)")

    # 2. Detectar nuevos route_ids
    known = set(state["resolved"]) | set(state["pending"])
    new_rids = set(active_today) - known
    if new_rids:
        print(f"  Nuevos: {sorted(new_rids)}")
        for rid in new_rids:
            state["pending"][rid] = {
                "first_seen": day,
                "direction_id": active_today[rid],
            }

    # 3. Actualizar last_seen en ramal_map para los activos
    for rid in active_today:
        update_map_entry(map_entries, rid, {"last_seen": day, "status": "active"})

    # 4. Marcar retired los que llevan > RETIRE_GAP_DAYS sin aparecer
    day_dt = datetime.strptime(day, "%Y-%m-%d")
    for entry in map_entries:
        if entry.get("status") == "active" and entry["route_id"] not in active_today:
            last = entry.get("last_seen") or entry.get("first_seen", day)
            gap = (day_dt - datetime.strptime(last, "%Y-%m-%d")).days
            if gap >= RETIRE_GAP_DAYS:
                entry["status"] = "retired"
                print(f"  Retired: {entry['route_id']} (último: {last})")

    # 5. Resolver pendientes si la línea tiene shapes
    if state["pending"] and line in LINES_WITH_SHAPES:
        families_path = Path(__file__).parent / f"families_{line}.json"
        if not families_path.exists():
            print(f"  Sin families_{line}.json, pendientes quedan sin resolver")
        else:
            shapes_data = load_shapes(str(SHAPES_PATH))
            if line not in shapes_data:
                print(f"  Línea {line} no está en line_shapes.json")
            else:
                families = load_families(families_path)
                shape_entries = build_shape_entries(shapes_data, line, families)

                # Días a procesar: desde el first_seen más antiguo hasta hoy
                earliest = min(p["first_seen"] for p in state["pending"].values())
                days_range = []
                d = datetime.strptime(earliest, "%Y-%m-%d")
                while d.date() <= datetime.strptime(day, "%Y-%m-%d").date():
                    days_range.append(d.strftime("%Y-%m-%d"))
                    d += timedelta(days=1)

                print(f"  Resolviendo {len(state['pending'])} pendientes "
                      f"({earliest} → {day}, {len(days_range)} días)...")

                t0 = time.time()
                evidence = accumulate_evidence(
                    data_dir, days_range,
                    set(state["pending"].keys()), line, label_line_map
                )
                lookup = build_lookup(evidence, shape_entries, families)
                print(f"  Cómputo: {time.time()-t0:.0f}s")

                for rid, result in lookup.items():
                    if result.status == "resolved":
                        state["resolved"][rid] = {
                            "shape_key": result.assigned_shape_key,
                            "short_name": result.short_name,
                            "confidence": result.confidence,
                            "method": result.method,
                            "assignment_type": result.assignment_type,
                            "resolved_on": day,
                        }
                        del state["pending"][rid]
                        update_map_entry(map_entries, rid, {
                            "shape_key": result.assigned_shape_key,
                            "short_name": result.short_name,
                            "confidence": result.confidence,
                            "method": result.method,
                            "assignment_status": "resolved",
                            "assignment_type": result.assignment_type,
                        })
                        print(f"  Resuelto: {rid} → {result.assigned_shape_key} "
                              f"(conf={result.confidence:.2f}, {result.method})")

                still_pending = [r for r in state["pending"] if r not in lookup or
                                 lookup[r].status != "resolved"]
                if still_pending:
                    print(f"  Aún pendientes: {still_pending}")

    elif state["pending"]:
        print(f"  {len(state['pending'])} pendientes (sin shapes para {line})")

    # 6. Guardar
    state["last_processed_day"] = day
    save_state(line, state)

    ramal_map["lines"].setdefault(line, {})["entries"] = map_entries
    ramal_map["generated_at"] = datetime.now().isoformat()
    save_ramal_map(ramal_map)

    resolved_today = len([r for r in state["resolved"]])
    pending_today = len(state["pending"])
    print(f"  Estado: {resolved_today} resueltos, {pending_today} pendientes")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Runner incremental ramal_map")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--day", type=str, default=date.today().isoformat(),
                        help="Día a procesar (YYYY-MM-DD, default: hoy)")
    parser.add_argument("--line", type=str, default=None,
                        help="Procesar solo esta línea")
    parser.add_argument(
        "--label-map", type=Path,
        default=Path(__file__).parent.parent / "LABEL_LINE_MAP.json",
    )
    args = parser.parse_args()

    label_line_map = load_label_line_map(str(args.label_map))
    ramal_map = load_ramal_map()
    lines = [args.line] if args.line else list(ramal_map["lines"].keys())

    print(f"Procesando {args.day} — líneas: {lines}")

    for line in lines:
        run_line(line, args.data_dir, args.day, label_line_map)

    print(f"\nramal_map.json actualizado.")


def load_label_line_map(path: str) -> dict:
    from prediccion.pipeline.shapes_io import load_label_line_map as _load
    return _load(path)


if __name__ == "__main__":
    main()
