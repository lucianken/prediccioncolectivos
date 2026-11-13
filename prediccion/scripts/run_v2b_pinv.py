"""
Segundo lanzador (encolado): modelo por tramos con `--loss pinball_inv` (q 0,5 -> 0,2 bajo 1 km), semillas 0 y 1, en
data/ml/v2b_sub/runs_l1/ (path_pinv_lr2e-3_s0/s1). Espera la línea final del lanzador l1 (run_v2b_l1.py) en el mismo
launcher.log; si ese terminó con ERROR, no sigue. Reanudable. Al final evalúa y escribe comparacion.md (pinball, l1, pinball_inv).
Línea final: `listo: l1 y pinball_inv entrenados y evaluados`.
"""

from __future__ import annotations

import json
import sys

from prediccion.scripts import run_v2b as R

R.BASE = R.ML / ("runs_l1_smoke" if R.SMOKE else "runs_l1")
SEEDS = (0, 1)
L1_DONE = "listo: l1 entrenado y evaluado"


def wait_for_l1() -> bool:
    lg = R.BASE / "launcher.log"
    while True:
        txt = lg.read_text(encoding="utf-8", errors="replace") if lg.exists() else ""
        if L1_DONE in txt:
            return True
        if "ERROR" in txt.splitlines()[-1:][0] if txt.strip() else False:
            return False
        R.time.sleep(30)


def latest(name: str, which: str) -> dict:
    fs = sorted((R.BASE / "eval" / name).glob(f"*_{which}_*.json"))
    return json.loads(fs[-1].read_text(encoding="utf-8"))


def comparison() -> None:
    groups = [("pinball", R.ML / "runs", "pinball_path_lr2e-3_s{s}"), ("l1", R.BASE, "l1_path_lr2e-3_s{s}"),
              ("pinball_inv", R.BASE, "pinv_path_pinv_lr2e-3_s{s}")]
    out = ["# Comparación de pérdidas, modelo por tramos (media de semillas 0 y 1)", "",
           "llega antes / después = % de filas con |error| > 60 s; espera extra = media de (real - pred) cuando llega después.", ""]
    for which in ("seen", "heldout"):
        out += [f"## {which}", "", "| pérdida | MAE (s) | 0-5 min: llega antes (%) | 0-5 min: llega después (%) | 0-5 min: espera extra (s) | "
                "<500 m: llega antes (%) | <500 m: llega después (%) | <500 m: espera extra (s) |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for label, _, pat in groups:
            rs = [latest(pat.format(s=s), which)["metrics"] for s in SEEDS]
            f = lambda sec, k, f_: sum(r[sec][k][f_] for r in rs) / len(rs)  # noqa: E731
            g = sum(r["global"]["mae"] for r in rs) / len(rs)
            out.append(f"| {label} | {g:.1f} | {f('by_eta', '0-5 min', 'pct_llega_antes_60s'):.1f} | {f('by_eta', '0-5 min', 'pct_llega_despues_60s'):.1f} | "
                       f"{f('by_eta', '0-5 min', 'espera_extra_media_s'):.1f} | {f('by_dist', '<500 m', 'pct_llega_antes_60s'):.1f} | "
                       f"{f('by_dist', '<500 m', 'pct_llega_despues_60s'):.1f} | {f('by_dist', '<500 m', 'espera_extra_media_s'):.1f} |")
        out.append("")
    (R.BASE / "comparacion.md").write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    (R.BASE / "logs").mkdir(parents=True, exist_ok=True)
    (R.BASE / "eval").mkdir(parents=True, exist_ok=True)
    R.log("lanzador pinball_inv: espera el final del lanzador l1" + (" [smoke]" if R.SMOKE else ""))
    try:
        if not R.SMOKE and not wait_for_l1():
            raise RuntimeError("el lanzador l1 terminó con ERROR; no se encola pinball_inv")
        for s in SEEDS:
            d = R.BASE / f"path_pinv_lr2e-3_s{s}"
            if R.metrics_path("path", d).exists():
                R.log(f"saltea {d.name}: ya terminó")
                continue
            d.mkdir(parents=True, exist_ok=True)
            R.log(f"entrena {d.name}")
            t0 = R.time.time()
            cmd = R.train_cmd("path", "2e-3", s)
            cmd[cmd.index("--out-dir") + 1] = str(d)
            rc = R.sh(cmd + ["--loss", "pinball_inv"], R.BASE / "logs" / f"{d.name}.log")
            if rc != 0 or not R.metrics_path("path", d).exists():
                raise RuntimeError(f"entrenando {d.name} (rc={rc}); relanzar para reanudar")
            R.log(f"terminó {d.name} en {(R.time.time() - t0) / 60:.1f} min; val MAE {R.val_mae('path', d):.1f}")
        for s in SEEDS:
            d = R.BASE / f"path_pinv_lr2e-3_s{s}"
            R.run_eval(f"path:{R.best_ckpt('path', d)}", "pinv_" + d.name, [])
        if not R.SMOKE:
            comparison()
    except Exception as e:  # noqa: BLE001
        R.log(f"ERROR {e}")
        return 1
    R.log("listo: l1 y pinball_inv entrenados y evaluados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
