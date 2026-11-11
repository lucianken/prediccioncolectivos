"""
Validación de la opción A contra el pipeline viejo, para UN día de UNA línea (por defecto 39, 2026-05-06):
  - viajes y filas: v2 (K pares y todos los pares) vs data/ml/training/days/<línea>/<día>.ndjson.parquet
  - coincidencia del recorrido elegido por geometría vs el que asignaba ramal_map (route_id, direction_id)
    en los viajes donde había asignación. route_id se usa SOLO acá, como verdad de referencia.

  python -m prediccion.v2.compare_old --line 39 --day 2026-05-06 [--v2-dir data/ml/v2_smoke]
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from prediccion.pipeline.build_dataset import load_ramal_map
from prediccion.pipeline.shapes_io import load_label_line_data
from prediccion.v2.day import process_day
from prediccion.v2.shapes import (DEFAULT_DATA_DIR, DEFAULT_LABEL_MAP, DEFAULT_V2_DIR, LineShapes)


def compare(line: str, day: str, v2_dir: Path, data_dir: Path, old_root: Path = Path("data/ml")) -> dict:
    old_rows_path = old_root / "training" / "days" / line / f"{day}.ndjson.parquet"
    old_trips_path = old_root / "trips" / "days" / line / f"{day}.ndjson.parquet"
    old_rows = pq.ParquetFile(old_rows_path).metadata.num_rows
    old_trips = pd.read_parquet(old_trips_path)

    v2_trips = pq.read_table(v2_dir / "daily" / f"{day}.trips.parquet").to_pandas()
    v2_trips = v2_trips[v2_trips["line"] == line]
    v2_meta = json.loads((v2_dir / "daily" / f"{day}.meta.json").read_text())

    # v2 con TODOS los pares (misma semántica que el viejo) en un dir temporal, para comparar filas 1:1
    with tempfile.TemporaryDirectory() as td:
        m_all = process_day(day, [line], data_dir=data_dir, out_dir=Path(td), shapes=LineShapes(),
                            label_data=load_label_line_data(DEFAULT_LABEL_MAP), k_pairs=10**6, use_carry=False)
        rows_all = m_all["per_line"][line]["rows"]

    ramal_map = load_ramal_map()
    # dirección de cada shape completo según el propio ramal_map (para medir acuerdo de sentido)
    shape_dir = {sh: d for (_, d), sh in ramal_map.items() if not str(sh).startswith("frac_")}
    old_trips = old_trips.copy()
    old_trips["map_shape"] = [ramal_map.get((str(r), int(d))) for r, d in zip(old_trips["route_id"], old_trips["direction_id"])]
    j = old_trips.merge(v2_trips, left_on=["vehicle_id", "start_time"], right_on=["vehicle_id", "start_ts"],
                        how="left", suffixes=("_old", "_v2"))
    matched = j[j["shape_id"].notna()]
    with_map = matched[matched["map_shape"].notna()].copy()
    is_frac = with_map["map_shape"].astype(str).str.startswith("frac_")
    # un "frac_X" es una variante fraccionada del recorrido X: se compara contra X
    with_map["map_parent"] = with_map["map_shape"].astype(str).str.replace("frac_", "", regex=False)
    agree = (with_map["map_parent"] == with_map["shape_id"].astype(str))
    same_dir = pd.Series([shape_dir.get(a) is not None and shape_dir.get(a) == shape_dir.get(b)
                          for a, b in zip(with_map["map_parent"], with_map["shape_id"].astype(str))], index=with_map.index)

    def pct(mask, sel):
        return float(100.0 * mask[sel].mean()) if sel.sum() else None

    out = {
        "line": line, "day": day,
        "old": {"trips": int(len(old_trips)), "rows": int(old_rows),
                "trips_with_ramal_map_shape": int(old_trips["map_shape"].notna().sum()),
                "trips_map_fraccionado(frac_*)": int(old_trips["map_shape"].astype(str).str.startswith("frac_").sum())},
        "v2": {"trips": int(len(v2_trips)), "rows_k": int(v2_meta["per_line"][line]["rows"]),
               "rows_all_pairs": int(rows_all), "k_pairs": v2_meta["k_pairs"],
               "trips_with_rows": int((v2_trips["n_rows"] > 0).sum())},
        "join": {"old_trips_matched_in_v2": int(len(matched)), "matched_with_map_assignment": int(len(with_map)),
                 "agree": int(agree.sum()), "agree_pct": float(100.0 * agree.mean()) if len(with_map) else None,
                 "agree_pct_completo": pct(agree, ~is_frac), "n_completo": int((~is_frac).sum()),
                 "agree_pct_fraccionado_vs_parent": pct(agree, is_frac), "n_fraccionado": int(is_frac.sum()),
                 "same_direction_pct": float(100.0 * same_dir.mean()) if len(with_map) else None},
    }
    npts = with_map["n_points_v2"] if "n_points_v2" in with_map else with_map["n_points"]
    out["agree_pct_by_trip_length"] = {
        label: {"n": int(sel.sum()), "agree_pct": pct(agree, sel)}
        for label, sel in (("<20 puntos", npts < 20), ("20-49 puntos", (npts >= 20) & (npts < 50)),
                           (">=50 puntos", npts >= 50))}
    dis = with_map[~agree]
    if len(dis):
        out["disagreements"] = {
            "n": int(len(dis)),
            "median_perp_v2_agree": float(with_map.loc[agree, "median_perp_m"].median()),
            "median_perp_v2_disagree": float(dis["median_perp_m"].median()),
            "top_pairs_map_vs_geom": [[a, b, int(n)] for (a, b), n in
                                       dis.groupby(["map_parent", "shape_id"]).size().sort_values(ascending=False).head(8).items()],
        }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--line", default="39")
    ap.add_argument("--day", default="2026-05-06")
    ap.add_argument("--v2-dir", type=Path, default=DEFAULT_V2_DIR)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    a = ap.parse_args(argv)
    print(json.dumps(compare(a.line, a.day, a.v2_dir, a.data_dir), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
