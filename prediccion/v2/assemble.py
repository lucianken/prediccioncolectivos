"""
assemble_dataset(): concatena daily/*.parquet en training/eta_train.parquet y training/eta_val.parquet.

Split (ARQUITECTURA.md §5), por fecha del día procesado:
  val   = VAL_START .. VAL_END (2026-09-15 .. 2026-10-14), solo líneas de train
  train = todo lo anterior a VAL_START, sin EXCLUDED_DAYS, solo líneas de train
  Las líneas heldout NUNCA entran a train ni a eta_val (se usan solo en eval_heldout).
  Días >= 2026-10-15 (día incompleto y hueco de la API CABA) no se usan.

También escribe, para que el trainer existente (ml_dir=data/ml/v2) funcione sin cambios de formato:
  shape_lengths.json            {shape_id: largo_m} de todas las líneas train+heldout (mismo largo con que se normaliza)
  schedule_dev_medians.json     medianas time_since_start por (shape_id, bucket) calculadas SOLO con train
  assembled.json                resumen (filas por línea / split)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import red

VAL_START = "2026-09-15"
VAL_END = "2026-10-14"


def load_lines_file(path: Path | str) -> dict:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {"train": [str(x) for x in d["train"]], "heldout": [str(x) for x in d.get("heldout", [])]}


def split_days(days, val_start: str = VAL_START, val_end: str = VAL_END, excluded=()) -> tuple[list[str], list[str]]:
    """Devuelve (train_days, val_days) ordenados. Ningún día cae en ambos."""
    excluded = set(excluded)
    days = sorted(d for d in days if d not in excluded)
    train = [d for d in days if d < val_start]
    val = [d for d in days if val_start <= d <= val_end]
    return train, val


def _write_filtered(days: list[str], daily_dir: Path, lines: set[str], out_path: Path,
                    sample_frac: float | None = None, seed: int = 0) -> dict[str, int]:
    """sample_frac (0-1): se queda con esa fracción de las filas, al azar con semilla fija por día (reproducible)."""
    import numpy as np
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    tmp = out_path.with_name(out_path.name + ".tmp")
    writer = None
    counts: dict[str, int] = {}
    line_arr = pa.array(sorted(lines))
    for day in days:
        p = daily_dir / f"{day}.parquet"
        if not p.exists():
            continue
        tbl = pq.read_table(p)
        tbl = tbl.filter(pc.is_in(tbl["line"], value_set=line_arr))
        if len(tbl) == 0:
            continue
        if sample_frac is not None and sample_frac < 1.0:
            rng = np.random.default_rng([seed, int(day.replace("-", ""))])
            tbl = tbl.filter(pa.array(rng.random(len(tbl)) < sample_frac))
            if len(tbl) == 0:
                continue
        if writer is None:
            writer = pq.ParquetWriter(str(tmp), tbl.schema)
        writer.write_table(tbl, row_group_size=250_000)
        for ln, n in zip(*[c.to_pylist() for c in pc.value_counts(tbl["line"]).flatten()]):
            counts[ln] = counts.get(ln, 0) + n
    if writer is not None:
        writer.close()
        os.replace(tmp, out_path)
    else:
        Path(tmp).unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)
    return counts


def assemble_dataset(
    v2_dir: Path | str,
    lines_file: Path | str,
    *,
    val_start: str = VAL_START,
    val_end: str = VAL_END,
    excluded=None,
    shapes_dir=None,
    sdn: bool = True,
    dest_dir: Path | str | None = None,
    only_lines=None,
    train_start: str | None = None,
    val_sample_frac: float | None = None,
    val_seed: int = 20261112,
) -> dict:
    from prediccion.pipeline.build_dataset import EXCLUDED_DAYS
    from prediccion.v2.day import read_meta
    from prediccion.v2.shapes import LineShapes, DEFAULT_LINE_SHAPES_DIR

    v2_dir = Path(v2_dir)
    daily = v2_dir / "daily"
    dest = Path(dest_dir) if dest_dir else v2_dir          # p.ej. data/ml/v2/e1_39 para experimentos con subconjunto
    train_dir = dest / "training"
    train_dir.mkdir(parents=True, exist_ok=True)
    lf = load_lines_file(lines_file)
    train_lines, heldout = set(lf["train"]), set(lf["heldout"])
    if only_lines:
        unknown = set(map(str, only_lines)) - train_lines
        if unknown:
            raise ValueError(f"--only-lines fuera de la lista train: {sorted(unknown)}")
        train_lines = set(map(str, only_lines))
    if train_lines & heldout:
        raise ValueError(f"líneas en train y heldout a la vez: {sorted(train_lines & heldout)}")
    excluded = set(EXCLUDED_DAYS if excluded is None else excluded)

    days = []
    for p in sorted(daily.glob("*.meta.json")):
        d = p.name[:10]
        m = read_meta(v2_dir, d)
        if m and not m.get("include_fleet") is None:
            days.append(d)
    train_days, val_days = split_days(days, val_start, val_end, excluded)
    if train_start is not None:
        # ventana de train acotada (subconjunto de iteración, ARQUITECTURA §6.2.2): solo días >= train_start.
        # Sigue siendo < val_start, así que no se superpone con la validación.
        train_days = [d for d in train_days if d >= train_start]

    c_train = _write_filtered(train_days, daily, train_lines, train_dir / "eta_train.parquet")
    c_val = _write_filtered(val_days, daily, train_lines, train_dir / "eta_val.parquet",
                         sample_frac=val_sample_frac, seed=val_seed)

    shapes = LineShapes(shapes_dir or DEFAULT_LINE_SHAPES_DIR)
    lengths = shapes.lengths(sorted(train_lines | heldout))
    with open(dest / "shape_lengths.json", "w", encoding="utf-8") as f:
        json.dump(lengths, f)

    if sdn and (train_dir / "eta_train.parquet").exists():
        from prediccion.pipeline.build_schedule_dev_table import build_medians
        build_medians(train_dir / "eta_train.parquet", dest / "schedule_dev_medians.json", force=True)

    summary = {
        "val_window": [val_start, val_end], "n_train_days": len(train_days), "n_val_days": len(val_days),
        "train_days": [train_days[0], train_days[-1]] if train_days else None,
        "val_days": [val_days[0], val_days[-1]] if val_days else None,
        "rows_train": sum(c_train.values()), "rows_val": sum(c_val.values()),
        "rows_train_by_line": c_train, "rows_val_by_line": c_val,
        "train_lines": sorted(train_lines, key=int), "heldout_lines": sorted(heldout, key=int),
        # versión de `red` (bondi/red) de este ensamblado y de los días usados (None = día armado antes de importar red)
        "red_version": red.__version__,
        "red_versions_dias": sorted({str((read_meta(v2_dir, d) or {}).get("red_version")) for d in train_days + val_days}),
    }
    with open(dest / "assembled.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    return summary


def main(argv=None):
    import argparse
    from prediccion.v2.shapes import DEFAULT_V2_DIR
    ap = argparse.ArgumentParser(description="Re-ensambla training/eta_train|eta_val desde daily/ (barato, sin releer NDJSON)")
    ap.add_argument("--v2-dir", type=Path, default=DEFAULT_V2_DIR)
    ap.add_argument("--lines-file", type=Path, default=None, help="default: <v2-dir>/lines.json")
    ap.add_argument("--only-lines", default=None, help="entrenar con un subconjunto de las líneas train (p.ej. 39)")
    ap.add_argument("--dest", type=Path, default=None, help="directorio de salida (default: --v2-dir)")
    ap.add_argument("--train-start", default=None, help="primer día de train (ventana acotada); default: todo el período")
    ap.add_argument("--val-sample-frac", type=float, default=None,
                    help="fracción de filas de val que se conserva (muestra reproducible); default: todas")
    ap.add_argument("--val-start", default=VAL_START)
    ap.add_argument("--val-end", default=VAL_END)
    a = ap.parse_args(argv)
    s = assemble_dataset(a.v2_dir, a.lines_file or a.v2_dir / "lines.json", val_start=a.val_start, val_end=a.val_end,
                         dest_dir=a.dest, only_lines=a.only_lines.split(",") if a.only_lines else None,
                         train_start=a.train_start, val_sample_frac=a.val_sample_frac)
    print(f"train {s['rows_train']:,} filas ({s['n_train_days']} días), val {s['rows_val']:,} filas ({s['n_val_days']} días)")


if __name__ == "__main__":
    main()
