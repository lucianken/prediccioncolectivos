"""
CLI: construye Parquet de entrenamiento desde archivos NDJSON.gz.

Uso:
  python -m prediccion.pipeline.build_dataset \\
    --data-dir "\\\\192.168.0.18\\buffer\\grabaciones" \\
    --ml-dir data\\ml \\
    --lines 39

Pasos que corre:
  [1/4] Cargar shapes para las líneas solicitadas
  [2/4] (Opcional) validate_projection — aborta si P90 perp_error > 150m
  [3/4] NDJSON → trips → features ETA por día y por línea (streaming, cacheado)
  [4/4] Merge de caché → eta_train.parquet / eta_val.parquet

Caché: training/days/{linea}/YYYY-MM-DD.parquet
  - El NDJSON de cada día se lee UNA sola vez y genera los parquets de todas
    las líneas solicitadas en ese run.
  - Si el parquet de una línea/día ya existe, se saltea.
  - Agregar una línea nueva solo procesa los días faltantes de esa línea.
  - El archivo del día de hoy siempre se excluye (está incompleto).

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
    load_label_line_map as _load_label_line_map,
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
                # Naive fallback key
                lengths[f"{line_num}-{ramal.get('direction', 0)}"] = polyline_length_m(pts)
                # Exact shape_key (e.g. "39A-d0")
                short_name = ramal.get("shortName", line_num)
                direction = ramal.get("direction", 0)
                lengths[f"{short_name}-d{direction}"] = polyline_length_m(pts)
    return lengths


def _process_daily_file(
    fp: Path,
    shapes: dict,
    label_line_map: dict,
    shape_lengths: dict[str, float],
    interval_s: int,
    vehicle_obs_carry: dict,
    ramal_id_map: dict[tuple[str, int], str] | None = None,
    ramal_key_map: dict[tuple[str, int], str] | None = None,
) -> tuple[dict[str, list], dict[str, list], dict]:
    """
    Procesa un archivo NDJSON.gz en un solo pase.
    Retorna:
      eta_by_line:   {line_num: [eta_row, ...]}
      trips_by_line: {line_num: [trip_row, ...]}
      nuevo_carry:   {vehicle_id: [obs, ...]}
    """
    from prediccion.pipeline.segmenter import segment_vehicle_history
    from prediccion.pipeline.projector import project_trip, ShapeIndex
    from prediccion.pipeline.features import make_training_rows_eta

    # Precomputar ShapeIndex por shape_id (exacto) y por (línea, dirección) (naive)
    shape_indices: dict[str, ShapeIndex] = {}
    naive_shape_indices: dict[tuple[str, int], ShapeIndex] = {}
    for line_num, line_data in shapes.items():
        for ramal in line_data.get("ramales", []):
            pts = [tuple(p) for p in ramal["points"]]
            if len(pts) >= 2:
                sh_id = ramal.get("shapeId")
                if sh_id:
                    shape_indices[sh_id] = ShapeIndex(pts)
                naive_key = (line_num, ramal.get("direction", 0))
                naive_shape_indices[naive_key] = ShapeIndex(pts)

    target_lines = set(shapes.keys()) if shapes else set()
    if target_lines:
        from prediccion.pipeline.reader import reconstruct_lines_snapshots
        snapshots_iter = reconstruct_lines_snapshots(
            fp, label_line_map, target_lines, interval_s=interval_s
        )
    else:
        from prediccion.pipeline.reader import reconstruct_snapshots
        snapshots_iter = reconstruct_snapshots(fp, interval_s=interval_s)

    fleet_by_line_at_ts: dict[tuple[str, int], list[dict]] = {}
    day_vehicle_obs: dict[str, list[dict]] = {
        vid: list(obs) for vid, obs in vehicle_obs_carry.items()
    }
    for ts, state in snapshots_iter:
        for vid, fields in state.items():
            obs = dict(fields)
            obs["ts"] = obs.get("ts", ts)
            day_vehicle_obs.setdefault(vid, []).append(obs)

            # Reconstruir estado de la flota
            raw_label = obs.get("label", "")
            suffix = raw_label.split("-")[-1] if raw_label else ""
            line_number = label_line_map.get(suffix)
            if line_number:
                fleet_by_line_at_ts.setdefault((line_number, ts), []).append({
                    "vehicle_id": vid,
                    "lat": obs.get("lat", 0.0),
                    "lon": obs.get("lon", 0.0),
                    "speed": obs.get("speed", 0.0),
                    "direction_id": obs.get("direction_id", 0),
                })

    day_trips = []
    new_carry: dict[str, list[dict]] = {}
    for vid, observations in day_vehicle_obs.items():
        observations.sort(key=lambda o: o["ts"])

        # Resolver línea por sufijo del VP_label (ej: "5-1350" → "1350" → "39")
        # El label es estable dentro de un vehículo; tomamos el primero disponible.
        raw_label = next((o.get("label", "") for o in observations if o.get("label")), "")
        suffix = raw_label.split("-")[-1] if raw_label else ""
        line_number = label_line_map.get(suffix)

        trips = segment_vehicle_history(vid, observations)
        for trip in trips:
            trip.line_number = line_number
        day_trips.extend(trips)
        if observations:
            cutoff = observations[-1]["ts"] - _CARRY_WINDOW_S
            new_carry[vid] = [o for o in observations if o["ts"] >= cutoff]

    eta_by_line: dict[str, list] = {}
    trips_by_line: dict[str, list] = {}

    for trip in day_trips:
        line_num = trip.line_number
        if line_num not in shapes:
            continue

        sh_id = None
        sh_key = None
        if ramal_id_map and ramal_key_map:
            key = (str(trip.route_id), int(trip.direction_id))
            sh_id = ramal_id_map.get(key)
            sh_key = ramal_key_map.get(key)

        idx = None
        if sh_id:
            idx = shape_indices.get(sh_id)
        if idx is None:
            idx = naive_shape_indices.get((line_num, trip.direction_id))

        if idx is None:
            continue

        pt = project_trip(trip, [], shape_index=idx)
        if not pt.points:
            continue

        trips_by_line.setdefault(line_num, []).append({
            "vehicle_id": pt.vehicle_id,
            "route_id": pt.route_id,
            "direction_id": pt.direction_id,
            "start_time": pt.start_time,
            "line_number": pt.line_number or "",
            "n_points": len(pt.points),
        })

        if sh_key:
            ramal_id = sh_key
        else:
            ramal_id = f"{line_num}-{pt.direction_id}"

        rows = make_training_rows_eta(
            pt,
            ramal_id,
            shape_lengths.get(ramal_id, 1.0),
            fleet_by_line_at_ts=fleet_by_line_at_ts,
        )
        if rows:
            eta_by_line.setdefault(line_num, []).extend(rows)

    return eta_by_line, trips_by_line, new_carry


def load_ramal_map() -> tuple[dict[tuple[str, int], str], dict[tuple[str, int], str]]:
    """
    Carga ramal_lookup/ramal_map.json y retorna dos mapeos:
    1. (route_id, direction_id) -> shape_id
    2. (route_id, direction_id) -> shape_key (ej: "39A-d0")
    """
    import json
    map_path = Path("ramal_lookup/ramal_map.json")
    if not map_path.exists():
        return {}, {}
    with open(map_path, encoding="utf-8") as f:
        data = json.load(f)
    
    id_map = {}
    key_map = {}
    for line_num, line_info in data.get("lines", {}).items():
        for entry in line_info.get("entries", []):
            r_id = entry.get("route_id")
            d_id = entry.get("direction_id")
            sh_id = entry.get("shape_id")
            sh_key = entry.get("shape_key")
            if r_id is not None and d_id is not None:
                if sh_id:
                    id_map[(str(r_id), int(d_id))] = sh_id
                if sh_key:
                    key_map[(str(r_id), int(d_id))] = sh_key
    return id_map, key_map


def run_build_dataset(
    data_dir: Path,
    ml_dir: Path,
    shapes_url: str,
    lines: list[str] | None = None,
    interval_s: int = 30,
    validate_projection: bool = False,
    label_map_path: Path | None = None,
):
    """Lógica principal — importable desde train.py"""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        logger.error("pyarrow not installed. Run: pip install -r requirements-train.txt")
        sys.exit(1)

    from prediccion.pipeline.reader import iter_daily_files

    # [1/4] Cargar shapes y mapa de labels
    print("[1/4] Cargando shapes desde:", shapes_url)
    all_shapes = _load_shapes(shapes_url)
    shapes = {k: v for k, v in all_shapes.items() if lines is None or k in lines}
    lines_to_process = list(shapes.keys())
    print(f"      Procesando {len(lines_to_process)} línea(s): {', '.join(lines_to_process)}")

    # Mapa de sufijo VP_label → line_number (fuente autoritativa)
    if label_map_path and label_map_path.exists():
        label_line_map = _load_label_line_map(label_map_path)
        print(f"      LABEL_LINE_MAP: {len(label_line_map)} sufijos cargados")
    else:
        if label_map_path:
            print(f"WARN: {label_map_path} no encontrado, usando fallback desde shapes", file=sys.stderr)
        from prediccion.pipeline.shapes_io import build_label_line_map as _build_fallback
        label_line_map = _build_fallback(shapes)

    # Cargar mapeo exacto de ramales (route_id, direction_id) -> shape_id/shape_key
    ramal_id_map, ramal_key_map = load_ramal_map()
    if ramal_id_map:
        print(f"      Cargado mapeo de ramales exactos: {len(ramal_id_map)} entradas")

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

    # Crear directorios de caché por línea
    trips_dir = ml_dir / "trips"
    training_dir = ml_dir / "training"
    for line_num in lines_to_process:
        (training_dir / "days" / line_num).mkdir(parents=True, exist_ok=True)
        (trips_dir / "days" / line_num).mkdir(parents=True, exist_ok=True)

    shape_lengths = _compute_shape_lengths(shapes)

    # Filtrar hoy (archivo parcial)
    today_name = f"{date.today().isoformat()}.ndjson.gz"
    all_daily_files = list(iter_daily_files(data_dir))
    daily_files = [f for f in all_daily_files if f.name != today_name]
    if len(all_daily_files) != len(daily_files):
        print(f"      Excluido {today_name} (día parcial)")
    if not daily_files:
        print("ERROR: No se encontraron archivos NDJSON.gz", file=sys.stderr)
        sys.exit(1)

    # [3/4] Caché por día × línea
    print(f"[3/4] Procesando {len(daily_files)} días...")
    vehicle_obs_carry: dict[str, list[dict]] = {}
    total_new_days = 0

    for fp in daily_files:
        day_key = fp.stem  # "2026-03-28"

        missing = [
            ln for ln in lines_to_process
            if not (training_dir / "days" / ln / f"{day_key}.parquet").exists()
        ]

        if not missing:
            print(f"      {fp.name}: [cached]")
            vehicle_obs_carry = {}
            continue

        eta_by_line, trips_by_line, vehicle_obs_carry = _process_daily_file(
            fp, shapes, label_line_map, shape_lengths, interval_s, vehicle_obs_carry,
            ramal_id_map=ramal_id_map, ramal_key_map=ramal_key_map,
        )

        for line_num in missing:
            eta_rows = eta_by_line.get(line_num, [])
            trip_rows = trips_by_line.get(line_num, [])

            eta_path = training_dir / "days" / line_num / f"{day_key}.parquet"
            trip_path = trips_dir / "days" / line_num / f"{day_key}.parquet"

            if eta_rows:
                tmp = eta_path.with_suffix(".tmp.parquet")
                pq.write_table(pa.Table.from_pylist(eta_rows), tmp)
                tmp.replace(eta_path)
            else:
                # Escribir parquet vacío para marcar el día como procesado
                eta_path.touch()

            if trip_rows:
                tmp = trip_path.with_suffix(".tmp.parquet")
                pq.write_table(pa.Table.from_pylist(trip_rows), tmp)
                tmp.replace(trip_path)

        summary = ", ".join(
            f"L{ln}:{len(eta_by_line.get(ln, []))} filas"
            for ln in missing
        )
        print(f"      {fp.name}: {summary}")
        total_new_days += 1

    print(f"      {total_new_days} días nuevos procesados")

    # [4/4] Merge → eta_train.parquet / eta_val.parquet
    print("[4/4] Merge de caché → train/val...")

    # Tomar el conjunto de días disponibles para todas las líneas (unión)
    all_day_keys: set[str] = set()
    for line_num in lines_to_process:
        for p in (training_dir / "days" / line_num).glob("*.parquet"):
            all_day_keys.add(p.stem)
    sorted_days = sorted(all_day_keys)

    if not sorted_days:
        print("WARN: No hay días cacheados", file=sys.stderr)
        return

    split_idx = max(1, int(len(sorted_days) * 0.8))
    train_days = sorted_days[:split_idx]
    val_days = sorted_days[split_idx:]
    print(f"      {len(sorted_days)} días: {len(train_days)} train / {len(val_days)} val")

    for day_subset, out_name in [(train_days, "eta_train.parquet"), (val_days, "eta_val.parquet")]:
        out_path = training_dir / out_name
        writer = None
        row_count = 0
        for day_key in day_subset:
            for line_num in lines_to_process:
                day_path = training_dir / "days" / line_num / f"{day_key}.parquet"
                if not day_path.exists() or day_path.stat().st_size == 0:
                    continue
                tbl = pq.read_table(day_path)
                if len(tbl) == 0:
                    continue
                if writer is None:
                    writer = pq.ParquetWriter(out_path, tbl.schema)
                writer.write_table(tbl)
                row_count += len(tbl)
        if writer:
            writer.close()
        print(f"      {out_name}: {row_count} filas")

    # Trips summary
    all_trip_tables = []
    for line_num in lines_to_process:
        for p in sorted((trips_dir / "days" / line_num).glob("*.parquet")):
            if p.stat().st_size > 0:
                all_trip_tables.append(pq.read_table(p))
    if all_trip_tables:
        import pyarrow as pa
        merged = pa.concat_tables(all_trip_tables)
        pq.write_table(merged, trips_dir / "trips_summary.parquet")
        print(f"      trips_summary.parquet: {len(merged)} trips")

    print("Done.")


from prediccion.pipeline.shapes_io import DEFAULT_SHAPES_PATH as _DEFAULT_SHAPES


_DEFAULT_LABEL_MAP = Path("LABEL_LINE_MAP.json")


def main():
    parser = argparse.ArgumentParser(description="Build ML dataset from NDJSON.gz")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--ml-dir", required=True, type=Path)
    parser.add_argument("--shapes-url", default=str(_DEFAULT_SHAPES))
    parser.add_argument("--label-map", type=Path, default=_DEFAULT_LABEL_MAP)
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
        label_map_path=args.label_map,
    )


if __name__ == "__main__":
    main()
