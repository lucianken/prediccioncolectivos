"""
Utilidades comunes de los diagnósticos A3 vs A1 (línea 39). Solo lectura: no toca modelos, pipeline ni datos.
Reusa prediccion.eval (métricas, predictores, buckets) y make_eval (filtro/estratificación por ETA).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from unittest import mock

import numpy as np

from prediccion.eval import (compute_metrics, load_eval_df, metrics_to_markdown, predict_a1, predict_a3,  # noqa: F401
                             _hours)
from prediccion.v2.make_eval import ETA_EDGES_S, MAX_ETA_S, eta_bucket, valid_mask
from prediccion.v2.shapes import DEFAULT_V2_DIR, REPO_ROOT

V2 = Path(DEFAULT_V2_DIR)
DIAG = V2 / "diag"
SHAPES_39 = REPO_ROOT.parent / "proyectoconsola" / "data" / "line_shapes" / "39.json"
A1_PKL = V2 / "models" / "a1_v1794415690.pkl"
A3_CKPTS = {"A3-K32": REPO_ROOT / "data/ml/v2_39_k32/models/eta_a3_best.pt",
            "A3-K64": REPO_ROOT / "data/ml/v2_39_k64/models/e1_k64.pt"}
TRAIN_PQ = REPO_ROOT / "data/ml/v2_39_k32/training/eta_train.parquet"
VAL_PQ = REPO_ROOT / "data/ml/v2_39_k32/training/eta_val.parquet"
EVAL_SEEN = V2 / "eval" / "eval_seen.parquet"
SEED = 20261111

EXTRA_COLS = ["shape_id", "ts_p", "dow", "hour_sin", "hour_cos"]
HOUR_BANDS = [("pico mañana 6-9", 6, 10), ("valle 10-15", 10, 16), ("pico tarde 16-19", 16, 20),
              ("noche 20-5", 20, 30)]


def shapes_meta() -> dict:
    with open(SHAPES_39, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for r in d["ramales"]:
        nm = r["name"]
        first = nm.split(":")[1].strip().split("→")[0].strip()
        out[str(r["shapeId"])] = {"name": nm, "short": r["shortName"],
                                  "sentido": "ida (Barracas→Chacarita)" if first == "Barracas" else "vuelta (Chacarita→Barracas)"}
    return out


def hour_band(hours: np.ndarray) -> np.ndarray:
    h = np.where(hours < 6, hours + 24, hours)
    out = np.empty(len(h), dtype=object)
    for name, lo, hi in HOUR_BANDS:
        out[(h >= lo) & (h < hi)] = name
    return out


def _read_pf_groups(path, groups, cols=None):
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    for g in groups:
        yield pf.read_row_group(g, columns=cols)


def make_stratified_sample(src: Path, dst: Path, n_per_bucket: int = 25_000, seed: int = SEED) -> Path:
    """~100k filas de `src` (solo 39), mismo filtro que la vara (valid_mask) y estratificadas por ETA real
    como eval_seen (n_per_bucket por bucket de 0-5, 5-10, 10-20, 20+ min)."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    if dst.exists():
        return dst
    pf = pq.ParquetFile(src)
    ng = pf.metadata.num_row_groups
    cap = math.ceil(3 * n_per_bucket / ng)
    rng = np.random.default_rng(seed)
    keep = {b: [] for b in range(len(ETA_EDGES_S) + 1)}
    for g in range(ng):
        t = pf.read_row_group(g)
        t = t.filter(pa.array(valid_mask(t)))
        bk = eta_bucket(np.asarray(t["observed_eta_s"]))
        keys = rng.random(len(t))
        for b in keep:
            idx = np.flatnonzero(bk == b)
            if len(idx) > cap:
                idx = idx[np.argpartition(keys[idx], cap - 1)[:cap]]
            if len(idx):
                keep[b].append((keys[idx], t.take(pa.array(idx))))
    parts = []
    for b, items in keep.items():
        k = np.concatenate([x for x, _ in items])
        tb = pa.concat_tables([x for _, x in items])
        order = np.sort(np.argsort(k, kind="stable")[:n_per_bucket])
        parts.append(tb.take(pa.array(order)))
    full = pa.concat_tables(parts)
    full = full.take(pa.array(np.argsort(np.asarray(full["ts_p"]), kind="stable")))
    dst.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(full, str(dst), row_group_size=100_000)
    return dst


def make_natural_sample(src: Path, dst: Path, per_group: int, seed: int = SEED) -> Path:
    """Muestra uniforme (distribución natural) con el filtro de ETADataset (la que ve el log de entrenamiento)."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    if dst.exists():
        return dst
    pf = pq.ParquetFile(src)
    rng = np.random.default_rng(seed)
    parts = []
    for g in range(pf.metadata.num_row_groups):
        t = pf.read_row_group(g)
        eta = np.asarray(t["observed_eta_s"], dtype=np.float32)
        dist = np.asarray(t["dist_remaining_m"], dtype=np.float32)
        nrm = np.asarray(t["dist_along_norm"], dtype=np.float32)
        ok = np.flatnonzero((eta > 0) & (dist >= 100.0) & (nrm >= 0) & (nrm <= 1.0))
        if len(ok) > per_group:
            ok = np.sort(rng.choice(ok, per_group, replace=False))
        parts.append(t.take(pa.array(ok)))
    pq.write_table(pa.concat_tables(parts), str(dst), row_group_size=100_000)
    return dst


def filter_eval_39(dst: Path) -> Path:
    """eval_seen restringido a la 39 (mismas filas y orden que `eval --lines 39`)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    if not dst.exists():
        t = pq.read_table(EVAL_SEEN)
        t = t.filter(pc.is_in(t["line"], value_set=pa.array(["39"])))
        pq.write_table(t, str(dst), row_group_size=100_000)
    return dst


def load_df(path: Path):
    import pyarrow.parquet as pq
    cols = ["line", "ramal_id", "dist_along_m", "dist_remaining_m", "speed_mps", "hour_sin", "hour_cos", "dow",
            "observed_eta_s", "shape_id", "ts_p", "dist_along_norm"]
    return pq.read_table(path, columns=cols).to_pandas()


def a3_predict(parquet: Path, n: int, ckpt: Path, dropout: bool = False) -> np.ndarray:
    """predict_a3 de eval.py. Con dropout=True deja el modelo en modo train (dropout activo) parcheando .eval()."""
    with open(V2 / "shape_lengths.json", encoding="utf-8") as f:
        lengths = json.load(f)
    sdn = Path(ckpt).resolve().parent.parent / "schedule_dev_medians.json"
    if dropout:
        import torch
        from prediccion.models.a3_eta import A3ETAModel
        torch.manual_seed(SEED)
        with mock.patch.object(A3ETAModel, "eval", lambda self, *a: self.train(True)):
            return predict_a3(parquet, ckpt, lengths, sdn, n)
    return predict_a3(parquet, ckpt, lengths, sdn, n)


def pinball(pred, true, dist_m):
    """Misma pérdida que trainer.train_phase3 (q 0,5 -> 0,8 bajo 1 km). Devuelve media."""
    pred = np.asarray(pred, np.float64)
    true = np.clip(np.asarray(true, np.float64), 1.0, 7200.0)
    q = 0.5 + 0.3 * np.clip(1.0 - np.asarray(dist_m, np.float64) / 1000.0, 0.0, 1.0)
    e = true - pred
    return np.where(e >= 0, q * e, (q - 1.0) * e)
