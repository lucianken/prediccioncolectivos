"""Resume las 6 corridas de la confirmación (lee data/ml/v2_sub/conf/eval/*.json y summary.json) y escribe markdown."""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

BASE = Path("data/ml/v2_sub/conf")


def load(name: str, which: str) -> dict:
    f = glob.glob(str(BASE / "eval" / f"*{name}_{which}.json"))
    return json.loads(Path(f[0]).read_text(encoding="utf-8"))


def row(r: dict) -> dict:
    m, p = r["metrics"], r["phase"]
    return {"global": m["global"]["mae"], "bias": m["global"]["bias"], "u60": m["global"]["pct_under_60s"],
            "eta": [m["by_eta"][k]["mae"] for k in m["by_eta"]], "dist": [m["by_dist"][k]["mae"] for k in m["by_dist"]],
            "u05": m["by_eta"]["0-5 min"]["pct_under_60s"], "inicio": p["inicio de viaje"]["mae"],
            "resto": p["resto del viaje"]["mae"], "sin_inicio": p["global sin inicio de viaje"]["mae"],
            "det": p["P detenido"]["mae"], "mov": p["P en movimiento"]["mae"]}


def fmt(v, n=1):
    return f"{v:.{n}f}"


def main():
    s = json.loads((BASE / "summary.json").read_text(encoding="utf-8"))
    names = s["runs"]
    out = []
    for which, title in (("seen", "train (12 líneas)"), ("heldout", "control (12, 15, 128)")):
        out += [f"### {title}", "", "| corrida | global | sesgo | subest.>60 s global | MAE 0–5 / 5–10 / 10–20 / 20+ | subest. 0–5 | por distancia | inicio | resto | sin inicio | detenido | en mov. |",
                "|---|---:|---:|---:|---|---:|---|---:|---:|---:|---:|---:|"]
        for n in names:
            r = row(load(n, which))
            out.append(f"| {n} | {fmt(r['global'])} | {fmt(r['bias'])} | {fmt(r['u60'])} | {' / '.join(f'{x:.0f}' for x in r['eta'])} | "
                       f"{fmt(r['u05'])} | {' / '.join(f'{x:.0f}' for x in r['dist'])} | {fmt(r['inicio'])} | {fmt(r['resto'])} | "
                       f"{fmt(r['sin_inicio'])} | {fmt(r['det'])} | {fmt(r['mov'])} |")
        out.append("")
        # mejor LR: 2 semillas
        res = {}
        for model in ("a3", "path"):
            lr = s["best_lr"][model]
            a, b = row(load(f"{model}_lr{lr}_s0", which)), row(load(f"{model}_lr{lr}_s1", which))
            res[model] = (a, b)
            out.append(f"- **{model}** (LR {lr}): global semillas {fmt(a['global'])} / {fmt(b['global'])}, media {fmt((a['global'] + b['global']) / 2)}, "
                       f"diferencia entre semillas {fmt(abs(a['global'] - b['global']))}; sin inicio {fmt((a['sin_inicio'] + b['sin_inicio']) / 2)}; "
                       f"20+ min {fmt((a['eta'][3] + b['eta'][3]) / 2)}")
        ma = np.mean([x["global"] for x in res["a3"]])
        mp = np.mean([x["global"] for x in res["path"]])
        d = max(abs(res["a3"][0]["global"] - res["a3"][1]["global"]), abs(res["path"][0]["global"] - res["path"][1]["global"]))
        out.append(f"- ventaja del modelo por tramos sobre A3 (media de 2 semillas): {fmt(ma - mp)} s ({fmt(100 * (ma - mp) / ma)} %); "
                   f"mayor diferencia entre semillas: {fmt(d)} s; ventaja / diferencia = {fmt((ma - mp) / max(d, 1e-9))}")
        out.append("")
    Path(BASE / "resumen.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
