"""
CLI: construye Parquet de entrenamiento desde archivos NDJSON.gz.

Uso:
  python -m prediccion.pipeline.build_dataset \\
    --data-dir "\\\\192.168.0.18\\buffer\\grabaciones" \\
    --ml-dir "\\\\192.168.0.18\\buffer\\ml" \\
    --shapes-url http://localhost:3000/api/line-shapes \\
    --lines 39,42,151 \\
    --validate-projection

Pasos que corre:
  [1/5] Cargar shapes desde --shapes-url (URL o path local)
  [2/5] (Opcional) validate_projection — aborta si P90 perp_error > 150m
  [3/5] NDJSON → snapshots → Parquet en ml-dir/snapshots/
  [4/5] Snapshots → trips proyectados → Parquet en ml-dir/trips/
  [5/5] Trips → features ETA + ramal → Parquet en ml-dir/training/ (80/20 split temporal)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_shapes(shapes_url: str) -> dict:
    """Carga shapes desde URL HTTP o path local JSON."""
    if shapes_url.startswith("http://") or shapes_url.startswith("https://"):
        import urllib.request
        with urllib.request.urlopen(shapes_url, timeout=30) as resp:
            return json.loads(resp.read())
    else:
        with open(shapes_url, encoding="utf-8") as f:
            return json.load(f)


def _get_shape_points(shapes: dict, line: str, direction: int) -> list[tuple[float, float]] | None:
    """Extrae puntos del shape para una línea y dirección."""
    if line not in shapes:
        return None
    for ramal in shapes[line].get("ramales", []):
        if ramal.get("direction") == direction:
            return [tuple(p) for p in ramal["points"]]
    return None


def run_build_dataset(
    data_dir: Path,
    ml_dir: Path,
    shapes_url: str,
    lines: list[str] | None = None,
    interval_s: int = 30,
    validate_projection: bool = False,
):
    """Lógica principal — importable desde train.py"""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        logger.error("pyarrow not installed. Run: pip install -r requirements-train.txt")
        sys.exit(1)

    from prediccion.pipeline.reader import iter_daily_files, reconstruct_snapshots, count_days
    from prediccion.pipeline.segmenter import extract_trips_from_snapshots
    from prediccion.pipeline.projector import project_trip
    from prediccion.pipeline.features import make_training_rows_eta

    # [1/5] Load shapes
    print("[1/5] Cargando shapes desde:", shapes_url)
    shapes = _load_shapes(shapes_url)
    print(f"      {len(shapes)} líneas disponibles")

    # Filter by requested lines
    if lines:
        shapes = {k: v for k, v in shapes.items() if k in lines}
        print(f"      Filtrando a {len(shapes)} líneas: {', '.join(shapes.keys())}")

    # Build label_line_map from shapes: {route_id: line_number}
    label_line_map: dict[str, str] = {}
    for line_num, line_data in shapes.items():
        for ramal in line_data.get("ramales", []):
            short_name = ramal.get("shortName", line_num)
            label_line_map[short_name] = line_num
        label_line_map[line_num] = line_num

    # [2/5] Optional validation
    if validate_projection:
        print("[2/5] Validando proyección...")
        import subprocess
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "scripts" / "validate_projection.py"),
                "--data-dir", str(data_dir),
                "--shapes-url", shapes_url,
            ],
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print("ABORT: validate_projection falló (P90 > 150m)", file=sys.stderr)
            sys.exit(1)
    else:
        print("[2/5] Saltando validación de proyección (usar --validate-projection para activar)")

    # Create output dirs
    snapshots_dir = ml_dir / "snapshots"
    trips_dir = ml_dir / "trips"
    training_dir = ml_dir / "training"
    for d in [snapshots_dir, trips_dir, training_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # [3/5] NDJSON → snapshots
    print("[3/5] Procesando archivos NDJSON → snapshots...")
    daily_files = list(iter_daily_files(data_dir))
    print(f"      {len(daily_files)} archivos encontrados")

    all_snapshots = []
    for fp in daily_files:
        day_snaps = list(reconstruct_snapshots(fp, interval_s=interval_s))
        all_snapshots.extend(day_snaps)
        print(f"      {fp.name}: {len(day_snaps)} snapshots")

    if not all_snapshots:
        print("ERROR: No snapshots encontrados", file=sys.stderr)
        sys.exit(1)

    # [4/5] Snapshots → trips
    print("[4/5] Segmentando trips y proyectando sobre shapes...")
    trips = extract_trips_from_snapshots(iter(all_snapshots), label_line_map)
    print(f"      {len(trips)} trips extraídos")

    projected_trips = []
    for trip in trips:
        # Find matching shape
        shape_pts = _get_shape_points(shapes, trip.line_number or trip.route_id, trip.direction_id)
        if shape_pts:
            pt = project_trip(trip, shape_pts)
            if pt.points:
                projected_trips.append(pt)

    print(f"      {len(projected_trips)} trips proyectados con puntos válidos")

    # Save trips summary as parquet
    trip_rows = []
    for trip in projected_trips:
        trip_rows.append({
            "vehicle_id": trip.vehicle_id,
            "route_id": trip.route_id,
            "direction_id": trip.direction_id,
            "start_time": trip.start_time,
            "line_number": trip.line_number or "",
            "n_points": len(trip.points),
        })
    if trip_rows:
        trips_table = pa.Table.from_pylist(trip_rows)
        pq.write_table(trips_table, trips_dir / "trips_summary.parquet")

    # [5/5] Features ETA → training parquet
    print("[5/5] Generando features ETA → Parquet de entrenamiento...")

    # Compute shape lengths
    shape_lengths: dict[str, float] = {}
    from prediccion.pipeline.projector import haversine_m
    for line_num, line_data in shapes.items():
        for ramal in line_data.get("ramales", []):
            pts = [tuple(p) for p in ramal["points"]]
            if len(pts) >= 2:
                total = sum(
                    haversine_m(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
                    for i in range(len(pts) - 1)
                )
                ramal_id = f"{line_num}-{ramal.get('direction', 0)}"
                shape_lengths[ramal_id] = total

    all_eta_rows = []
    for trip in projected_trips:
        line_num = trip.line_number or trip.route_id
        ramal_id = f"{line_num}-{trip.direction_id}"
        shape_len = shape_lengths.get(ramal_id, 1.0)
        from prediccion.pipeline.features import make_training_rows_eta
        rows = make_training_rows_eta(trip, ramal_id, shape_len)
        all_eta_rows.extend(rows)

    print(f"      {len(all_eta_rows)} filas de entrenamiento ETA generadas")

    if all_eta_rows:
        # 80/20 temporal split
        split_idx = int(len(all_eta_rows) * 0.8)
        train_rows = all_eta_rows[:split_idx]
        val_rows = all_eta_rows[split_idx:]

        train_table = pa.Table.from_pylist(train_rows)
        val_table = pa.Table.from_pylist(val_rows)
        pq.write_table(train_table, training_dir / "eta_train.parquet")
        pq.write_table(val_table, training_dir / "eta_val.parquet")
        print(f"      Guardado: {training_dir}/eta_train.parquet ({len(train_rows)} filas)")
        print(f"      Guardado: {training_dir}/eta_val.parquet ({len(val_rows)} filas)")
    else:
        print("WARN: No se generaron filas ETA")

    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Build ML dataset from NDJSON.gz")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--ml-dir", required=True, type=Path)
    parser.add_argument("--shapes-url", required=True)
    parser.add_argument("--lines", default=None)
    parser.add_argument("--validate-projection", action="store_true")
    parser.add_argument("--interval-s", type=int, default=30)
    args = parser.parse_args()

    run_build_dataset(
        data_dir=args.data_dir,
        ml_dir=args.ml_dir,
        shapes_url=args.shapes_url,
        lines=args.lines.split(",") if args.lines else None,
        interval_s=args.interval_s,
        validate_projection=args.validate_projection,
    )


if __name__ == "__main__":
    main()
