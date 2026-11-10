"""
Corre extracción + intervalos para un mes entero, un proceso por día.

Procesa día a día porque un mes de las 27 líneas de CABA son ~36 M de filas de
posiciones: no entran cómodas en RAM de una. Cada día es independiente (ningún
viaje cruza la medianoche), así que paraleliza sin coordinación.

Excluye los días de cobertura incompleta listados en
`prediccion.pipeline.build_dataset.EXCLUDED_DAYS`.

Uso:
    python -m experiments.velocidades.run_month --month 2026-07 \
        --outdir experiments/velocidades/out_caba_202607 --workers 8
"""

import argparse
import calendar
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

from experiments.velocidades.build_intervals import build_from_frame
from experiments.velocidades.extract_tracks import extract_day, DEFAULT_DATA_DIR, DEFAULT_MAP
from experiments.velocidades.lineas_caba import LINEAS_CABA
from prediccion.pipeline.build_dataset import EXCLUDED_DAYS
from prediccion.pipeline.shapes_io import load_label_line_data, resolve_label_line_map


def process_day(args: tuple[str, tuple[str, ...], Path, Path, Path]) -> tuple[str, int, float]:
    day, lines, data_dir, map_path, outdir = args
    t0 = time.perf_counter()
    map_data = load_label_line_data(map_path)
    llm = resolve_label_line_map(map_data, on_date=day)

    rows = extract_day(data_dir / f"{day}.ndjson.gz", llm, set(lines))
    df = pd.DataFrame(rows)
    df["date"] = day
    iv = build_from_frame(df)
    iv.to_parquet(outdir / f"iv_{day}.parquet", index=False)
    return day, len(iv), time.perf_counter() - t0


def month_days(month: str) -> list[str]:
    y, m = (int(x) for x in month.split("-"))
    n = calendar.monthrange(y, m)[1]
    return [date(y, m, d).isoformat() for d in range(1, n + 1)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--lines", nargs="+", default=list(LINEAS_CABA))
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--label-map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    days = []
    for d in month_days(args.month):
        if d in EXCLUDED_DAYS:
            print(f"  - {d}: excluido (cobertura incompleta)")
        elif not (args.data_dir / f"{d}.ndjson.gz").exists():
            print(f"  - {d}: sin archivo")
        else:
            days.append(d)
    print(f"{len(days)} días a procesar, {len(args.lines)} líneas, {args.workers} procesos\n")

    jobs = [(d, tuple(args.lines), args.data_dir, args.label_map, args.outdir) for d in days]
    t0 = time.perf_counter()
    total = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for day, n, dt in ex.map(process_day, jobs):
            total += n
            print(f"  {day}: {n:>8} intervalos  ({dt:.0f}s)")
    print(f"\n{total} intervalos en {time.perf_counter()-t0:.0f}s -> {args.outdir}")


if __name__ == "__main__":
    main()
