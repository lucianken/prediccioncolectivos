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
    "time_since_start", "traj_flat", "traj_len", "fleet_flat", "n_fleet",
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
    ):
        import pyarrow.parquet as pq

        self._path = str(parquet_path)
        self._shape_lengths: dict[str, float] = shape_lengths or {}
        self._max_eta = max_eta_s
        self._shuffle = shuffle

        pf = pq.ParquetFile(self._path)
        self._n_groups: int = pf.metadata.num_row_groups
        self._approx_len: int = pf.metadata.num_rows
        schema_names = set(pf.schema_arrow.names)
        self._read_cols: list[str] = _BASE_COLS + [
            c for c in _OPTIONAL_COLS if c in schema_names
        ]

        logger.info(
            f"[ETADataset] {Path(parquet_path).name}: "
            f"{self._approx_len:,} rows, {self._n_groups} row groups"
        )

    def __len__(self) -> int:
        return self._approx_len

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

        mask  = (eta_arr > 0) & (dist_rem_arr > 0) & (dist_along_arr >= 0)
        valid = np.where(mask)[0]

        if self._shuffle:
            np.random.shuffle(valid)

        hour_sin_arr = df["hour_sin"].astype(np.float32)
        hour_cos_arr = df["hour_cos"].astype(np.float32)
        dow_arr      = df["dow"].astype(np.int64)
        has_bus_arr  = df["has_active_bus"].astype(np.float32)
        eta_clipped  = np.clip(eta_arr, 1.0, self._max_eta)

        tss_arr = df["time_since_start"].astype(np.float32) if "time_since_start" in df \
            else np.zeros(len(eta_arr), dtype=np.float32)

        ramal_ids    = df["ramal_id"]
        shape_lengths = self._shape_lengths

        # FixedSizeList → 2D numpy via flatten (contiguous float32 buffer, zero-copy)
        if "traj_flat" in df:
            traj_all = _fsl_to_numpy(tbl["traj_flat"], 30).reshape(-1, 10, 3)  # (N, 10, 3)
            traj_len_all = df["traj_len"].astype(np.int32)                      # (N,)
        else:
            traj_all = np.zeros((len(eta_arr), 10, 3), dtype=np.float32)
            traj_len_all = np.ones(len(eta_arr), dtype=np.int32)
            traj_all[:, 0, 0] = dist_along_arr
            traj_all[:, 0, 1] = df["speed_mps"].astype(np.float32)

        if "fleet_flat" in df:
            fleet_all = _fsl_to_numpy(tbl["fleet_flat"], N_FLEET * 5).reshape(-1, N_FLEET, 5)
            n_fleet_all = df["n_fleet"].astype(np.int32)
        else:
            fleet_all = np.zeros((len(eta_arr), N_FLEET, 5), dtype=np.float32)
            n_fleet_all = np.zeros(len(eta_arr), dtype=np.int32)

        # Máscaras vectorizadas (sin loop por fila)
        traj_mask_all  = np.arange(10)[None, :]      >= traj_len_all[:, None]   # (N, 10)
        fleet_mask_all = np.arange(N_FLEET)[None, :] >= n_fleet_all[:, None]    # (N, N_FLEET)

        logger.debug(
            f"[ETADataset] group {g_idx}: {len(valid)}/{len(eta_arr)} valid, "
            f"read {time.time()-t0:.2f}s"
        )

        for idx in valid:
            ramal_id  = ramal_ids[idx]
            dist_rem  = float(dist_rem_arr[idx])
            shape_len = max(shape_lengths.get(ramal_id, 1.0), 1.0)

            yield {
                "trajectory":          torch.from_numpy(traj_all[idx]),
                "trajectory_mask":     torch.from_numpy(traj_mask_all[idx]),
                "fleet":               torch.from_numpy(fleet_all[idx]),
                "fleet_mask":          torch.from_numpy(fleet_mask_all[idx]),
                "hour_sin":            torch.tensor([hour_sin_arr[idx]], dtype=torch.float32),
                "hour_cos":            torch.tensor([hour_cos_arr[idx]], dtype=torch.float32),
                "dow":                 torch.tensor([dow_arr[idx]],      dtype=torch.int64),
                "dist_remaining_m":    torch.tensor([dist_rem],          dtype=torch.float32),
                "dist_remaining_norm": torch.tensor([dist_rem / shape_len], dtype=torch.float32),
                "time_since_start":    torch.tensor([tss_arr[idx]],      dtype=torch.float32),
                "has_active_bus":      torch.tensor([has_bus_arr[idx]],  dtype=torch.float32),
                "eta_seconds":         torch.tensor([eta_clipped[idx]],  dtype=torch.float32),
            }


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
        "has_active_bus":      torch.stack([item["has_active_bus"]     for item in batch]),
        "eta_seconds":         torch.stack([item["eta_seconds"]        for item in batch]),
    }
