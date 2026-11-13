"""
Lanzador del reentrenamiento sobre los datos v2b (segmentador nuevo; ARQUITECTURA.md §7, paso 6.2.5).

Misma receta que la confirmación (`run_confirmacion.py`): 12 épocas, batch 1024, OneCycle, pinball, mejor checkpoint por
MAE de val. Corridas, en secuencia, salida en data/ml/v2b_sub/runs/:
  - A3 + grilla, LR 1e-3, semillas 0 y 1
  - por tramos, LR 2e-3, semillas 0 y 1
  - A1 (tabla) sobre v2b_sub
Al final evalúa todo en data/ml/v2b/eval (seen = 12 líneas de train, heldout = 12, 15, 128) con la misma vara
(desglose por fase incluido) más el desglose por inicio conocido / desconocido.

Retomable: una corrida terminada (existe su *_metrics.json) se saltea; una cortada se relanza con --resume y sigue desde
su last.pt; una evaluación ya hecha se saltea. Si se corta, volver a ejecutar el mismo comando. Lanzar desacoplado:
  Start-Process python -ArgumentList "-u","-m","prediccion.scripts.run_v2b" -WindowStyle Hidden -RedirectStandardOutput <log>
`--smoke` hace una prueba rápida (pocos row groups, 1 época, directorio aparte) de cada modelo y de la evaluación.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ML = Path("data/ml/v2b_sub")
V2B = Path("data/ml/v2b")
BASE = ML / "runs"
EPOCHS, BATCH = "12", "1024"
RUNS = [("a3", "1e-3", 0), ("a3", "1e-3", 1), ("path", "2e-3", 0), ("path", "2e-3", 1)]
SMOKE = "--smoke" in sys.argv
if SMOKE:
    BASE = ML / "runs_smoke"
    EPOCHS = "1"


def run_dir(model: str, lr: str, seed: int) -> Path:
    return BASE / f"{model}_lr{lr}_s{seed}"


def metrics_path(model: str, d: Path) -> Path:
    return d / ("eta_a3_metrics.json" if model == "a3" else "path_eta_metrics.json")


def best_ckpt(model: str, d: Path) -> Path:
    return d / ("eta_a3_best.pt" if model == "a3" else "path_eta_best.pt")


def val_mae(model: str, d: Path) -> float:
    m = json.loads(metrics_path(model, d).read_text(encoding="utf-8"))
    return float(m["val_mae_s"] if model == "a3" else m["best_val_mae_s"])


def train_cmd(model: str, lr: str, seed: int) -> list[str]:
    d = run_dir(model, lr, seed)
    common = ["--epochs", EPOCHS, "--batch-size", BATCH, "--lr", lr, "--seed", str(seed), "--resume"]
    if SMOKE:
        common += ["--max-groups", "3"]
    if model == "a3":
        return [sys.executable, "-u", "-m", "prediccion.train", "--phase", "3", "--ml-dir", str(ML), "--output-dir", str(d),
                "--no-fleet", "--city-grid", "--device", "cuda", "--scheduler", "onecycle", "--patience", "99",
                "--select-by", "mae"] + common
    return [sys.executable, "-u", "-m", "prediccion.train_path", "--ml-dir", str(ML), "--out-dir", str(d),
            "--lines-file", str(V2B / "lines.json")] + common


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(BASE / "launcher.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def sh(cmd: list[str], logfile: Path) -> int:
    with open(logfile, "a", encoding="utf-8") as out:
        return subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT,
                              env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}).returncode


def run_training(model: str, lr: str, seed: int) -> None:
    d = run_dir(model, lr, seed)
    if metrics_path(model, d).exists():
        log(f"saltea {d.name}: ya terminó")
        return
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log(f"entrena {d.name}")
    rc = sh(train_cmd(model, lr, seed), BASE / "logs" / f"{d.name}.log")
    if rc != 0 or not metrics_path(model, d).exists():
        raise RuntimeError(f"entrenando {d.name} (rc={rc}); relanzar el lanzador para reanudar")
    log(f"terminó {d.name} en {(time.time() - t0) / 60:.1f} min; val MAE {val_mae(model, d):.1f}")


def run_a1() -> Path:
    d = BASE / "a1"
    found = sorted(d.glob("a1_v*.pkl"))
    if found:
        log("saltea a1: ya terminó")
        return found[-1]
    d.mkdir(parents=True, exist_ok=True)
    log("entrena a1")
    rc = sh([sys.executable, "-u", "-m", "prediccion.train", "--phase", "1", "--ml-dir", str(ML), "--skip-build",
             "--output-dir", str(d)], BASE / "logs" / "a1.log")
    found = sorted(d.glob("a1_v*.pkl"))
    if rc != 0 or not found:
        raise RuntimeError(f"entrenando a1 (rc={rc})")
    log(f"terminó a1: {found[-1].name}")
    return found[-1]


def run_eval(spec: str, name: str, extra: list[str]) -> None:
    for which in ("seen", "heldout"):
        out = BASE / "eval" / name
        if list(out.glob(f"*_{which}_*.json")):
            continue
        cmd = [sys.executable, "-m", "prediccion.eval", "--model", spec, "--set", which, "--v2-dir", str(V2B),
               "--out-dir", str(out)] + extra
        log(f"evalúa {name} {which}")
        rc = sh(cmd, BASE / "logs" / f"eval_{name}_{which}.log")
        if rc != 0:
            raise RuntimeError(f"evaluando {name} {which} (rc={rc})")


def main() -> int:
    (BASE / "logs").mkdir(parents=True, exist_ok=True)
    (BASE / "eval").mkdir(parents=True, exist_ok=True)
    log("inicio / reanudación del lanzador" + (" [smoke]" if SMOKE else ""))
    try:
        for model, lr, seed in RUNS:
            run_training(model, lr, seed)
        a1 = run_a1()
        for model, lr, seed in RUNS:
            d = run_dir(model, lr, seed)
            kind = "a3" if model == "a3" else "path"
            extra = ["--sdn", str(ML / "schedule_dev_medians.json")] if model == "a3" else []
            run_eval(f"{kind}:{best_ckpt(model, d)}", d.name, extra)
        run_eval(f"a1:{a1}", "a1", [])
        (BASE / "summary.json").write_text(json.dumps({"runs": [f"{m}_lr{lr}_s{s}" for m, lr, s in RUNS] + ["a1"]},
                                                      indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log(f"ERROR {e}")
        return 1
    log("listo: v2b entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
