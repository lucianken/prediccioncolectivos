"""Descomposicion por linea del MAE del proximo coche anunciado (replay v4, banda de ETA real 3-7 min). No toca calcula.py.

Uso (desde prediccion colectivos/): python data/ml/replay/porcoche/descomposicion.py [--src data/ml/replay/v4prod/v4] [--out data/ml/replay/v4prod]
Entrada: crudos <dia>_<linea>.veh.parquet / .inst.parquet (variante base). Salida en --out: descomposicion_lineas.csv, descomposicion_agregado.json.
Misma logica que calcula.py (banda real_next2_s 180-420 s, sin instantes con paso previo no verificable; err = anunciado - real;
err > 0 = llega antes de lo anunciado). Casos, mutuamente excluyentes, en este orden (por el estado del 1.o anunciado):
  a  el 1.o anunciado es el primero en llegar
  b  el 1.o anunciado ya habia pasado entre su ultimo ping y t (otro coche llega primero)
  c  el 1.o anunciado es bondi fantasma (no pasa en 40 min)
  d  el 1.o anunciado llega despues y el primero en llegar es otro coche listado (2.o-5.o)
  e  el 1.o anunciado llega despues y el primero en llegar es un bondi no anunciado (fuera de los 5 listados)
  f  el 1.o anunciado es no verificable (hueco de GPS)
Ademas: MAE por coche (listados con paso firme tp2_s en 3-7 min, err = eta0_s - tp2_s) y, para c, la causa de la falsa alarma
cuando el (dia, linea, parada, t, coche) esta en falsas/clasif.parquet (solo las 12 lineas de v3 con la vara anterior).
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DAYS = ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19", "2026-09-20", "2026-10-03", "2026-10-04", "2026-10-06", "2026-10-08"]
KEY = ["line", "day", "stop_id", "t"]
CASES = ["a", "b", "c", "d", "e", "f"]


def load_line(src: Path, ln: str):
    vs, is_ = [], []
    for d in DAYS:
        pv, pi = src / f"{d}_{ln}.veh.parquet", src / f"{d}_{ln}.inst.parquet"
        if pv.exists() and pi.exists():
            v = pd.read_parquet(pv); i = pd.read_parquet(pi)
            vs.append(v[v.variant == "base"]); is_.append(i[i.variant == "base"])
    if not vs:
        return None, None
    veh = pd.concat(vs, ignore_index=True).drop_duplicates(KEY + ["vehicle"])
    inst = pd.concat(is_, ignore_index=True).drop_duplicates(KEY)
    return inst, veh


def one_line(src: Path, ln: str):
    inst, veh = load_line(src, ln)
    if inst is None:
        return None
    L = veh[veh.listed].copy()
    L["_o"] = (L.group != "seguro").astype(int)
    L = L.sort_values(KEY + ["_o", "eta_s"])
    L["pos"] = L.groupby(KEY).cumcount() + 1
    # por coche (banda por el paso propio, como calcula.py)
    lst = L[L.tp2_s.notna()]
    err_c = (lst.eta0_s - lst.tp2_s)
    mb = (lst.tp2_s >= 180) & (lst.tp2_s <= 420) & err_c.notna()
    ec = err_c[mb].abs()
    # proximo coche
    i = inst
    unv = i.unv_first_s.notna() & (i.unv_first_s < i.real_next2_s.fillna(np.inf)) & (i.unv_first_s <= 1200)
    inb = (i.real_next2_s >= 180) & (i.real_next2_s <= 420)
    n_unv = int((inb & unv).sum())
    i = i[~unv & inb].copy()
    first = L[L.pos == 1][KEY + ["vehicle", "tp2_s", "past", "unv"]].rename(
        columns={"vehicle": "ann_veh", "tp2_s": "ann_tp2", "past": "ann_past", "unv": "ann_unv"})
    v2 = veh[veh.tp2_s.notna()].sort_values(KEY + ["tp2_s"]).drop_duplicates(KEY)[KEY + ["vehicle"]].rename(columns={"vehicle": "real_veh"})
    L2 = L[KEY + ["vehicle", "pos"]].rename(columns={"vehicle": "real_veh", "pos": "real_pos"})
    i = i.merge(first, on=KEY, how="left").merge(v2, on=KEY, how="left").merge(L2, on=KEY + ["real_veh"], how="left")
    i["err"] = i.ann0_any_s - i.real_next2_s
    sin = i.ann0_any_s.isna()
    con = i[~sin].copy()
    a = con.ann_veh == con.real_veh
    case = np.where(a, "a",
           np.where(con.ann_tp2.notna(), np.where(con.real_pos.notna(), "d", "e"),
           np.where(con.ann_past.fillna(False).astype(bool), "b",
           np.where(con.ann_unv.fillna(False).astype(bool), "f", "c"))))
    con["case"] = case
    ae = con.err.abs()
    row = {"line": ln, "n_inst_banda": int(len(i)), "n_excl_unv": n_unv, "n_con": int(len(con)), "n_sin": int(sin.sum()),
           "sum_abs": float(ae.sum()), "sum_antes": float((con.err > 60).sum()), "sum_despues": float((con.err < -60).sum()),
           "n_coche": int(len(ec)), "sum_coche": float(ec.sum()),
           "n_dias": int(inst.day.nunique()), "n_stops": int(inst.stop_id.nunique())}
    for c in CASES:
        m = con.case == c
        row[f"n_{c}"] = int(m.sum()); row[f"abs_{c}"] = float(ae[m].sum())
    # c con real listado o no (solo informativo)
    fant = con[con.case == "c"][KEY + ["ann_veh", "err"]].copy()
    return row, fant


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data/ml/replay/v4prod/v4"))
    ap.add_argument("--out", default=str(ROOT / "data/ml/replay/v4prod"))
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    lines = sorted({p.name.split("_", 1)[1].split(".")[0] for p in src.glob("*.veh.parquet")}, key=lambda x: (len(x), x))
    t0 = time.time()
    rows, fants = [], []
    for ln in lines:
        r = one_line(src, ln)
        if r is None:
            continue
        rows.append(r[0]); r[1]["line"] = ln; fants.append(r[1])
        print(ln, f"{time.time()-t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out / "descomposicion_lineas.csv", index=False)
    # causa de bondi fantasma (solo donde hay clasificacion de FALSAS_ALARMAS: 12 lineas viejas)
    F = pd.concat(fants, ignore_index=True)
    cl = pd.read_parquet(ROOT / "data/ml/replay/falsas/clasif.parquet", columns=["line", "day", "stop_id", "t", "vehicle", "cause"])
    cl = cl.drop_duplicates(["line", "day", "stop_id", "t", "vehicle"])
    F12 = F[F.line.isin(cl.line.unique())]
    M = F12.merge(cl, left_on=KEY + ["ann_veh"], right_on=KEY + ["vehicle"], how="left")
    M["cause"] = M.cause.fillna("sin clasificar")
    g = M.groupby("cause").agg(n=("err", "size"), abs_sum=("err", lambda s: s.abs().sum()))
    g["peso_pct"] = 100 * g.n / g.n.sum()
    g["aporte_s_por_instante_con_anuncio"] = g.abs_sum / df[df.line.isin(cl.line.unique())].n_con.sum()
    g.sort_values("n", ascending=False).to_csv(out / "descomposicion_fantasma_causas12.csv")
    print("hecho", f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
