"""Compara base contra las variantes prior del replay (pareado en los mismos (linea, dia, parada, t)). Vara corregida.

Uso (desde prediccion colectivos/, PYTHONPATH=.): python data/ml/replay/prior/reporte_prior.py [--src data/ml/replay/prior/run] [--v4 data/ml/replay/v4prod/v4]
Salida: tablas_prior.json, prior_lineas.csv, prior_dias.csv en data/ml/replay/prior/ (los consume PRIOR_RAMAL.md).
Metricas por (linea, dia, variante): MAE del proximo coche 3-7 min, % dentro de +-120 s, llega antes / despues > 60 s, bondi fantasma,
bondi no anunciado, sin aviso firme (report_vara.flat, corregida, hora comun). Agregado = recomputado sobre todas las filas juntas;
diferencia pareada dia por dia = media de (variante - base) por dia (los 10 dias), con cuantos dias mejoran.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from prediccion.replay import metrics as MT   # noqa: E402
from prediccion.replay.report_vara import flat   # noqa: E402

KEY = ["line", "day", "stop_id", "t"]
METS = [("mae", "MAE 3-7 (s)"), ("d120", "dentro +-120 s %"), ("antes", "llega antes >60 s %"), ("desp", "llega despues >60 s %"),
        ("fa", "bondi fantasma %"), ("om", "bondi no anunciado %"), ("vacio", "sin aviso firme %")]


def metrics(inst, veh):
    f = flat(inst, veh, True)
    w = MT.within_tol(inst, "ann0_any_s", (120.0,), 180.0, 420.0, corrected=True)
    return dict(mae=f["mae"], n_band=f["n_band"], d120=w["dentro_120_con_pct"], antes=f["antes"], desp=f["desp"], fa=f["fa"], om=f["om"],
                vacio=f["vacio"], n_fa=f["n_eval"], n_om=f["om_n"], n_vacio=f["vacio_n"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data/ml/replay/prior/run"))
    ap.add_argument("--v4", default=str(ROOT / "data/ml/replay/v4prod/v4"))
    ap.add_argument("--out", default=str(ROOT / "data/ml/replay/prior"))
    a = ap.parse_args()
    src, v4, out = Path(a.src), Path(a.v4), Path(a.out)
    files = sorted(src.glob("*.inst.parquet"))
    I, V = [], []
    for f in files:
        I.append(pd.read_parquet(f)); V.append(pd.read_parquet(str(f).replace(".inst.", ".veh.")))
    inst = pd.concat(I, ignore_index=True); veh = pd.concat(V, ignore_index=True)
    variants = [v for v in inst.variant.unique()]
    lines = sorted(inst.line.unique(), key=int); days = sorted(inst.day.unique())
    print("variantes", variants, "lineas", len(lines), "dias", len(days), flush=True)
    # chequeo: base == v4prod
    chk = {"dif_inst": 0, "dif_veh": 0, "n": 0}
    for (ln, day), g in inst[inst.variant == "base"].groupby(["line", "day"]):
        p = v4 / f"{day}_{ln}.inst.parquet"
        if not p.exists():
            continue
        o = pd.read_parquet(p); o = o[o.variant == "base"].sort_values(KEY).reset_index(drop=True); n = g.sort_values(KEY).reset_index(drop=True)
        chk["n"] += 1
        cols = [c for c in o.columns if c in n.columns and c != "variant"]
        same = len(o) == len(n) and all(((o[c] == n[c]) | (o[c].isna() & n[c].isna())).all() for c in cols)
        chk["dif_inst"] += int(not same)
        ov = pd.read_parquet(str(p).replace(".inst.", ".veh.")); ov = ov[ov.variant == "base"].sort_values(KEY + ["vehicle"]).reset_index(drop=True)
        nv = veh[(veh.variant == "base") & (veh.line == ln) & (veh.day == day)].sort_values(KEY + ["vehicle"]).reset_index(drop=True)
        cv = [c for c in ov.columns if c in nv.columns and c != "variant"]
        samev = len(ov) == len(nv) and all(((ov[c] == nv[c]) | (ov[c].isna() & nv[c].isna())).all() for c in cv)
        chk["dif_veh"] += int(not samev)
    print("chequeo base == v4prod:", chk, flush=True)
    rows = []
    for v in variants:
        iv, vv = inst[inst.variant == v], veh[veh.variant == v]
        for (ln, day), gi in iv.groupby(["line", "day"]):
            gv = vv[(vv.line == ln) & (vv.day == day)]
            rows.append(dict(variant=v, line=ln, day=day, **metrics(gi, gv)))
        print(v, flush=True)
    D = pd.DataFrame(rows); D.to_csv(out / "prior_dias.csv", index=False)
    # agregados (pooled) por linea y total, y pareado por dia
    L = []
    for v in variants:
        iv, vv = inst[inst.variant == v], veh[veh.variant == v]
        for ln in lines + ["TODAS"]:
            gi = iv if ln == "TODAS" else iv[iv.line == ln]; gv = vv if ln == "TODAS" else vv[vv.line == ln]
            L.append(dict(variant=v, line=ln, **metrics(gi, gv)))
        # agregado por dia (todas las lineas juntas) para el pareado
        for day in days:
            gi = iv[iv.day == day]; gv = vv[vv.day == day]
            L.append(dict(variant=v, line="DIA:" + day, **metrics(gi, gv)))
    Lc = pd.DataFrame(L); Lc.to_csv(out / "prior_lineas.csv", index=False)
    summ = {"check_base": chk, "variants": variants, "lines": lines, "days": days}
    json.dump(summ, open(out / "tablas_prior.json", "w"), indent=1)
    print("listo")


if __name__ == "__main__":
    main()
