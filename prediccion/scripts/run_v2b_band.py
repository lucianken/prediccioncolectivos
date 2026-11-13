"""
Lanzador reanudable: modelo por tramos con `--loss pinball_band` (q 0,3 en la banda de distancia donde cae la ETA 3-10 min,
rampa de 300 m a 0,5), receta de run_v2b.py (LR 2e-3, 12 épocas, batch 1024, OneCycle), semillas 0 y 1, en
data/ml/v2b_sub/runs_band/path_band_lr2e-3_s0/s1. Al final evalúa en data/ml/v2b/eval (seen y heldout) esos dos y los de
las otras pérdidas (pinball, l1, pinball_inv) con la tabla por bandas de ETA real, y escribe runs_band/comparacion.md.
Línea final del log: `listo: pinball_band entrenado y evaluado`. `--smoke`: prueba rápida (runs_band_smoke).
"""

from __future__ import annotations

import json
import sys

from prediccion.scripts import run_v2b as R

R.BASE = R.ML / ("runs_band_smoke" if R.SMOKE else "runs_band")
SEEDS = (0, 1)
# etiqueta -> directorio de la corrida, por semilla
LOSSES = [("pinball", lambda s: R.ML / "runs" / f"path_lr2e-3_s{s}"),
          ("l1", lambda s: R.ML / "runs_l1" / f"path_lr2e-3_s{s}"),
          ("pinball_inv", lambda s: R.ML / "runs_l1" / f"path_pinv_lr2e-3_s{s}"),
          ("pinball_band", lambda s: R.BASE / f"path_band_lr2e-3_s{s}")]
MAIN = "3-7 min (principal)"
BANDS = ["0-2 min", "2-4 min", "4-6 min", "6-8 min", "8-10 min", "10-15 min", "15-20 min", MAIN]
KEYS = [("mae", "MAE (s)"), ("p90", "P90 error abs. (s)"), ("pct_llega_antes_60s", "llega antes >60 s (%)"),
        ("pct_llega_despues_60s", "llega después >60 s (%)"), ("espera_extra_media_s", "espera extra media (s)")]


def ename(label: str, s: int) -> str:
    return f"{label}_s{s}"


def load(label: str, s: int, which: str) -> dict:
    fs = sorted((R.BASE / "eval" / ename(label, s)).glob(f"*_{which}_*.json"))
    return json.loads(fs[-1].read_text(encoding="utf-8"))["by_eta_band"]


def comparison() -> None:
    out = ["# Comparación de pérdidas por banda de ETA real, modelo por tramos", "",
           "Eval `data/ml/v2b/eval` (30.000 filas por conjunto). Cada celda es la media de las semillas 0 y 1. "
           "Llega antes / después = % de filas con |error| > 60 s; espera extra = media de (real - pred) cuando llega después. "
           f"Banda principal: {MAIN}.", ""]
    for which in ("seen", "heldout"):
        data = {lb: [load(lb, s, which) for s in SEEDS] for lb, _ in LOSSES}
        for band in BANDS:
            n = int(data["pinball"][0][band]["n"])
            out += [f"## {which}: ETA real {band} (n = {n})", "",
                    "| pérdida | " + " | ".join(h for _, h in KEYS) + " |", "|---|" + "---:|" * len(KEYS)]
            for lb, _ in LOSSES:
                vals = [sum(r[band][k] for r in data[lb]) / len(SEEDS) for k, _ in KEYS]
                out.append(f"| {lb} | " + " | ".join(f"{v:.1f}" for v in vals) + " |")
            out.append("")
        out += [f"## {which}: diferencia entre semillas en {MAIN}", "",
                "| pérdida | MAE s0 / s1 (s) | dif. MAE (s) | llega antes s0 / s1 (%) | dif. llega antes (pp) |", "|---|---|---:|---|---:|"]
        for lb, _ in LOSSES:
            a, b = (data[lb][i][MAIN] for i in (0, 1))
            out.append(f"| {lb} | {a['mae']:.1f} / {b['mae']:.1f} | {abs(a['mae'] - b['mae']):.1f} | "
                       f"{a['pct_llega_antes_60s']:.1f} / {b['pct_llega_antes_60s']:.1f} | "
                       f"{abs(a['pct_llega_antes_60s'] - b['pct_llega_antes_60s']):.1f} |")
        out.append("")
    (R.BASE / "comparacion.md").write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    (R.BASE / "logs").mkdir(parents=True, exist_ok=True)
    (R.BASE / "eval").mkdir(parents=True, exist_ok=True)
    R.log("inicio / reanudación del lanzador pinball_band" + (" [smoke]" if R.SMOKE else ""))
    try:
        for s in SEEDS:
            d = LOSSES[3][1](s)
            if R.metrics_path("path", d).exists():
                R.log(f"saltea {d.name}: ya terminó")
                continue
            d.mkdir(parents=True, exist_ok=True)
            R.log(f"entrena {d.name}")
            t0 = R.time.time()
            cmd = R.train_cmd("path", "2e-3", s)
            cmd[cmd.index("--out-dir") + 1] = str(d)
            rc = R.sh(cmd + ["--loss", "pinball_band"], R.BASE / "logs" / f"{d.name}.log")
            if rc != 0 or not R.metrics_path("path", d).exists():
                raise RuntimeError(f"entrenando {d.name} (rc={rc}); relanzar para reanudar")
            R.log(f"terminó {d.name} en {(R.time.time() - t0) / 60:.1f} min; val MAE {R.val_mae('path', d):.1f}")
        for label, dirf in (LOSSES[3:] if R.SMOKE else LOSSES):
            for s in SEEDS:
                R.run_eval(f"path:{R.best_ckpt('path', dirf(s))}", ename(label, s), [])
        if not R.SMOKE:
            comparison()
    except Exception as e:  # noqa: BLE001
        R.log(f"ERROR {e}")
        return 1
    R.log("listo: pinball_band entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
