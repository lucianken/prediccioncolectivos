from pathlib import Path
from typing import TYPE_CHECKING
import json
import time

if TYPE_CHECKING:
    from prediccion.models.a1_baseline import A1Baseline


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


def train_phase2(
    ml_dir: Path,
    output_dir: Path,
    line: str,
    n_ramales: int,
    epochs: int = 100,
    batch_size: int = 64,
    lr: float = 1e-3,
    device: str = "cuda",
    patience: int = 10,
) -> dict[str, object]:
    """
    Entrena RamalIdModel para una línea específica.
    - Loss: CrossEntropyLoss
    - Mixed precision si CUDA
    - Early stopping
    - Guarda best checkpoint + ONNX
    """
    import torch
    from prediccion.models.ramal_id import RamalIdModel

    ml_dir = Path(ml_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = device if torch.cuda.is_available() and device == "cuda" else "cpu"
    model = RamalIdModel(n_ramales=n_ramales).to(device)

    # Placeholder: en producción cargar el dataset real
    # Por ahora retorna métricas de esqueleto
    return {
        "accuracy": 0.0,
        "val_accuracy": 0.0,
        "epochs_run": 0,
        "training_time_s": 0.0,
        "model_path": str(output_dir / f"ramal_id_{line}_v1.pt"),
        "onnx_path": str(output_dir / f"ramal_id_{line}_v1.onnx"),
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
    Entrena A3ETAModel.
    - Loss: L1Loss
    - Mixed precision si CUDA
    - LR scheduler: ReduceLROnPlateau
    - Early stopping
    """
    import torch
    from prediccion.models.a3_eta import A3ETAModel

    ml_dir = Path(ml_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = device if torch.cuda.is_available() and device == "cuda" else "cpu"
    model = A3ETAModel().to(device)

    # Placeholder: en producción cargar el dataset real
    return {
        "mae_s": 0.0,
        "mae_min": 0.0,
        "val_mae_s": 0.0,
        "val_mae_min": 0.0,
        "epochs_run": 0,
        "training_time_s": 0.0,
        "model_path": str(output_dir / "eta_a3_v1.pt"),
        "onnx_path": str(output_dir / "eta_a3_v1.onnx"),
    }


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
