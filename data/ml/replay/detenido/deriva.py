"""Deriva una variante de la regla "coche detenido" a partir de la tabla de extrae.py (sin volver a predecir).
spec = dict(N=300|600|900 o None (base), A=metros, treat="a"|"b1"|"b2", loc="all"|"cab"|"mid")
  flag = ext_N < A (racha final cubre la ventana) y, segun loc, d_p < CAB_M (cabecera) / d_p >= CAB_M (mitad).
  a : el coche se descarta (sin grupo, no se lista); b1: pasa al grupo provisional (se ordena por ETA junto con "puede venir");
  b2: provisional y al final de la lista (despues de todo coche no bajado).
Devuelve (veh, inst) con las columnas de core.evaluate_line (variant, line, day, stop_id, t, vehicle, visible, group, eta_s, eta0_s,
listed, tp_s; inst: has_seguro, ann_*, ann0_*, n_listed, n_shown_status, real_next_s, n_pass_10, n_pass_20) para usar con metrics.
"""
import numpy as np
import pandas as pd

CAB_M = 300.0     # manifest terminal_zone_m
LIST_MAX = 5
KEY = ["line", "day", "stop_id", "t"]


def flags(veh, spec):
    if spec.get("N") is None:
        return np.zeros(len(veh), bool)
    ext = veh[f"ext{spec['N']}"].to_numpy()
    f = (veh.group.to_numpy() != "") & (ext < spec["A"])          # nan < x es False
    if spec.get("loc", "all") == "cab":
        f &= veh.d_p.to_numpy() < CAB_M
    elif spec.get("loc") == "mid":
        f &= veh.d_p.to_numpy() >= CAB_M
    return f


def derive(veh, inst, spec, name="v"):
    """veh: tabla de extrae (filas de un conjunto de (dia, linea) completos)."""
    v = veh.copy()
    f = flags(v, spec)
    v["flag"] = f
    treat = spec.get("treat", "a")
    grp = v.group.to_numpy().astype(object)
    cls = np.where(grp == "seguro", 0, 1)
    if treat == "a":
        grp[f] = ""
    else:
        grp[f] = np.where(grp[f] == "seguro", "provisional", grp[f])
        # bajados: solo los que eran "seguro" cambian de grupo; los demas ya estaban fuera de "viene"
        if treat == "b2":
            cls = np.where(f, 2, cls)
    v["group"] = grp
    shown = grp != ""
    v["cls"] = np.where(shown, cls, 9)
    v["eta_k"] = np.where(shown, v.eta_s.to_numpy(), np.inf)
    v = v.sort_values(KEY + ["cls", "eta_k"], kind="stable")
    rank = v.groupby(KEY, sort=False).cumcount().to_numpy()
    shown = (v.group.to_numpy() != "")
    v["listed"] = shown & (rank < LIST_MAX)
    # instante
    s = v[shown]
    g = s.groupby(KEY, sort=False)
    first = g.head(1).set_index(KEY)
    n_shown = g.size().rename("n_shown_status")
    n_listed = v[v.listed].groupby(KEY, sort=False).size().rename("n_listed")
    sure = s[s.group == "seguro"]
    first_sure = sure.groupby(KEY, sort=False).head(1).set_index(KEY)   # ya ordenado por (cls, eta)
    i = inst.set_index(KEY).join(n_shown).join(n_listed)
    i["n_shown_status"] = i.n_shown_status.fillna(0).astype(int)
    i["n_listed"] = i.n_listed.fillna(0).astype(int)
    i["has_seguro"] = i.index.isin(first_sure.index)
    i["ann_seguro_s"] = first_sure.eta_s.reindex(i.index)
    i["ann0_seguro_s"] = first_sure.eta0_s.reindex(i.index)
    i["ann_any_s"] = np.where(i.has_seguro, i.ann_seguro_s, first.eta_s.reindex(i.index))
    i["ann0_any_s"] = np.where(i.has_seguro, i.ann0_seguro_s, first.eta0_s.reindex(i.index))
    i = i.reset_index()
    i["variant"] = name
    keep = v.listed | v.tp_s.notna()
    if "tp2_s" in v:
        keep = keep | v.tp2_s.notna()
    out = v[keep].copy()
    out["variant"] = name
    return out.drop(columns=["cls", "eta_k"]), i


def load(run_dir, days=None, lines=None):
    from pathlib import Path
    d = Path(run_dir)
    vs, is_ = [], []
    for p in sorted(d.glob("*.veh.parquet")):
        day, ln = p.name.split(".")[0].split("_")
        if (days and day not in days) or (lines and ln not in lines):
            continue
        vs.append(pd.read_parquet(p))
        is_.append(pd.read_parquet(p.with_name(p.name.replace(".veh.", ".inst."))))
    return pd.concat(vs, ignore_index=True), pd.concat(is_, ignore_index=True)
