"""
Tablas de VARA_CORREGIDA.md (vara anterior contra corregida) y FILTRO_RAMAL_CS.md (base / cs / oráculo de ramal).

  python -m prediccion.replay.report_vara vara --runs data/ml/replay/vara/run_base data/ml/replay/vara/run_cs --days d1,d2,... --out f.md
  python -m prediccion.replay.report_vara cs   --runs data/ml/replay/vara/run_cs --out f.md
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.replay import metrics as M

ROOT = Path(__file__).resolve().parents[2]
CLASIF = ROOT / "data/ml/replay/falsas/clasif.parquet"
BANDS = [(0, 120), (120, 180), (180, 300), (300, 420), (420, 600), (600, 1200), (1200, 2400), (2400, 1e9)]
BAND_NAMES = ["0-2", "2-3", "3-5", "5-7", "7-10", "10-20", "20-40", ">40"]


def f(x, d=1):
    return "—" if x is None or x != x else f"{x:.{d}f}"


def load(runs, days=None, variants=None):
    insts, vehs, css = [], [], []
    for r in runs:
        i, v = M.load_run(r)
        css += [pd.read_parquet(p) for p in sorted(Path(r).glob("*.cs.parquet"))]
        insts.append(i)
        vehs.append(v)
    # un (variante, línea, día, parada, t[, coche]) que está en dos corridas (p. ej. el mismo día en run_base y run_cs) cuenta una vez
    inst = pd.concat(insts, ignore_index=True).drop_duplicates(["variant", "line", "day", "stop_id", "t"])
    veh = pd.concat(vehs, ignore_index=True).drop_duplicates(["variant", "line", "day", "stop_id", "t", "vehicle"])
    if days:
        inst, veh = inst[inst.day.isin(days)], veh[veh.day.isin(days)]
    if variants:
        inst, veh = inst[inst.variant.isin(variants)], veh[veh.variant.isin(variants)]
    cs = pd.concat(css, ignore_index=True) if css else pd.DataFrame()
    if days and len(cs):
        cs = cs[cs.day.isin(days)]
    return inst, veh, cs


def flat(inst, veh, corrected):
    s = M.summarize(inst, veh, corrected, ann0=True)
    band = M.false_alarms(veh, corrected, eta_band=(180, 420))
    fb = s["prox_seguro_o_fallback_banda"]
    sb = s["prox_seguro_banda"]
    return {"listados": s["falsas"]["listados"], "fa": s["falsas"]["falsa_alarma_pct"], "fa_37": band["falsa_alarma_pct"],
            "fa_seg": s["falsas"]["fa_seguro_pct"], "fa_pv": s["falsas"]["fa_puede_venir_pct"], "fa_prov": s["falsas"]["fa_provisional_pct"],
            "n_fuera": s["falsas"].get("n_fuera_horizonte"), "n_unv": s["falsas"].get("n_no_verificable"),
            "n_pasado": s["falsas"].get("n_ya_paso"), "n_eval": s["falsas"].get("n_evaluados", s["falsas"]["listados"]),
            "om": s["omisiones"]["omision_pct"], "om_n": s["omisiones"]["visibles"],
            "vacio": s["seguro_vacio"]["sin_seguro_pct"], "vacio_n": s["seguro_vacio"]["n"], "vacio_excl": s["seguro_vacio"]["n_excl_unv"],
            "mae": fb["mae_s"], "n_band": fb["n"], "antes": fb["antes_pct"], "desp": fb["despues_pct"], "sin_anuncio": fb["sin_anuncio_pct"],
            "n_excl_band": fb["n_excl_unv"], "mae_seg": sb["mae_s"], "antes_seg": sb["antes_pct"], "desp_seg": sb["despues_pct"],
            "n_seg": sb["n"]}


def vara_global(inst, veh):
    o, n = flat(inst, veh, False), flat(inst, veh, True)
    rows = [("Coches listados (los 5 mostrados)", "listados", 0), ("Falsas alarmas %, todo ETA anunciado", "fa", 1),
            ("Falsas alarmas %, ETA anunciado 3–7 min", "fa_37", 1), ("  «viene» (seguro) %", "fa_seg", 1),
            ("  «puede venir» %", "fa_pv", 1), ("  «sentido sin confirmar» (provisional) %", "fa_prov", 1),
            ("Omisión ≤10 min %", "om", 1), ("  n coches que pasan en ≤10 min con ping vigente", "om_n", 0),
            ("«Viene» vacío %", "vacio", 1), ("  n instantes con paso ≤10 min", "vacio_n", 0),
            ("MAE próximo coche, banda 3–7 min (s)", "mae", 0), ("  n instantes en la banda", "n_band", 0),
            ("Llega antes >60 s % (banda 3–7)", "antes", 1), ("Llega después >60 s % (banda 3–7)", "desp", 1),
            ("Sin anuncio % (banda 3–7)", "sin_anuncio", 1),
            ("MAE solo «viene», banda 3–7 (s)", "mae_seg", 0), ("  llega antes / después >60 s % (solo «viene»)", None, 0)]
    out = ["| métrica | anterior | corregida |", "|---|---|---|"]
    for name, k, d in rows:
        if k is None:
            out.append(f"| {name} | {f(o['antes_seg'])} / {f(o['desp_seg'])} | {f(n['antes_seg'])} / {f(n['desp_seg'])} |")
        else:
            out.append(f"| {name} | {f(o[k], d)} | {f(n[k], d)} |")
    ex = ["", "Lo que la vara corregida deja afuera o reclasifica (no es lo mismo que «falsa alarma resuelta»):", "",
          "| concepto | n |", "|---|---|",
          f"| listados con ETA anunciado > 40 min (fuera del horizonte; no entran en el denominador) | {n['n_fuera']} |",
          f"| listados «no verificables» (par de pings con hueco de 10–40 min que encierra la parada; no entran) | {n['n_unv']} |",
          f"| listados que ya habían pasado entre su último ping y t (llega antes; no es falsa alarma, entran en el denominador) | {n['n_pasado']} |",
          f"| listados evaluados (denominador de la falsa alarma corregida) | {n['n_eval']} |",
          f"| instantes en la banda 3–7 min excluidos por paso previo no verificable | {n['n_excl_band']} |",
          f"| instantes con paso ≤10 min excluidos del «viene» vacío por lo mismo | {n['vacio_excl']} |"]
    return "\n".join(out + ex) + "\n"


def vara_by_line(inst, veh):
    out = ["| línea | listados | falsas alarmas % ant → corr | FA 3–7 min % ant → corr | omisión % ant → corr | «viene» vacío % ant → corr | MAE 3–7 (s) ant → corr | llega antes % ant → corr | llega después % ant → corr |",
           "|---|---|---|---|---|---|---|---|---|"]
    for ln in sorted(inst.line.unique(), key=lambda x: (len(x), x)):
        i, v = inst[inst.line == ln], veh[veh.line == ln]
        o, n = flat(i, v, False), flat(i, v, True)
        p = lambda k, d=1: f"{f(o[k], d)} → {f(n[k], d)}"  # noqa: E731
        out.append(f"| {ln} | {o['listados']} | {p('fa')} | {p('fa_37')} | {p('om')} | {p('vacio')} | {p('mae', 0)} | {p('antes')} | {p('desp')} |")
    return "\n".join(out) + "\n"


def vara_by_band(veh):
    l = veh[veh.listed]
    out = ["| ETA anunciado (min) | listados | FA anterior % | listados evaluados | FA corregida % | ya pasó % | no verificable % |", "|---|---|---|---|---|---|---|"]
    for (lo, hi), nm in zip(BANDS, BAND_NAMES):
        x = l[(l.eta0_s >= lo) & (l.eta0_s < hi)]
        if not len(x):
            continue
        o = M.false_alarms(x, False)
        n = M.false_alarms(x, True)
        out.append(f"| {nm} | {len(x)} | {f(o['falsa_alarma_pct'])} | {n['n_evaluados']} | {f(n['falsa_alarma_pct'])} | "
                   f"{f(100 * n['n_ya_paso'] / max(len(x), 1))} | {f(100 * n['n_no_verificable'] / max(len(x), 1))} |")
    return "\n".join(out) + "\n"


def vara_by_cause(veh):
    """Qué le pasa a cada causa de FALSAS_ALARMAS (clasif.parquet, base, 10 días) con la definición corregida."""
    b = veh[(veh.variant == "base") & veh.listed]
    c = pd.read_parquet(CLASIF, columns=["line", "day", "stop_id", "t", "vehicle", "cause"])
    k = ["line", "day", "stop_id", "t", "vehicle"]
    m = c.merge(b[k + ["tp_s", "tp2_s", "unv", "past", "eta0_s"]], on=k, how="left")
    n_miss = int(m.eta0_s.isna().sum())
    m["res"] = "sigue falsa alarma"
    m.loc[m.eta0_s > M.HORIZON_S, "res"] = "fuera del horizonte"
    m.loc[(m.res == "sigue falsa alarma") & m.tp2_s.notna(), "res"] = "pasa (cruce firme)"
    m.loc[(m.res == "sigue falsa alarma") & m.unv, "res"] = "no verificable"
    m.loc[(m.res == "sigue falsa alarma") & m.past, "res"] = "ya pasó"
    m["cod"] = m.cause.str.split(" ").str[0]
    order = ["X0", "X3", "X2a", "X2b", "X2c", "X2d", "X1", "X4", "P", "S", "R1", "T1", "T2", "C", "G", "D", "O"]
    cols = ["fuera del horizonte", "pasa (cruce firme)", "no verificable", "ya pasó", "sigue falsa alarma"]
    ct = pd.crosstab(m.cod, m.res).reindex(order).fillna(0).astype(int)
    for cc in cols:
        if cc not in ct:
            ct[cc] = 0
    out = ["| causa (FALSAS_ALARMAS) | FA anteriores | fuera del horizonte | pasa (cruce firme) | no verificable | ya pasó | sigue falsa alarma | % que sale de las FA |", "|---|---|---|---|---|---|---|---|"]
    for cod in order:
        r = ct.loc[cod]
        tot = int(r[cols].sum())
        if not tot:
            continue
        out.append(f"| {cod} | {tot} | " + " | ".join(str(int(r[cc])) for cc in cols) + f" | {f(100 * (tot - r['sigue falsa alarma']) / tot, 0)} |")
    tot = ct[cols].sum()
    out.append(f"| **total** | {int(tot.sum())} | " + " | ".join(str(int(tot[cc])) for cc in cols) + f" | {f(100 * (tot.sum() - tot['sigue falsa alarma']) / tot.sum())} |")
    return "\n".join(out) + f"\n\n(Filas de FALSAS_ALARMAS sin par en esta corrida: {n_miss} de {len(m)}.)\n"


# ── filtro de ramal CuandoSubo ───────────────────────────────────────────────────────────────────────────

def cs_global(inst, veh):
    cols = {}
    for v in ("base", "cs", "ramal"):
        i, w = M.select(inst, veh, variant=v)
        cols[v] = flat(i, w, True)
    rows = [("Falsas alarmas %, todo ETA anunciado", "fa", 1), ("Falsas alarmas %, ETA anunciado 3–7 min", "fa_37", 1),
            ("  «viene» %", "fa_seg", 1), ("  «puede venir» %", "fa_pv", 1), ("  «sentido sin confirmar» %", "fa_prov", 1),
            ("Omisión ≤10 min %", "om", 1), ("«Viene» vacío %", "vacio", 1), ("MAE próximo coche 3–7 min (s)", "mae", 0),
            ("Llega antes >60 s % (3–7)", "antes", 1), ("Llega después >60 s % (3–7)", "desp", 1), ("Sin anuncio % (3–7)", "sin_anuncio", 1),
            ("MAE solo «viene» 3–7 (s)", "mae_seg", 0), ("Coches listados", "listados", 0)]
    out = ["| métrica (vara corregida) | base | cs (filtro CuandoSubo) | oráculo de ramal |", "|---|---|---|---|"]
    for name, k, d in rows:
        out.append(f"| {name} | " + " | ".join(f(cols[v][k], d) for v in ("base", "cs", "ramal")) + " |")
    return "\n".join(out) + "\n", cols


def cs_by_line(inst, veh):
    out = ["| línea | n banda | FA % base → cs → oráculo | omisión % | «viene» vacío % | MAE 3–7 (s) | llega antes % | llega después % |", "|---|---|---|---|---|---|---|---|"]
    for ln in sorted(inst.line.unique(), key=lambda x: (len(x), x)):
        c = {}
        for v in ("base", "cs", "ramal"):
            i, w = M.select(inst, veh, variant=v, line=ln)
            c[v] = flat(i, w, True)
        p = lambda k, d=1: " → ".join(f(c[v][k], d) for v in ("base", "cs", "ramal"))  # noqa: E731
        out.append(f"| {ln} | {c['base']['n_band']} | {p('fa')} | {p('om')} | {p('vacio')} | {p('mae', 0)} | {p('antes')} | {p('desp')} |")
    return "\n".join(out) + "\n"


def cs_by_day(inst, veh):
    """Diferencia cs − base por día (corregida): estabilidad del efecto."""
    rows = []
    for d in sorted(inst.day.unique()):
        c = {}
        for v in ("base", "cs"):
            i, w = M.select(inst[inst.day == d], veh[veh.day == d], variant=v)
            c[v] = flat(i, w, True)
        rows.append({"day": d, **{k: c["cs"][k] - c["base"][k] for k in ("fa", "om", "vacio", "mae", "antes", "desp")}})
    df = pd.DataFrame(rows)
    out = ["| día | Δ falsas alarmas (pp) | Δ omisión (pp) | Δ «viene» vacío (pp) | Δ MAE 3–7 (s) | Δ llega antes (pp) | Δ llega después (pp) |", "|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        out.append(f"| {r.day} | " + " | ".join(f"{r[k]:+.1f}" for k in ("fa", "om", "vacio", "mae", "antes", "desp")) + " |")
    out.append("| **media (rango)** | " + " | ".join(f"{df[k].mean():+.1f} ({df[k].min():+.1f}…{df[k].max():+.1f})" for k in ("fa", "om", "vacio", "mae", "antes", "desp")) + " |")
    out.append("| días con Δ < 0 | " + " | ".join(str(int((df[k] < 0).sum())) for k in ("fa", "om", "vacio", "mae", "antes", "desp")) + " |")
    return "\n".join(out) + "\n"


def cs_accuracy(cs):
    def row(x, name):
        n = len(x)
        inf = x.informado.mean() * 100
        tab = x.en_tabla.mean() * 100
        ap = x.aplicado.mean() * 100
        t = x[x.en_tabla & x.true_conocido]
        ok_t = t.true_en_terna.mean() * 100 if len(t) else np.nan
        a = x[x.aplicado & x.true_conocido]
        ok_a = a.true_en_inter.mean() * 100 if len(a) else np.nan
        # error: el filtro aplicado deja afuera el recorrido real
        err = (~a.true_en_inter).mean() * 100 if len(a) else np.nan
        return (f"| {name} | {n} | {f(inf)} | {f(tab)} | {f(ap)} | {len(t)} | {f(ok_t)} | {len(a)} | {f(ok_a)} | {f(err)} |")
    hdr = ["| grupo | (t, coche) | ramal informado % | y en la tabla (34 pares) % | filtro aplicado % | n con viaje ex post y en tabla | ramal correcto % (recorrido real ∈ shapes de la terna) | n aplicado con viaje ex post | recorrido real ∈ restricción % | restricción que excluye el recorrido real % |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    out = hdr + [row(cs, "todos")]
    out.append(row(cs[cs.n_compat >= 2], "ambiguos (≥2 shapes compatibles en la posición)"))
    out.append(row(cs[cs.n_compat == 1], "no ambiguos (1 shape compatible)"))
    for ln in sorted(cs.line.unique(), key=lambda x: (len(x), x)):
        out.append(row(cs[cs.line == ln], f"línea {ln}"))
    return "\n".join(out) + "\n"


def cs_effect(veh):
    """Omisiones y falsas alarmas que cambian de base a cs, partidas por si el ramal informado es incorrecto para ese coche."""
    k = ["line", "day", "stop_id", "t", "vehicle"]
    b = veh[veh.variant == "base"]
    c = veh[veh.variant == "cs"]
    pb = b[(b.tp2_s <= 600) & b.visible][k + ["listed"]].rename(columns={"listed": "lb"})
    pc = c[(c.tp2_s <= 600) & c.visible][k + ["listed", "cs_applied", "cs_wrong"]].rename(columns={"listed": "lc"})
    m = pb.merge(pc, on=k, how="inner")
    new = m[m.lb & ~m.lc]
    fixed = m[~m.lb & m.lc]
    out = {"n": len(m), "omit_base": int((~m.lb).sum()), "omit_cs": int((~m.lc).sum()), "nuevas": len(new), "arregladas": len(fixed),
           "nuevas_wrong": int(new.cs_wrong.sum()), "nuevas_aplicado_ok": int((new.cs_applied & ~new.cs_wrong).sum()),
           "nuevas_sin_filtro": int((~new.cs_applied).sum()), "wrong_total": int(m.cs_wrong.sum()), "applied_total": int(m.cs_applied.sum())}
    # falsas alarmas
    bl = b[b.listed & (b.eta0_s <= M.HORIZON_S) & ~(b.tp2_s.isna() & b.unv)].copy()
    bl["fa"] = bl.tp2_s.isna() & ~bl.past
    cl = c[c.listed & (c.eta0_s <= M.HORIZON_S) & ~(c.tp2_s.isna() & c.unv)].copy()
    cl["fa"] = cl.tp2_s.isna() & ~cl.past
    out["fa_base"], out["fa_cs"] = int(bl.fa.sum()), int(cl.fa.sum())
    out["n_base"], out["n_cs"] = len(bl), len(cl)
    out["fa_cs_wrong"] = int(cl[cl.fa].cs_wrong.sum())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["vara", "cs"])
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--days", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    days = [d for d in a.days.split(",") if d]
    parts = []
    if a.what == "vara":
        inst, veh, _ = load(a.runs, days, ["base"])
        parts += [f"Días: {', '.join(sorted(inst.day.unique()))}. Líneas: {', '.join(sorted(inst.line.unique(), key=lambda x: (len(x), x)))}.", "",
                  "### Global", "", vara_global(inst, veh), "### Por línea", "", vara_by_line(inst, veh),
                  "### Falsa alarma por ETA anunciado", "", vara_by_band(veh), "### Qué le pasa a cada causa de FALSAS_ALARMAS", "", vara_by_cause(veh)]
    else:
        inst, veh, cs = load(a.runs, days)
        g, _ = cs_global(inst, veh)
        eff = cs_effect(veh)
        parts += [f"Días: {', '.join(sorted(inst.day.unique()))}. Líneas: {', '.join(sorted(inst.line.unique(), key=lambda x: (len(x), x)))}.", "",
                  "### Global", "", g, "### Por línea", "", cs_by_line(inst, veh), "### Diferencia cs − base por día", "", cs_by_day(inst, veh),
                  "### Qué informa CuandoSubo y cuánto acierta", "", cs_accuracy(cs), "### Efecto de los errores", "", repr(eff), ""]
    Path(a.out).write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    main()
