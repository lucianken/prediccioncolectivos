import sys
from pathlib import Path
import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prediccion.models.a1_baseline import A1Baseline

# NOTE: train_phase2 (RamalIdModel / fleet-level transformer) fue eliminado.
# Ramal ID se resuelve por lookup geométrica offline en ramal_lookup/.
# Ver prediccion_ml_plan.md §6 y §10.2.


def _require_valid_parquet(path: Path, label: str) -> None:
    """Verifica que el parquet exista, no esté vacío y tenga footer válido."""
    if not path.exists():
        raise FileNotFoundError(f"{label} no encontrado: {path}")
    if path.stat().st_size == 0:
        raise ValueError(
            f"{label} está vacío: {path}\n"
            "Regenerar con --merge-only en build_dataset o correr phase 1 completa."
        )
    try:
        import pyarrow.parquet as pq
        pq.read_metadata(str(path))
    except Exception as exc:
        raise ValueError(
            f"{label} corrupto o incompleto: {path}\n"
            "Probable causa: merge interrumpido. Regenerar con:\n"
            "  python -m prediccion.pipeline.build_dataset --merge-only "
            f'--data-dir <grabaciones> --ml-dir "{path.parent.parent}"\n'
            f"Detalle: {exc}"
        ) from exc


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
        USING SAMPLE 500000 ROWS
    """).fetchall()
    con.close()

    if not rows:
        return {"mae_s": None, "mae_min": None, "n_val": 0}

    errors = []
    bucket_errors: dict[str, list[float]] = {"0_500m": [], "500m_2km": [], "2km_plus": []}
    n_negative = 0
    import math as _math

    for ramal_id, seg_idx, dist_remaining_m, hour_sin, hour_cos, dow, observed_eta_s in rows:
        hour = int(round(_math.atan2(hour_sin, hour_cos) * 24 / (2 * _math.pi))) % 24
        eta, conf = model.predict_direct(ramal_id, 0.0, dist_remaining_m, hour, int(dow))
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
    d_model: int = 128,
    use_fleet: bool = True,
    resume: bool = False,
    max_groups: int | None = None,
    fleet_same_dir_cap: int | None = None,
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
    import logging
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    from torch.amp import GradScaler, autocast
    from prediccion.models.a3_eta import A3ETAModel
    from prediccion.models.eta_dataset import ETADataset, collate_identity

    logger = logging.getLogger(__name__)
    logger.info(f"[train_phase3] Starting with config: epochs={epochs}, batch_size={batch_size}, lr={lr}, device={device}, patience={patience}")

    ml_dir = Path(ml_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_parquet = ml_dir / "training" / "eta_train.parquet"
    val_parquet   = ml_dir / "training" / "eta_val.parquet"

    _require_valid_parquet(train_parquet, "eta_train.parquet")

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
                    # Clave primaria: shape_id de OSM
                    sh_id = ramal.get("shapeId")
                    if sh_id:
                        shape_lengths[sh_id] = polyline_length_m(pts)
                    # Fallback naive
                    shape_lengths[f"{line_num}-{ramal.get('direction', 0)}"] = polyline_length_m(pts)
        print(f"      Shape lengths cargados: {len(shape_lengths)} shapes")
    except Exception as e:
        print(f"      WARN: no se pudieron cargar shape lengths: {e}. Usando dist_remaining sin normalizar.")

    actual_device = "cuda" if torch.cuda.is_available() and device == "cuda" else "cpu"
    use_amp = actual_device == "cuda"
    print(f"      Device: {actual_device} | AMP: {use_amp}")

    # Datasets — IterableDataset: lee de a un row group por vez, no carga todo en RAM
    print("      Inicializando dataset de entrenamiento...")
    print(f"      Fleet encoder: {'habilitado' if use_fleet else 'DESHABILITADO (--no-fleet)'}")
    if max_groups is not None:
        print(f"      WARN: --max-groups {max_groups} activo — subsampling para iteración rápida, no usar para modelo final")
    train_ds = ETADataset(train_parquet, shape_lengths=shape_lengths, shuffle=True, yield_batch_size=batch_size, use_fleet=use_fleet, max_groups=max_groups, fleet_same_dir_cap=fleet_same_dir_cap)
    print(f"      Train: ~{train_ds.approx_batches * batch_size:,} muestras en ~{train_ds.approx_batches:,} batches ({train_ds._n_groups} row groups)")

    has_val = val_parquet.exists() and val_parquet.stat().st_size > 0
    if has_val:
        try:
            _require_valid_parquet(val_parquet, "eta_val.parquet")
        except ValueError as exc:
            print(f"      WARN: {exc}")
            has_val = False
    if has_val:
        val_ds = ETADataset(val_parquet, shape_lengths=shape_lengths, shuffle=False, yield_batch_size=batch_size, use_fleet=use_fleet, max_groups=max_groups, fleet_same_dir_cap=fleet_same_dir_cap)
        print(f"      Val:   ~{val_ds.approx_batches * batch_size:,} muestras en ~{val_ds.approx_batches:,} batches ({val_ds._n_groups} row groups)")
    else:
        print("      WARN: eta_val.parquet no encontrado. No habrá val loss.")
        has_val = False

    num_workers = 4 if actual_device == "cuda" else 0
    persistent = num_workers > 0
    logger.info(f"[train_phase3] Creating DataLoaders: yield_batch_size={batch_size}, num_workers={num_workers}")
    t_loader = time.time()
    train_loader = DataLoader(
        train_ds,
        batch_size=1,
        shuffle=False,
        collate_fn=collate_identity,
        num_workers=num_workers,
        pin_memory=(actual_device == "cuda"),
        persistent_workers=persistent,
        prefetch_factor=2 if num_workers > 0 else None,
    )
    val_loader = None
    if has_val:
        val_loader = DataLoader(
            val_ds,
            batch_size=1,
            shuffle=False,
            collate_fn=collate_identity,
            num_workers=num_workers,
            pin_memory=(actual_device == "cuda"),
            persistent_workers=persistent,
            prefetch_factor=2 if num_workers > 0 else None,
        )
    logger.info(f"[train_phase3] DataLoaders ready: {time.time()-t_loader:.2f}s")

    t_model = time.time()
    model = A3ETAModel(d_model=d_model).to(actual_device)
    logger.info(f"[train_phase3] Model initialized and moved to {actual_device}: {time.time()-t_model:.2f}s")
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=3
    )
    def criterion(pred, target, dist_m):
        # Pinball loss con q variable por distancia (ver prediccion_ml_plan.md §7b):
        #   dist > 1km  → q = 0.5 (L1 simétrica, aprende la mediana)
        #   dist < 1km  → q sube hasta 0.8 (underestimar penaliza 4x más que overestimar)
        # Razón: cuando el bus está cerca, perder el colectivo por subestimar es peor
        # que esperar un poco más por sobreestimar.
        q = 0.5 + 0.3 * torch.clamp(1.0 - dist_m / 1000.0, 0.0, 1.0)  # (batch, 1)
        error = target - pred   # positivo = subestimé (pred < target)
        loss = torch.where(error >= 0, q * error, (q - 1.0) * error)
        return loss.mean()
    amp_dtype = torch.bfloat16  # bfloat16: mismo rango que fp32, sin overflow en fp16
    scaler = GradScaler("cuda", enabled=False)  # bfloat16 no necesita escala — no hay overflow

    best_val_mae = float("inf")
    best_epoch = 0
    no_improve = 0
    history: list[dict] = []
    start_epoch = 1

    best_ckpt_path = output_dir / "eta_a3_best.pt"

    if resume and best_ckpt_path.exists():
        ckpt = torch.load(best_ckpt_path, map_location=actual_device)
        model.load_state_dict(ckpt["model_state_dict"])
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        best_val_mae = ckpt.get("val_mae_s", float("inf"))
        best_epoch   = ckpt.get("epoch", 0)
        start_epoch  = best_epoch + 1
        print(f"      Resumiendo desde epoch {best_epoch} (val MAE={best_val_mae:.1f}s)")
    elif resume:
        print("      WARN: --resume pero no existe eta_a3_best.pt — arrancando desde cero")
    onnx_path = output_dir / "eta_a3_final.onnx"
    metrics_path = output_dir / "eta_a3_metrics.json"

    # Prevenir sleep de Windows durante el entrenamiento
    import ctypes, sys as _sys
    if _sys.platform == "win32":
        ES_CONTINUOUS      = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        logger.info("[train_phase3] SetThreadExecutionState: sleep bloqueado durante entrenamiento")

    t_start = time.time()
    import time as _time
    import json as _json
    import warnings as _warnings
    _warnings.filterwarnings("ignore", message="Length of IterableDataset", category=UserWarning)

    _perf_log_path = output_dir / "perf_log.jsonl"

    def _log_perf(record: dict) -> None:
        """Appendea métricas de timing al perf_log.jsonl (solo archivo, no consola)."""
        with open(_perf_log_path, "a", encoding="utf-8") as _f:
            _f.write(_json.dumps(record) + "\n")

    _PERF_INTERVAL = 200  # loguear cada N batches

    def _run_epoch(loader, train_mode: bool, epoch: int) -> tuple[float, dict[str, float]] | float:
        t_epoch = _time.perf_counter()
        model.train(train_mode)
        total_loss = 0.0
        n = 0
        ctx = torch.enable_grad() if train_mode else torch.no_grad()
        phase = "train" if train_mode else "val"

        desc = "Train" if train_mode else "Val"
        try:
            from tqdm import tqdm
            pbar = tqdm(loader, desc=desc, leave=False, dynamic_ncols=True, file=sys.stderr)
        except ImportError:
            pbar = loader

        if actual_device == "cuda":
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()

        if not train_mode:
            bucket_sums   = {"0_500m": 0.0, "500m_2km": 0.0, "2km_plus": 0.0, "under_500m": 0.0}
            bucket_counts = {"0_500m": 0,   "500m_2km": 0,   "2km_plus": 0,   "under_500m": 0}
            naive_sum = 0.0
            naive_n   = 0

        # Acumuladores de timing para el intervalo actual
        acc = {"fetch": 0.0, "todev": 0.0, "fwd": 0.0, "bwd": 0.0, "total": 0.0}
        batch_idx = 0
        t_batch_start = _time.perf_counter()

        with ctx:
            for batch in pbar:
                t0 = _time.perf_counter()
                acc["fetch"] += t0 - t_batch_start  # tiempo esperando el siguiente batch del dataloader

                # ── transferencia a GPU ──────────────────────────────────────
                traj       = batch["trajectory"].to(actual_device)
                traj_mask  = batch["trajectory_mask"].to(actual_device)
                fleet      = batch["fleet"].to(actual_device)
                fleet_mask = batch["fleet_mask"].to(actual_device)
                h_sin      = batch["hour_sin"].to(actual_device)
                h_cos      = batch["hour_cos"].to(actual_device)
                dow        = batch["dow"].to(actual_device)
                dist_rem     = batch["dist_remaining_norm"].to(actual_device)
                dist_rem_m   = batch["dist_remaining_m"].to(actual_device)
                tss          = batch["time_since_start"].to(actual_device)
                ts_age       = batch["ts_age_s"].to(actual_device)
                has_bus      = batch["has_active_bus"].to(actual_device)
                eta_target   = batch["eta_seconds"].to(actual_device)
                # No synchronize aquí — .to() es async, medir sin frenar el pipeline
                t1 = _time.perf_counter()
                acc["todev"] += t1 - t0

                if train_mode:
                    optimizer.zero_grad(set_to_none=True)

                # ── forward ─────────────────────────────────────────────────
                with autocast(device_type=actual_device, dtype=amp_dtype, enabled=use_amp):
                    pred = model(
                        traj, traj_mask, fleet, fleet_mask,
                        h_sin, h_cos, dow, dist_rem, tss, ts_age, has_bus,
                    )
                    loss = criterion(pred, eta_target, dist_rem_m)
                # No synchronize — forward es async hasta que necesitemos el valor
                t2 = _time.perf_counter()
                acc["fwd"] += t2 - t1

                # ── backward / eval metrics ──────────────────────────────────
                if train_mode:
                    if not torch.isfinite(loss):
                        logger.warning(f"[_run_epoch] NaN/inf loss detectado — batch saltado (loss={loss.item()})")
                        optimizer.zero_grad(set_to_none=True)
                        t_batch_start = _time.perf_counter()
                        continue
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    errors = torch.abs(pred - eta_target)
                    signed = pred - eta_target  # positivo = sobreestimé
                    mask_0_500  = dist_rem_m <= 500
                    mask_500_2k = (dist_rem_m > 500) & (dist_rem_m <= 2000)
                    mask_2k_plus = dist_rem_m > 2000

                    bucket_sums["0_500m"]   += errors[mask_0_500].sum().item()
                    bucket_counts["0_500m"] += mask_0_500.sum().item()
                    bucket_sums["500m_2km"]   += errors[mask_500_2k].sum().item()
                    bucket_counts["500m_2km"] += mask_500_2k.sum().item()
                    bucket_sums["2km_plus"]   += errors[mask_2k_plus].sum().item()
                    bucket_counts["2km_plus"] += mask_2k_plus.sum().item()

                    # Validación de asimetría en sub-500m: ¿el modelo sobreestima más que subestima?
                    n_500 = mask_0_500.sum().item()
                    if n_500 > 0:
                        under_500 = (signed[mask_0_500] < 0).sum().item()  # pred < real → subestimé
                        bucket_sums["under_500m"]   += under_500
                        bucket_counts["under_500m"] += n_500

                    # Naive baseline: dist_remaining_m / 7 m/s (fallback de A1)
                    naive_pred = dist_rem_m / 7.0
                    naive_sum += (naive_pred - eta_target).abs().sum().item()
                    naive_n   += eta_target.shape[0]

                t3 = _time.perf_counter()
                acc["bwd"] += t3 - t2
                acc["total"] += t3 - t_batch_start

                bs = eta_target.shape[0]
                total_loss += loss.item() * bs
                n += bs
                batch_idx += 1

                if hasattr(pbar, "set_postfix"):
                    pbar.set_postfix(loss=f"{loss.item():.1f}")

                # ── log de performance cada N batches ────────────────────────
                if batch_idx % _PERF_INTERVAL == 0:
                    inv = 1.0 / _PERF_INTERVAL
                    vram = torch.cuda.memory_allocated() / 1e9 if actual_device == "cuda" else 0.0
                    record = {
                        "ts": _time.time(),
                        "phase": phase,
                        "epoch": epoch,
                        "batch_end": batch_idx,
                        "t_fetch_ms":  acc["fetch"]  * 1000 * inv,
                        "t_todev_ms":  acc["todev"]  * 1000 * inv,
                        "t_fwd_ms":    acc["fwd"]    * 1000 * inv,
                        "t_bwd_ms":    acc["bwd"]    * 1000 * inv,
                        "t_total_ms":  acc["total"]  * 1000 * inv,
                        "its_per_sec": _PERF_INTERVAL / acc["total"] if acc["total"] > 0 else 0,
                        "vram_gb":     vram,
                        "loss":        loss.item(),
                    }
                    _log_perf(record)
                    acc = {"fetch": 0.0, "todev": 0.0, "fwd": 0.0, "bwd": 0.0, "total": 0.0}

                t_batch_start = _time.perf_counter()

        t_epoch = _time.perf_counter() - t_epoch
        if actual_device == "cuda":
            torch.cuda.synchronize()
            peak_mem_gb = torch.cuda.max_memory_allocated() / 1e9
            logger.info(f"[_run_epoch] {'Train' if train_mode else 'Val  '}: time={t_epoch:.2f}s, peak_vram={peak_mem_gb:.2f}GB, batches={n//batch_size if batch_size else '?'}")

        if not train_mode:
            by_bucket = {
                k: (bucket_sums[k] / bucket_counts[k] if bucket_counts[k] > 0 else 0.0)
                for k in bucket_sums if k != "under_500m"
            }
            # Ratio de subestimaciones en sub-500m (target: bajar de 50% con pinball loss)
            n_500 = bucket_counts["under_500m"]
            by_bucket["under_500m_ratio"] = (
                bucket_sums["under_500m"] / n_500 if n_500 > 0 else 0.0
            )
            by_bucket["naive_mae"] = naive_sum / naive_n if naive_n > 0 else 0.0
            return (total_loss / n if n > 0 else float("inf")), by_bucket
        return total_loss / n if n > 0 else float("inf")

    print(f"\n{'Epoch':>5}  {'Train MAE':>11}  {'Val MAE':>11}  {'Naive':>9}  {'0-500m':>9}  {'500m-2km':>9}  {'2km+':>9}  {'Under<500m':>11}  {'LR':>9}  {'Best':>5}")
    print("-" * 107)

    for epoch in range(start_epoch, epochs + 1):
        train_mae = _run_epoch(train_loader, train_mode=True, epoch=epoch)
        val_mae = float("inf")
        val_by_bucket = {}
        if val_loader is not None:
            val_mae, val_by_bucket = _run_epoch(val_loader, train_mode=False, epoch=epoch)
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
                "val_mae_by_bucket": val_by_bucket if has_val else None,
            }, best_ckpt_path)
        else:
            no_improve += 1

        current_lr = optimizer.param_groups[0]["lr"]
        val_str   = f"{val_mae:11.1f}" if has_val else "        N/A"
        b0_str    = f"{val_by_bucket.get('0_500m', 0.0):9.1f}" if has_val else "      N/A"
        b1_str    = f"{val_by_bucket.get('500m_2km', 0.0):9.1f}" if has_val else "      N/A"
        b2_str    = f"{val_by_bucket.get('2km_plus', 0.0):9.1f}" if has_val else "      N/A"
        under_str = f"{val_by_bucket.get('under_500m_ratio', 0.0)*100:9.1f}%" if has_val else "        N/A"
        naive_str = f"{val_by_bucket.get('naive_mae', 0.0):9.1f}" if has_val else "      N/A"
        best_str  = "  ★" if is_best else ""
        print(f"{epoch:>5}  {train_mae:11.1f}  {val_str}  {naive_str}  {b0_str}  {b1_str}  {b2_str}  {under_str}  {current_lr:9.2e}{best_str}")

        history.append({
            "epoch": epoch,
            "train_mae_s": train_mae,
            "val_mae_s": val_mae if has_val else None,
            "val_mae_by_bucket": val_by_bucket if has_val else None,
            "lr": current_lr,
        })

        if no_improve >= patience:
            print(f"\nEarly stopping en epoch {epoch} (sin mejora por {patience} épocas).")
            break

    # Restaurar comportamiento de sleep normal
    if _sys.platform == "win32":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    training_time_s = time.time() - t_start
    print(f"\nMejor epoch: {best_epoch} | Mejor val MAE: {best_val_mae:.1f}s ({best_val_mae/60:.2f} min)")

    logger.info(f"[train_phase3] TRAINING COMPLETE")
    logger.info(f"  Total time: {training_time_s:.2f}s ({training_time_s/60:.2f} min)")
    logger.info(f"  Epochs completed: {epoch}/{epochs}")
    logger.info(f"  Best epoch: {best_epoch} (val_mae={best_val_mae:.1f}s)")
    logger.info(f"  Time per epoch: {training_time_s/epoch:.2f}s avg")
    logger.info(f"  Samples trained: {train_ds.approx_batches:,} × {epoch} = {train_ds.approx_batches*epoch:,}")
    print(f"Tiempo entrenamiento: {training_time_s/60:.1f} min")

    # Cargar mejor checkpoint
    if best_ckpt_path.exists():
        ckpt = torch.load(best_ckpt_path, map_location=actual_device)
        model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    # Exportar ONNX
    _export_a3_onnx(model, onnx_path, actual_device)

    import shutil as _shutil
    from datetime import datetime as _dt

    metrics = {
        "model": "A3ETAModel",
        "best_epoch": best_epoch,
        "epochs_run": epoch,
        "train_mae_s": history[best_epoch - 1]["train_mae_s"] if history else None,
        "val_mae_s": best_val_mae if has_val else None,
        "val_mae_min": best_val_mae / 60 if has_val else None,
        "val_mae_by_bucket": history[best_epoch - 1]["val_mae_by_bucket"] if (history and has_val) else None,
        "training_time_s": training_time_s,
        "device": actual_device,
        "batch_size": batch_size,
        "lr_initial": lr,
        "use_fleet": use_fleet,
        "d_model": d_model,
        "max_groups": max_groups,
        "model_path": str(best_ckpt_path),
        "onnx_path": str(onnx_path),
        "n_train": train_ds.approx_batches,
        "n_val": val_ds.approx_batches if has_val else 0,
        "history": history,
    }
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    # Copia archivada con timestamp para no perder runs anteriores
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    fleet_tag = "fleet" if use_fleet else "nofleet"
    groups_tag = f"g{max_groups}" if max_groups else "gfull"
    mae_tag = f"mae{int(best_val_mae)}s" if has_val else "noval"
    run_tag = f"{fleet_tag}_{groups_tag}_ep{best_epoch}_{mae_tag}_{ts}"
    archived_metrics = output_dir / f"eta_a3_{run_tag}_metrics.json"
    _shutil.copy2(metrics_path, archived_metrics)
    logger.info(f"[train_phase3] Métricas archivadas: {archived_metrics.name}")

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
        torch.zeros(1, 1, 5,  device=device),                      # fleet (1 bus de ejemplo)
        torch.zeros(1, 1,     device=device, dtype=torch.bool),  # fleet_mask
        torch.zeros(1, 1,     device=device),   # hour_sin
        torch.zeros(1, 1,     device=device),   # hour_cos
        torch.zeros(1, 1,     device=device, dtype=torch.int64),  # dow (batch, 1) → squeeze → (batch,)
        torch.zeros(1, 1,     device=device),   # dist_remaining_norm
        torch.zeros(1, 1,     device=device),   # time_since_start
        torch.zeros(1, 1,     device=device),   # ts_age_s
        torch.zeros(1, 1,     device=device),   # has_active_bus
    )
    input_names = [
        "trajectory", "trajectory_mask", "fleet", "fleet_mask",
        "hour_sin", "hour_cos", "dow",
        "dist_remaining_norm", "time_since_start", "ts_age_s", "has_active_bus",
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
        # Filtrar inputs según lo que realmente espera el modelo ONNX exportado (ya que PyTorch optimiza y remueve inputs no usados como fleet/fleet_mask cuando n_fleet=0)
        ort_inputs = {
            name: val.cpu().numpy()
            for name, val in zip(input_names, ex)
        }
        expected_names = {i.name for i in sess.get_inputs()}
        ort_inputs = {k: v for k, v in ort_inputs.items() if k in expected_names}
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
