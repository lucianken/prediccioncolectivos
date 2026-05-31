"""
ETADataset — PyTorch Dataset para entrenar A3ETAModel.

Formato del parquet (columnas de ETATrainingRow):
  ramal_id        str
  seg_idx         int
  dist_remaining_m  float
  dist_along_norm   float   (posición actual / largo del shape)
  speed_mps         float
  hour_sin          float
  hour_cos          float
  dow               int     (0=Lunes … 6=Domingo)
  has_active_bus    bool
  observed_eta_s    float   (label)

Tensores que entrega __getitem__:
  trajectory        (1, 3)   [dist_along_norm, speed_mps, dt=0]  — 1 punto
  trajectory_mask   (1,)     [False]                             — no hay padding
  fleet             (0, 5)   tensor vacío                        — sin fleet en MVP
  fleet_mask        (0,)     tensor vacío
  hour_sin          (1,)
  hour_cos          (1,)
  dow               ()       int64
  dist_remaining_norm (1,)   dist_remaining_m / shape_length_m
  time_since_start  (1,)     0.0 (no disponible en el dataset plano)
  has_active_bus    (1,)     float
  eta_seconds       (1,)     label

NOTA: dist_remaining_norm usa shape_length_m por ramal_id.
  Si el shape_length no está disponible, cae a 1.0 (dist_remaining_m sin normalizar).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset


class ETADataset(Dataset):
    """
    Dataset que lee el parquet de entrenamiento ETA y expone tensores
    listos para A3ETAModel.

    Args:
        parquet_path: Path al eta_train.parquet o eta_val.parquet.
        shape_lengths: dict ramal_id → longitud en metros del shape.
                       Usado para normalizar dist_remaining_m.
                       Si None o ramal no presente → normalización = 1.0 (metros crudos).
        max_eta_s: clamp superior del label (default 7200s = 2h).
        ramal_ids: lista ordenada de ramal_ids conocidos (para construir el embedding index).
                   Si None se infiere del parquet.
    """

    def __init__(
        self,
        parquet_path: Path | str,
        shape_lengths: dict[str, float] | None = None,
        max_eta_s: float = 7200.0,
        ramal_ids: list[str] | None = None,
    ):
        import pyarrow.parquet as pq

        self._max_eta = max_eta_s
        self._shape_lengths: dict[str, float] = shape_lengths or {}

        tbl = pq.read_table(
            str(parquet_path),
            columns=[
                "ramal_id", "dist_remaining_m", "dist_along_norm",
                "speed_mps", "hour_sin", "hour_cos", "dow",
                "has_active_bus", "observed_eta_s",
            ] + [
                c for c in ["time_since_start", "traj_dist", "traj_speed", "traj_dt", "fleet_features_flat", "n_fleet"]
                if c in pq.read_metadata(str(parquet_path)).schema.names
            ],
        )
        df = tbl.to_pydict()

        # Filtrar filas inválidas
        n = len(df["observed_eta_s"])
        mask = [
            df["observed_eta_s"][i] > 0
            and df["dist_remaining_m"][i] > 0
            and df["dist_along_norm"][i] >= 0
            for i in range(n)
        ]
        valid = [i for i, ok in enumerate(mask) if ok]

        self._ramal_id:        list[str]   = [df["ramal_id"][i]        for i in valid]
        self._dist_remaining:  np.ndarray  = np.array([df["dist_remaining_m"][i]  for i in valid], dtype=np.float32)
        self._dist_along_norm: np.ndarray  = np.array([df["dist_along_norm"][i]   for i in valid], dtype=np.float32)
        self._speed_mps:       np.ndarray  = np.array([df["speed_mps"][i]         for i in valid], dtype=np.float32)
        self._hour_sin:        np.ndarray  = np.array([df["hour_sin"][i]           for i in valid], dtype=np.float32)
        self._hour_cos:        np.ndarray  = np.array([df["hour_cos"][i]           for i in valid], dtype=np.float32)
        self._dow:             np.ndarray  = np.array([df["dow"][i]                for i in valid], dtype=np.int64)
        self._has_bus:         np.ndarray  = np.array([float(df["has_active_bus"][i]) for i in valid], dtype=np.float32)
        self._eta_s:           np.ndarray  = np.clip(
            np.array([df["observed_eta_s"][i] for i in valid], dtype=np.float32),
            1.0, max_eta_s,
        )

        # Normalizar dist_remaining por shape_length del ramal
        self._dist_remaining_norm: np.ndarray = np.array([
            self._dist_remaining[j] / max(self._shape_lengths.get(self._ramal_id[j], 1.0), 1.0)
            for j in range(len(valid))
        ], dtype=np.float32)

        # Extraer variables extendidas con defaults para compatibilidad hacia atrás
        time_since_start_list = df.get("time_since_start", [0.0] * n)
        traj_dist_list = df.get("traj_dist", [[df["dist_along_norm"][i]] for i in range(n)])
        traj_speed_list = df.get("traj_speed", [[df["speed_mps"][i]] for i in range(n)])
        traj_dt_list = df.get("traj_dt", [[0.0] for i in range(n)])
        fleet_flat_list = df.get("fleet_features_flat", [[] for i in range(n)])
        n_fleet_list = df.get("n_fleet", [0] * n)

        self._time_since_start = np.array([float(time_since_start_list[i]) for i in valid], dtype=np.float32)

        # Pre-convertir arrays de NumPy a tensores PyTorch de una vez para evitar alocaciones repetidas
        self._hour_sin_t = torch.from_numpy(self._hour_sin)
        self._hour_cos_t = torch.from_numpy(self._hour_cos)
        self._dow_t      = torch.from_numpy(self._dow)
        self._has_bus_t  = torch.from_numpy(self._has_bus)
        self._eta_s_t    = torch.from_numpy(self._eta_s)
        self._dist_remaining_t = torch.from_numpy(self._dist_remaining)
        self._dist_remaining_norm_t = torch.from_numpy(self._dist_remaining_norm)
        self._time_since_start_t = torch.from_numpy(self._time_since_start).unsqueeze(-1)  # (len, 1)

        # Pre-construir tensor de trayectorias (len, 10, 3) y su máscara
        self._trajectories = torch.zeros(len(valid), 10, 3, dtype=torch.float32)
        self._trajectory_masks = torch.ones(len(valid), 10, dtype=torch.bool)
        
        # Pre-construir tensor de flota (len, 20, 5) y su máscara
        self._fleets = torch.zeros(len(valid), 20, 5, dtype=torch.float32)
        self._fleet_masks = torch.ones(len(valid), 20, dtype=torch.bool)

        for idx, i in enumerate(valid):
            # Llenar trayectoria de forma robusta
            td = traj_dist_list[i]
            ts = traj_speed_list[i]
            tdt = traj_dt_list[i]
            sl = min(len(td), len(ts), len(tdt), 10)
            if sl > 0:
                self._trajectories[idx, :sl, 0] = torch.tensor(td[:sl], dtype=torch.float32)
                self._trajectories[idx, :sl, 1] = torch.tensor(ts[:sl], dtype=torch.float32)
                self._trajectories[idx, :sl, 2] = torch.tensor(tdt[:sl], dtype=torch.float32)
                self._trajectory_masks[idx, :sl] = False

            # Llenar flota de forma robusta
            nf = n_fleet_list[i]
            if nf > 0:
                flat_f = fleet_flat_list[i]
                fl = min(nf, 20)
                for f_idx in range(fl):
                    chunk = flat_f[f_idx*5 : (f_idx+1)*5]
                    if len(chunk) < 5:
                        chunk = chunk + [0.0] * (5 - len(chunk))
                    self._fleets[idx, f_idx, :] = torch.tensor(chunk, dtype=torch.float32)
                    self._fleet_masks[idx, f_idx] = False

    def __len__(self) -> int:
        return len(self._eta_s)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        return {
            "trajectory":           self._trajectories[idx],          # (10, 3)
            "trajectory_mask":      self._trajectory_masks[idx],      # (10,)
            "fleet":                self._fleets[idx],                # (20, 5)
            "fleet_mask":           self._fleet_masks[idx],           # (20,)
            "hour_sin":             self._hour_sin_t[idx:idx+1],      # (1,)
            "hour_cos":             self._hour_cos_t[idx:idx+1],      # (1,)
            "dow":                  self._dow_t[idx],                 # ()
            "dist_remaining_m":     self._dist_remaining_t[idx:idx+1], # (1,)
            "dist_remaining_norm":  self._dist_remaining_norm_t[idx:idx+1],  # (1,)
            "time_since_start":     self._time_since_start_t[idx],    # (1,)
            "has_active_bus":       self._has_bus_t[idx:idx+1],        # (1,)
            "eta_seconds":          self._eta_s_t[idx:idx+1],          # (1,)
        }


def collate_eta(batch: list[dict]) -> dict[str, torch.Tensor]:
    """
    Collate function para DataLoader.
    trajectory y fleet pueden tener longitudes distintas → padding.
    En el MVP (1 punto, 0 fleet) no hay variación, pero el collate
    maneja el caso general para cuando enriquezcamos el dataset.
    """
    from torch.nn.utils.rnn import pad_sequence

    # Trajectory: (batch, seq, 3) — pad al máximo seq_len en el batch
    trajs = [item["trajectory"] for item in batch]           # list of (seq, 3)
    traj_masks = [item["trajectory_mask"] for item in batch] # list of (seq,)
    traj_padded = pad_sequence(trajs, batch_first=True)           # (B, maxseq, 3)
    traj_mask_padded = pad_sequence(traj_masks, batch_first=True, padding_value=True)  # (B, maxseq)

    # Fleet: (batch, n_fleet, 5) — pad al máximo n_fleet en el batch
    fleets = [item["fleet"] for item in batch]           # list of (n_fleet, 5)
    fleet_masks = [item["fleet_mask"] for item in batch] # list of (n_fleet,)
    max_fleet = max(f.shape[0] for f in fleets)

    if max_fleet == 0:
        fleet_padded = torch.zeros(len(batch), 0, 5)
        fleet_mask_padded = torch.zeros(len(batch), 0, dtype=torch.bool)
    else:
        fleet_padded = pad_sequence(fleets, batch_first=True)
        fleet_mask_padded = pad_sequence(fleet_masks, batch_first=True, padding_value=True)

    return {
        "trajectory":           traj_padded,
        "trajectory_mask":      traj_mask_padded,
        "fleet":                fleet_padded,
        "fleet_mask":           fleet_mask_padded,
        "hour_sin":             torch.stack([item["hour_sin"]            for item in batch]),
        "hour_cos":             torch.stack([item["hour_cos"]            for item in batch]),
        "dow":                  torch.stack([item["dow"]                 for item in batch]),
        "dist_remaining_m":     torch.stack([item["dist_remaining_m"]   for item in batch]),
        "dist_remaining_norm":  torch.stack([item["dist_remaining_norm"] for item in batch]),
        "time_since_start":     torch.stack([item["time_since_start"]   for item in batch]),
        "has_active_bus":       torch.stack([item["has_active_bus"]     for item in batch]),
        "eta_seconds":          torch.stack([item["eta_seconds"]        for item in batch]),
    }
