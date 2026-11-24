"""Paso 3 de YA_PASO: regla causal de "ya paso" sobre los crudos v4 (sin volver a predecir). Calibra P(paso | eta0, edad del ping) por
validacion cruzada de DIAS (pliegue A calibra B y viceversa) y recalcula la vara vigente por linea y variante.
Uso (desde prediccion colectivos/): python data/ml/replay/v4prod/yapaso/evalua.py [lineas_csv]   -> variantes.csv, calibracion.csv
No toca prediccion/replay ni los crudos. Las metricas replican prediccion/replay/metrics.py (corregida) y porcoche/descomposicion.py."""
from __future__ import annotations
import ctypes, json, sys, time
from pathlib import Path
import numpy as np, pandas as pd
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x40)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SRC = ROOT / "data/ml/replay/v4prod/v4"
DAYS = ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19", "2026-09-20", "2026-10-03", "2026-10-04", "2026-10-06", "2026-10-08"]
FOLD_A = {"2026-09-15", "2026-09-17", "2026-09-19", "2026-10-03", "2026-10-06"}     # 2 martes/jueves, 2 sabados, 1 martes
KEY = ["line", "day", "stop_id", "t"]
E_BINS = [-1, 0, 15, 30, 45, 60, 75, 90, 120, 180, 300]   # eta0_s (0 = clamp); > 300 -> P = 0
A_BINS = [-1, 30, 60, 120, 240, 1e9]
THR = [0.3, 0.5, 0.7, 0.9]
VARIANTS = ["base"] + [f"{r}_{m}" for r in ["app"] + [f"p{int(t*100)}" for t in THR] for m in ("dem", "rem")]
CASES = "abcdef"


def ebin(x): return np.clip(np.searchsorted(E_BINS, x, side="left") - 1, 0, len(E_BINS) - 2)
def abin(x): return np.clip(np.searchsorted(A_BINS, x, side="right") - 1, 0, len(A_BINS) - 2)


def build_tables(cal: pd.DataFrame):
    """cal: filas listadas (no unv) con eta0<=300, age_s, past. Devuelve (T2d[e,a], T1d[e]) de P(past) con suavizado y respaldo."""
    cal = cal[cal.eta0_s <= 300]
    e = ebin(cal.eta0_s.values); a = np.where(cal.age_s.isna(), -1, abin(cal.age_s.fillna(0).values)); y = cal.past.values.astype(float)
    ne, na = len(E_BINS) - 1, len(A_BINS) - 1
    n1 = np.bincount(e, minlength=ne); s1 = np.bincount(e, weights=y, minlength=ne)
    p1 = (s1 + 0.5) / (n1 + 1)
    p2 = np.tile(p1[:, None], (1, na))
    m = a >= 0
    n2 = np.zeros((ne, na)); s2 = np.zeros((ne, na))
    np.add.at(n2, (e[m], a[m]), 1); np.add.at(s2, (e[m], a[m]), y[m])
    ok = n2 >= 300
    p2[ok] = ((s2 + 0.5) / (n2 + 1))[ok]
    return p2, p1, n2, n1


def lookup(T, eta0, age):
    p2, p1 = T[0], T[1]
    eta0 = np.asarray(eta0, dtype=float); age = np.asarray(age, dtype=float)
    e = ebin(eta0); a = abin(np.nan_to_num(age, nan=0))
    out = np.where(np.isnan(age), p1[e], p2[e, a])
    return np.where(eta0 > 300, 0.0, out)


def calibrate():
    d = pd.read_parquet(HERE / "listados_eta900.parquet"); ed = pd.read_parquet(HERE / "edades.parquet")
    d = d[~d.unv & (d.eta0_s <= 300)].merge(ed[["line", "day", "vehicle", "t", "age_s"]], on=["line", "day", "vehicle", "t"], how="left")
    inA = d.day.isin(FOLD_A)
    TA, TB = build_tables(d[inA]), build_tables(d[~inA])
    rows = []
    for nm, T in (("A (15-sep,17-sep,19-sep,3-oct,6-oct)", TA), ("B (resto)", TB)):
        p2, p1, n2, n1 = T
        for i in range(len(E_BINS) - 1):
            rows.append({"pliegue": nm, "eta0_desde_exclusivo": E_BINS[i], "eta0_hasta": E_BINS[i + 1], "n": int(n1[i]), "P_eta0": p1[i],
                         **{f"P_edad{A_BINS[j]}_{A_BINS[j+1]:.0f}": p2[i, j] for j in range(len(A_BINS) - 1)},
                         **{f"n_edad{A_BINS[j]}_{A_BINS[j+1]:.0f}": int(n2[i, j]) for j in range(len(A_BINS) - 1)}})
    pd.DataFrame(rows).to_csv(HERE / "calibracion.csv", index=False)
    return TA, TB, ed


def load_line(ln):
    vs, is_ = [], []
    for dd in DAYS:
        pv, pi = SRC / f"{dd}_{ln}.veh.parquet", SRC / f"{dd}_{ln}.inst.parquet"
        if pv.exists() and pi.exists():
            v = pd.read_parquet(pv); i = pd.read_parquet(pi)
            vs.append(v[v.variant == "base"]); is_.append(i[i.variant == "base"])
    if not vs: return None, None
    return (pd.concat(is_, ignore_index=True).drop_duplicates(KEY),
            pd.concat(vs, ignore_index=True).drop_duplicates(KEY + ["vehicle"]).reset_index(drop=True))


def one_line(ln, TA, TB, ed):
    inst, veh = load_line(ln)
    if inst is None: return []
    veh["_o"] = (veh.group != "seguro").astype(np.int8)
    lm = veh.listed.values
    P = np.zeros(len(veh))
    sub = veh.loc[lm, ["line", "day", "vehicle", "t", "eta0_s"]].merge(
        ed[ed.line == ln][["line", "day", "vehicle", "t", "age_s"]], on=["line", "day", "vehicle", "t"], how="left")
    assert len(sub) == lm.sum()
    inA = sub.day.isin(FOLD_A).values
    p = np.where(inA, lookup(TB, sub.eta0_s.values, sub.age_s.values), lookup(TA, sub.eta0_s.values, sub.age_s.values))  # dia en A -> tabla de B
    P[lm] = np.nan_to_num(p, nan=0.0)
    veh["P"] = P
    i = inst
    unv = i.unv_first_s.notna() & (i.unv_first_s < i.real_next2_s.fillna(np.inf)) & (i.unv_first_s <= 1200)
    n_vac_den = i[(i.real_next2_s <= 600) & ~unv][KEY]
    ib0 = i[(i.real_next2_s >= 0) & (i.real_next2_s <= 900) & ~unv][KEY + ["real_next2_s", "ann0_any_s"]].copy()   # bandas 0-3, 3-7, 7-15
    ib0["bd"] = np.where(ib0.real_next2_s < 180, "0_3", np.where(ib0.real_next2_s <= 420, "3_7", "7_15"))
    ib = ib0[ib0.bd == "3_7"].copy()
    v2 = veh[veh.tp2_s.notna()].sort_values(KEY + ["tp2_s"]).drop_duplicates(KEY)[KEY + ["vehicle"]].rename(columns={"vehicle": "real_veh"})
    ib = ib.merge(v2, on=KEY, how="left")
    ib0 = ib0.merge(v2, on=KEY, how="left")
    pas = veh[veh.tp2_s <= 600]; pasv = pas[pas.visible]
    rows = []
    for var in VARIANTS:
        if var == "base":
            rem = np.zeros(len(veh), bool); mode = "dem"
        else:
            rule, mode = var.split("_")
            rem = (lm & (veh.eta_s.values == 0)) if rule == "app" else (lm & (veh.P.values > int(rule[1:]) / 100))
        listed = lm & ~rem if mode == "rem" else lm
        L = veh[listed].copy()
        L["_d"] = rem[listed].astype(np.int8) if mode == "dem" else 0
        L = L.sort_values(KEY + ["_d", "_o", "eta_s"]).reset_index(drop=True)
        L["pos"] = L.groupby(KEY).cumcount() + 1
        first = L[L.pos == 1][KEY + ["vehicle", "tp2_s", "past", "unv", "eta0_s"]].rename(
            columns={"vehicle": "ann_veh", "tp2_s": "ann_tp2", "past": "ann_past", "unv": "ann_unv", "eta0_s": "ann"})
        L2 = L[KEY + ["vehicle", "pos"]].rename(columns={"vehicle": "real_veh", "pos": "real_pos"})
        c = ib.merge(first, on=KEY, how="left").merge(L2, on=KEY + ["real_veh"], how="left")
        sin = c.ann.isna(); con = c[~sin].copy()
        err = con.ann - con.real_next2_s
        a = con.ann_veh == con.real_veh
        con["case"] = np.where(a, "a", np.where(con.ann_tp2.notna(), np.where(con.real_pos.notna(), "d", "e"),
                       np.where(con.ann_past.eq(True), "b", np.where(con.ann_unv.eq(True), "f", "c"))))
        ae = err.abs()
        # otras bandas (el real 0-3 y 7-15 min): costo de bajar/sacar coches que llegan pronto
        o = ib0[ib0.bd != "3_7"].merge(first[KEY + ["ann"]], on=KEY, how="left")
        oe = o.ann - o.real_next2_s
        r = {"line": ln, "variant": var, "n_band": len(c), "n_con": len(con), "n_sin": int(sin.sum()), "sum_abs": float(ae.sum()),
             "n_antes": int((err > 60).sum()), "n_desp": int((err < -60).sum())}
        for bd in ("0_3", "7_15"):
            m = (o.bd == bd).values; k = m & o.ann.notna().values
            r[f"n_{bd}"] = int(m.sum()); r[f"con_{bd}"] = int(k.sum()); r[f"abs_{bd}"] = float(oe.abs().values[k].sum())
            r[f"antes_{bd}"] = int((oe.values[k] > 60).sum()); r[f"desp_{bd}"] = int((oe.values[k] < -60).sum())
        if var == "base":
            r["chk_ann0"] = float(np.isclose(con.ann, con.ann0_any_s).mean()) if len(con) else 1.0
        for k in CASES:
            m = (con.case == k).values; r[f"n_{k}"] = int(m.sum()); r[f"abs_{k}"] = float(ae.values[m].sum())
        l = veh[listed]; fuera = l.eta0_s > 2400; unvl = ~fuera & l.tp2_s.isna() & l.unv
        base = l[~fuera & ~unvl]
        r["n_eval"] = len(base); r["n_fa"] = int((base.tp2_s.isna() & ~base.past).sum()); r["n_listados"] = len(l)
        r["n_vis"] = len(pasv); r["n_om"] = int((~listed[pasv.index.values]).sum())
        seg = L[L.group == "seguro"][KEY].drop_duplicates(); seg["_s"] = 1
        vv = n_vac_den.merge(seg, on=KEY, how="left")
        r["n_vac_den"] = len(vv); r["n_vac"] = int(vv._s.isna().sum())
        rr = rem & lm
        r["n_rule"] = int(rr.sum()); r["n_rule_past"] = int((rr & veh.past.values).sum())
        r["n_rule_pasa10"] = int((rr & (veh.tp2_s.values <= 600)).sum()); r["n_rule_pasa"] = int((rr & veh.tp2_s.notna().values).sum())
        rows.append(r)
    return rows


if __name__ == "__main__":
    cfg = json.load(open(ROOT.parent / "proyectoconsola/public/config/prediccion.json", encoding="utf-8"))
    lines = sys.argv[1].split(",") if len(sys.argv) > 1 else [e["line"] for e in cfg["enabledLines"]]
    TA, TB, ed = calibrate()
    out = []; t0 = time.time()
    for ln in lines:
        out += one_line(ln, TA, TB, ed); print(ln, f"{time.time()-t0:.0f}s", flush=True)
        pd.DataFrame(out).to_csv(HERE / "variantes.csv", index=False)
    print("hecho")
