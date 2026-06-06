"""
Análisis de headway y cobertura de interpolación para feature time_since_last_bus_s.
Línea 39 únicamente.

Responde 4 preguntas:
  1. Distribución de gaps entre pings consecutivos del mismo vehículo (dt entre TripPoints)
  2. Fracción de targets hipotéticos que estarían "bracketados" por pings consecutivos
  3. Distribución de headways reales en la línea 39 (por checkpoint cada 500m)
  4. Error del supuesto de velocidad constante: interpolación lineal vs ping real del medio

Uso:
  cd "prediccion colectivos"
  python experiments/headway_analysis/analyze_headway_l39.py --date 2026-06-03
  python experiments/headway_analysis/analyze_headway_l39.py --date 2026-06-03 --date 2026-06-04
"""

import argparse
import sys
import json
from pathlib import Path
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")

from prediccion.pipeline.reader import reconstruct_lines_snapshots, iter_daily_files
from prediccion.pipeline.segmenter import segment_vehicle_history
from prediccion.pipeline.projector import project_trip, ShapeIndex, polyline_length_m
from prediccion.pipeline.shapes_io import load_shapes, load_label_line_map, DEFAULT_SHAPES_PATH

DATA_DIR = Path("Z:/grabaciones")
LINE = "39"
CHECKPOINT_STEP_M = 500
FALLBACK_RADIUS_M = 250
INTERP_ERROR_TRIPLET = True   # analizar triplets para medir error de interpolación


def load_line39_assets():
    shapes = load_shapes(str(DEFAULT_SHAPES_PATH))
    line_data = shapes.get(LINE)
    if not line_data:
        sys.exit(f"ERROR: línea {LINE} no encontrada en shapes")

    label_map = load_label_line_map(Path("LABEL_LINE_MAP.json"))

    # Todos los ramales de la línea 39
    ramales = []
    for ramal in line_data.get("ramales", []):
        pts = [tuple(p) for p in ramal["points"]]
        if len(pts) < 2:
            continue
        sh_id = ramal.get("shapeId", f"{LINE}-{ramal.get('direction',0)}")
        length_m = polyline_length_m(pts)
        ramales.append({
            "shape_id": sh_id,
            "direction": ramal.get("direction", 0),
            "length_m": length_m,
            "index": ShapeIndex(pts),
        })
    return label_map, ramales


def collect_projected_trips(daily_files, label_map, ramales):
    """
    Lee NDJSON(s), reconstruye observaciones, segmenta trips, proyecta.
    Retorna lista de trips proyectados: [{vehicle_id, shape_id, points: [(dist_m, ts), ...]}]
    """
    shape_indices = {r["shape_id"]: r["index"] for r in ramales}
    # Para dirección agnostica: también indexar por dirección
    dir_to_ramales = defaultdict(list)
    for r in ramales:
        dir_to_ramales[r["direction"]].append(r)

    vehicle_obs: dict[str, list[dict]] = {}

    for fp in daily_files:
        print(f"  Leyendo {fp.name}...")
        snapshots = reconstruct_lines_snapshots(fp, label_map, {LINE}, interval_s=30)
        day_obs: dict[str, list[dict]] = {}
        for ts, state in snapshots:
            for vid, fields in state.items():
                obs = dict(fields)
                obs["frame_ts"] = ts
                day_obs.setdefault(vid, []).append(obs)
        # merge carry
        for vid, obs_list in day_obs.items():
            vehicle_obs.setdefault(vid, []).extend(obs_list)

    print(f"  Vehículos acumulados: {len(vehicle_obs)}")

    projected_trips = []
    n_trips_total = 0
    n_trips_projected = 0

    for vid, observations in vehicle_obs.items():
        observations.sort(key=lambda o: o["ts"])
        trips = segment_vehicle_history(vid, observations)
        n_trips_total += len(trips)

        for trip in trips:
            # Elegir ShapeIndex por direction_id
            candidates = dir_to_ramales.get(trip.direction_id, [])
            if not candidates:
                candidates = ramales  # fallback: probar todos

            best_pt = None
            best_ramal = None
            best_valid = 0

            for ramal in candidates:
                pt = project_trip(trip, [], shape_index=ramal["index"])
                valid = sum(1 for p in pt.points if p.dist_along_shape_m >= 0 and p.perp_error_m < 150)
                if valid > best_valid:
                    best_valid = valid
                    best_pt = pt
                    best_ramal = ramal

            if best_pt is None or best_valid < 3:
                continue

            pts_ok = [
                (p.dist_along_shape_m, p.ts)
                for p in best_pt.points
                if p.dist_along_shape_m >= 0 and p.perp_error_m < 150
            ]
            if len(pts_ok) < 3:
                continue

            # Verificar que el trip recorra en orden creciente (no hay retrocesos graves)
            dists = [d for d, _ in pts_ok]
            if max(dists) - min(dists) < 200:
                continue  # apenas se movio

            n_trips_projected += 1
            projected_trips.append({
                "vehicle_id": vid,
                "shape_id": best_ramal["shape_id"],
                "length_m": best_ramal["length_m"],
                "direction": best_ramal["direction"],
                "points": pts_ok,   # list[(dist_m, ts)]
            })

    print(f"  Trips totales: {n_trips_total}, proyectados válidos: {n_trips_projected}")
    return projected_trips


# ── Análisis 1: distribución de gaps dt entre pings consecutivos ─────────────

def analysis_ping_gaps(projected_trips):
    print("\n═══ ANÁLISIS 1: Gaps entre pings consecutivos (dt) ═══")
    gaps = []
    for trip in projected_trips:
        pts = trip["points"]
        for i in range(len(pts) - 1):
            dt = pts[i + 1][1] - pts[i][1]
            if 0 < dt < 3600:
                gaps.append(dt)

    gaps = np.array(gaps)
    print(f"  N pares consecutivos: {len(gaps):,}")
    for p in [25, 50, 75, 90, 95, 99]:
        print(f"  P{p:2d}: {np.percentile(gaps, p):.0f}s")
    print(f"  Media: {gaps.mean():.1f}s  Max: {gaps.max():.0f}s")
    print(f"  Gaps > 60s: {(gaps > 60).mean():.1%}")
    print(f"  Gaps > 120s: {(gaps > 120).mean():.1%}")
    print(f"  Gaps > 300s: {(gaps > 300).mean():.1%}")
    return gaps


# ── Análisis 2: fracción de targets bracketados ───────────────────────────────

def analysis_bracket_coverage(projected_trips, n_samples=5000, rng_seed=42):
    print("\n═══ ANÁLISIS 2: Fracción de targets hipotéticos bracketados ═══")
    rng = np.random.default_rng(rng_seed)

    if not projected_trips:
        print("  Sin trips proyectados")
        return

    results = {"bracketed": 0, "fallback_250m": 0, "miss": 0}

    for _ in range(n_samples):
        trip = projected_trips[rng.integers(len(projected_trips))]
        pts = trip["points"]
        dists = [d for d, _ in pts]
        # Target aleatorio dentro del rango del trip
        f_dist = rng.uniform(min(dists) + 100, max(dists) - 100)

        # Buscar bracket
        bracketed = False
        nearest_gap = float("inf")
        for i in range(len(pts) - 1):
            d0, _ = pts[i]
            d1, _ = pts[i + 1]
            if d0 <= f_dist <= d1:
                bracketed = True
                break
            # Distancia mínima al target para fallback
            nearest_gap = min(nearest_gap, abs(d0 - f_dist), abs(d1 - f_dist))

        if bracketed:
            results["bracketed"] += 1
        elif nearest_gap <= FALLBACK_RADIUS_M:
            results["fallback_250m"] += 1
        else:
            results["miss"] += 1

    total = sum(results.values())
    print(f"  Samples: {total}")
    print(f"  Bracketados exactos: {results['bracketed']/total:.1%}  ({results['bracketed']})")
    print(f"  Fallback ≤{FALLBACK_RADIUS_M}m:     {results['fallback_250m']/total:.1%}  ({results['fallback_250m']})")
    print(f"  Miss total:          {results['miss']/total:.1%}  ({results['miss']})")
    print(f"  Cobertura total:     {(results['bracketed']+results['fallback_250m'])/total:.1%}")
    return results


# ── Análisis 3: distribución de headways reales ───────────────────────────────

def analysis_headway(projected_trips):
    print("\n═══ ANÁLISIS 3: Distribución de headways reales (L39) ═══")

    if not projected_trips:
        print("  Sin trips proyectados")
        return

    # Agrupar trips por shape_id y calcular headways por checkpoint
    by_shape = defaultdict(list)
    for trip in projected_trips:
        by_shape[trip["shape_id"]].append(trip)

    all_headways = []
    peak_headways = []   # 7-9h y 17-19h
    offpeak_headways = []

    PEAK_HOURS = {7, 8, 17, 18}

    for shape_id, trips in by_shape.items():
        if len(trips) < 3:
            continue

        shape_len = trips[0]["length_m"]
        checkpoints = np.arange(CHECKPOINT_STEP_M, shape_len, CHECKPOINT_STEP_M)

        for ck in checkpoints:
            # Estimar cuando cada trip pasó por este checkpoint
            passage_times = []
            for trip in trips:
                pts = trip["points"]
                for i in range(len(pts) - 1):
                    d0, t0 = pts[i]
                    d1, t1 = pts[i + 1]
                    if d0 <= ck <= d1 and d1 > d0:
                        t_est = t0 + (ck - d0) / (d1 - d0) * (t1 - t0)
                        passage_times.append(t_est)
                        break

            if len(passage_times) < 2:
                continue

            passage_times.sort()
            for i in range(len(passage_times) - 1):
                hw = passage_times[i + 1] - passage_times[i]
                if hw <= 0 or hw > 7200:  # ignorar > 2h (gaps de datos)
                    continue
                all_headways.append(hw)
                import time as _time
                import datetime
                hour = datetime.datetime.fromtimestamp(passage_times[i]).hour
                if hour in PEAK_HOURS:
                    peak_headways.append(hw)
                else:
                    offpeak_headways.append(hw)

    all_hw = np.array(all_headways)
    print(f"  N headways medidos: {len(all_hw):,}")
    if len(all_hw) == 0:
        print("  Sin datos suficientes")
        return

    for label, arr in [("Todo el día", all_hw), ("Hora pico (7-9h, 17-19h)", np.array(peak_headways)), ("Fuera de pico", np.array(offpeak_headways))]:
        if len(arr) == 0:
            continue
        print(f"\n  [{label}] n={len(arr):,}")
        for p in [10, 25, 50, 75, 90, 95]:
            print(f"    P{p:2d}: {np.percentile(arr, p)/60:.1f} min")
        print(f"    Media: {arr.mean()/60:.1f} min  Max: {arr.max()/60:.1f} min")
        print(f"    Headway < 3 min:  {(arr < 180).mean():.1%}")
        print(f"    Headway 3-10 min: {((arr >= 180) & (arr < 600)).mean():.1%}")
        print(f"    Headway > 10 min: {(arr >= 600).mean():.1%}")
        print(f"    Cap 3600s útil? >{(arr > 3600).mean():.1%} superan 1h")

    return all_hw


# ── Análisis 4: error de interpolación lineal ─────────────────────────────────

def analysis_interpolation_error(projected_trips):
    print("\n═══ ANÁLISIS 4: Error de interpolación lineal (validación velocidad constante) ═══")

    errors_s = []

    for trip in projected_trips:
        pts = trip["points"]
        if len(pts) < 3:
            continue

        for i in range(len(pts) - 2):
            d0, t0 = pts[i]
            d1, t1 = pts[i + 1]  # punto "real" del medio — actúa como target
            d2, t2 = pts[i + 2]

            # Solo si los puntos avanzan (no retrocesos)
            if not (d0 < d1 < d2):
                continue
            if t2 <= t0:
                continue

            # Interpolación lineal: ¿cuándo estimamos que el bus estuvo en d1?
            t_interp = t0 + (d1 - d0) / (d2 - d0) * (t2 - t0)
            error = abs(t_interp - t1)
            errors_s.append(error)

    errors = np.array(errors_s)
    print(f"  N triplets válidos: {len(errors):,}")
    if len(errors) == 0:
        print("  Sin datos")
        return

    for p in [50, 75, 90, 95, 99]:
        print(f"  P{p:2d}: {np.percentile(errors, p):.1f}s")
    print(f"  Media: {errors.mean():.1f}s")
    print(f"  Error < 10s: {(errors < 10).mean():.1%}")
    print(f"  Error < 30s: {(errors < 30).mean():.1%}")
    print(f"  Error < 60s: {(errors < 60).mean():.1%}")
    print(f"\n  → Si P90 < 30s: interpolación lineal es suficiente.")
    print(f"  → Si P90 > 60s: hay aceleración/frenada no lineal significativa.")
    return errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", action="append", dest="dates",
                        help="Fecha YYYY-MM-DD a analizar (puede repetirse)")
    parser.add_argument("--data-dir", default=str(DATA_DIR), type=Path)
    args = parser.parse_args()

    if not args.dates:
        # Default: últimos 2 días disponibles
        all_files = sorted(args.data_dir.glob("????-??-??.ndjson.gz"))
        if len(all_files) >= 2:
            # Excluir hoy (potencialmente parcial)
            from datetime import date
            today = date.today().isoformat()
            all_files = [f for f in all_files if f.stem != today]
            daily_files = all_files[-2:]
        else:
            daily_files = all_files
    else:
        daily_files = [args.data_dir / f"{d}.ndjson.gz" for d in args.dates]

    print(f"Archivos a procesar: {[f.name for f in daily_files]}")

    label_map, ramales = load_line39_assets()
    print(f"Ramales L39: {len(ramales)} ({[r['shape_id'] for r in ramales]})")

    projected_trips = collect_projected_trips(daily_files, label_map, ramales)

    if not projected_trips:
        print("ERROR: No se pudieron proyectar trips. Verificar datos y shapes.")
        sys.exit(1)

    # Resumen básico
    dists_per_trip = [max(d for d, _ in t["points"]) - min(d for d, _ in t["points"]) for t in projected_trips]
    print(f"\nTrips proyectados: {len(projected_trips)}")
    print(f"Distancia cubierta por trip — mediana: {np.median(dists_per_trip)/1000:.1f}km  P10: {np.percentile(dists_per_trip,10)/1000:.1f}km  P90: {np.percentile(dists_per_trip,90)/1000:.1f}km")

    analysis_ping_gaps(projected_trips)
    analysis_bracket_coverage(projected_trips)
    analysis_headway(projected_trips)
    analysis_interpolation_error(projected_trips)

    print("\n✓ Análisis completo.")


if __name__ == "__main__":
    main()
