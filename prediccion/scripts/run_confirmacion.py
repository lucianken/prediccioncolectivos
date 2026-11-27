"""
Lanzador de la confirmación A3 con grilla vs modelo por tramos en el subconjunto 12 + 3 (RESULTADOS.md).

6 corridas en secuencia, receta igualada (12 épocas, batch 1024, OneCycle, misma val; mejor checkpoint por MAE de val):
  1) LR 1e-3 y 2e-3 para cada modelo, semilla 0  (4 corridas)
  2) semilla 1 del mejor LR de cada modelo (el de menor MAE de val con semilla 0)  (2 corridas)
  3) evaluación de las 6 con la vara del subconjunto (train y control, con desglose por fase)

Retomable: una corrida terminada (existe su *_metrics.json) se saltea; una cortada se relanza con --resume y sigue desde
su last.pt. Si se corta la PC o el lanzador, volver a ejecutar el mismo comando. Lanzar desacoplado:
  Start-Process python -ArgumentList "-u","-m","prediccion.scripts.run_confirmacion" -WindowStyle Hidden -RedirectStandardOutput <log>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ML = Path("data/ml/v2_sub")
BASE = ML / "conf"
TRAIN_LINES = "26,39,42,92,124,151,168,50,106,107,108,132"
CONTROL_LINES = "12,15,128"
LRS = ("1e-3", "2e-3")
EPOCHS, BATCH = "12", "1024"


def run_dir(model: str, lr: str, seed: int) -> Path:
    return BASE / f"{model}_lr{lr}_s{seed}"


def metrics_path(model: str, d: Path) -> Path:
    return d / ("eta_a3_metrics.json" if model == "a3" else "path_eta_metrics.json")


def best_ckpt(model: str, d: Path) -> Path:
    return d / ("eta_a3_best.pt" if model == "a3" else "path_eta_best.pt")


def val_mae(model: str, d: Path) -> float:
    m = json.loads(metrics_path(model, d).read_text(encoding="utf-8"))
    return float(m["val_mae_s"] if model == "a3" else m["best_val_mae_s"])      # a3: con --select-by mae es el MAE


def train_cmd(model: str, lr: str, seed: int) -> list[str]:
    d = run_dir(model, lr, seed)
    common = ["--epochs", EPOCHS, "--batch-size", BATCH, "--lr", lr, "--seed", str(seed), "--resume"]
    if model == "a3":
        return [sys.executable, "-u", "-m", "prediccion.train", "--phase", "3", "--ml-dir", str(ML), "--output-dir", str(d),
                "--no-fleet", "--city-grid", "--device", "cuda", "--scheduler", "onecycle", "--patience", "99",
                "--select-by", "mae"] + common
    return [sys.executable, "-u", "-m", "prediccion.train_path", "--ml-dir", str(ML), "--out-dir", str(d)] + common


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(BASE / "launcher.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_training(model: str, lr: str, seed: int) -> None:
    d = run_dir(model, lr, seed)
    if metrics_path(model, d).exists():
        log(f"saltea {d.name}: ya terminó")
        return
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log(f"entrena {d.name}")
    with open(BASE / "logs" / f"{d.name}.log", "a", encoding="utf-8") as out:
        rc = subprocess.run(train_cmd(model, lr, seed), stdout=out, stderr=subprocess.STDOUT).returncode
    if rc != 0 or not metrics_path(model, d).exists():
        log(f"ERROR en {d.name} (rc={rc}); relanzar el lanzador para reanudar")
        raise SystemExit(1)
    log(f"terminó {d.name} en {(time.time() - t0) / 60:.1f} min; val MAE {val_mae(model, d):.1f}")


def run_eval(model: str, lr: str, seed: int) -> None:
    d = run_dir(model, lr, seed)
    kind = "a3" if model == "a3" else "path"
    for which, lines in (("seen", TRAIN_LINES), ("heldout", CONTROL_LINES)):
        tag = f"{d.name}_{which}"
        if list((BASE / "eval").glob(f"*{tag}.json")):
            continue
        cmd = [sys.executable, "-m", "prediccion.eval", "--model", f"{kind}:{best_ckpt(model, d)}", "--set", which,
               "--lines", lines, "--tag", tag, "--out-dir", str(BASE / "eval")]
        if model == "a3":
            cmd += ["--sdn", str(ML / "schedule_dev_medians.json")]
        log(f"evalúa {tag}")
        with open(BASE / "logs" / f"eval_{tag}.log", "a", encoding="utf-8") as out:
            rc = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT).returncode
        if rc != 0:
            log(f"ERROR evaluando {tag} (rc={rc})")
            raise SystemExit(1)


def main() -> int:
    (BASE / "logs").mkdir(parents=True, exist_ok=True)
    (BASE / "eval").mkdir(parents=True, exist_ok=True)
    log("inicio / reanudación del lanzador")
    for model in ("a3", "path"):
        for lr in LRS:
            run_training(model, lr, 0)
    best = {}
    for model in ("a3", "path"):
        maes = {lr: val_mae(model, run_dir(model, lr, 0)) for lr in LRS}
        best[model] = min(maes, key=maes.get)
        log(f"{model}: val MAE por LR (semilla 0) {maes}; mejor LR {best[model]}")
    for model in ("a3", "path"):
        run_training(model, best[model], 1)
    runs = [(m, lr, 0) for m in ("a3", "path") for lr in LRS] + [(m, best[m], 1) for m in ("a3", "path")]
    for m, lr, seed in runs:
        run_eval(m, lr, seed)
    (BASE / "summary.json").write_text(json.dumps({"best_lr": best, "runs": [f"{m}_lr{lr}_s{s}" for m, lr, s in runs]},
                                                  indent=1), encoding="utf-8")
    log("listo: 6 corridas entrenadas y evaluadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
