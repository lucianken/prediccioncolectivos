from pathlib import Path
import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prediccion.models.a1_baseline import A1Baseline

# NOTE: train_phase2 (RamalIdModel / fleet-level transformer) fue eliminado.
# Ramal ID se resuelve por lookup geométrica offline en ramal_lookup/.
# Ver prediccion_ml_plan.md §6 y §10.2.


def train_phase1(
    ml_dir: Path,
    output_dir: Path,
    val_fraction: float = 0.2,
) -> dict[str, object]:
    """
    Entrena A1Baseline y evalúa sobre val.parquet.
    Returns métricas dict.
    """
    from prediccion.models.a1_baseline import A1Baseline

    ml_dir = Path(ml_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_parquet = ml_dir / "training" / "eta_train.parquet"
    val_parquet = ml_dir / "training" / "eta_val.parquet"

    start = time.time()

    model = A1Baseline()
    model.fit(train_parquet)

    metrics: dict[str, object] = {"n_train": 0, "n_val": 0, "mae_s": None, "mae_min": None}

    import duckdb
    con = duckdb.connect()
    n_train = con.execute(f"SELECT COUNT(*) FROM read_parquet('{train_parquet}')").fetchone()[0]
    metrics["n_train"] = n_train
    con.close()

    if val_parquet.exists():
        eval_metrics = evaluate_a1(model, val_parquet)
        metrics.update(eval_metrics)

    ts = int(time.time())
    model_path = output_dir / f"a1_v{ts}.pkl"
    model.save(model_path)

    metrics_path = output_dir / f"a1_v{ts}_metrics.json"
    metrics["model_version"] = model.model_version
    metrics["training_time_s"] = time.time() - start
    metrics["ramal_ids"] = model.ramal_ids
    metrics["model_path"] = str(model_path)

    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


def evaluate_a1(model: "A1Baseline", val_parquet: Path) -> dict[str, object]:
    """Evalúa A1Baseline sobre val.parquet."""
    import duckdb

    path = str(val_parquet)
    con = duckdb.connect()

    rows = con.execute(f"""
        SELECT ramal_id, seg_idx, dist_remaining_m, hour_sin, hour_cos, dow, observed_eta_s
        FROM read_parquet('{path}')
        WHERE observed_eta_s > 0 AND dist_remaining_m > 0
        LIMIT 10000
    """).fetchall()
    con.close()

    if not rows:
        return {"mae_s": None, "mae_min": None, "n_val": 0}

    errors = []
    bucket_errors: dict[str, list[float]] = {"0_500m": [], "500m_2km": [], "2km_plus": []}
    n_negative = 0
    now = int(time.time())

    for ramal_id, seg_idx, dist_remaining_m, hour_sin, hour_cos, dow, observed_eta_s in rows:
        eta, conf = model.predict(ramal_id, 0.0, dist_remaining_m, now)
        err = abs(eta - observed_eta_s)
        errors.append(err)

        if eta < 0:
            n_negative += 1

        if dist_remaining_m <= 500:
            bucket_errors["0_500m"].append(err)
        elif dist_remaining_m <= 2000:
            bucket_errors["500m_2km"].append(err)
        else:
            bucket_errors["2km_plus"].append(err)

    mae_s = sum(errors) / len(errors) if errors else None
    mae_min = mae_s / 60 if mae_s is not None else None

    by_bucket = {
        k: (sum(v) / len(v) if v else None)
        for k, v in bucket_errors.items()
    }

    errors_sorted = sorted(errors)
    n = len(errors_sorted)

    return {
        "mae_s": mae_s,
        "mae_min": mae_min,
        "n_val": len(rows),
        "n_negative": n_negative,
        "by_bucket": by_bucket,
        "p50_s": errors_sorted[n // 2] if errors_sorted else None,
        "p90_s": errors_sorted[int(n * 0.9)] if errors_sorted else None,
        "p99_s": errors_sorted[int(n * 0.99)] if errors_sorted else None,
    }



def train_phase3(
    ml_dir: Path,
    output_dir: Path,
    epochs: int = 50,
    batch_size: int = 256,
    lr: float = 1e-3,
    device: str = "cuda",
    patience: int = 8,
) -> dict[str, object]:
    """
    Entrena A3ETAModel con L1Loss + mixed precision + early stopping.

    Lee:
      ml_dir/training/eta_train.parquet
      ml_dir/training/eta_val.parquet
    Guarda:
      output_dir/eta_a3_best.pt      — mejor checkpoint (val MAE)
      output_dir/eta_a3_final.onnx   — exportado para inferencia
      output_dir/eta_a3_metrics.json — métricas del entrenamiento

    MVP: trajectory=1punto, fleet vacío → A2 behaviour.
    Cuando el dataset incluya historia y fleet_state, el mismo modelo
    los aprovecha sin cambiar la arquitectura.
    """
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    from torch.amp import GradScaler, autocast
    from prediccion.models.a3_eta import A3ETAModel
    from prediccion.models.eta_dataset import ETADataset, collate_eta

    ml_dir = Path(ml_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_parquet = ml_dir / "training" / "eta_train.parquet"
    val_parquet   = ml_dir / "training" / "eta_val.parquet"

    if not train_parquet.exists():
        raise FileNotFoundError(
            f"eta_train.parquet no encontrado: {train_parquet}\n"
            "Correr primero: python prediccion/train.py --phase 1 ..."
        )

    # Calcular shape_lengths desde line_shapes.json (para normalizar dist_remaining)
    from prediccion.pipeline.shapes_io import DEFAULT_SHAPES_PATH, load_shapes
    from prediccion.pipeline.projector import polyline_length_m
    shape_lengths: dict[str, float] = {}
    try:
        shapes = load_shapes(str(DEFAULT_SHAPES_PATH))
        for line_num, line_data in shapes.items():
            for ramal in line_data.get("ramales", []):
                pts = [tuple(p) for p in ramal["points"]]
                if len(pts) >= 2:
                    ramal_id = f"{line_num}-{ramal.get('direction', 0)}"
                    shape_lengths[ramal_id] = polyline_length_m(pts)
        print(f"      Shape lengths cargados: {len(shape_lengths)} ramales")
    except Exception as e:
        print(f"      WARN: no se pudieron cargar shape lengths: {e}. Usando dist_remaining sin normalizar.")

    actual_device = "cuda" if torch.cuda.is_available() and device == "cuda" else "cpu"
    use_amp = actual_device == "cuda"
    print(f"      Device: {actual_device} | AMP: {use_amp}")

    # Datasets
    print("      Cargando dataset de entrenamiento...")
    train_ds = ETADataset(train_parquet, shape_lengths=shape_lengths)
    print(f"      Train: {len(train_ds):,} ejemplos")

    has_val = val_parquet.exists() and val_parquet.stat().st_size > 0
    if has_val:
        val_ds = ETADataset(val_parquet, shape_lengths=shape_lengths)
        print(f"      Val:   {len(val_ds):,} ejemplos")
    else:
        print("      WARN: eta_val.parquet no encontrado. No habrá val loss.")
        has_val = False

    num_workers = 4 if actual_device == "cuda" else 0
    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate_eta,
        num_workers=num_workers,
        pin_memory=(actual_device == "cuda"),
    )
    val_loader = None
    if has_val:
        val_loader = DataLoader(
            val_ds,
            batch_size=batch_size * 2,
            shuffle=False,
            collate_fn=collate_eta,
            num_workers=num_workers,
            pin_memory=(actual_device == "cuda"),
        )

    model = A3ETAModel().to(actual_device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=3
    )
    criterion = nn.L1Loss()
    scaler = GradScaler("cuda", enabled=use_amp)

    best_val_mae = float("inf")
    best_epoch = 0
    no_improve = 0
    history: list[dict] = []

    best_ckpt_path = output_dir / "eta_a3_best.pt"
    onnx_path = output_dir / "eta_a3_final.onnx"
    metrics_path = output_dir / "eta_a3_metrics.json"

    t_start = time.time()

    def _run_epoch(loader, train_mode: bool) -> float:
        model.train(train_mode)
        total_loss = 0.0
        n = 0
        ctx = torch.enable_grad() if train_mode else torch.no_grad()
        
        desc = "Train" if train_mode else "Val"
        try:
            from tqdm import tqdm
            pbar = tqdm(loader, desc=desc, leave=False)
        except ImportError:
            pbar = loader

        with ctx:
            for batch in pbar:
                traj       = batch["trajectory"].to(actual_device)
                traj_mask  = batch["trajectory_mask"].to(actual_device)
                fleet      = batch["fleet"].to(actual_device)
                fleet_mask = batch["fleet_mask"].to(actual_device)
                h_sin      = batch["hour_sin"].to(actual_device)
                h_cos      = batch["hour_cos"].to(actual_device)
                dow        = batch["dow"].to(actual_device)
                dist_rem   = batch["dist_remaining_norm"].to(actual_device)
                tss        = batch["time_since_start"].to(actual_device)
                has_bus    = batch["has_active_bus"].to(actual_device)
                eta_target = batch["eta_seconds"].to(actual_device)

                if train_mode:
                    optimizer.zero_grad(set_to_none=True)

                with autocast(device_type=actual_device, enabled=use_amp):
                    pred = model(
                        traj, traj_mask, fleet, fleet_mask,
                        h_sin, h_cos, dow, dist_rem, tss, has_bus,
                    )
                    loss = criterion(pred, eta_target)

                if train_mode:
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()

                bs = eta_target.shape[0]
                total_loss += loss.item() * bs
                n += bs

                if hasattr(pbar, "set_postfix"):
                    pbar.set_postfix(loss=loss.item())

        return total_loss / n if n > 0 else float("inf")

    print(f"\n{'Epoch':>6}  {'Train MAE (s)':>14}  {'Val MAE (s)':>12}  {'LR':>10}  {'Best':>5}")
    print("-" * 60)

    for epoch in range(1, epochs + 1):
        train_mae = _run_epoch(train_loader, train_mode=True)
        val_mae = float("inf")
        if val_loader is not None:
            val_mae = _run_epoch(val_loader, train_mode=False)
            scheduler.step(val_mae)
        else:
            scheduler.step(train_mae)

        monitor = val_mae if has_val else train_mae
        is_best = monitor < best_val_mae
        if is_best:
            best_val_mae = monitor
            best_epoch = epoch
            no_improve = 0
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_mae_s": best_val_mae,
                "train_mae_s": train_mae,
            }, best_ckpt_path)
        else:
            no_improve += 1

        current_lr = optimizer.param_groups[0]["lr"]
        val_str = f"{val_mae:12.1f}" if has_val else "         N/A"
        best_str = "  ★" if is_best else ""
        print(f"{epoch:>6}  {train_mae:14.1f}  {val_str}  {current_lr:10.2e}{best_str}")

        history.append({
            "epoch": epoch,
            "train_mae_s": train_mae,
            "val_mae_s": val_mae if has_val else None,
            "lr": current_lr,
        })

        if no_improve >= patience:
            print(f"\nEarly stopping en epoch {epoch} (sin mejora por {patience} épocas).")
            break

    training_time_s = time.time() - t_start
    print(f"\nMejor epoch: {best_epoch} | Mejor val MAE: {best_val_mae:.1f}s ({best_val_mae/60:.2f} min)")
    print(f"Tiempo entrenamiento: {training_time_s/60:.1f} min")

    # Cargar mejor checkpoint
    if best_ckpt_path.exists():
        ckpt = torch.load(best_ckpt_path, map_location=actual_device)
        model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    # Exportar ONNX
    _export_a3_onnx(model, onnx_path, actual_device)

    metrics = {
        "model": "A3ETAModel",
        "best_epoch": best_epoch,
        "epochs_run": epoch,
        "train_mae_s": history[best_epoch - 1]["train_mae_s"] if history else None,
        "val_mae_s": best_val_mae if has_val else None,
        "val_mae_min": best_val_mae / 60 if has_val else None,
        "training_time_s": training_time_s,
        "device": actual_device,
        "batch_size": batch_size,
        "lr_initial": lr,
        "model_path": str(best_ckpt_path),
        "onnx_path": str(onnx_path),
        "n_train": len(train_ds),
        "n_val": len(val_ds) if has_val else 0,
        "history": history,
    }
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


def _export_a3_onnx(model, onnx_path: Path, device: str) -> None:
    """Exporta A3ETAModel a ONNX con inputs de ejemplo. Verifica con onnxruntime."""
    import torch

    model.eval()
    onnx_path = Path(onnx_path)

    # Inputs de ejemplo (batch=1, MVP: traj=1pt, fleet vacío)
    ex = (
        torch.zeros(1, 1, 3,  device=device),   # trajectory
        torch.zeros(1, 1,     device=device, dtype=torch.bool),  # trajectory_mask
        torch.zeros(1, 0, 5,  device=device),   # fleet
        torch.zeros(1, 0,     device=device, dtype=torch.bool),  # fleet_mask
        torch.zeros(1, 1,     device=device),   # hour_sin
        torch.zeros(1, 1,     device=device),   # hour_cos
        torch.zeros(1,        device=device, dtype=torch.int64),  # dow
        torch.zeros(1, 1,     device=device),   # dist_remaining_norm
        torch.zeros(1, 1,     device=device),   # time_since_start
        torch.zeros(1, 1,     device=device),   # has_active_bus
    )
    input_names = [
        "trajectory", "trajectory_mask", "fleet", "fleet_mask",
        "hour_sin", "hour_cos", "dow",
        "dist_remaining_norm", "time_since_start", "has_active_bus",
    ]

    try:
        torch.onnx.export(
            model,
            ex,
            str(onnx_path),
            input_names=input_names,
            output_names=["eta_seconds"],
            opset_version=17,
            dynamic_axes={name: {0: "batch"} for name in input_names + ["eta_seconds"]},
        )
        print(f"      ONNX exportado: {onnx_path}")
    except Exception as e:
        print(f"      WARN: ONNX export falló: {e}")
        return

    # Verificar con onnxruntime
    try:
        import onnxruntime as ort
        import numpy as np
        sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        ort_inputs = {
            "trajectory":          np.zeros((1, 1, 3),  dtype=np.float32),
            "trajectory_mask":     np.zeros((1, 1),     dtype=bool),
            "fleet":               np.zeros((1, 0, 5),  dtype=np.float32),
            "fleet_mask":          np.zeros((1, 0),     dtype=bool),
            "hour_sin":            np.zeros((1, 1),     dtype=np.float32),
            "hour_cos":            np.zeros((1, 1),     dtype=np.float32),
            "dow":                 np.zeros((1,),       dtype=np.int64),
            "dist_remaining_norm": np.zeros((1, 1),     dtype=np.float32),
            "time_since_start":    np.zeros((1, 1),     dtype=np.float32),
            "has_active_bus":      np.zeros((1, 1),     dtype=np.float32),
        }
        out = sess.run(None, ort_inputs)
        print(f"      ONNX verificado con onnxruntime. Salida de prueba: {out[0]}")
    except ImportError:
        print("      onnxruntime no instalado — saltar verificación ONNX")
    except Exception as e:
        print(f"      WARN: verificación ONNX falló: {e}")


def save_onnx(
    model,
    path: Path,
    example_inputs: tuple,
    input_names: list[str],
    output_names: list[str] | None = None,
    opset_version: int = 17,
) -> None:
    """Exporta modelo PyTorch a ONNX y verifica con onnxruntime."""
    import torch
    if output_names is None:
        output_names = ["eta_seconds"]
    path = Path(path)
    torch.onnx.export(
        model,
        example_inputs,
        str(path),
        input_names=input_names,
        output_names=output_names,
        opset_version=opset_version,
        dynamic_axes={name: {0: "batch"} for name in input_names + output_names},
    )
    # Verificar con onnxruntime
    try:
        import onnxruntime as ort
        import numpy as np
        sess = ort.InferenceSession(str(path))
        print(f"ONNX export verified: {[i.name for i in sess.get_inputs()]}")
    except ImportError:
        pass
