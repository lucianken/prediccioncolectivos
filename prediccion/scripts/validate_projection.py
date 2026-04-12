"""
Verifica que la proyección de GPS sobre shapes sea válida ANTES de correr
el pipeline completo.

Uso:
  python prediccion/scripts/validate_projection.py \\
    --data-dir "\\\\192.168.0.18\\buffer\\grabaciones" \\
    --shapes-url http://localhost:3000/api/line-shapes \\
    --line 39 \\
    --sample-days 1

Output:
  Vehicles processed: 847
  Projection points: 12,340
  P50 perp_error_m: 34.2m  OK
  P90 perp_error_m: 89.1m  OK
  Points with error > 150m: 3.2%  OK
  OK PASS: Shapes válidos.
  (si P90 > 150m → ABORT con exit code 1)

Exit code: 0 = OK, 1 = P90 > 150m
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path


def load_shapes(shapes_url: str) -> dict:
    if shapes_url.startswith("http://") or shapes_url.startswith("https://"):
        with urllib.request.urlopen(shapes_url, timeout=30) as resp:
            return json.loads(resp.read())
    else:
        with open(shapes_url, encoding="utf-8") as f:
            return json.load(f)


def get_shape_points(shapes: dict, line: str, direction: int) -> list[tuple[float, float]] | None:
    if line not in shapes:
        return None
    for ramal in shapes[line].get("ramales", []):
        if ramal.get("direction") == direction:
            return [tuple(p) for p in ramal["points"]]
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Valida proyección GPS sobre shapes antes del pipeline completo"
    )
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--shapes-url", required=True)
    parser.add_argument("--line", required=True)
    parser.add_argument("--sample-days", type=int, default=1)
    args = parser.parse_args()

    # Import pipeline modules
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from prediccion.pipeline.reader import iter_daily_files, reconstruct_snapshots
    from prediccion.pipeline.segmenter import extract_trips_from_snapshots
    from prediccion.pipeline.projector import project_trip

    # Load shapes
    shapes = load_shapes(args.shapes_url)
    line = args.line

    if line not in shapes:
        print(f"ERROR: Línea '{line}' no encontrada en shapes", file=sys.stderr)
        sys.exit(1)

    # Collect sample daily files
    daily_files = list(iter_daily_files(args.data_dir))
    sample_files = daily_files[:args.sample_days]
    if not sample_files:
        print("ERROR: No se encontraron archivos NDJSON.gz", file=sys.stderr)
        sys.exit(1)

    # Build label map
    label_line_map = {line: line}
    for ramal in shapes[line].get("ramales", []):
        short_name = ramal.get("shortName", line)
        label_line_map[short_name] = line

    # Process
    perp_errors = []
    vehicles_processed = set()

    for fp in sample_files:
        snapshots = reconstruct_snapshots(fp, interval_s=30)
        trips = extract_trips_from_snapshots(snapshots, label_line_map)

        for trip in trips:
            if (trip.line_number or trip.route_id) != line:
                continue
            shape_pts = get_shape_points(shapes, line, trip.direction_id)
            if not shape_pts:
                continue
            vehicles_processed.add(trip.vehicle_id)
            pt = project_trip(trip, shape_pts, max_perp_error_m=float("inf"))
            for point in pt.points:
                if point.perp_error_m >= 0:
                    perp_errors.append(point.perp_error_m)

    if not perp_errors:
        print("ERROR: No se procesaron puntos de proyección", file=sys.stderr)
        sys.exit(1)

    perp_errors.sort()
    n = len(perp_errors)
    p50 = perp_errors[int(n * 0.50)]
    p90 = perp_errors[int(n * 0.90)]
    pct_over_150 = 100.0 * sum(1 for e in perp_errors if e > 150.0) / n

    print(f"Vehicles processed: {len(vehicles_processed):,}")
    print(f"Projection points: {n:,}")
    p50_ok = "OK" if p50 <= 150.0 else "WARN"
    p90_ok = "OK" if p90 <= 150.0 else "FAIL"
    pct_ok = "OK" if pct_over_150 <= 10.0 else "WARN"
    print(f"P50 perp_error_m: {p50:.1f}m  {p50_ok}")
    print(f"P90 perp_error_m: {p90:.1f}m  {p90_ok}")
    print(f"Points with error > 150m: {pct_over_150:.1f}%  {pct_ok}")

    if p90 > 150.0:
        print("ABORT: P90 perp_error > 150m — shapes inválidos o desactualizados.")
        sys.exit(1)
    else:
        print("PASS: Shapes válidos.")
        sys.exit(0)


if __name__ == "__main__":
    main()
