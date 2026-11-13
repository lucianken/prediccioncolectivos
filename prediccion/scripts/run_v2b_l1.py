"""
Lanzador reanudable: modelo por tramos con pérdida L1 (q 0,5 en todas las distancias) sobre los datos v2b.

Misma receta que run_v2b.py (LR 2e-3, 12 épocas, batch 1024, OneCycle), semillas 0 y 1; salida en
data/ml/v2b_sub/runs_l1/. Al final evalúa en data/ml/v2b/eval (seen y heldout) con el eval nuevo (llega antes / después
de lo anunciado) los dos modelos l1 y, para comparar en la misma tabla, los dos por tramos con pinball de runs/.
Retomable: volver a ejecutar el mismo comando. Lanzar desacoplado con Start-Process (ver run_v2b.py). `--smoke`: prueba rápida.
"""

from __future__ import annotations

import sys

from prediccion.scripts import run_v2b as R

SEEDS = (0, 1)
OLD_BASE = R.ML / "runs"
R.BASE = R.ML / ("runs_l1_smoke" if R.SMOKE else "runs_l1")


def main() -> int:
    (R.BASE / "logs").mkdir(parents=True, exist_ok=True)
    (R.BASE / "eval").mkdir(parents=True, exist_ok=True)
    R.log("inicio / reanudación del lanzador l1" + (" [smoke]" if R.SMOKE else ""))
    try:
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
        for s in SEEDS:
            d = R.run_dir("path", "2e-3", s)
            R.run_eval(f"path:{R.best_ckpt('path', d)}", "l1_" + d.name, [])
        if not R.SMOKE:
            for s in SEEDS:      # pinball viejos, re-evaluados con el eval nuevo
                d = OLD_BASE / f"path_lr2e-3_s{s}"
                R.run_eval(f"path:{R.best_ckpt('path', d)}", "pinball_" + d.name, [])
    except Exception as e:  # noqa: BLE001
        R.log(f"ERROR {e}")
        return 1
    R.log("listo: l1 entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
