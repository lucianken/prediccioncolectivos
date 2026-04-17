"""
CLI: construye Parquet de entrenamiento desde archivos NDJSON.gz.

Uso:
  python -m prediccion.pipeline.build_dataset \\
    --data-dir "\\\\192.168.0.18\\buffer\\grabaciones" \\
    --ml-dir data\\ml \\
    --lines 39,42,151

Pasos que corre:
  [1/4] Cargar shapes desde --shapes-url (URL o path local)
  [2/4] (Opcional) validate_projection — aborta si P90 perp_error > 150m
  [3/4] NDJSON → trips → features ETA (streaming día a día, sin acumular en RAM)
  [4/4] Trips summary → Parquet en ml-dir/trips/

Split temporal: primeros 80% de días → eta_train.parquet, resto → eta_val.parquet.
"""

import argparse
import logging
import sys
from pathlib import Path

from prediccion.pipeline.shapes_io import (
    load_shapes as _load_shapes,
    get_shape_points as _get_shape_points,
    build_label_line_map as _build_label_line_map,
)

logger = logging.getLogger(__name__)

_CARRY_WINDOW_S = 900  # 15 min de observaciones carry-forward entre días


def _compute_shape_lengths(shapes: dict) -> dict[str, float]:
    from prediccion.pipeline.projector import polyline_length_m
    lengths: dict[str, float] = {}
    for line_num, line_data in shapes.items():
        for ramal in line_data.get("ramales", []):
            pts = [tuple(p) for p in ramal["points"]]
            if len(pts) >= 2:
                ramal_id = f"{line_num}-{ramal.get('direction', 0)}"
                lengths[ramal_id] = polyline_length_m(pts)
    return lengths


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

    from prediccion.pipeline.reader import iter_daily_files, reconstruct_snapshots
    from prediccion.pipeline.segmenter import segment_vehicle_history
    from prediccion.pipeline.projector import project_trip
    from prediccion.pipeline.features import make_training_rows_eta

    # [1/4] Load shapes
    print("[1/4] Cargando shapes desde:", shapes_url)
    shapes = _load_shapes(shapes_url)
    print(f"      {len(shapes)} líneas disponibles")

    if lines:
        shapes = {k: v for k, v in shapes.items() if k in lines}
        print(f"      Filtrando a {len(shapes)} líneas: {', '.join(shapes.keys())}")

    label_line_map = _build_label_line_map(shapes)

    # [2/4] Optional validation
    if validate_projection:
        print("[2/4] Validando proyección...")
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
        print("[2/4] Saltando validación (usar --validate-projection para activar)")

    # Create output dirs
    trips_dir = ml_dir / "trips"
    training_dir = ml_dir / "training"
    for d in [trips_dir, training_dir]:
        d.mkdir(parents=True, exist_ok=True)

    shape_lengths = _compute_shape_lengths(shapes)

    # [3/4] Streaming día a día: NDJSON → trips → features → Parquet
    print("[3/4] Procesando NDJSON → Parquet (streaming día a día)...")
    daily_files = list(iter_daily_files(data_dir))
    if not daily_files:
        print("ERROR: No se encontraron archivos NDJSON.gz", file=sys.stderr)
        sys.exit(1)

    split_file_idx = max(1, int(len(daily_files) * 0.8))
    print(f"      {len(daily_files)} archivos: {split_file_idx} train / {len(daily_files) - split_file_idx} val")

    train_writer = None
    val_writer = None
    trip_rows = []
    total_trips = 0
    total_eta_rows = 0
    vehicle_obs_carry: dict[str, list[dict]] = {}

    for file_idx, fp in enumerate(daily_files):
        is_train = file_idx < split_file_idx

        # Carry-forward del día anterior + observaciones del día actual
        day_vehicle_obs: dict[str, list[dict]] = {
            vid: list(obs) for vid, obs in vehicle_obs_carry.items()
        }
        for ts, state in reconstruct_snapshots(fp, interval_s=interval_s):
            for vid, fields in state.items():
                obs = dict(fields)
                obs["ts"] = obs.get("ts", ts)
                day_vehicle_obs.setdefault(vid, []).append(obs)

        # Segmentar y preparar carry-forward para el día siguiente
        day_trips = []
        new_carry: dict[str, list[dict]] = {}
        for vid, observations in day_vehicle_obs.items():
            observations.sort(key=lambda o: o["ts"])
            trips = segment_vehicle_history(vid, observations)
            for trip in trips:
                trip.line_number = label_line_map.get(trip.route_id)
            day_trips.extend(trips)
            if observations:
                cutoff = observations[-1]["ts"] - _CARRY_WINDOW_S
                new_carry[vid] = [o for o in observations if o["ts"] >= cutoff]
        vehicle_obs_carry = new_carry

        # Proyectar sobre shapes y generar features ETA
        eta_rows = []
        for trip in day_trips:
            shape_pts = _get_shape_points(shapes, trip.line_number or trip.route_id, trip.direction_id)
            if not shape_pts:
                continue
            pt = project_trip(trip, shape_pts)
            if not pt.points:
                continue
            trip_rows.append({
                "vehicle_id": pt.vehicle_id,
                "route_id": pt.route_id,
                "direction_id": pt.direction_id,
                "start_time": pt.start_time,
                "line_number": pt.line_number or "",
                "n_points": len(pt.points),
            })
            ramal_id = f"{pt.line_number or pt.route_id}-{pt.direction_id}"
            rows = make_training_rows_eta(pt, ramal_id, shape_lengths.get(ramal_id, 1.0))
            eta_rows.extend(rows)

        total_trips += len(day_trips)
        total_eta_rows += len(eta_rows)

        # Escribir batch al Parquet correspondiente
        if eta_rows:
            batch = pa.RecordBatch.from_pylist(eta_rows)
            if is_train:
                if train_writer is None:
                    train_writer = pq.ParquetWriter(training_dir / "eta_train.parquet", batch.schema)
                train_writer.write_batch(batch)
            else:
                if val_writer is None:
                    val_writer = pq.ParquetWriter(training_dir / "eta_val.parquet", batch.schema)
                val_writer.write_batch(batch)

        split_label = "train" if is_train else "val"
        print(f"      {fp.name}: {len(day_trips)} trips, {len(eta_rows)} filas [{split_label}]")

    if train_writer:
        train_writer.close()
    if val_writer:
        val_writer.close()

    print(f"      Total: {total_trips} trips, {total_eta_rows} filas ETA")

    # [4/4] Trips summary
    print("[4/4] Guardando trips summary...")
    if trip_rows:
        trips_table = pa.Table.from_pylist(trip_rows)
        pq.write_table(trips_table, trips_dir / "trips_summary.parquet")
        print(f"      {len(trip_rows)} trips → {trips_dir}/trips_summary.parquet")
    else:
        print("WARN: No se generaron trips")

    print("Done.")


from prediccion.pipeline.shapes_io import DEFAULT_SHAPES_PATH as _DEFAULT_SHAPES


def main():
    parser = argparse.ArgumentParser(description="Build ML dataset from NDJSON.gz")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--ml-dir", required=True, type=Path)
    parser.add_argument("--shapes-url", default=str(_DEFAULT_SHAPES))
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
