"""
Lanzador reanudable de v2c: dataset con asignación geométrica `geo3` (prediccion/v2/geo_assign.py), subconjunto,
eval y modelo por tramos con pérdida L1 (RESULTADOS.md).

Etapas, todas idempotentes (se saltean si ya están hechas; si algo se corta, volver a ejecutar el mismo comando):
  1. build de las 15 líneas en data/ml/v2c (segmentación geo2, asignación geo3, K=32, 2026-03-28:2026-10-14, 3 workers,
     prioridad baja; reanuda por día)
  2. subconjunto data/ml/v2c_sub (12 líneas, train desde 2026-07-20, 40 % de la val) y eval congelado data/ml/v2c/eval
     (7.500 filas por bucket de ETA) con la misma receta que v2b_sub / v2b/eval
  3. modelo por tramos `--loss l1`, LR 2e-3, 12 épocas, OneCycle, batch 1024, semillas 0 y 1 -> data/ml/v2c_sub/runs/
  4. evaluación en data/ml/v2c/eval (seen y heldout) de esos dos y, como comparación sobre el MISMO eval, de los L1 entrenados
     sobre v2b (data/ml/v2b_sub/runs_l1/path_lr2e-3_s0/s1); tabla por bandas de ETA real (principal 3-7 min) en
     runs/comparacion.md
Línea final del log (runs/launcher.log): `listo: v2c entrenado y evaluado` o `ERROR ...`.

Lanzar desacoplado (las tareas de fondo mueren a las 2 h):
  Start-Process python -ArgumentList "-u","-m","prediccion.scripts.run_v2c" -WindowStyle Hidden -RedirectStandardOutput <log>
`--smoke`: prueba rápida de entrenamiento y evaluación (pocos row groups, 1 época) sobre los datos v2b, en
data/ml/v2c_sub/runs_smoke; no corre el build ni el ensamblado.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from prediccion.scripts import run_v2b as R

V2C = Path("data/ml/v2c")
SUB = Path("data/ml/v2c_sub")
V2B_SUB = Path("data/ml/v2b_sub")
LINES_12 = "26,39,42,92,124,151,168,50,106,107,108,132"
LINES_15 = LINES_12 + ",12,15,128"
SEEDS = (0, 1)
SMOKE = R.SMOKE

# El trainer y las evaluaciones usan los directorios de run_v2b; en smoke se prueban sobre v2b (el v2c no existe todavía)
R.ML = V2B_SUB if SMOKE else SUB
R.V2B = Path("data/ml/v2b") if SMOKE else V2C
R.BASE = SUB / ("runs_smoke" if SMOKE else "runs")

OLD = [("v2b_l1", lambda s: V2B_SUB / "runs_l1" / f"path_lr2e-3_s{s}")]
NEW = [("v2c_l1", lambda s: R.BASE / f"path_lr2e-3_s{s}")]
MAIN = "3-7 min (principal)"
BANDS = ["0-2 min", "2-4 min", "4-6 min", "6-8 min", "8-10 min", "10-15 min", "15-20 min", MAIN]
KEYS = [("mae", "MAE (s)"), ("p90", "P90 error abs. (s)"), ("pct_llega_antes_60s", "llega antes >60 s (%)"),
        ("pct_llega_despues_60s", "llega después >60 s (%)"), ("espera_extra_media_s", "espera extra media (s)")]


def step(cmd: list[str], logname: str) -> None:
    rc = R.sh(cmd, R.BASE / "logs" / logname)
    if rc != 0:
        raise RuntimeError(f"{' '.join(cmd[2:5])} (rc={rc}); ver logs/{logname} y relanzar para reanudar")


def build_and_assemble() -> None:
    py = [sys.executable, "-u", "-m"]
    R.log("build v2c (reanuda por día)")
    step(py + ["prediccion.v2.build", "--lines-file", "data/ml/v2/lines.json", "--lines", LINES_15,
               "--days", "2026-03-28:2026-10-14", "--pairs-per-trip", "32", "--workers", "3", "--segmentation", "geo2",
               "--assign", "geo3", "--low-priority", "--out-dir", str(V2C), "--no-assemble",
               "--data-dir", "//192.168.0.18/buffer/grabaciones"], "build.log")
    lf = V2C / "lines.json"
    if not lf.exists():
        lf.write_text(Path("data/ml/v2b/lines.json").read_text(encoding="utf-8"), encoding="utf-8")
    if not (SUB / "assembled.json").exists():
        R.log("ensambla v2c_sub")
        step(py + ["prediccion.v2.assemble", "--v2-dir", str(V2C), "--lines-file", str(lf), "--only-lines", LINES_12,
                   "--dest", str(SUB), "--train-start", "2026-07-20", "--val-sample-frac", "0.4"], "assemble.log")
    if not (V2C / "eval" / "eval_seen.parquet").exists():
        R.log("congela el eval v2c")
        step(py + ["prediccion.v2.make_eval", "--v2-dir", str(V2C), "--lines-file", str(lf), "--n-per-bucket", "7500"],
             "make_eval.log")


def ename(label: str, s: int) -> str:
    return f"{label}_s{s}"


def load(label: str, s: int, which: str) -> dict:
    fs = sorted((R.BASE / "eval" / ename(label, s)).glob(f"*_{which}_*.json"))
    return json.loads(fs[-1].read_text(encoding="utf-8"))["by_eta_band"]


def comparison() -> None:
    labels = [lb for lb, _ in OLD + NEW]
    out = ["# Comparación sobre el eval de v2c, modelo por tramos con pérdida L1", "",
           "Eval `data/ml/v2c/eval` (30.000 filas por conjunto, asignación geo3). `v2b_l1`: entrenado sobre v2b "
           "(`data/ml/v2b_sub/runs_l1`); `v2c_l1`: entrenado sobre v2c. Cada celda es la media de las semillas 0 y 1. "
           "Llega antes / después = % de filas con |error| > 60 s; espera extra = media de (real - pred) cuando llega "
           f"después. Banda principal: {MAIN}.", ""]
    for which in ("seen", "heldout"):
        data = {lb: [load(lb, s, which) for s in SEEDS] for lb in labels}
        for band in [MAIN] + [b for b in BANDS if b != MAIN]:
            n = int(data[labels[0]][0][band]["n"])
            out += [f"## {which}: ETA real {band} (n = {n})", "",
                    "| modelo | " + " | ".join(h for _, h in KEYS) + " |", "|---|" + "---:|" * len(KEYS)]
            for lb in labels:
                vals = [sum(r[band][k] for r in data[lb]) / len(SEEDS) for k, _ in KEYS]
                out.append(f"| {lb} | " + " | ".join(f"{v:.1f}" for v in vals) + " |")
            out.append("")
        out += [f"## {which}: semillas 0 / 1 en {MAIN}", "", "| modelo | MAE s0 / s1 (s) | llega antes s0 / s1 (%) |", "|---|---|---|"]
        for lb in labels:
            a, b = (data[lb][i][MAIN] for i in (0, 1))
            out.append(f"| {lb} | {a['mae']:.1f} / {b['mae']:.1f} | "
                       f"{a['pct_llega_antes_60s']:.1f} / {b['pct_llega_antes_60s']:.1f} |")
        out.append("")
    (R.BASE / "comparacion.md").write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    (R.BASE / "logs").mkdir(parents=True, exist_ok=True)
    (R.BASE / "eval").mkdir(parents=True, exist_ok=True)
    R.log("inicio / reanudación del lanzador v2c" + (" [smoke]" if SMOKE else ""))
    try:
        if not SMOKE:
            build_and_assemble()
        for s in SEEDS:
            d = R.run_dir("path", "2e-3", s)
            if R.metrics_path("path", d).exists():
                R.log(f"saltea {d.name}: ya terminó")
                continue
            d.mkdir(parents=True, exist_ok=True)
            R.log(f"entrena {d.name}")
            t0 = R.time.time()
            rc = R.sh(R.train_cmd("path", "2e-3", s) + ["--loss", "l1"], R.BASE / "logs" / f"{d.name}.log")
            if rc != 0 or not R.metrics_path("path", d).exists():
                raise RuntimeError(f"entrenando {d.name} (rc={rc}); relanzar el lanzador para reanudar")
            R.log(f"terminó {d.name} en {(R.time.time() - t0) / 60:.1f} min; val MAE {R.val_mae('path', d):.1f}")
        for label, dirf in (NEW if SMOKE else NEW + OLD):
            for s in SEEDS:
                R.run_eval(f"path:{R.best_ckpt('path', dirf(s))}", ename(label, s), [])
        if not SMOKE:
            comparison()
    except Exception as e:  # noqa: BLE001
        R.log(f"ERROR {e}")
        return 1
    R.log("listo: v2c entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
