"""
Extrae los tracks crudos (una fila por posición reportada) de un conjunto de
líneas y días, desde los NDJSON.gz del grabador.

Salida: parquet con una fila por (vehículo, ts) con los campos necesarios para
el análisis de velocidades. NO hace ningún cálculo de velocidad — eso es
responsabilidad de analyze.py.

Uso:
    python -m experiments.velocidades.extract_tracks \
        --lines 39 42 \
        --days 2026-07-21 2026-07-22 2026-07-23 2026-07-18 \
        --out experiments/velocidades/out/tracks.parquet
"""

import argparse
from pathlib import Path

import pandas as pd

from prediccion.pipeline.reader import iter_frames
from prediccion.pipeline.shapes_io import load_label_line_data, resolve_label_line_map

DEFAULT_DATA_DIR = Path("Z:/grabaciones")
DEFAULT_MAP = Path("LABEL_LINE_MAP.json")

# Campos que arrastramos del estado del vehículo. `upd` trae solo los que
# cambiaron, así que el estado se acumula y cada fila es el estado completo.
CARRY = ("trip_id", "route_id", "direction_id", "start_date", "start_time")


def extract_day(
    path: Path,
    label_line_map: dict[str, str],
    lines: set[str],
) -> list[dict]:
    """
    Recorre un día completo y devuelve una fila por (vid, ts) de los vehículos
    de `lines`.

    Detalles del formato que importan acá:
    - `upd` trae solo los campos que cambiaron. Si no trae lat/lon, el vehículo
      no se movió respecto del ciclo anterior: repetimos la última posición y
      marcamos `moved=False`.
    - Hay frames duplicados con el mismo `t`; deduplicamos por (vid, ts).
    - Un `gap` invalida la continuidad temporal: marcamos `after_gap` en la
      primera fila posterior para que analyze.py no calcule un intervalo a
      través del agujero.
    """
    state: dict[str, dict] = {}
    rows: list[dict] = []
    seen: set[tuple[str, int]] = set()
    pending_gap = False

    def emit(vid: str, v: dict, moved: bool) -> None:
        nonlocal pending_gap
        key = (vid, v["ts"])
        if key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "vid": vid,
                "line": v["line"],
                "ts": v["ts"],
                "lat": v["lat"],
                "lon": v["lon"],
                "speed_api": v.get("speed"),
                "odo": v.get("odo"),
                "status": v.get("status"),
                "trip_id": v.get("trip_id"),
                "route_id": v.get("route_id"),
                "direction_id": v.get("direction_id"),
                "start_date": v.get("start_date"),
                "start_time": v.get("start_time"),
                "moved": moved,
                "after_gap": pending_gap,
            }
        )

    for frame in iter_frames(path):
        if frame.get("gap"):
            pending_gap = True
            continue

        is_keyframe = frame.get("keyframe", False)
        if is_keyframe:
            state = {}

        for v in frame.get("new", []):
            suffix = v.get("label", "").split("-")[-1]
            line = label_line_map.get(suffix)
            if line not in lines:
                continue
            rec = dict(v)
            rec["line"] = line
            state[v["id"]] = rec
            emit(v["id"], rec, moved=True)

        for vid in frame.get("del", []):
            state.pop(vid, None)

        for upd in frame.get("upd", []):
            vid = upd["id"]
            rec = state.get(vid)
            if rec is None:
                continue
            moved = "lat" in upd or "lon" in upd
            rec.update(upd)
            emit(vid, rec, moved=moved)

        if rows:
            pending_gap = False

    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", nargs="+", required=True)
    ap.add_argument("--days", nargs="+", required=True, help="YYYY-MM-DD")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--label-map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    lines = set(args.lines)
    map_data = load_label_line_data(args.label_map)

    frames = []
    for day in args.days:
        path = args.data_dir / f"{day}.ndjson.gz"
        if not path.exists():
            print(f"  !! falta {path}, salteo")
            continue
        # El map cambia con el tiempo (rotación de flota): resolver por fecha.
        llm = resolve_label_line_map(map_data, on_date=day)
        rows = extract_day(path, llm, lines)
        df = pd.DataFrame(rows)
        df["date"] = day
        frames.append(df)
        by_line = df.groupby("line").size().to_dict() if len(df) else {}
        print(f"  {day}: {len(df):>7} filas  {by_line}")

    out = pd.concat(frames, ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    print(f"\n{len(out)} filas -> {args.out}")


if __name__ == "__main__":
    main()
