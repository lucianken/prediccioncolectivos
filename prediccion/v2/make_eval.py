"""
Genera los conjuntos de evaluación CONGELADOS (ARQUITECTURA.md §5):

  data/ml/v2/eval/eval_seen.parquet     líneas de train, período de validación
  data/ml/v2/eval/eval_heldout.parquet  líneas de control (nunca entran al train), mismo período
  data/ml/v2/eval/eval_meta.json        semilla, tamaños, ventana, líneas

Cada fila es una consulta (coche en P a tiempo t, punto objetivo F adelante en el mismo viaje) con el ETA
real observado; salen de los daily parquets del período de validación. Muestreo estratificado por ETA real
(0-5, 5-10, 10-20, 20+ min): `--n-per-bucket` filas por bucket y por conjunto, uniforme dentro del bucket.
Si los archivos ya existen NO se regeneran salvo con --force (la vara tiene que ser única y estable).

  python -m prediccion.v2.make_eval [--n-per-bucket 25000] [--seed 20261110] [--force]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

from prediccion.v2.assemble import VAL_END, VAL_START, load_lines_file, split_days
from prediccion.v2.shapes import DEFAULT_V2_DIR

ETA_EDGES_S = (300.0, 600.0, 1200.0)   # buckets: <5, 5-10, 10-20, 20+ min
MAX_ETA_S = 7200.0
DEFAULT_SEED = 20261110


def eta_bucket(eta_s: np.ndarray) -> np.ndarray:
    return np.searchsorted(np.asarray(ETA_EDGES_S), eta_s, side="right")


def valid_mask(tbl) -> np.ndarray:
    """Mismo filtro que ETADataset (así todos los modelos ven exactamente las mismas filas)."""
    eta = np.asarray(tbl["observed_eta_s"], dtype=np.float32)
    dist = np.asarray(tbl["dist_remaining_m"], dtype=np.float32)
    norm = np.asarray(tbl["dist_along_norm"], dtype=np.float32)
    return (eta > 0) & (eta <= MAX_ETA_S) & (dist >= 100.0) & (norm >= 0) & (norm <= 1.0)


def make_eval(v2_dir: Path, lines_file: Path, n_per_bucket: int = 25_000, seed: int = DEFAULT_SEED,
              force: bool = False, val_start: str = VAL_START, val_end: str = VAL_END, excluded=None) -> dict:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    from prediccion.pipeline.build_dataset import EXCLUDED_DAYS

    v2_dir = Path(v2_dir)
    eval_dir = v2_dir / "eval"
    out = {"seen": eval_dir / "eval_seen.parquet", "heldout": eval_dir / "eval_heldout.parquet"}
    if all(p.exists() for p in out.values()) and not force:
        print("eval_seen/eval_heldout ya existen: no se regeneran (usar --force).")
        with open(eval_dir / "eval_meta.json", encoding="utf-8") as f:
            return json.load(f)
    eval_dir.mkdir(parents=True, exist_ok=True)

    lf = load_lines_file(lines_file)
    sets = {"seen": set(lf["train"]), "heldout": set(lf["heldout"])}
    days = [p.name[:10] for p in sorted((v2_dir / "daily").glob("*.meta.json"))]
    _, val_days = split_days(days, val_start, val_end, EXCLUDED_DAYS if excluded is None else excluded)
    if not val_days:
        raise RuntimeError(f"no hay días de validación procesados en {v2_dir / 'daily'}")

    n_days = len(val_days)
    cap_day = math.ceil(3 * n_per_bucket / n_days)     # por día, set y bucket; luego se recorta a n_per_bucket
    n_buckets = len(ETA_EDGES_S) + 1
    keep: dict[tuple[str, int], list] = {(s, b): [] for s in sets for b in range(n_buckets)}  # (keys, table)

    for di, day in enumerate(val_days):
        tbl = pq.read_table(v2_dir / "daily" / f"{day}.parquet")
        if "fleet_flat" in tbl.column_names:
            tbl = tbl.drop(["fleet_flat", "n_fleet"])
        tbl = tbl.filter(pa.array(valid_mask(tbl)))
        if len(tbl) == 0:
            continue
        rng = np.random.default_rng([seed, di])
        keys = rng.random(len(tbl))
        bucket = eta_bucket(np.asarray(tbl["observed_eta_s"]))
        lines_col = np.asarray(tbl["line"].to_pylist(), dtype=object)
        for sname, lset in sets.items():
            in_set = np.isin(lines_col, list(lset))
            for b in range(n_buckets):
                idx = np.flatnonzero(in_set & (bucket == b))
                if len(idx) > cap_day:
                    idx = idx[np.argpartition(keys[idx], cap_day - 1)[:cap_day]]
                if len(idx):
                    keep[(sname, b)].append((keys[idx], tbl.take(pa.array(idx))))

    meta = {"seed": seed, "n_per_bucket": n_per_bucket, "val_window": [val_start, val_end], "val_days": val_days,
            "eta_edges_s": list(ETA_EDGES_S), "train_lines": lf["train"], "heldout_lines": lf["heldout"],
            "created": time.strftime("%Y-%m-%d %H:%M:%S"), "counts": {}}
    for sname, path in out.items():
        parts = []
        for b in range(n_buckets):
            items = keep[(sname, b)]
            if not items:
                meta["counts"][f"{sname}/eta_bucket{b}"] = 0
                continue
            keys = np.concatenate([k for k, _ in items])
            t = pa.concat_tables([t for _, t in items])
            order = np.argsort(keys, kind="stable")[:n_per_bucket]
            parts.append(t.take(pa.array(np.sort(order))))
            meta["counts"][f"{sname}/eta_bucket{b}"] = len(order)
        if not parts:
            continue
        full = pa.concat_tables(parts)
        # orden fijo y reproducible: por ts_p
        full = full.take(pa.array(np.argsort(np.asarray(full["ts_p"]), kind="stable")))
        tmp = path.with_name(path.name + ".tmp")
        pq.write_table(full, str(tmp), row_group_size=100_000)
        os.replace(tmp, path)
        meta["counts"][f"{sname}/total"] = len(full)
    with open(eval_dir / "eval_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--v2-dir", type=Path, default=DEFAULT_V2_DIR)
    ap.add_argument("--lines-file", type=Path, default=None, help="default: <v2-dir>/lines.json")
    ap.add_argument("--n-per-bucket", type=int, default=25_000)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--val-start", default=VAL_START)
    ap.add_argument("--val-end", default=VAL_END)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    meta = make_eval(a.v2_dir, a.lines_file or a.v2_dir / "lines.json", a.n_per_bucket, a.seed, a.force,
                     a.val_start, a.val_end)
    print(json.dumps(meta["counts"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
