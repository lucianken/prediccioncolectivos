"""
Reanudación exacta de entrenamientos (A3 y modelo por tramos).

Al final de cada época el trainer escribe `last.pt` de forma atómica (a `.tmp` y `os.replace`) con todo lo
necesario para continuar como si no se hubiera cortado: modelo, optimizador, estado del scheduler, época,
mejor métrica / mejor época, historial, estado de los RNG (torch, numpy, python) y la config del run.
`--resume` retoma desde `last.pt` (nunca desde `best.pt`) en la época siguiente. Si el run se corta a mitad de
una época se pierde solo esa época. Si la config guardada difiere de la actual en lo que importa
(`RECIPE_KEYS`), se falla con un mensaje claro en vez de mezclar recetas.

Límite: con DataLoader de varios workers persistentes (GPU) el orden de las filas dentro de la época que se
reanuda no es idéntico al de un run sin cortes (los workers tienen su propio RNG); modelo, optimizador, scheduler
(LR) y RNG del proceso principal sí se restauran exactos. En CPU (sin workers) la reanudación es bit a bit.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import torch


def get_rng_state() -> dict:
    st = {"torch": torch.get_rng_state(), "numpy": np.random.get_state(), "python": random.getstate()}
    if torch.cuda.is_available():
        st["cuda"] = torch.cuda.get_rng_state_all()
    return st


def set_rng_state(st: dict) -> None:
    torch.set_rng_state(st["torch"])
    np.random.set_state(st["numpy"])
    random.setstate(st["python"])
    if "cuda" in st and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(st["cuda"])


def data_fingerprint(path) -> str:
    """Identifica el archivo de datos (nombre, tamaño, mtime): si cambia, no se puede reanudar con la misma receta."""
    p = Path(path)
    if not p.exists():
        return f"{p.name}:missing"
    s = p.stat()
    return f"{p.name}:{s.st_size}:{int(s.st_mtime)}"


def check_config(saved: dict, current: dict, keys=None) -> None:
    """Todas las claves de la config actual son parte de la receta y tienen que coincidir con las guardadas."""
    keys = list(current) if keys is None else keys
    diffs = [f"  {k}: guardado={saved.get(k)!r} actual={current.get(k)!r}"
             for k in keys if saved.get(k) != current.get(k)]
    if diffs:
        raise ValueError("no se puede reanudar: la config del run guardado difiere de la actual en la receta:\n"
                         + "\n".join(diffs)
                         + "\nUsar los mismos argumentos que el run original (o empezar de cero sin --resume).")


def save_last(path, *, model, optimizer, scheduler, epoch: int, best: float, best_epoch: int, history: list,
              config: dict, extra: dict | None = None, top: dict | None = None) -> None:
    """Escritura atómica: .tmp + os.replace; un corte durante el guardado deja intacto el last.pt anterior."""
    path = Path(path)
    state = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict() if scheduler is not None else None,
        "epoch": int(epoch), "best": float(best), "best_epoch": int(best_epoch), "history": history,
        "rng": get_rng_state(), "config": config, "extra": extra or {},
        **(top or {}),
    }
    tmp = path.with_name(path.name + ".tmp")
    torch.save(state, tmp)
    os.replace(tmp, path)


def load_last(path, *, model, optimizer, scheduler, config: dict, map_location="cpu") -> dict:
    """Restaura todo desde last.pt y devuelve {epoch, best, best_epoch, history, extra}. Valida la config."""
    st = torch.load(str(path), map_location=map_location, weights_only=False)
    check_config(st["config"], config)
    model.load_state_dict(st["model_state_dict"])
    optimizer.load_state_dict(st["optimizer_state_dict"])
    if scheduler is not None and st.get("scheduler_state_dict") is not None:
        scheduler.load_state_dict(st["scheduler_state_dict"])
    set_rng_state(st["rng"])
    return {"epoch": st["epoch"], "best": st["best"], "best_epoch": st["best_epoch"],
            "history": st["history"], "extra": st.get("extra", {})}
