"""Arma tablas.md (fragmentos para COCHE_DETENIDO.md) desde out/daily.csv, byline.csv, flags.csv. Uso: python tablas_md.py [REC] (cfg recomendada)"""
import sys
import numpy as np, pandas as pd

REC = sys.argv[1] if len(sys.argv) > 1 else "N5_A50_b2_all"
d = pd.read_csv("out/daily.csv")
bl = pd.read_csv("out/byline.csv", dtype={"line": str})
fl = pd.read_csv("out/flags.csv", dtype={"line": str})
M = ["fa", "faC", "om", "om_b", "om_1", "vac", "mae", "antes", "desp"]
H = ["falsas alarmas %", "falsas alarmas causa C (pp de los listados)", "omisión %", "omisión 3–7 min %", "omisión 1.er coche %",
     "«viene» vacío %", "MAE próx. 3–7 (s)", "llega antes >60 s %", "llega después >60 s %"]
DG = {"mae": 1}
dg = lambda m: DG.get(m, 2 if m == "faC" else 1)
base = d[d.cfg == "base"].set_index("day")[M]
TR = {"a": "(a) descartar", "b1": "(b1) a provisional", "b2": "(b2) provisional y al final"}


def cell(x, g):
    return f"{x.mean():.{g}f} ± {x.std():.{g}f}"


def pair(c):
    x = d[d.cfg == c].set_index("day")[M] - base
    return " | ".join(f"{x[m].mean():+.{dg(m)+ (1 if m=='mae' else 0)}f} ± {x[m].std():.{dg(m)+ (1 if m=='mae' else 0)}f} ({int((x[m] > 0).sum())}↑/{int((x[m] < 0).sum())}↓)" for m in M)


def name(c):
    if c == "base":
        return "base (regla vigente, sin filtro)"
    n, a, t, l = c.split("_")
    return f"{n[1:]} min, {a[1:]} m, {TR[t]}" + ("" if l == "all" else f", solo {'cabecera' if l == 'cab' else 'mitad'}")


out = []
HEAD = "| variante | " + " | ".join(H) + " |\n|---|" + "---|" * len(M)
out.append("### T1. Grilla completa (posición: cualquiera). Media de los 10 días ± desvío día a día\n\n" + HEAD)
x = d[d.cfg == "base"]
out.append("| " + name("base") + " | " + " | ".join(cell(x[m], dg(m) if m != "mae" else 0) for m in M) + " |")
for N in (5, 10, 15):
    for A in (20, 50, 100):
        for t in ("a", "b1", "b2"):
            c = f"N{N}_A{A}_{t}_all"
            x = d[d.cfg == c]
            out.append("| " + name(c) + " | " + " | ".join(cell(x[m], dg(m) if m != "mae" else 0) for m in M) + " |")
PH = "| variante | " + " | ".join(H) + " |\n|---|" + "---|" * len(M)
out.append("\n### T2. Diferencia pareada contra base, por día (media ± desvío; días con diferencia > 0 ↑ / < 0 ↓), posición cualquiera\n\n" + PH)
for N in (5, 10, 15):
    for A in (20, 50, 100):
        for t in ("a", "b1", "b2"):
            c = f"N{N}_A{A}_{t}_all"
            out.append(f"| {name(c)} | {pair(c)} |")
out.append("\n### T3. Cabecera contra mitad de recorrido (ventana 5 min, avance 50 m): diferencia pareada contra base\n\n" + PH)
for t in ("a", "b1", "b2"):
    for l in ("all", "cab", "mid"):
        c = f"N5_A50_{t}_{l}"
        out.append(f"| {name(c)} | {pair(c)} |")
out.append("\n### T3b. Idem con ventana 10 min, avance 50 m\n\n" + PH)
for t in ("a", "b1", "b2"):
    for l in ("all", "cab", "mid"):
        c = f"N10_A50_{t}_{l}"
        out.append(f"| {name(c)} | {pair(c)} |")
f = fl.groupby(["N", "A", "loc"]).sum(numeric_only=True)
out.append("\n### T4. Coches que la regla marca entre los listados de la base (suma de 10 días): qué pasó con ellos\n\n"
           "| ventana (min) | avance (m) | posición | marcados | pasan ≤10 min % | pasan en 3–7 min % | pasan en 40 min % | falsa alarma % | falsa alarma causa C % | inmóviles todo el horizonte % | estaban en «viene» % | a < 500 m de la parada % |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
for (N, A, l), r in f.iterrows():
    out.append(f"| {N} | {A} | {l} | {int(r.n)} | {100*r.pass10/r.n:.1f} | {100*r.pass37/r.n:.1f} | {100*r.pass40/r.n:.1f} | {100*r.fa/r.n:.1f} | {100*r.faC/r.n:.1f} | {100*r.immobile/r.n:.1f} | {100*r.seguro/r.n:.1f} | {100*r.rem_lt500/r.n:.1f} |")
LM = ["fa", "faC", "om", "om_b", "vac", "mae", "antes", "desp"]
LH = ["falsas alarmas %", "causa C (pp)", "omisión %", "omisión 3–7 %", "«viene» vacío %", "MAE (s)", "antes %", "después %"]
bb = bl[bl.cfg == "base"].set_index("line")
rr = bl[bl.cfg == REC].set_index("line")
out.append(f"\n### T5. Por línea: base → {name(REC)} (10 días; la 26 solo 3)\n\n| línea | " + " | ".join(LH) + " |\n|---|" + "---|" * len(LM))
for ln in sorted(bb.index, key=int):
    out.append(f"| {ln} | " + " | ".join(f"{bb.loc[ln, m]:.{0 if m=='mae' else (2 if m=='faC' else 1)}f} → {rr.loc[ln, m]:.{0 if m=='mae' else (2 if m=='faC' else 1)}f}" for m in LM) + " |")
for alt in ("N5_A50_b2_mid", "N5_A50_a_all"):
    ar = bl[bl.cfg == alt].set_index("line")
    out.append(f"\n### T5b. Por línea: base → {name(alt)}\n\n| línea | " + " | ".join(LH) + " |\n|---|" + "---|" * len(LM))
    for ln in sorted(bb.index, key=int):
        out.append(f"| {ln} | " + " | ".join(f"{bb.loc[ln, m]:.{0 if m=='mae' else (2 if m=='faC' else 1)}f} → {ar.loc[ln, m]:.{0 if m=='mae' else (2 if m=='faC' else 1)}f}" for m in LM) + " |")
open("tablas.md", "w", encoding="utf-8").write("\n".join(out))
print("ok")
