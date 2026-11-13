"""Métricas de producto del replay (ver core.evaluate_line para las columnas)."""
from __future__ import annotations

import numpy as np
import pandas as pd

BAND = (180.0, 420.0)     # tiempo real hasta el próximo coche: banda principal 3-7 min
GLOBAL_MAX = 1200.0       # y global <= 20 min
TOL_S = 60.0


def load_run(run_dir) -> tuple[pd.DataFrame, pd.DataFrame]:
    from pathlib import Path
    d = Path(run_dir)
    inst = pd.concat([pd.read_parquet(p) for p in sorted(d.glob("*.inst.parquet"))], ignore_index=True)
    veh = pd.concat([pd.read_parquet(p) for p in sorted(d.glob("*.veh.parquet"))], ignore_index=True)
    cls = inst[["line", "stop_id", "stop_class"]].drop_duplicates()
    return inst, veh.merge(cls, on=["line", "stop_id"], how="left")


def next_bus(inst: pd.DataFrame, col: str, lo: float = 0.0, hi: float = GLOBAL_MAX) -> dict:
    """Próximo coche que sirve: real (min de los pasos) contra lo anunciado (`col`). Instantes con real en [lo, hi]."""
    s = inst[(inst.real_next_s >= lo) & (inst.real_next_s <= hi)]
    ann = s[col]
    has = ann.notna()
    err = (s.real_next_s - ann)[has]          # <0: llega antes de lo anunciado
    return {"n": int(len(s)), "sin_anuncio_pct": float(100 * (1 - has.mean())) if len(s) else np.nan,
            "mae_s": float(err.abs().mean()) if has.any() else np.nan,
            "antes_pct": float(100 * (err < -TOL_S).mean()) if has.any() else np.nan,
            "despues_pct": float(100 * (err > TOL_S).mean()) if has.any() else np.nan}


def false_alarms(veh: pd.DataFrame) -> dict:
    l = veh[veh.listed]
    fa = l.tp_s.isna()
    out = {"listados": int(len(l)), "falsa_alarma_pct": float(100 * fa.mean()) if len(l) else np.nan}
    for g in ("seguro", "puede_venir", "provisional"):
        x = l[l.group == g]
        out[f"fa_{g}_pct"] = float(100 * x.tp_s.isna().mean()) if len(x) else np.nan
        out[f"n_{g}"] = int(len(x))
    return out


def omissions(veh: pd.DataFrame, within_s: float = 600.0) -> dict:
    """Coches que pasan en <= within_s y no están en la lista (o fuera del top 5). Los sin ping vigente en t se cuentan aparte."""
    p = veh[veh.tp_s <= within_s]
    vis = p[p.visible]
    return {"pasan": int(len(p)), "visibles": int(len(vis)),
            "omision_pct": float(100 * (~vis.listed).mean()) if len(vis) else np.nan,
            "omision_con_invisibles_pct": float(100 * (~p.listed).mean()) if len(p) else np.nan}


def seguro_vacio(inst: pd.DataFrame, within_s: float = 600.0) -> dict:
    s = inst[inst.real_next_s <= within_s]
    return {"n": int(len(s)), "sin_seguro_pct": float(100 * (~s.has_seguro).mean()) if len(s) else np.nan}


def coverage(inst: pd.DataFrame) -> dict:
    return {"instantes": int(len(inst)), "coches_evaluados": int(inst.n_shown_status.sum()),
            "con_paso_20min_pct": float(100 * (inst.n_pass_20 > 0).mean()) if len(inst) else np.nan}


def summarize(inst: pd.DataFrame, veh: pd.DataFrame) -> dict:
    out = {"cobertura": coverage(inst), "falsas": false_alarms(veh), "omisiones": omissions(veh),
           "seguro_vacio": seguro_vacio(inst)}
    for name, col in (("seguro", "ann_seguro_s"), ("seguro_o_fallback", "ann_any_s")):
        out[f"prox_{name}_banda"] = next_bus(inst, col, *BAND)
        out[f"prox_{name}_global"] = next_bus(inst, col, 0.0, GLOBAL_MAX)
    return out


def select(inst, veh, variant=None, line=None, cls=None):
    mi = pd.Series(True, index=inst.index)
    mv = pd.Series(True, index=veh.index)
    for df, m in ((inst, mi), (veh, mv)):
        pass
    if variant is not None:
        mi &= inst.variant == variant
        mv &= veh.variant == variant
    if line is not None:
        mi &= inst.line == line
        mv &= veh.line == line
    if cls is not None:
        mi &= inst.stop_class.isin(cls)
        mv &= veh.stop_class.isin(cls)
    return inst[mi], veh[mv]
