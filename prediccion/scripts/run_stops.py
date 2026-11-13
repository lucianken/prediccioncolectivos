"""
Lanzador reanudable del experimento "Paradas por tramo" (ARQUITECTURA.md §6.2): modelo por tramos con la entrada nueva
(`--stops-feature`: paradas del recorrido en cada tramo de 250 m y metros a la próxima parada), misma receta que v2c.

Etapas, todas idempotentes (si algo se corta, volver a ejecutar el mismo comando):
  1. entrenamiento sobre data/ml/v2c_sub, `--loss l1`, LR 2e-3, 12 épocas, OneCycle, batch 1024, semillas 0 y 1
     -> data/ml/v2c_sub/runs_stops/path_lr2e-3_s{0,1}
  2. evaluación en data/ml/v2c/eval (seen y heldout) de esos dos y, sobre el MISMO eval, de los v2c L1
     (data/ml/v2c_sub/runs/path_lr2e-3_s0/s1)
  3. runs_stops/comparacion.md: tabla por bandas de ETA real (principal 3-7 min), media de semillas, diferencia entre
     semillas y veredicto según el criterio de adopción (mejora en 3-7 min mayor que la diferencia entre semillas)
Línea final de runs_stops/launcher.log: `listo: paradas entrenado y evaluado` o `ERROR ...`.

Lanzar desacoplado (las tareas de fondo mueren a las 2 h):
  Start-Process python -ArgumentList "-u","-m","prediccion.scripts.run_stops" -WindowStyle Hidden -RedirectStandardOutput <log>
`--smoke`: prueba rápida (pocos row groups, 1 época) sobre los datos v2b, en data/ml/v2c_sub/runs_stops_smoke.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from prediccion.scripts import run_v2b as R
from prediccion.scripts.run_v2c import BANDS, KEYS, MAIN, SEEDS, SUB, V2B_SUB, V2C

SMOKE = R.SMOKE
R.ML = V2B_SUB if SMOKE else SUB
R.V2B = Path("data/ml/v2b") if SMOKE else V2C
R.BASE = SUB / ("runs_stops_smoke" if SMOKE else "runs_stops")

BASE_RUNS = SUB / "runs"          # v2c L1, referencia
OLD = [("v2c_l1", lambda s: BASE_RUNS / f"path_lr2e-3_s{s}")]
NEW = [("v2c_l1_paradas", lambda s: R.BASE / f"path_lr2e-3_s{s}")]


def ename(label: str, s: int) -> str:
    return f"{label}_s{s}"


def load(label: str, s: int, which: str) -> dict:
    fs = sorted((R.BASE / "eval" / ename(label, s)).glob(f"*_{which}_*.json"))
    return json.loads(fs[-1].read_text(encoding="utf-8"))["by_eta_band"]


def comparison() -> None:
    (ref, _), (new, _) = OLD[0], NEW[0]
    out = ["# Paradas por tramo contra v2c L1, mismo eval (`data/ml/v2c/eval`)", "",
           f"`{ref}`: modelo por tramos L1 sin la feature (`data/ml/v2c_sub/runs`); `{new}`: igual con `--stops-feature`. "
           "Cada celda es la media de las semillas 0 y 1. Llega antes / después = % de filas con error > 60 s; espera "
           f"extra = media de (real - pred) cuando llega después. Banda principal: {MAIN}. Criterio de adopción "
           "(ARQUITECTURA §6.2): mejora del MAE en 3-7 min mayor que la diferencia entre semillas.", ""]
    verdict = []
    for which in ("seen", "heldout"):
        data = {lb: [load(lb, s, which) for s in SEEDS] for lb in (ref, new)}
        for band in [MAIN] + [b for b in BANDS if b != MAIN]:
            n = int(data[ref][0][band]["n"])
            out += [f"## {which}: ETA real {band} (n = {n})", "",
                    "| modelo | " + " | ".join(h for _, h in KEYS) + " |", "|---|" + "---:|" * len(KEYS)]
            for lb in (ref, new):
                out.append(f"| {lb} | " + " | ".join(f"{sum(r[band][k] for r in data[lb]) / len(SEEDS):.1f}" for k, _ in KEYS) + " |")
            out.append("")
        out += [f"## {which}: semillas 0 / 1 en {MAIN}", "",
                "| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) |", "|---|---|---:|---|"]
        mae, gap = {}, {}
        for lb in (ref, new):
            a, b = (data[lb][i][MAIN] for i in (0, 1))
            mae[lb], gap[lb] = (a["mae"] + b["mae"]) / 2, abs(a["mae"] - b["mae"])
            out.append(f"| {lb} | {a['mae']:.1f} / {b['mae']:.1f} | {gap[lb]:.1f} | "
                       f"{a['pct_llega_antes_60s']:.1f} / {b['pct_llega_antes_60s']:.1f} |")
        gain = mae[ref] - mae[new]
        thr = max(gap.values())
        verdict.append((which, gain, thr))
        out += ["", f"Mejora del MAE medio en {MAIN}: {gain:+.1f} s (diferencia entre semillas: {thr:.1f} s, la mayor de las dos "
                    f"familias) -> {'supera' if gain > thr else 'no supera'} el criterio.", ""]
    out += ["## Veredicto", ""] + [f"- {w}: mejora {g:+.1f} s contra diferencia entre semillas {t:.1f} s -> "
                                   f"{'SUPERA' if g > t else 'no supera'}" for w, g, t in verdict]
    (R.BASE / "comparacion.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    (R.BASE / "logs").mkdir(parents=True, exist_ok=True)
    (R.BASE / "eval").mkdir(parents=True, exist_ok=True)
    R.log("inicio / reanudación del lanzador paradas" + (" [smoke]" if SMOKE else ""))
    try:
        for s in SEEDS:
            d = R.run_dir("path", "2e-3", s)
            if R.metrics_path("path", d).exists():
                R.log(f"saltea {d.name}: ya terminó")
                continue
            d.mkdir(parents=True, exist_ok=True)
            R.log(f"entrena {d.name}")
            t0 = R.time.time()
            rc = R.sh(R.train_cmd("path", "2e-3", s) + ["--loss", "l1", "--stops-feature"], R.BASE / "logs" / f"{d.name}.log")
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
    R.log("listo: paradas entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
