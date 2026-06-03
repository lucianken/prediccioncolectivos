"""
ETADataset — PyTorch IterableDataset para entrenar A3ETAModel.

Lee el parquet de entrenamiento de a un row group por vez para evitar
cargar los ~55 GB descomprimidos en RAM.

Columnas del parquet (schema nuevo con FixedSizeList — zero-copy via np.asarray):
  ramal_id             str
  seg_idx              int32
  dist_remaining_m     float32
  dist_along_norm      float32
  speed_mps            float32
  hour_sin / hour_cos  float32
  dow                  int8 (0=Lunes … 6=Domingo)
  has_active_bus       bool
  observed_eta_s       float32  (label)
  time_since_start     float32
  traj_flat            FixedSizeList<float32>[30]   — 10 puntos × 3 features, paddeado
  traj_len             int8     — longitud real (1–10)
  fleet_flat           FixedSizeList<float32>[N_FLEET*5] — paddeado con ceros
  n_fleet              int8     — vehículos reales en la flota

Tensores que devuelve cada item:
  trajectory           (10, 3)       float32
  trajectory_mask      (10,)         bool     True = padding
  fleet                (N_FLEET, 5)  float32
  fleet_mask           (N_FLEET,)    bool
  hour_sin / hour_cos  (1,)          float32
  dow                  (1,)          int64
  dist_remaining_m     (1,)          float32
  dist_remaining_norm  (1,)          float32
  time_since_start     (1,)          float32
  has_active_bus       (1,)          float32
  eta_seconds          (1,)          float32  (clampeado a max_eta_s)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import torch
from torch.utils.data import IterableDataset

logger = logging.getLogger(__name__)

from prediccion.pipeline.features import N_FLEET


def _fsl_to_numpy(col: Any, width: int) -> np.ndarray:
    """Convierte columna Arrow FixedSizeList a numpy (N, width) float32 via flatten."""
    combined = col.combine_chunks() if hasattr(col, "combine_chunks") else col
    return np.asarray(combined.flatten(), dtype=np.float32).reshape(-1, width)

_BASE_COLS = [
    "ramal_id", "dist_remaining_m", "dist_along_norm",
    "speed_mps", "hour_sin", "hour_cos", "dow",
    "has_active_bus", "observed_eta_s",
]
_OPTIONAL_COLS = [
    "time_since_start", "ts_age_s", "traj_flat", "traj_len", "fleet_flat", "n_fleet",
]


class ETADataset(IterableDataset):
    """
    Lee el parquet de entrenamiento ETA de a un row group por vez.

    Args:
        parquet_path: Path al eta_train.parquet o eta_val.parquet.
        shape_lengths: dict ramal_id → longitud en metros.
        max_eta_s: clamp superior del label (default 7200 s = 2 h).
        shuffle: si True, mezcla el orden de los row groups y las filas
                 dentro de cada grupo (recomendado para train, False para val).
    """

    def __init__(
        self,
        parquet_path: Path | str,
        shape_lengths: dict[str, float] | None = None,
        max_eta_s: float = 7200.0,
        ramal_ids: list[str] | None = None,
        shuffle: bool = True,
        yield_batch_size: int = 2048,
        use_fleet: bool = True,
        max_groups: int | None = None,
        fleet_same_dir_cap: int | None = None,
    ):
        import pyarrow.parquet as pq

        self._path = str(parquet_path)
        self._shape_lengths: dict[str, float] = shape_lengths or {}
        self._max_eta = max_eta_s
        self._shuffle = shuffle
        self._yield_batch_size = yield_batch_size
        self._use_fleet = use_fleet
        self._fleet_same_dir_cap = fleet_same_dir_cap  # si es int, filtra same_dir y capea

        pf = pq.ParquetFile(self._path)
        total_groups = pf.metadata.num_row_groups
        self._n_groups: int = min(total_groups, max_groups) if max_groups is not None else total_groups
        rows_per_group = pf.metadata.num_rows / total_groups if total_groups > 0 else 0
        self._approx_len: int = int(rows_per_group * self._n_groups)
        schema_names = set(pf.schema_arrow.names)
        skip = {"fleet_flat", "n_fleet"} if not use_fleet else set()
        self._read_cols: list[str] = _BASE_COLS + [
            c for c in _OPTIONAL_COLS if c in schema_names and c not in skip
        ]

        logger.info(
            f"[ETADataset] {Path(parquet_path).name}: "
            f"{self._approx_len:,} rows, {self._n_groups} row groups"
        )

    def __len__(self) -> int:
        import math
        return math.ceil(self._approx_len / self._yield_batch_size)

    @property
    def approx_batches(self) -> int:
        return len(self)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        import pyarrow.parquet as pq

        worker_info = torch.utils.data.get_worker_info()
        group_indices = list(range(self._n_groups))

        if worker_info is not None:
            # Distribuir row groups entre workers
            group_indices = group_indices[worker_info.id :: worker_info.num_workers]

        if self._shuffle:
            np.random.shuffle(group_indices)

        pf = pq.ParquetFile(self._path)
        for g_idx in group_indices:
            yield from self._iter_group(pf, g_idx)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _iter_group(self, pf: Any, g_idx: int) -> Iterator[dict[str, Any]]:
        t0 = time.time()
        tbl = pf.read_row_group(g_idx, columns=self._read_cols)

        # ramal_id es el único string; todo lo demás es escalar o FixedSizeList → np.asarray
        df: dict[str, Any] = {}
        for col in self._read_cols:
            if col == "ramal_id":
                df[col] = tbl[col].to_pylist()
            else:
                df[col] = np.asarray(tbl[col])

        eta_arr        = df["observed_eta_s"].astype(np.float32)
        dist_rem_arr   = df["dist_remaining_m"].astype(np.float32)
        dist_along_arr = df["dist_along_norm"].astype(np.float32)

        # dist_along_norm > 1.0 indica shape_length_m=1.0 fallback (ramal sin resolver)
        # → traj_flat contiene metros crudos en vez de 0-1, overflow en fp16
        # dist_rem < 100m: sub-100m no se predice — la app muestra "llegando". Ver ML plan §7.
        mask  = (eta_arr > 0) & (dist_rem_arr >= 100.0) & (dist_along_arr >= 0) & (dist_along_arr <= 1.0)
        valid = np.where(mask)[0]

        if self._shuffle:
            np.random.shuffle(valid)

        hour_sin_arr = df["hour_sin"].astype(np.float32)
        hour_cos_arr = df["hour_cos"].astype(np.float32)
        dow_arr      = df["dow"].astype(np.int64)
        has_bus_arr  = df["has_active_bus"].astype(np.float32)
        eta_clipped  = np.clip(eta_arr, 1.0, self._max_eta)

        tss_arr = (df["time_since_start"].astype(np.float32) / 3600.0) if "time_since_start" in df \
            else np.zeros(len(eta_arr), dtype=np.float32)  # normalizar a horas (0-3.3h)
        ts_age_arr = (df["ts_age_s"].astype(np.float32) / 600.0) if "ts_age_s" in df \
            else np.zeros(len(eta_arr), dtype=np.float32)  # normalizar a 0-1 (cap=600s)

        ramal_ids    = df["ramal_id"]
        shape_lengths = self._shape_lengths

        # FixedSizeList → 2D numpy via flatten (contiguous float32 buffer, zero-copy)
        if "traj_flat" in df:
            traj_all = _fsl_to_numpy(tbl["traj_flat"], 30).reshape(-1, 10, 3).copy()  # (N, 10, 3)
            traj_len_all = df["traj_len"].astype(np.int32)                      # (N,)
            # col 0 = dist_along_norm: historiales con shape_length=1 fallback → max 12756
            #         clipear a [0, 1]
            # col 1 = speed (0-30 m/s) → /30
            # col 2 = dt (0-1200 s)    → /30, luego clipear a [0, 5] (max 150s gap)
            np.clip(traj_all[:, :, 0], 0.0, 1.0, out=traj_all[:, :, 0])
            traj_all[:, :, 1] /= 30.0
            traj_all[:, :, 2] /= 30.0
            np.clip(traj_all[:, :, 2], 0.0, 5.0, out=traj_all[:, :, 2])
        else:
            traj_all = np.zeros((len(eta_arr), 10, 3), dtype=np.float32)
            traj_len_all = np.ones(len(eta_arr), dtype=np.int32)
            traj_all[:, 0, 0] = dist_along_arr
            traj_all[:, 0, 1] = df["speed_mps"].astype(np.float32)

        if "fleet_flat" in df:
            fleet_all = _fsl_to_numpy(tbl["fleet_flat"], N_FLEET * 5).reshape(-1, N_FLEET, 5).copy()
            n_fleet_all = df["n_fleet"].astype(np.int32)

            if self._fleet_same_dir_cap is not None:
                cap = self._fleet_same_dir_cap
                # col 4 = is_same_direction. Ordenar same_dir (1.0) primero, luego tomar cap primeros.
                # argsort descendente por col4: los 1.0 quedan al principio, los 0.0 (opuesto + padding) al final
                order = np.argsort(-fleet_all[:, :, 4], axis=1)          # (N, N_FLEET)
                fleet_all = fleet_all[np.arange(len(fleet_all))[:, None], order, :][:, :cap, :].copy()
                n_fleet_all = np.minimum((fleet_all[:, :, 4] == 1.0).sum(axis=1).astype(np.int32), cap)
        else:
            # use_fleet=False: shape (N, 0, 5) activa el branch n_fleet==0 en FleetEncoder
            # y evita que el transformer procese 60 tokens de padding por nada
            fleet_all = np.zeros((len(eta_arr), 0, 5), dtype=np.float32)
            n_fleet_all = np.zeros(len(eta_arr), dtype=np.int32)

        # Limpiar cualquier NaN/inf residual antes de mandar a la GPU
        np.nan_to_num(traj_all,  nan=0.0, posinf=0.0, neginf=0.0, copy=False)
        np.nan_to_num(fleet_all, nan=0.0, posinf=0.0, neginf=0.0, copy=False)

        # Máscaras vectorizadas (sin loop por fila)
        traj_mask_all  = np.arange(10)[None, :]                >= traj_len_all[:, None]  # (N, 10)
        actual_fleet_dim = fleet_all.shape[1]  # 0 cuando use_fleet=False, N_FLEET cuando True
        fleet_mask_all = np.arange(actual_fleet_dim)[None, :] >= n_fleet_all[:, None]    # (N, fleet_dim)

        logger.debug(
            f"[ETADataset] group {g_idx}: {len(valid)}/{len(eta_arr)} valid, "
            f"read {time.time()-t0:.2f}s"
        )

        # Pre-compute shape_len_arr for all rows (vectorized, not per-sample lookup)
        shape_len_arr = np.array([
            max(shape_lengths.get(ramal_ids[i], 1.0), 1.0)
            for i in range(len(eta_arr))
        ], dtype=np.float32)

        # Batch-level yields (FAST) instead of per-sample loop (SLOW)
        B = self._yield_batch_size
        for start in range(0, len(valid), B):
            sl = valid[start:start + B]
            yield {
                "trajectory":      torch.from_numpy(np.ascontiguousarray(traj_all[sl])),       # (b, 10, 3)
                "trajectory_mask": torch.from_numpy(np.ascontiguousarray(traj_mask_all[sl])),  # (b, 10)
                "fleet":           torch.from_numpy(np.ascontiguousarray(fleet_all[sl])),      # (b, N_FLEET, 5)
                "fleet_mask":      torch.from_numpy(np.ascontiguousarray(fleet_mask_all[sl])), # (b, N_FLEET)
                "hour_sin":        torch.from_numpy(np.ascontiguousarray(hour_sin_arr[sl, None])),  # (b, 1)
                "hour_cos":        torch.from_numpy(np.ascontiguousarray(hour_cos_arr[sl, None])),  # (b, 1)
                "dow":             torch.from_numpy(np.ascontiguousarray(dow_arr[sl, None])),        # (b, 1)
                "dist_remaining_m":    torch.from_numpy(np.ascontiguousarray(dist_rem_arr[sl, None])),   # (b, 1)
                "dist_remaining_norm": torch.from_numpy(np.ascontiguousarray((dist_rem_arr[sl] / shape_len_arr[sl])[:, None])),  # (b, 1)
                "time_since_start":    torch.from_numpy(np.ascontiguousarray(tss_arr[sl, None])),        # (b, 1)
                "ts_age_s":            torch.from_numpy(np.ascontiguousarray(ts_age_arr[sl, None])),     # (b, 1)
                "has_active_bus":      torch.from_numpy(np.ascontiguousarray(has_bus_arr[sl, None])),    # (b, 1)
                "eta_seconds":         torch.from_numpy(np.ascontiguousarray(eta_clipped[sl, None])),    # (b, 1)
            }


def collate_identity(batch: list[dict]) -> dict[str, torch.Tensor]:
    """Collate para cuando el dataset ya emite batches completos (batch_size=1 en DataLoader)."""
    return batch[0]


def collate_eta(batch: list[dict]) -> dict[str, torch.Tensor]:
    """
    Collate function para DataLoader.
    Con dimensiones fijas (10 puntos traj, 20 fleet) el padding no hace nada,
    pero el código es correcto para cualquier longitud variable también.
    """
    from torch.nn.utils.rnn import pad_sequence

    trajs      = [item["trajectory"]      for item in batch]
    traj_masks = [item["trajectory_mask"] for item in batch]
    traj_padded      = pad_sequence(trajs,      batch_first=True)
    traj_mask_padded = pad_sequence(traj_masks, batch_first=True, padding_value=True)

    fleets      = [item["fleet"]      for item in batch]
    fleet_masks = [item["fleet_mask"] for item in batch]
    max_fleet = max(f.shape[0] for f in fleets)

    if max_fleet == 0:
        fleet_padded      = torch.zeros(len(batch), 0, 5)
        fleet_mask_padded = torch.zeros(len(batch), 0, dtype=torch.bool)
    else:
        fleet_padded      = pad_sequence(fleets,      batch_first=True)
        fleet_mask_padded = pad_sequence(fleet_masks, batch_first=True, padding_value=True)

    return {
        "trajectory":          traj_padded,
        "trajectory_mask":     traj_mask_padded,
        "fleet":               fleet_padded,
        "fleet_mask":          fleet_mask_padded,
        "hour_sin":            torch.stack([item["hour_sin"]            for item in batch]),
        "hour_cos":            torch.stack([item["hour_cos"]            for item in batch]),
        "dow":                 torch.stack([item["dow"]                 for item in batch]),
        "dist_remaining_m":    torch.stack([item["dist_remaining_m"]   for item in batch]),
        "dist_remaining_norm": torch.stack([item["dist_remaining_norm"] for item in batch]),
        "time_since_start":    torch.stack([item["time_since_start"]   for item in batch]),
        "ts_age_s":            torch.stack([item["ts_age_s"]           for item in batch]),
        "has_active_bus":      torch.stack([item["has_active_bus"]     for item in batch]),
        "eta_seconds":         torch.stack([item["eta_seconds"]        for item in batch]),
    }
