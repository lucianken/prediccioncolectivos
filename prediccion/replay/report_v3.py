"""
Informe de la vara de producto para v2c vs v3 (data/ml/replay/V3_PRODUCCION.md).

python -m prediccion.replay.report_v3 --v2c data/ml/replay/v3prod/v2c --v3 data/ml/replay/v3prod/v3 \
    --out data/ml/replay/V3_PRODUCCION.md --header h.md --conclusion c.md

Criterio de hora: el ETA anunciado es el de la app con la corrección de hora de CABA (ann0_*: mismo reloj del sello para los
pings y para el paso real, que es lo que da la app con CABA_TS_OFFSET_S contra la hora real). Sensibilidad: ann_* descuenta
además CABA_TS_OFFSET_S contra el paso real medido en la hora del sello.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.replay import metrics as M

PROD12 = ["26", "39", "42", "50", "92", "106", "107", "108", "124", "132", "151", "168"]
OFF = ["61", "88"]
KEYS = ["line", "day", "stop_id", "t"]


def f(x, d=1):
    return "—" if x is None or x != x else f"{x:.{d}f}"


def lsort(ls):
    return sorted(ls, key=lambda x: (len(x), x))


def line_metrics(inst: pd.DataFrame, veh: pd.DataFrame, col: str = "ann0_any_s") -> dict:
    b = M.next_bus(inst, col, *M.BAND)
    fa = M.false_alarms(veh)
    om = M.omissions(veh)
    sv = M.seguro_vacio(inst)
    return {"n": b["n"], "mae": b["mae_s"], "antes": b["antes_pct"], "despues": b["despues_pct"], "sin_anuncio": b["sin_anuncio_pct"],
            "fa": fa["falsa_alarma_pct"], "n_list": fa["listados"], "om": om["omision_pct"], "n_om": om["visibles"],
            "vacio": sv["sin_seguro_pct"], "n_vac": sv["n"]}


def by_line(inst, veh, lines, col="ann0_any_s") -> pd.DataFrame:
    rows = []
    for ln in lines:
        i, v = inst[inst.line == ln], veh[veh.line == ln]
        if len(i):
            rows.append({"line": ln, **line_metrics(i, v, col)})
    return pd.DataFrame(rows).set_index("line") if rows else pd.DataFrame()


def pooled(inst, veh, lines, col="ann0_any_s") -> dict:
    return line_metrics(inst[inst.line.isin(lines)], veh[veh.line.isin(lines)], col)


def common(i2, v2, i3, v3, lines):
    """Restringe v2c y v3 a los mismos (línea, día, parada, t) y a los mismos coches-instante."""
    i2, i3 = i2[i2.line.isin(lines)], i3[i3.line.isin(lines)]
    k = i2[KEYS].merge(i3[KEYS], on=KEYS)
    i2 = i2.merge(k, on=KEYS)
    i3 = i3.merge(k, on=KEYS)
    v2 = v2[v2.line.isin(lines)].merge(k, on=KEYS)
    v3 = v3[v3.line.isin(lines)].merge(k, on=KEYS)
    return i2, v2, i3, v3


def fmt_row(name, m):
    return (f"| {name} | {m['n']} | {f(m['mae'],0)} | {f(m['antes'])} | {f(m['despues'])} | {f(m['fa'])} | {f(m['om'])} | {f(m['vacio'])} | {f(m['sin_anuncio'])} |")


HDR = ("| {k} | n (parada,t) en banda | MAE próximo 3–7 min (s) | llega antes >60 s % | llega después >60 s % | falsas alarmas % | omisión ≤10 min % | «viene» vacío % | sin anuncio 3–7 min % |\n"
       "|---|---|---|---|---|---|---|---|---|")


def compare_table(i2, v2, i3, v3, lines) -> str:
    a, b = by_line(i2, v2, lines), by_line(i3, v3, lines)
    out = ["| línea | n banda | MAE v2c → v3 (s) | llega antes % v2c → v3 | llega después % v2c → v3 | falsas alarmas % v2c → v3 | omisión % v2c → v3 | «viene» vacío % v2c → v3 |", "|---|---|---|---|---|---|---|---|"]
    for ln in lines:
        if ln not in a.index:
            continue
        x, y = a.loc[ln], b.loc[ln]
        p = lambda k, d=1: f"{f(x[k], d)} → {f(y[k], d)}"  # noqa: E731
        out.append(f"| {ln} | {int(x['n'])} | {p('mae',0)} | {p('antes')} | {p('despues')} | {p('fa')} | {p('om')} | {p('vacio')} |")
    pa, pb = pooled(i2, v2, lines), pooled(i3, v3, lines)
    p = lambda k, d=1: f"{f(pa[k], d)} → {f(pb[k], d)}"  # noqa: E731
    out.append(f"| **12 líneas (agregado)** | {pa['n']} | **{p('mae',0)}** | {p('antes')} | {p('despues')} | {p('fa')} | {p('om')} | {p('vacio')} |")
    return "\n".join(out)


def flag_table(i3, v3, lines, title) -> tuple[str, pd.DataFrame]:
    d = by_line(i3, v3, lines)
    cols = ["mae", "antes", "despues", "fa", "om", "vacio"]
    med = d[cols].median()
    mad = (d[cols] - med).abs().median() * 1.4826
    z = (d[cols] - med) / mad.replace(0, np.nan)
    flag = []
    for ln in d.index:
        zz = z.loc[ln]
        bad = [c for c in cols if zz[c] > 1.5]
        small = d.loc[ln, "n"] < 200
        flag.append(("MUESTRA CHICA " if small else "") + ("PEOR: " + ", ".join(bad) if ("mae" in bad or len([c for c in bad if c != "mae"]) >= 2) else ""))
    d["marca"] = flag
    out = [f"#### {title}", "", "| línea | n banda | MAE (s) | llega antes % | llega después % | falsas alarmas % | omisión % | «viene» vacío % | sin anuncio % | marca |", "|---|---|---|---|---|---|---|---|---|---|"]
    for ln in d.index:
        r = d.loc[ln]
        out.append(f"| {ln} | {int(r['n'])} | {f(r['mae'],0)} | {f(r['antes'])} | {f(r['despues'])} | {f(r['fa'])} | {f(r['om'])} | {f(r['vacio'])} | {f(r['sin_anuncio'])} | {r['marca']} |")
    out.append(f"| **mediana** | | **{f(med['mae'],0)}** | {f(med['antes'])} | {f(med['despues'])} | {f(med['fa'])} | {f(med['om'])} | {f(med['vacio'])} | | |")
    out.append(f"| **MAD×1,4826** | | {f(mad['mae'],0)} | {f(mad['antes'])} | {f(mad['despues'])} | {f(mad['fa'])} | {f(mad['om'])} | {f(mad['vacio'])} | | |")
    return "\n".join(out), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2c", required=True)
    ap.add_argument("--v3", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--header", default=None)
    ap.add_argument("--conclusion", default=None)
    a = ap.parse_args()
    i2, v2 = M.load_run(a.v2c)
    i3, v3 = M.load_run(a.v3)
    days = lsort(set(i3.day.unique()))
    all3 = lsort(i3.line.unique())
    new34 = [ln for ln in all3 if ln not in PROD12 and ln not in OFF]
    parts = []
    if a.header:
        parts.append(Path(a.header).read_text(encoding="utf-8"))
    if a.conclusion:
        parts.append(Path(a.conclusion).read_text(encoding="utf-8"))
    parts += ["## Tablas", "", f"Días: {', '.join(days)}. Cada celda sale de los (parada, t) con coche real en la banda 3–7 min (próximo coche = primero del grupo «viene» y, si no hay, primero de «puede venir»/provisional).", ""]

    # 1. 12 líneas, v2c vs v3 en los mismos (parada, t)
    c2, cv2, c3, cv3 = common(i2, v2, i3, v3, PROD12)
    parts += ["### 1. 12 líneas de producción: v2c vs v3 (mismos días, paradas e instantes)", "",
              f"(parada, t) comunes: {len(c3)} de {len(i2[i2.line.isin(PROD12)])} (v2c) y {len(i3[i3.line.isin(PROD12)])} (v3).", "",
              "#### Agregado (ponderado por n)", "", HDR.format(k="modelo"),
              fmt_row("v2c_l1_s1 (contrato 2.1)", pooled(c2, cv2, PROD12)), fmt_row("v3_l1_s1 (contrato 2.2)", pooled(c3, cv3, PROD12)), "",
              "#### Por línea", "", compare_table(c2, cv2, c3, cv3, PROD12), ""]
    # sensibilidad de hora
    parts += ["#### Sensibilidad a la corrección de hora (12 líneas, agregado)", "",
              "| criterio | modelo | MAE 3–7 min (s) | llega antes >60 s % | llega después >60 s % |", "|---|---|---|---|---|"]
    for nm, col in (("con corrección de hora (ann0)", "ann0_any_s"), ("ETA − 60 s contra el paso en la hora del sello (ann)", "ann_any_s")):
        for mn, (ii, vv) in (("v2c", (c2, cv2)), ("v3", (c3, cv3))):
            m = pooled(ii, vv, PROD12, col)
            parts.append(f"| {nm} | {mn} | {f(m['mae'],0)} | {f(m['antes'])} | {f(m['despues'])} |")
    parts.append("")
    # por tipo de parada
    parts += ["#### Por tipo de parada (12 líneas)", "", "| tipo | modelo | n banda | MAE (s) | llega antes % | llega después % | falsas alarmas % | «viene» vacío % |", "|---|---|---|---|---|---|---|---|"]
    for cls in ("compartido", "exclusivo", "unico"):
        for mn, (ii, vv) in (("v2c", (c2, cv2)), ("v3", (c3, cv3))):
            i, v = ii[ii.stop_class == cls], vv[vv.stop_class == cls]
            if len(i):
                m = line_metrics(i, v)
                parts.append(f"| {cls} | {mn} | {m['n']} | {f(m['mae'],0)} | {f(m['antes'])} | {f(m['despues'])} | {f(m['fa'])} | {f(m['vacio'])} |")
    parts.append("")

    # 2. 34 líneas nuevas
    t2, d2 = flag_table(i3, v3, new34, "2. Las 34 líneas nuevas habilitadas (solo v3)")
    parts += ["### 2. Las 34 líneas nuevas habilitadas (solo v3)", "", t2.split("\n", 2)[2], ""]
    pn = pooled(i3, v3, new34)
    p12 = pooled(i3, v3, PROD12)
    parts += ["Agregado v3:", "", HDR.format(k="grupo"), fmt_row("12 líneas de producción", p12), fmt_row("34 líneas nuevas", pn), ""]

    # 3. no habilitadas
    parts += ["### 3. Líneas 61 y 88 (no habilitadas; solo v3)", "", HDR.format(k="línea")]
    for ln in OFF:
        if ln in all3:
            parts.append(fmt_row(ln, line_metrics(i3[i3.line == ln], v3[v3.line == ln])))
    parts.append("")
    parts += ["Contexto de datos de la muestra (v3):", "", "| línea | paradas | coches con ping | instantes (parada,t) | con paso ≤20 min % | coches evaluados por instante |", "|---|---|---|---|---|---|"]
    for ln in OFF + ["50", "39"]:
        i, v = i3[i3.line == ln], v3[v3.line == ln]
        if len(i):
            parts.append(f"| {ln} | {i.stop_id.nunique()} | {v.vehicle.nunique()} | {len(i)} | {f(100*(i.n_pass_20>0).mean())} | {f(i.n_shown_status.mean(),2)} |")
    parts.append("")
    # por día: variabilidad
    parts += ["### Variabilidad por día (agregado v3, 12 líneas / 34 nuevas)", "", "| día | MAE 12 líneas (s) | MAE 34 nuevas (s) |", "|---|---|---|"]
    for dd in days:
        a_ = pooled(i3[i3.day == dd], v3[v3.day == dd], PROD12)
        b_ = pooled(i3[i3.day == dd], v3[v3.day == dd], new34)
        parts.append(f"| {dd} | {f(a_['mae'],0)} | {f(b_['mae'],0)} |")
    Path(a.out).write_text("\n".join(parts) + "\n", encoding="utf-8")
    d2.to_csv(Path(a.out).with_suffix(".nuevas.csv"))


if __name__ == "__main__":
    main()
