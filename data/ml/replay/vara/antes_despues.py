"""Tablas antes / después de la verdad por recorrido ex post (2026-11-16, segunda corrección).
antes = run_*_sg (verdad corregida sin filtro por recorrido); después = run_*_xp (con el filtro). Mismas filas y predicciones.
Uso: python antes_despues.py OUT_MD
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from prediccion.replay import report_vara as RV  # noqa: E402

V = ROOT / "data/ml/replay/vara"
D10 = "2026-09-15,2026-09-16,2026-09-17,2026-09-18,2026-09-19,2026-09-20,2026-10-03,2026-10-04,2026-10-06,2026-10-08".split(",")
D6 = "2026-09-23,2026-09-24,2026-09-25,2026-09-26,2026-10-02,2026-10-03".split(",")

ROWS = [("Falsas alarmas %, todo ETA anunciado", "fa", 1), ("Falsas alarmas %, ETA anunciado 3–7 min", "fa_37", 1),
        ("  «viene» %", "fa_seg", 1), ("  «puede venir» %", "fa_pv", 1), ("  «sentido sin confirmar» %", "fa_prov", 1),
        ("Omisión ≤10 min %", "om", 1), ("  n coches que pasan en ≤10 min con ping vigente", "om_n", 0),
        ("«Viene» vacío %", "vacio", 1), ("  n instantes con paso ≤10 min", "vacio_n", 0),
        ("MAE próximo coche 3–7 min (s)", "mae", 0), ("  n instantes en la banda", "n_band", 0),
        ("Llega antes >60 s % (3–7)", "antes", 1), ("Llega después >60 s % (3–7)", "desp", 1), ("Sin anuncio % (3–7)", "sin_anuncio", 1),
        ("MAE solo «viene» 3–7 (s)", "mae_seg", 0), ("Coches listados", "listados", 0),
        ("Listados evaluados (denominador FA)", "n_eval", 0), ("Listados no verificables (excluidos)", "n_unv", 0),
        ("Listados ya pasó (entran como acierto)", "n_pasado", 0), ("Instantes banda 3–7 excluidos por no verificable", "n_excl_band", 0),
        ("Instantes paso ≤10 min excluidos del «viene» vacío", "vacio_excl", 0)]


def fl(x, d):
    return "—" if x is None or x != x else (f"{x:.{d}f}" if d else f"{int(round(x))}")


def stats(run, days):
    tot = {}
    for p in Path(run).glob("*.truth_stats.json"):
        if p.name[:10] not in days:
            continue
        for k, v in json.loads(p.read_text()).items():
            tot[k] = tot.get(k, 0) + v
    return tot


def main():
    out = []
    # vara 10 días, base
    ra, rb = [V / "run_base_sg", V / "run_cs_sg"], [V / "run_base_xp", V / "run_cs_xp"]
    ia, va, _ = RV.load(ra, D10, ["base"])
    ib, vb, _ = RV.load(rb, D10, ["base"])
    a, b = RV.flat(ia, va, True), RV.flat(ib, vb, True)
    o = RV.flat(ia, va, False)
    out += ["## VARA 10 dias base: anterior | corregida previa (sin filtro recorrido) | corregida vigente", "",
            "| métrica | anterior | corregida previa | corregida vigente |", "|---|---|---|---|"]
    for n, k, d in ROWS:
        out.append(f"| {n} | {fl(o.get(k), d) if k in o else '—'} | {fl(a[k], d)} | {fl(b[k], d)} |")
    out += ["", RV.vara_by_line(ib, vb), ""]
    # por línea previa vs vigente
    out += ["### por linea: corregida previa -> vigente (FA / FA3-7 / om / vacio / MAE / antes / despues)", ""]
    for ln in sorted(ib.line.unique(), key=lambda x: (len(x), x)):
        x, y = RV.flat(ia[ia.line == ln], va[va.line == ln], True), RV.flat(ib[ib.line == ln], vb[vb.line == ln], True)
        out.append("| " + ln + " | " + " | ".join(f"{fl(x[k], d)} → {fl(y[k], d)}" for k, d in
                   (("fa", 1), ("fa_37", 1), ("om", 1), ("vacio", 1), ("mae", 0), ("antes", 1), ("desp", 1))) + " |")
    out += ["", RV.vara_by_band(vb), "", RV.vara_by_cause(vb), ""]
    # filtro cs 6 dias
    ia, va, _ = RV.load([V / "run_cs_sg"], D6)
    ib, vb, cs = RV.load([V / "run_cs_xp"], D6)
    ga, ca = RV.cs_global(ia, va)
    gb, cb = RV.cs_global(ib, vb)
    out += ["## FILTRO CS 6 dias: previa | vigente (base / cs / oraculo)", "", "| métrica | base | cs | oráculo |", "|---|---|---|---|"]
    for n, k, d in ROWS:
        out.append(f"| {n} | " + " | ".join(f"{fl(ca[v][k], d)} → {fl(cb[v][k], d)}" for v in ("base", "cs", "ramal")) + " |")
    out += ["", "### vigente", "", gb, RV.cs_by_line(ib, vb), RV.cs_by_day(ib, vb)]
    eff = RV.cs_effect(vb)
    out += ["", "efecto: " + repr(eff), "efecto previo: " + repr(RV.cs_effect(va)), ""]
    # estadísticas de la verdad
    for nm, run, days in (("base 10d", [V / "run_base_xp", V / "run_cs_xp"], D10), ("cs 6d", [V / "run_cs_xp"], D6)):
        tot = {}
        seen = set()
        for r in run:
            for p in sorted(Path(r).glob("*.truth_stats.json")):
                if p.name[:10] in days and p.name not in seen:
                    seen.add(p.name)
                    for k, v in json.loads(p.read_text()).items():
                        tot[k] = tot.get(k, 0) + v
        out.append(f"stats verdad {nm}: {tot}")
    Path(sys.argv[1]).write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
