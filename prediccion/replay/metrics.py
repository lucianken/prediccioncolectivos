"""Métricas de producto del replay (ver core.evaluate_line para las columnas)."""
from __future__ import annotations

import numpy as np
import pandas as pd

BAND = (180.0, 420.0)     # tiempo real hasta el próximo coche: banda principal 3-7 min
GLOBAL_MAX = 1200.0       # y global <= 20 min
TOL_S = 60.0
HORIZON_S = 2400.0      # horizonte de la verdad (core.HORIZON_S); una falsa alarma solo se cuenta si el ETA anunciado cae dentro


def load_run(run_dir) -> tuple[pd.DataFrame, pd.DataFrame]:
    from pathlib import Path
    d = Path(run_dir)
    inst = pd.concat([pd.read_parquet(p) for p in sorted(d.glob("*.inst.parquet"))], ignore_index=True)
    veh = pd.concat([pd.read_parquet(p) for p in sorted(d.glob("*.veh.parquet"))], ignore_index=True)
    cls = inst[["line", "stop_id", "stop_class"]].drop_duplicates()
    return inst, veh.merge(cls, on=["line", "stop_id"], how="left")


def _real(inst: pd.DataFrame, corrected: bool) -> pd.Series:
    return inst.real_next2_s if corrected else inst.real_next_s


def _unverifiable(inst: pd.DataFrame, real: pd.Series) -> pd.Series:
    """Instantes cuyo próximo paso real es incierto: hay un par de pings con hueco de 10-40 min que encierra la parada y
    el paso pudo ocurrir antes del próximo paso verificado (o no hay ninguno) y dentro de GLOBAL_MAX."""
    u = inst.unv_first_s
    return u.notna() & (u < real.fillna(np.inf)) & (u <= GLOBAL_MAX)


def next_bus(inst: pd.DataFrame, col: str, lo: float = 0.0, hi: float = GLOBAL_MAX, corrected: bool = False) -> dict:
    """Próximo coche que sirve: real (min de los pasos) contra lo anunciado (`col`). Instantes con real en [lo, hi].
    corrected: paso de la vara corregida; se excluyen los instantes con paso previo no verificable (n_excl_unv)."""
    real = _real(inst, corrected)
    n_unv = 0
    if corrected:
        unv = _unverifiable(inst, real)
        n_unv = int(((real >= lo) & (real <= hi) & unv).sum())
        inst, real = inst[~unv], real[~unv]
    s = inst[(real >= lo) & (real <= hi)]
    ann = s[col]
    has = ann.notna()
    err = (_real(s, corrected) - ann)[has]          # <0: llega antes de lo anunciado
    return {"n": int(len(s)), "sin_anuncio_pct": float(100 * (1 - has.mean())) if len(s) else np.nan,
            "mae_s": float(err.abs().mean()) if has.any() else np.nan,
            "antes_pct": float(100 * (err < -TOL_S).mean()) if has.any() else np.nan,
            "despues_pct": float(100 * (err > TOL_S).mean()) if has.any() else np.nan, "n_excl_unv": n_unv}


def within_tol(inst: pd.DataFrame, col: str = "ann0_any_s", tols=(60.0, 120.0, 180.0), lo: float = 180.0, hi: float = 420.0,
               corrected: bool = True) -> dict:
    """Fracción de instantes en que el primer arribo anunciado (`col`) cae dentro de ±tol del primer paso real de cualquier coche
    que sirve la parada (misma verdad e instantes que `next_bus`: real en [lo, hi], sin los de paso previo no verificable si
    `corrected`). Devuelve por tol: pct_con_anuncio (sobre los instantes con anuncio, como el MAE) y pct_total (los sin anuncio
    cuentan como falla); n = instantes de la banda, n_con = con anuncio."""
    real = _real(inst, corrected)
    if corrected:
        unv = _unverifiable(inst, real)
        inst, real = inst[~unv], real[~unv]
    m = (real >= lo) & (real <= hi)
    s, r = inst[m], real[m]
    ann = s[col]
    has = ann.notna()
    err = (ann - r).abs()
    out = {"n": int(len(s)), "n_con": int(has.sum())}
    for t in tols:
        ok = err <= t
        out[f"dentro_{int(t)}_con_pct"] = float(100 * ok[has].mean()) if has.any() else np.nan
        out[f"dentro_{int(t)}_total_pct"] = float(100 * ok.mean()) if len(s) else np.nan
    return out


def false_alarms(veh: pd.DataFrame, corrected: bool = False, eta_band: tuple | None = None) -> dict:
    """
    Anterior: coche listado sin cruce estricto en 40 min. Corregida: sobre los listados con ETA anunciado (eta0) dentro del
    horizonte (<= HORIZON_S; el resto se informa en n_fuera_horizonte), sin los "no verificables" (n_no_verificable);
    un coche que ya pasó entre su último ping y t no es falsa alarma (n_ya_paso: llegó antes de lo anunciado).
    eta_band: (lo, hi) filtra por ETA anunciado (eta0).
    """
    l = veh[veh.listed]
    if eta_band is not None:
        l = l[(l.eta0_s >= eta_band[0]) & (l.eta0_s < eta_band[1])]
    out = {"listados": int(len(l))}
    if not corrected:
        fa = l.tp_s.isna()
        out["falsa_alarma_pct"] = float(100 * fa.mean()) if len(l) else np.nan
        groups = {g: l[l.group == g] for g in ("seguro", "puede_venir", "provisional")}
        out.update({f"fa_{g}_pct": float(100 * x.tp_s.isna().mean()) if len(x) else np.nan for g, x in groups.items()})
        out.update({f"n_{g}": int(len(x)) for g, x in groups.items()})
        return out
    fuera = l.eta0_s > HORIZON_S
    unv = ~fuera & l.tp2_s.isna() & l.unv
    base = l[~fuera & ~unv]
    fa = base.tp2_s.isna() & ~base.past
    out.update({"n_fuera_horizonte": int(fuera.sum()), "n_no_verificable": int(unv.sum()),
                "n_ya_paso": int((base.tp2_s.isna() & base.past).sum()), "n_evaluados": int(len(base)),
                "falsa_alarma_pct": float(100 * fa.mean()) if len(base) else np.nan})
    for g in ("seguro", "puede_venir", "provisional"):
        m = base.group == g
        out[f"fa_{g}_pct"] = float(100 * fa[m].mean()) if m.any() else np.nan
        out[f"n_{g}"] = int(m.sum())
    return out


def omissions(veh: pd.DataFrame, within_s: float = 600.0, corrected: bool = False) -> dict:
    """Coches que pasan en <= within_s y no están en la lista (o fuera del top 5). Los sin ping vigente en t se cuentan aparte.
    corrected: pasos de la vara corregida (columna tp2_s)."""
    col = "tp2_s" if corrected else "tp_s"
    p = veh[veh[col] <= within_s]
    vis = p[p.visible]
    out = {"pasan": int(len(p)), "visibles": int(len(vis)),
           "omision_pct": float(100 * (~vis.listed).mean()) if len(vis) else np.nan,
           "omision_con_invisibles_pct": float(100 * (~p.listed).mean()) if len(p) else np.nan}
    return out


def seguro_vacio(inst: pd.DataFrame, within_s: float = 600.0, corrected: bool = False) -> dict:
    real = _real(inst, corrected)
    n_unv = 0
    if corrected:
        unv = _unverifiable(inst, real)
        n_unv = int(((real <= within_s) & unv).sum())
        inst, real = inst[~unv], real[~unv]
    s = inst[real <= within_s]
    return {"n": int(len(s)), "sin_seguro_pct": float(100 * (~s.has_seguro).mean()) if len(s) else np.nan, "n_excl_unv": n_unv}


def coverage(inst: pd.DataFrame, corrected: bool = False) -> dict:
    c = "n_pass2_20" if corrected else "n_pass_20"
    return {"instantes": int(len(inst)), "coches_evaluados": int(inst.n_shown_status.sum()),
            "con_paso_20min_pct": float(100 * (inst[c] > 0).mean()) if len(inst) else np.nan}


def summarize(inst: pd.DataFrame, veh: pd.DataFrame, corrected: bool = False, ann0: bool = False) -> dict:
    """ann0: ETA anunciado en la hora común (sin el descuento de 60 s del sello de CABA), como V3_PRODUCCION.md y los informes
    posteriores; por defecto el ETA con el descuento (report.py)."""
    pre = "ann0" if ann0 else "ann"
    out = {"cobertura": coverage(inst, corrected), "falsas": false_alarms(veh, corrected), "omisiones": omissions(veh, corrected=corrected),
           "seguro_vacio": seguro_vacio(inst, corrected=corrected)}
    for name, col in (("seguro", f"{pre}_seguro_s"), ("seguro_o_fallback", f"{pre}_any_s")):
        out[f"prox_{name}_banda"] = next_bus(inst, col, *BAND, corrected=corrected)
        out[f"prox_{name}_global"] = next_bus(inst, col, 0.0, GLOBAL_MAX, corrected=corrected)
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
