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
import sys
from pathlib import Path

from prediccion.pipeline.shapes_io import load_shapes, get_shape_points, build_label_line_map, DEFAULT_SHAPES_PATH


def run_validation(
    data_dir: Path,
    shapes_url: str,
    lines: list[str] | None = None,
    sample_days: int = 1,
) -> dict:
    """
    Programmatic API para train.py.  Retorna dict con:
      {"ok": bool, "p90_m": float, "p50_m": float,
       "pct_over_150": float, "n_points": int, "n_vehicles": int}
    """
    from prediccion.pipeline.reader import iter_daily_files, reconstruct_snapshots
    from prediccion.pipeline.segmenter import extract_trips_from_snapshots
    from prediccion.pipeline.projector import project_trip

    shapes = load_shapes(shapes_url)
    target_lines = lines if lines else list(shapes.keys())
    label_line_map = build_label_line_map(shapes)

    perp_errors = []
    vehicles_processed: set[str] = set()

    for line in target_lines:
        if line not in shapes:
            continue

        daily_files = list(iter_daily_files(Path(data_dir)))
        for fp in daily_files[:sample_days]:
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
        return {
            "ok": False,
            "p90_m": None, "p50_m": None,
            "pct_over_150": None, "n_points": 0,
            "n_vehicles": len(vehicles_processed),
        }

    perp_errors.sort()
    n = len(perp_errors)
    p50 = perp_errors[int(n * 0.50)]
    p90 = perp_errors[int(n * 0.90)]
    pct_over_150 = 100.0 * sum(1 for e in perp_errors if e > 150.0) / n

    return {
        "ok": p90 <= 150.0,
        "p90_m": p90,
        "p50_m": p50,
        "pct_over_150": pct_over_150,
        "n_points": n,
        "n_vehicles": len(vehicles_processed),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Valida proyección GPS sobre shapes antes del pipeline completo"
    )
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--shapes-url", default=str(DEFAULT_SHAPES_PATH))
    parser.add_argument("--line", required=True)
    parser.add_argument("--sample-days", type=int, default=1)
    args = parser.parse_args()

    # Validate that the line exists before running the full pipeline
    shapes = load_shapes(args.shapes_url)
    if args.line not in shapes:
        print(f"ERROR: Línea '{args.line}' no encontrada en shapes", file=sys.stderr)
        sys.exit(1)

    result = run_validation(
        data_dir=args.data_dir,
        shapes_url=args.shapes_url,
        lines=[args.line],
        sample_days=args.sample_days,
    )

    if result["n_points"] == 0:
        print("ERROR: No se procesaron puntos de proyección", file=sys.stderr)
        sys.exit(1)

    p50 = result["p50_m"]
    p90 = result["p90_m"]
    pct_over_150 = result["pct_over_150"]
    n = result["n_points"]

    p50_ok = "OK" if p50 <= 150.0 else "WARN"
    p90_ok = "OK" if p90 <= 150.0 else "FAIL"
    pct_ok = "OK" if pct_over_150 <= 10.0 else "WARN"

    print(f"Vehicles processed: {result['n_vehicles']:,}")
    print(f"Projection points: {n:,}")
    print(f"P50 perp_error_m: {p50:.1f}m  {p50_ok}")
    print(f"P90 perp_error_m: {p90:.1f}m  {p90_ok}")
    print(f"Points with error > 150m: {pct_over_150:.1f}%  {pct_ok}")

    if not result["ok"]:
        print("ABORT: P90 perp_error > 150m — shapes inválidos o desactualizados.")
        sys.exit(1)
    else:
        print("PASS: Shapes válidos.")
        sys.exit(0)


if __name__ == "__main__":
    main()
