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
  [3/4] NDJSON → trips → features ETA por día (streaming, cacheado en days/)
  [4/4] Merge de días cacheados → eta_train.parquet / eta_val.parquet

Caché: cada día completo se guarda en ml-dir/training/days/YYYY-MM-DD.parquet
con TODAS las líneas. El filtro --lines se aplica solo al merge final.
Si el parquet del día ya existe, se saltea el procesamiento del NDJSON.

El archivo del día de hoy siempre se excluye (está incompleto).

Split temporal: primeros 80% de días → eta_train.parquet, resto → eta_val.parquet.
"""

import argparse
import logging
import sys
from datetime import date
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


def _process_daily_file(
    fp: Path,
    shapes: dict,
    label_line_map: dict,
    shape_lengths: dict[str, float],
    interval_s: int,
    vehicle_obs_carry: dict,
) -> tuple[list[dict], list[dict], dict]:
    """Procesa un archivo NDJSON.gz y retorna (eta_rows, trip_rows, nuevo_carry)."""
    from prediccion.pipeline.reader import reconstruct_snapshots
    from prediccion.pipeline.segmenter import segment_vehicle_history
    from prediccion.pipeline.projector import project_trip
    from prediccion.pipeline.features import make_training_rows_eta

    day_vehicle_obs: dict[str, list[dict]] = {
        vid: list(obs) for vid, obs in vehicle_obs_carry.items()
    }
    for ts, state in reconstruct_snapshots(fp, interval_s=interval_s):
        for vid, fields in state.items():
            obs = dict(fields)
            obs["ts"] = obs.get("ts", ts)
            day_vehicle_obs.setdefault(vid, []).append(obs)

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

    eta_rows = []
    trip_rows = []
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

    return eta_rows, trip_rows, new_carry


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
        import pyarrow.compute as pc
    except ImportError:
        logger.error("pyarrow not installed. Run: pip install -r requirements-train.txt")
        sys.exit(1)

    from prediccion.pipeline.reader import iter_daily_files

    # [1/4] Load shapes — SIN filtrar por --lines (el caché guarda todas las líneas)
    print("[1/4] Cargando shapes desde:", shapes_url)
    shapes = _load_shapes(shapes_url)
    print(f"      {len(shapes)} líneas disponibles")

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
    day_cache_dir = training_dir / "days"
    trip_cache_dir = trips_dir / "days"
    for d in [trips_dir, training_dir, day_cache_dir, trip_cache_dir]:
        d.mkdir(parents=True, exist_ok=True)

    shape_lengths = _compute_shape_lengths(shapes)

    # Filtrar hoy (archivo parcial) y ordenar
    today_name = f"{date.today().isoformat()}.ndjson.gz"
    all_daily_files = list(iter_daily_files(data_dir))
    daily_files = [f for f in all_daily_files if f.name != today_name]
    if len(all_daily_files) != len(daily_files):
        print(f"      Excluido {today_name} (día parcial)")

    if not daily_files:
        print("ERROR: No se encontraron archivos NDJSON.gz", file=sys.stderr)
        sys.exit(1)

    # [3/4] Caché por día: si ya existe el Parquet del día, se saltea el NDJSON
    print(f"[3/4] Procesando días (caché en {day_cache_dir})...")
    vehicle_obs_carry: dict[str, list[dict]] = {}
    total_trips = 0
    total_eta_rows = 0

    for fp in daily_files:
        day_key = fp.stem  # "2026-03-28"
        day_cache = day_cache_dir / f"{day_key}.parquet"
        trip_cache = trip_cache_dir / f"{day_key}.parquet"

        if day_cache.exists():
            print(f"      {fp.name}: [cached]")
            # El carry-forward se pierde al saltear días, pero es aceptable:
            # el segmenter maneja trips que cruzan días vía el carry en runs frescos.
            vehicle_obs_carry = {}
            continue

        eta_rows, trip_rows_day, vehicle_obs_carry = _process_daily_file(
            fp, shapes, label_line_map, shape_lengths, interval_s, vehicle_obs_carry
        )
        total_trips += len(trip_rows_day)
        total_eta_rows += len(eta_rows)

        # Escribir atómicamente: .tmp → rename
        if eta_rows:
            tmp = day_cache.with_suffix(".tmp.parquet")
            pq.write_table(pa.Table.from_pylist(eta_rows), tmp)
            tmp.rename(day_cache)

        if trip_rows_day:
            tmp = trip_cache.with_suffix(".tmp.parquet")
            pq.write_table(pa.Table.from_pylist(trip_rows_day), tmp)
            tmp.rename(trip_cache)

        print(f"      {fp.name}: {len(trip_rows_day)} trips, {len(eta_rows)} filas ETA")

    print(f"      Total nuevos: {total_trips} trips, {total_eta_rows} filas ETA")

    # [4/4] Merge de días cacheados → eta_train.parquet / eta_val.parquet
    print("[4/4] Merge de días → train/val...")
    all_day_caches = sorted(day_cache_dir.glob("*.parquet"))
    if not all_day_caches:
        print("WARN: No hay días cacheados para hacer merge", file=sys.stderr)
        return

    split_idx = max(1, int(len(all_day_caches) * 0.8))
    train_days = all_day_caches[:split_idx]
    val_days = all_day_caches[split_idx:]
    print(f"      {len(all_day_caches)} días: {len(train_days)} train / {len(val_days)} val")
    if lines:
        print(f"      Filtrando líneas: {', '.join(lines)}")

    for subset, out_name in [(train_days, "eta_train.parquet"), (val_days, "eta_val.parquet")]:
        out_path = training_dir / out_name
        writer = None
        row_count = 0
        for dp in subset:
            tbl = pq.read_table(dp)
            if lines:
                mask = pc.is_in(tbl.column("line_number"), value_set=pa.array(lines))
                tbl = tbl.filter(mask)
            if len(tbl) == 0:
                continue
            if writer is None:
                writer = pq.ParquetWriter(out_path, tbl.schema)
            writer.write_table(tbl)
            row_count += len(tbl)
        if writer:
            writer.close()
        print(f"      {out_name}: {row_count} filas")

    # Trips summary merge
    all_trip_caches = sorted(trip_cache_dir.glob("*.parquet"))
    if all_trip_caches:
        tables = []
        for dp in all_trip_caches:
            tbl = pq.read_table(dp)
            if lines:
                mask = pc.is_in(tbl.column("line_number"), value_set=pa.array(lines))
                tbl = tbl.filter(mask)
            if len(tbl) > 0:
                tables.append(tbl)
        if tables:
            import pyarrow as pa
            merged = pa.concat_tables(tables)
            pq.write_table(merged, trips_dir / "trips_summary.parquet")
            print(f"      trips_summary.parquet: {len(merged)} filas")

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
