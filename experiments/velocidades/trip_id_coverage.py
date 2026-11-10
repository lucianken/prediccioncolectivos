"""
Cobertura de `trip_id` por línea en un mes.

Importa porque el pipeline descarta las muestras sin `trip_id` (son tiempo de
espera en cabecera, no servicio) y hay operadores que directamente no publican
viajes: con 0 % de cobertura la línea desaparece del análisis, y con cobertura
baja el resultado se apoya en una fracción chica y posiblemente sesgada de su
operación.

Uso:
    python -m experiments.velocidades.trip_id_coverage --month 2026-07 \
        --out experiments/velocidades/out_caba_202607/trip_id_coverage.csv
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from experiments.velocidades.extract_tracks import extract_day, DEFAULT_DATA_DIR, DEFAULT_MAP
from experiments.velocidades.lineas_caba import LINEAS_CABA
from experiments.velocidades.run_month import month_days
from prediccion.pipeline.build_dataset import EXCLUDED_DAYS
from prediccion.pipeline.shapes_io import load_label_line_data, resolve_label_line_map


def count_day(args) -> pd.DataFrame:
    day, lines, data_dir, map_path = args
    llm = resolve_label_line_map(load_label_line_data(map_path), on_date=day)
    df = pd.DataFrame(extract_day(data_dir / f"{day}.ndjson.gz", llm, set(lines)))
    if df.empty:
        return pd.DataFrame(columns=["line", "filas", "con_trip"])
    df["tiene"] = df.trip_id.notna() & (df.trip_id != "")
    g = df.groupby("line").agg(filas=("tiene", "size"), con_trip=("tiene", "sum"))
    return g.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--lines", nargs="+", default=list(LINEAS_CABA))
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--label-map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    days = [
        d for d in month_days(args.month)
        if d not in EXCLUDED_DAYS and (args.data_dir / f"{d}.ndjson.gz").exists()
    ]
    jobs = [(d, tuple(args.lines), args.data_dir, args.label_map) for d in days]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        parts = list(ex.map(count_day, jobs))

    g = pd.concat(parts).groupby("line")[["filas", "con_trip"]].sum()
    g["pct_con_trip_id"] = (100 * g.con_trip / g.filas).round(1)
    g = g.sort_values("pct_con_trip_id")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    g.to_csv(args.out)
    print(g.to_string())


if __name__ == "__main__":
    main()
