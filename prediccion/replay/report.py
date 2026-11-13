"""Informe markdown del replay: python -m prediccion.replay.report --run data/ml/replay/run1 --out data/ml/replay/ORACULO_RAMAL.md [--conclusion f.md]"""
from __future__ import annotations

import argparse
from pathlib import Path

from prediccion.replay import metrics as M

VARS = ("base", "sentido", "ramal")
NAMES = {"base": "base (ramal y sentido desconocidos)", "sentido": "solo sentido conocido", "ramal": "oráculo ramal"}


def f(x, d=1):
    return "—" if x is None or x != x else f"{x:.{d}f}"


def scope_table(inst, veh, title, **sel) -> str:
    rows = []
    for v in VARS:
        i, w = M.select(inst, veh, variant=v, **sel)
        if not len(i):
            continue
        s = M.summarize(i, w)
        rows.append((v, s))
    if not rows:
        return ""
    out = [f"#### {title}", "",
           "| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for v, s in rows:
        a, b, g = s["prox_seguro_banda"], s["prox_seguro_o_fallback_banda"], s["prox_seguro_o_fallback_global"]
        fa = s["falsas"]
        out.append(f"| {NAMES[v]} | {s['cobertura']['instantes']} | {s['cobertura']['coches_evaluados']} | {f(s['cobertura']['con_paso_20min_pct'])} | "
                   f"{f(a['mae_s'],0)} (n={a['n']}) | {f(a['antes_pct'])} / {f(a['despues_pct'])} | {f(b['mae_s'],0)} | {f(b['antes_pct'])} / {f(b['despues_pct'])} | "
                   f"{f(g['mae_s'],0)} (n={g['n']}) | {f(b['sin_anuncio_pct'])} | {f(fa['falsa_alarma_pct'])} ({f(fa['fa_seguro_pct'])} / {f(fa['fa_puede_venir_pct'])} / {f(fa['fa_provisional_pct'])}) | "
                   f"{f(s['omisiones']['omision_pct'])} (n={s['omisiones']['visibles']}) | {f(s['seguro_vacio']['sin_seguro_pct'])} (n={s['seguro_vacio']['n']}) |")
    return "\n".join(out) + "\n"


def per_line_table(inst, veh) -> str:
    out = ["#### Por línea: base → oráculo ramal", "",
           "| línea | n (parada,t) | MAE 3–7 min base → ramal (s) | falsas alarmas % | omisión % | seguro vacío % | MAE 3–7 min en tronco compartido | en exclusivo |",
           "|---|---|---|---|---|---|---|---|"]
    for ln in sorted(inst.line.unique(), key=lambda x: (len(x), x)):
        r = {}
        for v in ("base", "ramal"):
            i, w = M.select(inst, veh, variant=v, line=ln)
            r[v] = M.summarize(i, w)
        def mae(v, cls):
            i, w = M.select(inst, veh, variant=v, line=ln, cls=cls)
            return M.next_bus(i, "ann_any_s", *M.BAND)["mae_s"]
        pair = lambda k, sub, d=0: f"{f(r['base'][k][sub], d)} → {f(r['ramal'][k][sub], d)}"  # noqa: E731
        out.append(f"| {ln} | {r['base']['cobertura']['instantes']} | {pair('prox_seguro_o_fallback_banda','mae_s')} | {pair('falsas','falsa_alarma_pct',1)} | "
                   f"{pair('omisiones','omision_pct',1)} | {pair('seguro_vacio','sin_seguro_pct',1)} | "
                   f"{f(mae('base',['compartido']),0)} → {f(mae('ramal',['compartido']),0)} | {f(mae('base',['exclusivo']),0)} → {f(mae('ramal',['exclusivo']),0)} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--conclusion", default=None)
    ap.add_argument("--header", default="")
    a = ap.parse_args()
    inst, veh = M.load_run(a.run)
    days = sorted(inst.day.unique())
    parts = [a.header]
    if a.conclusion:
        parts.append(Path(a.conclusion).read_text(encoding="utf-8"))
    parts += ["## Tablas", "",
              f"Días: {', '.join(days)}. Líneas: {', '.join(sorted(inst.line.unique(), key=lambda x:(len(x),x)))}. "
              "Criterio «seguro»: primer coche del grupo pasa seguro (solo instantes en que hay); «seguro-o-fallback»: primero de pasa seguro y, si no hay, primero de pueden venir/provisional. "
              "«Antes»: el coche llega >60 s antes de lo anunciado; «después»: >60 s después.", "",
              scope_table(inst, veh, "Global"), scope_table(inst, veh, "Línea 39", line="39"),
              scope_table(inst, veh, "Tronco compartido (todas las líneas)", cls=["compartido"]),
              scope_table(inst, veh, "Tramo exclusivo (todas las líneas)", cls=["exclusivo"]),
              scope_table(inst, veh, "Línea 39, tronco compartido", line="39", cls=["compartido"]),
              scope_table(inst, veh, "Línea 39, tramo exclusivo", line="39", cls=["exclusivo"]),
              scope_table(inst, veh, "Líneas con un solo recorrido por sentido (paradas «únicas»)", cls=["unico"]),
              per_line_table(inst, veh)]
    Path(a.out).write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    main()
