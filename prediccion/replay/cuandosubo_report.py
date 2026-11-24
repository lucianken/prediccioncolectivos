"""
Tablas de la comparación CuandoSubo vs modelo (salida de cuandosubo_cmp.py).
Uso: python -m prediccion.replay.cuandosubo_report data/ml/replay/cuandosubo/run [--out tablas.md]

Convenciones:
- Tiempos en la hora común de CABA (la de la verdad y la del ETA0 del modelo). El ETA de CuandoSubo está en hora real:
  su error es  real - anunciado = (tp2 - OFF) - eta_cs  con OFF = corrimiento del sello de CABA (60 s vigente; sensibilidad 0/60/120).
  El modelo no depende de OFF (ETA0 vs verdad en la misma hora).
- err = real - anunciado: < 0 llega antes de lo anunciado; > 0 llega después.
- Banda de ETA real 3-7 min: tp2 en [180, 420] s (hora común) para las dos fuentes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.replay import metrics as M

BAND = (180.0, 420.0)
TOL = 60.0
OFF = 60.0
KEY = ["day", "line", "stop_id", "t", "vehicle"]


def stats(err: pd.Series) -> dict:
    e = err.dropna()
    if not len(e):
        return {"n": 0, "mae": np.nan, "p90": np.nan, "antes": np.nan, "despues": np.nan, "espera": np.nan}
    return {"n": int(len(e)), "mae": float(e.abs().mean()), "p90": float(e.abs().quantile(0.9)),
            "antes": float(100 * (e < -TOL).mean()), "despues": float(100 * (e > TOL).mean()),
            "espera": float(e[e > 0].mean()) if (e > 0).any() else np.nan}


def load(run: Path):
    def cat(suf):
        fs = sorted(run.glob(f"*.{suf}.parquet"))
        return pd.concat([pd.read_parquet(p) for p in fs], ignore_index=True) if fs else pd.DataFrame()
    inst, veh, cs = cat("inst"), cat("veh"), cat("cs")
    meta = {p.stem.replace(".meta", ""): json.loads(p.read_text(encoding="utf-8")) for p in sorted(run.glob("*.meta.json"))}
    return inst, veh, cs, meta


def prep_cs(cs: pd.DataFrame) -> pd.DataFrame:
    c = cs[(cs.veh_line == cs.line) & cs.predicted & cs.pred_arr.notna() & (cs.stops_away >= 0)].copy()
    c["cs_eta_s"] = c.cs_eta_s.clip(lower=0)
    return c


def row(name, s, extra=""):
    f = lambda x, d=0: "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"   # noqa: E731
    return f"| {name} | {s['n']} | {f(s['mae'])} | {f(s['p90'])} | {f(s['antes'],1)} | {f(s['despues'],1)} | {f(s['espera'])} |{extra}"


HEAD = "| {} | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |\n|---|---|---|---|---|---|---|"


def per_vehicle(c: pd.DataFrame, mv: pd.DataFrame, off: float = OFF):
    """Por coche, banda 3-7 min: devuelve (cs, modelo, cs_emparejado, modelo_emparejado) como DataFrames con columna err."""
    cb = c[c.tp2_s.between(*BAND)].copy()
    cb["err"] = cb.tp2_s - off - cb.cs_eta_s
    mb = mv[mv.listed & mv.tp2_s.between(*BAND) & mv.eta0_s.notna()].copy()
    mb["err"] = mb.tp2_s - mb.eta0_s
    j = cb.merge(mb[KEY + ["err"]], on=KEY, suffixes=("_cs", "_m"))
    return cb, mb, j


def next_bus(inst: pd.DataFrame, c: pd.DataFrame, off: float = OFF):
    """Próximo coche anunciado, instantes con paso real en la banda (sin no verificables)."""
    real = inst.real_next2_s
    ok = inst[real.between(*BAND) & ~M._unverifiable(inst, real)].copy()
    nxt = c.groupby(["day", "line", "stop_id", "t"]).cs_eta_s.min().rename("cs_next").reset_index()
    ok = ok.merge(nxt, on=["day", "line", "stop_id", "t"], how="left")
    ok["err_cs"] = ok.real_next2_s - off - ok.cs_next
    ok["err_seg"] = ok.real_next2_s - ok.ann0_seguro_s
    ok["err_any"] = ok.real_next2_s - ok.ann0_any_s
    return ok


def fantasma(c: pd.DataFrame, mv: pd.DataFrame, off: float = OFF):
    l = c[c.in_caba & ((c.cs_eta_s + off) <= M.HORIZON_S)]
    unv = l.tp2_s.isna() & l.unv
    base = l[~unv]
    fa = base.tp2_s.isna() & ~base.past
    cs = {"listados": int(len(l)), "n_evaluados": int(len(base)), "n_no_verificable": int(unv.sum()), "n_ya_paso": int((base.tp2_s.isna() & base.past).sum()),
          "fantasma_pct": float(100 * fa.mean()) if len(base) else np.nan}
    m = M.false_alarms(mv, corrected=True)
    return cs, m


def no_anunciado(mv: pd.DataFrame, c: pd.DataFrame, within=600.0):
    p = mv[mv.tp2_s <= within].copy()
    ann = c[["day", "line", "stop_id", "t", "vehicle"]].drop_duplicates().assign(en_cs=True)
    p = p.merge(ann, on=KEY, how="left")
    p["en_cs"] = p.en_cs.fillna(False).astype(bool)
    vis = p[p.visible]
    return {"pasan": int(len(p)), "modelo_no_anunciado_pct": float(100 * (~p.listed).mean()) if len(p) else np.nan,
            "cs_no_anunciado_pct": float(100 * (~p.en_cs).mean()) if len(p) else np.nan,
            "pasan_visibles_modelo": int(len(vis)),
            "modelo_no_anunciado_visibles_pct": float(100 * (~vis.listed).mean()) if len(vis) else np.nan,
            "cs_no_anunciado_visibles_pct": float(100 * (~vis.en_cs).mean()) if len(vis) else np.nan}


def block(inst, mv, cs_all, off=OFF):
    c = prep_cs(cs_all)
    cb, mb, j = per_vehicle(c, mv, off)
    nb = next_bus(inst, c, off)
    fcs, fm = fantasma(c, mv, off)
    return {"cb": cb, "mb": mb, "j": j, "nb": nb, "fcs": fcs, "fm": fm, "na": no_anunciado(mv, c)}


def tables(run: Path) -> str:
    inst, veh, cs, meta = load(run)
    inst = inst[inst.variant == "base"]
    veh = veh[veh.variant == "base"]
    out = []
    lines = sorted(inst.line.unique(), key=lambda x: int(x))
    days = sorted(inst.day.unique())
    out.append(f"Corrida `{run}`: días {', '.join(days)}; líneas {', '.join(lines)}.\n")
    groups = [(f"línea {ln}", ln) for ln in lines] + [("agregado", None)]
    res = {}
    for name, ln in groups:
        sel = (lambda d: d[d.line == ln]) if ln else (lambda d: d)
        res[name] = block(sel(inst), sel(veh), sel(cs))
    # A. por coche
    out.append("### A. ETA por coche, banda de ETA real 3–7 min\n")
    out.append("Todos los coches que cada fuente lista y que cruzan firme la parada con ETA real 3–7 min.\n")
    out.append(HEAD.format("línea / fuente"))
    for name, _ in groups:
        r = res[name]
        out.append(row(f"{name}: CuandoSubo", stats(r["cb"].err)))
        out.append(row(f"{name}: modelo `path_v4_l1_s1`", stats(r["mb"].err)))
    out.append("\nSolo coches listados por las dos fuentes en el mismo (parada, instante).\n")
    out.append(HEAD.format("línea / fuente"))
    for name, _ in groups:
        r = res[name]
        out.append(row(f"{name}: CuandoSubo", stats(r["j"].err_cs)))
        out.append(row(f"{name}: modelo", stats(r["j"].err_m)))
    # B. próximo
    out.append("\n### B. Próximo coche anunciado, instantes con paso real en 3–7 min\n")
    out.append("| línea | n instantes | CuandoSubo: sin anuncio (%) | CuandoSubo MAE (s) | antes (%) | después (%) | modelo (cualquier grupo): sin anuncio (%) | MAE (s) | antes (%) | después (%) | modelo («Viene»): MAE (s) | antes (%) | después (%) |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, _ in groups:
        nb = res[name]["nb"]
        a, b, s = [], [], []
        def st(col):
            e = nb[col].dropna()
            return stats(e), 100 * (1 - len(e) / len(nb)) if len(nb) else np.nan
        (sc, nc), (sa, na_), (ss, ns) = st("err_cs"), st("err_any"), st("err_seg")
        f = lambda x, d=0: "–" if x is None or np.isnan(x) else f"{x:.{d}f}"   # noqa: E731
        out.append(f"| {name} | {len(nb)} | {f(nc,1)} | {f(sc['mae'])} | {f(sc['antes'],1)} | {f(sc['despues'],1)} | {f(na_,1)} | {f(sa['mae'])} | {f(sa['antes'],1)} | {f(sa['despues'],1)} | {f(ss['mae'])} | {f(ss['antes'],1)} | {f(ss['despues'],1)} |")
    # C. fantasma
    out.append("\n### C. Bondi fantasma\n")
    out.append("| línea | CuandoSubo: listados ≤ 40 min | evaluados | no verificables | ya pasó | bondi fantasma (%) | modelo: listados | evaluados | bondi fantasma (%) |\n|---|---|---|---|---|---|---|---|---|")
    for name, _ in groups:
        f_, m_ = res[name]["fcs"], res[name]["fm"]
        g = lambda x: "–" if x is None or np.isnan(x) else f"{x:.1f}"   # noqa: E731
        out.append(f"| {name} | {f_['listados']} | {f_['n_evaluados']} | {f_['n_no_verificable']} | {f_['n_ya_paso']} | {g(f_['fantasma_pct'])} | {m_['listados']} | {m_['n_evaluados']} | {g(m_['falsa_alarma_pct'])} |")
    # D. no anunciado
    out.append("\n### D. Bondi no anunciado (coches que pasan en ≤ 10 min)\n")
    out.append("| línea | pasan | CuandoSubo no anunciado (%) | modelo no anunciado (%) | pasan con ping vigente | CuandoSubo (%) | modelo (%) |\n|---|---|---|---|---|---|---|")
    for name, _ in groups:
        n = res[name]["na"]
        g = lambda x: "–" if x is None or np.isnan(x) else f"{x:.1f}"   # noqa: E731
        out.append(f"| {name} | {n['pasan']} | {g(n['cs_no_anunciado_pct'])} | {g(n['modelo_no_anunciado_pct'])} | {n['pasan_visibles_modelo']} | {g(n['cs_no_anunciado_visibles_pct'])} | {g(n['modelo_no_anunciado_visibles_pct'])} |")
    # E. sensibilidad
    out.append("\n### E. Sensibilidad de CuandoSubo al corrimiento del sello de CABA (agregado, banda 3–7 min)\n")
    out.append(HEAD.format("fuente / corrimiento"))
    c_all = prep_cs(cs)
    for off in (0.0, 60.0, 120.0):
        cb, mb, _ = per_vehicle(c_all, veh, off)
        out.append(row(f"CuandoSubo, por coche, corrimiento {off:.0f} s", stats(cb.err)))
    out.append(row("modelo, por coche (no depende del corrimiento)", stats(res["agregado"]["mb"].err)))
    out.append("\n| próximo coche, agregado | n | MAE (s) | antes (%) | después (%) |\n|---|---|---|---|---|")
    for off in (0.0, 60.0, 120.0):
        nb = next_bus(inst, c_all, off)
        s = stats(nb.err_cs)
        out.append(f"| CuandoSubo, corrimiento {off:.0f} s | {s['n']} | {s['mae']:.0f} | {s['antes']:.1f} | {s['despues']:.1f} |")
    s = stats(next_bus(inst, c_all, OFF).err_any)
    out.append(f"| modelo (cualquier grupo) | {s['n']} | {s['mae']:.0f} | {s['antes']:.1f} | {s['despues']:.1f} |")
    # F. por parada
    out.append("\n### F. Por parada, banda 3–7 min (MAE por coche)\n")
    out.append("| línea | parada OBA → OSM | n CuandoSubo | MAE CuandoSubo (s) | n modelo | MAE modelo (s) |\n|---|---|---|---|---|---|")
    r = res["agregado"]
    cbs, mbs = r["cb"], r["mb"]
    for (ln, sid), g in cbs.groupby(["line", "stop_id"]):
        gm = mbs[(mbs.line == ln) & (mbs.stop_id == sid)]
        oba = g.stop_oba.iloc[0]
        out.append(f"| {ln} | {oba} → {sid} | {len(g)} | {g.err.abs().mean():.0f} | {len(gm)} | {gm.err.abs().mean() if len(gm) else float('nan'):.0f} |")
    # G. tipo de día
    out.append("\n### G. Por tipo de día (agregado, por coche, banda 3–7 min)\n")
    out.append(HEAD.format("tipo de día / fuente"))
    for lab, ds in (("hábiles (lun–vie)", [d for d in days if pd.Timestamp(d).weekday() < 5]), ("fin de semana", [d for d in days if pd.Timestamp(d).weekday() >= 5])):
        if not ds:
            continue
        sub = lambda d: d[d.day.isin(ds)]   # noqa: E731
        cb, mb, _ = per_vehicle(prep_cs(sub(cs)), sub(veh))
        out.append(row(f"{lab}: CuandoSubo", stats(cb.err)))
        out.append(row(f"{lab}: modelo", stats(mb.err)))
    # H. cobertura/contexto
    out.append("\n### H. Contexto de CuandoSubo en las paradas\n")
    tot = {k: sum(m.get(k, 0) for m in meta.values()) for k in ("entradas_con_coche", "entradas_otra_linea", "entradas_sin_linea", "entradas_solo_horario")}
    out.append(f"Entradas de arribo con coche: {tot['entradas_con_coche']}; de otra línea (por label): {tot['entradas_otra_linea']}; sin línea (label desconocido): {tot['entradas_sin_linea']}; solo horario (sin tiempo real, sin coche): {tot['entradas_solo_horario']}.\n")
    c_ = cs[(cs.veh_line == cs.line)]
    out.append(f"Entradas de coches de la línea con tiempo real y `stops_away ≥ 0`: {len(prep_cs(cs))}; de ellas, coche presente en CABA ese día: {int(prep_cs(cs).in_caba.sum())}.")
    lag = (c_.t - c_.veh_ts)
    out.append(f"Antigüedad del GPS de CuandoSubo (t − `veh_ts`): P50 {lag.median():.0f} s, P90 {lag.quantile(.9):.0f} s.")
    return "\n".join(out)


if __name__ == "__main__":
    run = Path(sys.argv[1])
    txt = tables(run)
    outp = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else run.parent / "tablas.md"
    outp.write_text(txt, encoding="utf-8")
    print(txt)
