"""
Diagnóstico de NaN/inf en el pipeline de entrenamiento.

Corre ANTES de entrenar para entender qué valores problemáticos llegan al modelo.

Uso:
    python diagnose_nan.py
"""
import numpy as np
import pyarrow.parquet as pq
import torch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prediccion.pipeline.features import N_FLEET
from prediccion.models.eta_dataset import _fsl_to_numpy

PARQUET = "data/ml/training/eta_train.parquet"
N_GROUPS_TO_CHECK = 3  # cuántos row groups inspeccionar


def check_array(name, arr):
    n_nan = np.isnan(arr).sum()
    n_inf = np.isinf(arr).sum()
    finite = arr[np.isfinite(arr)]
    if len(finite) == 0:
        print(f"  {name:35s}: TODOS NaN/inf ({len(arr)} valores)")
        return
    print(f"  {name:35s}: "
          f"nan={n_nan:6d}  inf={n_inf:6d}  "
          f"min={finite.min():10.3f}  max={finite.max():10.3f}  "
          f"mean={finite.mean():10.3f}  p99={np.percentile(finite,99):10.3f}")


def check_group(pf, g_idx):
    print(f"\n=== Row group {g_idx} ===")
    read_cols = [
        "ramal_id", "dist_remaining_m", "dist_along_norm", "speed_mps",
        "hour_sin", "hour_cos", "dow", "has_active_bus", "observed_eta_s",
        "time_since_start", "traj_flat", "traj_len", "fleet_flat", "n_fleet",
    ]
    schema_names = set(pf.schema_arrow.names)
    read_cols = [c for c in read_cols if c in schema_names]
    tbl = pf.read_row_group(g_idx, columns=read_cols)
    n = tbl.num_rows
    print(f"  Filas: {n:,}")

    # --- Escalares ---
    for col in ["dist_remaining_m", "dist_along_norm", "speed_mps",
                "hour_sin", "hour_cos", "observed_eta_s", "time_since_start"]:
        if col in schema_names:
            check_array(col, np.asarray(tbl[col], dtype=np.float32))

    # --- Filtro actual ---
    eta_arr       = np.asarray(tbl["observed_eta_s"], dtype=np.float32)
    dist_rem_arr  = np.asarray(tbl["dist_remaining_m"], dtype=np.float32)
    dist_along    = np.asarray(tbl["dist_along_norm"], dtype=np.float32)
    mask = (eta_arr > 0) & (dist_rem_arr > 0) & (dist_along >= 0) & (dist_along <= 1.0)
    n_valid = mask.sum()
    n_filtered_norm = ((dist_along > 1.0) | (dist_along < 0)).sum()
    print(f"\n  Válidas tras filtro: {n_valid:,}/{n:,}  "
          f"(descartadas por dist_along>1: {n_filtered_norm:,})")

    # --- Trayectoria ---
    if "traj_flat" in schema_names:
        traj_all = _fsl_to_numpy(tbl["traj_flat"], 30).reshape(-1, 10, 3)
        print(f"\n  traj_flat shape: {traj_all.shape}")
        check_array("traj[:,:,0] dist_along_norm", traj_all[:, :, 0].ravel())
        check_array("traj[:,:,1] speed_mps (raw)", traj_all[:, :, 1].ravel())
        check_array("traj[:,:,2] dt_s (raw)",      traj_all[:, :, 2].ravel())
        check_array("traj[:,:,1] speed /30",        (traj_all[:, :, 1] / 30.0).ravel())
        check_array("traj[:,:,2] dt /30",           (traj_all[:, :, 2] / 30.0).ravel())

        # NaN/inf dentro de traj solo para filas válidas
        traj_valid = traj_all[mask]
        n_traj_nan = np.isnan(traj_valid).sum()
        n_traj_inf = np.isinf(traj_valid).sum()
        print(f"  traj (solo válidas): nan={n_traj_nan}  inf={n_traj_inf}")

    # --- Flota ---
    if "fleet_flat" in schema_names:
        fleet_all = _fsl_to_numpy(tbl["fleet_flat"], N_FLEET * 5).reshape(-1, N_FLEET, 5)
        n_fleet_arr = np.asarray(tbl["n_fleet"], dtype=np.int32)
        print(f"\n  fleet shape: {fleet_all.shape}")
        print(f"  n_fleet: min={n_fleet_arr.min()}  max={n_fleet_arr.max()}  "
              f"mean={n_fleet_arr.mean():.1f}")
        check_array("fleet lat_norm  [:,0]", fleet_all[:, :, 0].ravel())
        check_array("fleet lon_norm  [:,1]", fleet_all[:, :, 1].ravel())
        check_array("fleet speed     [:,2]", fleet_all[:, :, 2].ravel())
        check_array("fleet direction [:,3]", fleet_all[:, :, 3].ravel())
        check_array("fleet same_dir  [:,4]", fleet_all[:, :, 4].ravel())

        n_fleet_nan = np.isnan(fleet_all).sum()
        n_fleet_inf = np.isinf(fleet_all).sum()
        print(f"  fleet total: nan={n_fleet_nan}  inf={n_fleet_inf}")

    # --- Verificar fix sobre TODAS las filas válidas ---
    if "traj_flat" in schema_names:
        traj_valid_all = traj_all[mask].copy()
        np.clip(traj_valid_all[:, :, 0], 0.0, 1.0, out=traj_valid_all[:, :, 0])
        traj_valid_all[:, :, 1] /= 30.0
        traj_valid_all[:, :, 2] /= 30.0
        print(f"\n  Tras clip+norm sobre TODAS las válidas ({mask.sum():,} filas):")
        check_array("  traj col0 dist_norm clipped", traj_valid_all[:, :, 0].ravel())
        check_array("  traj col1 speed/30",          traj_valid_all[:, :, 1].ravel())
        check_array("  traj col2 dt/30",             traj_valid_all[:, :, 2].ravel())
        fp16_max = torch.from_numpy(traj_valid_all).half().abs().max().item()
        print(f"  fp16 max abs sobre todas las válidas: {fp16_max:.3f}")

    # --- Simular forward pass con 1 batch ---
    print(f"\n  --- Simulación forward pass (primer batch válido) ---")
    valid_idx = np.where(mask)[0]
    if len(valid_idx) == 0:
        print("  Sin filas válidas.")
        return

    sl = valid_idx[:64]  # batch pequeño para prueba
    traj_b   = torch.from_numpy(np.ascontiguousarray(traj_all[sl])).float()
    fleet_b  = torch.from_numpy(np.ascontiguousarray(fleet_all[sl])).float()

    # Aplicar normalización
    traj_b[:, :, 1] /= 30.0
    traj_b[:, :, 2] /= 30.0
    torch.nan_to_num_(traj_b,  nan=0.0, posinf=0.0, neginf=0.0)
    torch.nan_to_num_(fleet_b, nan=0.0, posinf=0.0, neginf=0.0)

    print(f"  traj_b  max abs: {traj_b.abs().max().item():.3f}  "
          f"nan: {traj_b.isnan().sum().item()}  inf: {traj_b.isinf().sum().item()}")
    print(f"  fleet_b max abs: {fleet_b.abs().max().item():.3f}  "
          f"nan: {fleet_b.isnan().sum().item()}  inf: {fleet_b.isinf().sum().item()}")

    # Probar en fp16
    traj_fp16  = traj_b.half()
    fleet_fp16 = fleet_b.half()
    print(f"  traj_fp16  max abs: {traj_fp16.abs().max().item():.3f}  "
          f"nan: {traj_fp16.isnan().sum().item()}  inf: {traj_fp16.isinf().sum().item()}")
    print(f"  fleet_fp16 max abs: {fleet_fp16.abs().max().item():.3f}  "
          f"nan: {fleet_fp16.isnan().sum().item()}  inf: {fleet_fp16.isinf().sum().item()}")

    # Simular proyección lineal (input_proj del transformer) en fp16
    torch.manual_seed(0)
    proj = torch.nn.Linear(3, 64, bias=False).half()
    with torch.no_grad():
        out = proj(traj_fp16)
    print(f"  TrajectoryEncoder input_proj fp16: "
          f"max={out.abs().max().item():.1f}  "
          f"nan={out.isnan().sum().item()}  inf={out.isinf().sum().item()}")

    proj2 = torch.nn.Linear(5, 64, bias=False).half()
    with torch.no_grad():
        out2 = proj2(fleet_fp16)
    print(f"  FleetEncoder input_proj fp16:      "
          f"max={out2.abs().max().item():.1f}  "
          f"nan={out2.isnan().sum().item()}  inf={out2.isinf().sum().item()}")


def main():
    print(f"Parquet: {PARQUET}")
    pf = pq.ParquetFile(PARQUET)
    print(f"Total rows: {pf.metadata.num_rows:,}  Row groups: {pf.metadata.num_row_groups}")

    for g in range(min(N_GROUPS_TO_CHECK, pf.metadata.num_row_groups)):
        check_group(pf, g)

    print("\n=== FIN ===")


if __name__ == "__main__":
    main()
