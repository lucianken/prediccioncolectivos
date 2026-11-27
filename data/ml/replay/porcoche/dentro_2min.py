"""Metrica de producto "dentro de +-2 min" y desglose del caso (d) de la descomposicion (replay v4, vara corregida).

Uso (desde prediccion colectivos/): python data/ml/replay/porcoche/dentro_2min.py [--src data/ml/replay/v4prod/v4] [--out data/ml/replay/v4prod]
Entrada: crudos <dia>_<linea>.veh/.inst.parquet (variante base) de las 126 lineas habilitadas. Sin volver a predecir.
Salida en --out: dentro_2min_lineas.csv, dentro_2min.json y DENTRO_2MIN.md.
Metrica: % de instantes (banda de ETA real al primer paso, de cualquier coche que sirve la parada, real_next2_s) en que el primer
arribo anunciado (ann0_any_s: 1.o de "viene" o, si no hay, de "puede venir"/provisional, hora comun) cae dentro de +-tol del primer
paso real. Mismos instantes que next_bus corregido (sin paso previo no verificable). Casos (a)-(f) como descomposicion.py.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from prediccion.replay import metrics as MT          # noqa: E402
from descomposicion import load_line, KEY            # noqa: E402

PROY = ROOT.parent / "proyectoconsola"
SHAPES_DIR = PROY / "data/backup_line_shapes_2026-11-26"   # = shapes del export path_v4_l1_s1 (line_shapes actuales cambiaron el 2026-11-26: 132, 47)
BANDS = {"3-7 min": (180.0, 420.0), "0-15 min": (0.0, 900.0)}
TOLS = (60.0, 120.0, 180.0)


def enabled_lines():
    d = json.loads((PROY / "public/config/prediccion.json").read_text(encoding="utf-8"))
    return [str(e["line"]) for e in d["enabledLines"]]


def shapes_by_line():
    out = {}
    for p in SHAPES_DIR.glob("*.json"):
        if p.stem != "index":
            d = json.loads(p.read_text(encoding="utf-8")); out[p.stem] = (len(d["ramales"]), len({r["shortName"] for r in d["ramales"]}))
    return out


def grupo(n):
    return "1-2" if n <= 2 else "3-4" if n <= 4 else "5-6" if n <= 6 else ">=7"


def case_frame(src: Path, ln: str):
    """Instantes de la banda 3-7 min con anuncio, con caso (a-f), error y separacion de pasos (como descomposicion.one_line)."""
    inst, veh = load_line(src, ln)
    if inst is None:
        return None
    L = veh[veh.listed].copy()
    L["_o"] = (L.group != "seguro").astype(int)
    L = L.sort_values(KEY + ["_o", "eta_s"])
    L["pos"] = L.groupby(KEY).cumcount() + 1
    i = inst
    unv = i.unv_first_s.notna() & (i.unv_first_s < i.real_next2_s.fillna(np.inf)) & (i.unv_first_s <= 1200)
    i = i[~unv & (i.real_next2_s >= 180) & (i.real_next2_s <= 420)].copy()
    first = L[L.pos == 1][KEY + ["vehicle", "tp2_s", "past", "unv", "eta0_s"]].rename(
        columns={"vehicle": "ann_veh", "tp2_s": "ann_tp2", "past": "ann_past", "unv": "ann_unv", "eta0_s": "ann_eta0"})
    v2 = veh[veh.tp2_s.notna()].sort_values(KEY + ["tp2_s"]).drop_duplicates(KEY)[KEY + ["vehicle"]].rename(columns={"vehicle": "real_veh"})
    L2 = L[KEY + ["vehicle", "pos"]].rename(columns={"vehicle": "real_veh", "pos": "real_pos"})
    i = i.merge(first, on=KEY, how="left").merge(v2, on=KEY, how="left").merge(L2, on=KEY + ["real_veh"], how="left")
    con = i[i.ann0_any_s.notna()].copy()
    con["err"] = con.ann0_any_s - con.real_next2_s
    a = con.ann_veh == con.real_veh
    con["case"] = np.where(a, "a", np.where(con.ann_tp2.notna(), np.where(con.real_pos.notna(), "d", "e"),
                  np.where(con.ann_past.fillna(False).astype(bool), "b", np.where(con.ann_unv.fillna(False).astype(bool), "f", "c"))))
    con["sep"] = con.ann_tp2 - con.real_next2_s            # >= 0: cuanto despues llega el 1.o anunciado que el primero real
    con["own_err"] = con.ann_eta0 - con.ann_tp2            # error del anuncio contra el paso del propio coche anunciado
    con["line"] = ln
    return con[["line", "day", "stop_id", "t", "case", "err", "sep", "own_err", "real_next2_s", "ann0_any_s", "real_pos"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data/ml/replay/v4prod/v4"))
    ap.add_argument("--out", default=str(ROOT / "data/ml/replay/v4prod"))
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    lines = enabled_lines(); SH = shapes_by_line()
    rows, cases = [], []
    for ln in lines:
        inst, _ = load_line(src, ln)
        if inst is None:
            continue
        for bn, (lo, hi) in BANDS.items():
            r = MT.within_tol(inst, "ann0_any_s", TOLS, lo, hi, corrected=True)
            rows.append({"line": ln, "banda": bn, "shapes": SH.get(ln, (np.nan,))[0], **r})
        c = case_frame(src, ln)
        if c is not None:
            cases.append(c)
        print(ln, flush=True)
    R = pd.DataFrame(rows); R["grupo"] = R.shapes.map(grupo)
    R.to_csv(out / "dentro_2min_lineas.csv", index=False)
    C = pd.concat(cases, ignore_index=True)
    summ = {"global": {}, "grupo": {}}
    for bn in BANDS:
        x = R[R.banda == bn]
        def agg(df):
            n, nc = df.n.sum(), df.n_con.sum(); o = {"n": int(n), "n_con": int(nc), "lineas": int(len(df))}
            for t in TOLS:
                k = int(t)
                o[f"{k}_con"] = float((df[f"dentro_{k}_con_pct"] * df.n_con).sum() / nc); o[f"{k}_total"] = float((df[f"dentro_{k}_total_pct"] * df.n).sum() / n)
            return o
        summ["global"][bn] = agg(x)
        summ["grupo"][bn] = {g: agg(x[x.grupo == g]) for g in ("1-2", "3-4", "5-6", ">=7")}
    # casos
    C["abs"] = C.err.abs()
    nt = len(C)
    cs = {}
    for k in "abcdef":
        x = C[C.case == k]
        if not len(x):
            continue
        cs[k] = {"n": int(len(x)), "pct": float(100 * len(x) / nt), "mae": float(x["abs"].mean()), "med": float(x["abs"].median()),
                 "p25": float(x["abs"].quantile(.25)), "p75": float(x["abs"].quantile(.75)), "p90": float(x["abs"].quantile(.9)),
                 "lt60": float(100 * (x["abs"] < 60).mean()), "lt120": float(100 * (x["abs"] < 120).mean()), "lt180": float(100 * (x["abs"] < 180).mean())}
    summ["casos"] = cs
    D = C[C.case == "d"]
    bins = [-0.1, 60, 120, 300, 600, 1e9]; lab = ["<=60 s", "60-120 s", "120-300 s", "300-600 s", ">600 s"]
    D = D.assign(sepb=pd.cut(D.sep, bins, labels=lab), chico=D["abs"] < 120)
    sepb = D.groupby("sepb", observed=False).agg(n=("err", "size"), lt120=("chico", "mean"), abs_med=("abs", "median"), own=("own_err", lambda s: s.abs().median()))
    summ["d_sep"] = {str(k): {"n": int(v.n), "pct": float(100 * v.n / len(D)), "lt120": float(100 * v.lt120), "abs_med": float(v.abs_med), "own_med": float(v.own)} for k, v in sepb.iterrows()}
    amon = (D.sep <= 120) & D.chico
    summ["d_resumen"] = {"n": int(len(D)), "sep_le120": float(100 * (D.sep <= 120).mean()), "err_lt120": float(100 * D.chico.mean()),
                         "amontonado_err_chico": float(100 * amon.mean()), "sep_le120_err_grande": float(100 * ((D.sep <= 120) & ~D.chico).mean()),
                         "inversion_sep_gt120": float(100 * (D.sep > 120).mean()), "inversion_sep_gt300": float(100 * (D.sep > 300).mean()),
                         "sep_med": float(D.sep.median()), "own_abs_med": float(D.own_err.abs().median()), "own_lt60": float(100 * (D.own_err.abs() < 60).mean()),
                         "anunciado_antes_que_real": float(100 * (D.err < 0).mean())}
    json.dump(summ, open(out / "dentro_2min.json", "w"), indent=1)
    print(json.dumps(summ["global"], indent=1)); print(json.dumps(summ["d_resumen"], indent=1))


if __name__ == "__main__":
    main()
