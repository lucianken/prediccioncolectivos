"""
CLI del pipeline v2.

  python -m prediccion.v2.build --lines-file data/ml/v2/lines.json --days 2026-03-28:2026-10-14 \
      --pairs-per-trip 64 --workers 6

- Procesa train + heldout de lines.json (o --lines 39,26 para un subconjunto; las heldout siguen
  excluidas del train en assemble).
- Paralelo por día: los días se reparten en chunks de días consecutivos (--chunk-days, default 7); dentro de
  un chunk se procesan en orden, así cada día usa el carry del anterior. El primer día de cada chunk usa el
  carry del día previo solo si ya existe (se registra como carry_in en el manifest).
- Reanudable/idempotente: un día cuyo meta cubre las líneas pedidas se saltea. Agregar una línea reprocesa
  solo los días que no la tienen.
- Al terminar corre assemble_dataset() (desactivable con --no-assemble).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date as _date, timedelta
from pathlib import Path

from prediccion.pipeline.build_dataset import EXCLUDED_DAYS
from prediccion.pipeline.shapes_io import load_label_line_data
from prediccion.v2.assemble import VAL_END, VAL_START, assemble_dataset, load_lines_file
from prediccion.v2.day import process_day, update_manifest
from prediccion.v2.shapes import (DEFAULT_DATA_DIR, DEFAULT_LABEL_MAP, DEFAULT_LINE_SHAPES_DIR,
                                  DEFAULT_V2_DIR, LineShapes)


def parse_days(spec: str) -> list[str]:
    """'2026-03-28:2026-10-14' (rango inclusivo) o lista 'a,b,c'."""
    out: list[str] = []
    for part in spec.split(","):
        if ":" in part:
            a, b = (_date.fromisoformat(x) for x in part.split(":"))
            d = a
            while d <= b:
                out.append(d.isoformat())
                d += timedelta(days=1)
        else:
            out.append(_date.fromisoformat(part).isoformat())
    return sorted(set(out))


def available_days(days: list[str], data_dir: Path, excluded=EXCLUDED_DAYS) -> list[str]:
    today = _date.today().isoformat()
    return [d for d in days if d != today and d not in excluded and (data_dir / f"{d}.ndjson.gz").exists()]


def set_low_priority() -> None:
    """Prioridad baja del proceso (Windows: BELOW_NORMAL_PRIORITY_CLASS), para no pelear con otros trabajos."""
    try:
        import psutil
        p = psutil.Process()
        if sys.platform == "win32":
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            p.nice(10)
    except Exception:
        pass


def _run_chunk(args):
    days, lines, kw = args
    if kw.get("low_priority"):
        set_low_priority()
    shapes = LineShapes(kw["shapes_dir"])
    label_data = load_label_line_data(kw["label_map"])
    out = []
    for d in days:
        try:
            m = process_day(d, lines, data_dir=Path(kw["data_dir"]), out_dir=Path(kw["out_dir"]), shapes=shapes,
                            label_data=label_data, k_pairs=kw["k_pairs"], include_fleet=kw["include_fleet"],
                            force=kw["force"], segmentation=kw["segmentation"])
            out.append((d, m.get("status"), m["n_rows"], m["n_trips"], m["elapsed_s"], m["carry_in"], None))
        except Exception as exc:  # no tirar el build entero por un día corrupto
            out.append((d, "error", 0, 0, 0.0, False, f"{type(exc).__name__}: {exc}"))
    return out


def run_build(days: list[str], lines: list[str], *, data_dir, out_dir, shapes_dir, label_map, k_pairs: int,
              workers: int, include_fleet: bool = False, force: bool = False, chunk_days: int = 7,
              segmentation: str = "geo", low_priority: bool = False) -> dict:
    chunks = [days[i:i + chunk_days] for i in range(0, len(days), chunk_days)]
    kw = dict(data_dir=str(data_dir), out_dir=str(out_dir), shapes_dir=str(shapes_dir), label_map=str(label_map),
              k_pairs=k_pairs, include_fleet=include_fleet, force=force, segmentation=segmentation,
              low_priority=low_priority)
    jobs = [(c, lines, kw) for c in chunks]
    total = len(days)
    done = 0
    stats = {"processed": 0, "skipped": 0, "error": 0, "rows": 0}
    t0 = time.time()

    def report(results):
        nonlocal done
        for d, status, rows, trips, el, carry_in, err in results:
            done += 1
            stats[status] = stats.get(status, 0) + 1
            if status == "processed":
                stats["rows"] += rows
            elapsed = time.time() - t0
            eta = elapsed / done * (total - done) if done else 0
            extra = f" ERROR {err}" if err else ""
            print(f"[{done}/{total}] {d} {status:9s} filas={rows:>9,} viajes={trips:>6,} "
                  f"({el:.0f}s{'' if carry_in else ', sin carry'}) | transcurrido {elapsed/60:.1f} min, "
                  f"resta ~{eta/60:.1f} min{extra}", flush=True)

    if workers <= 1:
        for j in jobs:
            report(_run_chunk(j))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_run_chunk, j) for j in jobs]
            for fu in as_completed(futs):
                report(fu.result())
    update_manifest(Path(out_dir))
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lines-file", type=Path, default=DEFAULT_V2_DIR / "lines.json")
    ap.add_argument("--lines", default=None, help="subconjunto de líneas (coma); default: train+heldout del lines-file")
    ap.add_argument("--days", required=True, help="rango 'A:B' inclusivo o lista 'a,b,c'")
    ap.add_argument("--pairs-per-trip", type=int, default=32)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--chunk-days", type=int, default=7)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_V2_DIR)
    ap.add_argument("--shapes-dir", type=Path, default=DEFAULT_LINE_SHAPES_DIR)
    ap.add_argument("--label-map", type=Path, default=DEFAULT_LABEL_MAP)
    ap.add_argument("--include-fleet", action="store_true", help="agrega fleet_flat/n_fleet (apagado por defecto)")
    ap.add_argument("--segmentation", choices=["geo", "geo2"], default="geo",
                    help="geo = segmentador v2 de siempre (default); geo2 = v2b: une huecos, arranca al salir de "
                         "cabecera, columna start_unknown y daily/*.waiting.parquet")
    ap.add_argument("--low-priority", action="store_true", help="procesos en prioridad baja (BELOW_NORMAL)")
    ap.add_argument("--force", action="store_true", help="reprocesa aunque el día ya esté hecho")
    ap.add_argument("--no-assemble", action="store_true")
    ap.add_argument("--val-start", default=VAL_START)
    ap.add_argument("--val-end", default=VAL_END)
    a = ap.parse_args(argv)

    lf = load_lines_file(a.lines_file)
    lines = a.lines.split(",") if a.lines else sorted(set(lf["train"]) | set(lf["heldout"]), key=int)
    days = available_days(parse_days(a.days), a.data_dir)
    if not days:
        print("ERROR: ningún día con archivo en", a.data_dir, file=sys.stderr)
        return 1
    if a.low_priority:
        set_low_priority()
    print(f"v2 build: segmentación={a.segmentation}, {len(lines)} líneas, {len(days)} días ({days[0]} .. {days[-1]}), K={a.pairs_per_trip}, "
          f"workers={a.workers}, out={a.out_dir}", flush=True)

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        stats = run_build(days, lines, data_dir=a.data_dir, out_dir=a.out_dir, shapes_dir=a.shapes_dir,
                          label_map=a.label_map, k_pairs=a.pairs_per_trip, workers=a.workers,
                          include_fleet=a.include_fleet, force=a.force, chunk_days=a.chunk_days,
                          segmentation=a.segmentation, low_priority=a.low_priority)
    finally:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    print(f"build: {stats}", flush=True)
    if stats.get("error"):
        print("WARN: hubo días con error; reintentar el mismo comando (reanuda).", file=sys.stderr)
    if not a.no_assemble:
        summary = assemble_dataset(a.out_dir, a.lines_file, val_start=a.val_start, val_end=a.val_end,
                                   shapes_dir=a.shapes_dir)
        print(f"assemble: train {summary['rows_train']:,} filas ({summary['n_train_days']} días), "
              f"val {summary['rows_val']:,} filas ({summary['n_val_days']} días)", flush=True)
    return 1 if stats.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
