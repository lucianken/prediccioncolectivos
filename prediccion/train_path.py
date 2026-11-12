"""
Entrena el modelo por tramos (models/path_eta.py) con la receta fija de ARQUITECTURA.md §6.2.2:
presupuesto fijo de épocas, OneCycleLR (coseno), sin early stopping, mismo pinball que el A3.
Checkpoint: el mejor sobre la muestra de validación (eta_val del dir; en el subconjunto son ~2,3 M filas de 25 días,
estable) y también el último. Todo en <ml-dir>/models_path/ por defecto.

  python -m prediccion.train_path --ml-dir data/ml/v2_sub --epochs 16 --batch-size 1024 --lr 2e-3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch


def train(ml_dir: Path, out_dir: Path, epochs: int, batch_size: int, lr: float, max_groups: int | None,
          unk_line_p: float, workers: int, lines_file: Path, device: str = "cuda", seed: int = 0,
          resume: bool = False, stop_after_epoch: int | None = None, lr_trace: list | None = None,
          shapes_dir=None) -> dict:
    """resume: retoma desde out_dir/path_eta_last.pt (guardado atómico al final de cada época; ver models/resume.py).
    stop_after_epoch / lr_trace: ganchos de test (cortar el run; registrar el LR de cada paso)."""
    from prediccion.models.eta_dataset import collate_identity
    from prediccion.models.path_eta import (PathETADataset, PathETAModel, build_shape_table, load_shape_points,
                                            pinball, run_model)
    torch.manual_seed(seed)
    np.random.seed(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_p = ml_dir / "training" / "eta_train.parquet"
    val_p = ml_dir / "training" / "eta_val.parquet"
    lf = json.loads(Path(lines_file).read_text(encoding="utf-8"))
    import pyarrow.parquet as pq
    train_lines = sorted({str(x) for x in pq.read_table(train_p, columns=["line"])["line"].to_pylist()}, key=int)
    geo_lines = sorted({*map(str, lf["train"]), *map(str, lf.get("heldout", []))}, key=int)   # solo geometría
    ids, lat, lon, off = build_shape_table(load_shape_points(geo_lines, shapes_dir))
    model = PathETAModel(ids, lat, lon, off, train_lines)
    dev = "cuda" if torch.cuda.is_available() and device == "cuda" else "cpu"
    model.to(dev)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"shapes={len(ids)} celdas={len(lat)} lineas_train={len(train_lines)} params={n_params:,} device={dev}", flush=True)

    tr = PathETADataset(train_p, model.maps, batch_size, shuffle=True, max_groups=max_groups, unk_line_p=unk_line_p)
    va = PathETADataset(val_p, model.maps, 4096, shuffle=False, max_groups=max_groups)
    mk = lambda ds: torch.utils.data.DataLoader(ds, batch_size=1, collate_fn=collate_identity, num_workers=workers,  # noqa: E731
                                                persistent_workers=workers > 0, prefetch_factor=4 if workers else None)
    tl, vl = mk(tr), mk(va)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    steps = len(tl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, steps_per_epoch=steps, epochs=epochs, pct_start=0.3,
                                                anneal_strategy="cos", div_factor=10, final_div_factor=100)
    best, best_ep, hist = float("inf"), 0, []
    from prediccion.models import resume as R
    last_p = out_dir / "path_eta_last.pt"
    config = {"model": "PathETAModel", "epochs": epochs, "scheduler": "onecycle", "lr": lr, "batch_size": batch_size,
              "train_data": R.data_fingerprint(train_p), "val_data": R.data_fingerprint(val_p),
              "max_groups": max_groups, "unk_line_p": unk_line_p, "seed": seed, "train_lines": train_lines}
    start_ep = 1
    if resume and last_p.exists():
        st = R.load_last(last_p, model=model, optimizer=opt, scheduler=sched, config=config)
        best, best_ep, hist, start_ep = st["best"], st["best_epoch"], st["history"], st["epoch"] + 1
        print(f"reanudando desde la época {st['epoch']} (last.pt); sigue la {start_ep}/{epochs}", flush=True)
    elif resume:
        print(f"WARN: --resume pero no existe {last_p.name}: se empieza de cero", flush=True)
    t0 = time.time()
    for ep in range(start_ep, epochs + 1):
        te = time.time()
        model.train()
        tot, n, done = 0.0, 0, 0
        for b in tl:
            pred = run_model(model, b, dev)
            tgt = b["eta"].to(dev).squeeze(-1)
            loss = pinball(pred, tgt, b["rem"].to(dev))
            if not torch.isfinite(loss):
                opt.zero_grad(set_to_none=True)
                continue
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            if lr_trace is not None:
                lr_trace.append(opt.param_groups[0]["lr"])
            opt.step()
            if sched.last_epoch < steps * epochs - 1:     # len() del loader es aproximado: no pasarse del total
                sched.step()
            done += 1
            tot += float(loss) * len(tgt)
            n += len(tgt)
        model.eval()
        ae, nv = 0.0, 0
        with torch.no_grad():
            for b in vl:
                pred = run_model(model, b, dev).clamp(min=0.0)
                tgt = b["eta"].to(dev).squeeze(-1)
                ae += float((pred - tgt).abs().sum())
                nv += len(tgt)
        val_mae = ae / max(nv, 1)
        is_best = val_mae < best
        if is_best:
            best, best_ep = val_mae, ep
            torch.save({**model.checkpoint_dict(), "epoch": ep, "val_mae_s": val_mae}, out_dir / "path_eta_best.pt")
        lr_now = opt.param_groups[0]["lr"]
        hist.append({"epoch": ep, "train_pinball": tot / max(n, 1), "val_mae_s": val_mae, "lr": lr_now,
                     "epoch_s": time.time() - te})
        print(f"ep {ep:>2}/{epochs} train_pinball={tot / max(n, 1):7.1f} val_mae={val_mae:7.1f}s lr={lr_now:.2e} "
              f"{time.time() - te:5.0f}s{' *' if is_best else ''}", flush=True)
        # last.pt: estado completo de reanudación + los campos que usa PathETAModel.from_checkpoint (sirve para evaluar)
        R.save_last(last_p, model=model, optimizer=opt, scheduler=sched, epoch=ep, best=best, best_epoch=best_ep,
                    history=hist, config=config,
                    top={k: v for k, v in model.checkpoint_dict().items() if k != "model_state_dict"})
        if stop_after_epoch is not None and ep >= stop_after_epoch:
            return {"stopped_after_epoch": ep}
    total = time.time() - t0
    res = {"model": "PathETAModel", "epochs": epochs, "batch_size": batch_size, "lr": lr, "best_epoch": best_ep,
           "best_val_mae_s": best, "last_val_mae_s": hist[-1]["val_mae_s"], "training_time_s": total,
           "n_params": n_params, "n_train_rows_approx": tr.approx_len, "history": hist}
    (out_dir / "path_eta_metrics.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"listo en {total / 60:.1f} min; mejor ep {best_ep} val_mae {best:.1f}s", flush=True)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ml-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--lines-file", type=Path, default=Path("data/ml/v2/lines.json"))
    ap.add_argument("--epochs", type=int, default=16)
    ap.add_argument("--batch-size", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--max-groups", type=int, default=None)
    ap.add_argument("--unk-line-p", type=float, default=0.1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--resume", action="store_true", help="retomar desde <out-dir>/path_eta_last.pt")
    a = ap.parse_args(argv)
    train(a.ml_dir, a.out_dir or a.ml_dir / "models_path", a.epochs, a.batch_size, a.lr, a.max_groups,
          a.unk_line_p, a.workers, a.lines_file, a.device, seed=a.seed, resume=a.resume)
    return 0


if __name__ == "__main__":
    sys.exit(main())
