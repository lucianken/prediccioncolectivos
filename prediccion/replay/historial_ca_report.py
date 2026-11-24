"""
Tablas de HISTORIAL_COCHE_ADELANTE.md. python -m prediccion.replay.historial_ca_report [--run data/ml/replay/histca/run]
Por (variante, día, grupo de frecuencia): métricas pareadas (mismas filas); diferencia contra w20 con IC 95 % por bootstrap de días.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.replay.report_vara import flat

ROOT = Path(__file__).resolve().parents[2]
VARS = ["w20", "w60", "wdia", "wviaje"]
GROUPS = [("alta (<= 5 min)", 0, 5), ("media (5-8 min)", 5, 8), ("baja (8-12 min)", 8, 12), ("muy baja (> 12 min)", 12, 1e9)]
KEY = ["line", "day", "stop_id", "t"]
BAND = (180, 420)
METRICS = ["mae_prox", "antes_prox", "desp_prox", "fantasma", "no_anunciado", "mae_coche", "antes_coche", "desp_coche", "lbf0_coche", "lbf0_all"]


def per_coche(v):
    x = v[v.listed & v.tp2_s.notna() & (v.tp2_s >= BAND[0]) & (v.tp2_s < BAND[1])]
    e = x.eta0_s - x.tp2_s
    allv = v[v.listed & (v.lbf >= 0)]
    return {"mae_coche": float(e.abs().mean()) if len(x) else np.nan, "antes_coche": float((e > 60).mean() * 100) if len(x) else np.nan,
            "desp_coche": float((e < -60).mean() * 100) if len(x) else np.nan, "n_coche": len(x),
            "lbf0_coche": float((x.lbf == 0).mean() * 100) if len(x) else np.nan,
            "lbf0_all": float((allv.lbf == 0).mean() * 100) if len(allv) else np.nan, "n_all": len(allv)}


def summarize(i, v):
    f = flat(i, v, True)
    return {"mae_prox": f["mae"], "antes_prox": f["antes"], "desp_prox": f["desp"], "fantasma": f["fa"], "no_anunciado": f["om"],
            "n_prox": f["n_band"], **per_coche(v)}


def load_all(run, lines=None):
    run = Path(run)
    I, V = [], []
    for p in sorted(run.glob("*.inst.parquet")):
        if lines and p.name.split("_")[1].split(".")[0] not in lines:
            continue
        i = pd.read_parquet(p)
        v = pd.read_parquet(p.with_name(p.name.replace(".inst.", ".veh.")))
        I.append(i[i.variant.isin(VARS)]); V.append(v[v.variant.isin(VARS)])
    return pd.concat(I, ignore_index=True), pd.concat(V, ignore_index=True)


def headways(inst):
    """Intervalo medio entre coches de la línea (min): 20 min / media de coches que pasan en los 20 min siguientes (instantes de 6 a 23 h)."""
    x = inst[inst.variant == "w20"]
    return (20.0 / x.groupby("line").n_pass2_20.mean()).rename("hw_min")


def boot(diffs, n=10000, seed=0):
    d = np.asarray([x for x in diffs if x == x])
    if len(d) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    m = rng.choice(d, (n, len(d))).mean(axis=1)
    return float(d.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(ROOT / "data/ml/replay/histca/run"))
    ap.add_argument("--out", default=str(ROOT / "data/ml/replay/histca/resumen.json"))
    ap.add_argument("--lines", default="", help="solo estas líneas (las completas)")
    a = ap.parse_args()
    inst, veh = load_all(a.run, set(filter(None, a.lines.split(","))))
    hw = headways(inst)
    hw.to_csv(Path(a.out).with_name("headway.csv"))
    glab = {}
    for ln, h in hw.items():
        for name, lo, hi in GROUPS:
            if lo <= h < hi:
                glab[ln] = name
    inst["grupo"] = inst.line.map(glab); veh["grupo"] = veh.line.map(glab)
    days = sorted(inst.day.unique())
    res = {"hw": hw.round(2).to_dict(), "glab": glab, "days": days, "lines": sorted(inst.line.unique(), key=lambda x: (len(x), x)),
           "cells": {}}
    sets = [("todas", None)] + [(g[0], g[0]) for g in GROUPS]
    for gname, g in sets:
        for var in VARS:
            for day in days:
                i = inst[(inst.variant == var) & (inst.day == day)]; v = veh[(veh.variant == var) & (veh.day == day)]
                if g:
                    i, v = i[i.grupo == g], v[v.grupo == g]
                if not len(i):
                    continue
                res["cells"][f"{gname}|{var}|{day}"] = summarize(i, v)
    # agregado por línea (todos los días)
    res["lines_tab"] = {}
    for ln in res["lines"]:
        for var in VARS:
            i = inst[(inst.variant == var) & (inst.line == ln)]; v = veh[(veh.variant == var) & (veh.line == ln)]
            res["lines_tab"][f"{ln}|{var}"] = summarize(i, v)
    # pooled y bootstrap
    res["pooled"], res["boot"] = {}, {}
    for gname, g in sets:
        for var in VARS:
            i = inst[inst.variant == var]; v = veh[veh.variant == var]
            if g:
                i, v = i[i.grupo == g], v[v.grupo == g]
            if len(i):
                res["pooled"][f"{gname}|{var}"] = summarize(i, v)
        for var in VARS[1:]:
            for m in METRICS:
                d = [res["cells"].get(f"{gname}|{var}|{day}", {}).get(m, np.nan) - res["cells"].get(f"{gname}|w20|{day}", {}).get(m, np.nan)
                     for day in days if f"{gname}|{var}|{day}" in res["cells"]]
                res["boot"][f"{gname}|{var}|{m}"] = boot(d)
    res["n_lines_group"] = {g[0]: sum(1 for x in glab.values() if x == g[0]) for g in GROUPS}
    Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    print("listo", len(res["lines"]), "líneas", len(days), "días")


if __name__ == "__main__":
    main()
