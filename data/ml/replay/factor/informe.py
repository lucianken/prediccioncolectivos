import sys, json
import numpy as np, pandas as pd
from analisis import *

REC = float(sys.argv[1]) if len(sys.argv) > 1 else 0.08


def fmt(m, sd, d=1): return f"{m:.{d}f} ± {sd:.{d}f}"


out = []
def P(s=""): out.append(s)


def block(cfgdict, band, mask=None):
    base_df, _ = table(prop(0), band, mask)
    P("| cfg | n | MAE próximo (s) | llega antes >60 s % | llega después >60 s % | espera extra media (s) | P90 error (s) | Δ MAE (s) | Δ antes (pp) | Δ después (pp) | Δ espera extra (s) |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    rows = {}
    for name, fn in cfgdict.items():
        o, df = summarize(name, fn, band, base_df, mask); rows[name] = o
        def d(k, dec=1): return f"{o['d_'+k]:+.{dec}f} ± {o['d_'+k+'_sd']:.{dec}f} ({o['d_'+k+'_pos']}/10)"
        P(f"| {name} | {o['n']} | {fmt(o['mae'],o['mae_sd'],0)} | {fmt(o['antes'],o['antes_sd'])} | {fmt(o['desp'],o['desp_sd'])} | {fmt(o['extra'],o['extra_sd'],0)} | {fmt(o['p90'],o['p90_sd'],0)} | {d('mae')} | {d('antes',2)} | {d('desp',2)} | {d('extra',0)} |")
    return rows


def loss(o, w): return w*o["antes"] + o["desp"]


prop_cfg = {("a = "+str(a).replace(".", ",")): prop(a) for a in AS}
res = {}
for band in ("3-7", "0-3", "7-15"):
    P(f"#### Banda de ETA real {band} min")
    P()
    res[band] = block(prop_cfg, band)
    P()

P("#### Pérdida ponderada L = w·(llega antes %) + (llega después %), banda 3–7 min")
P()
P("| a | L (w=1) | L (w=2) | L (w=3) | L (w=4) |")
P("|---|---|---|---|---|")
for name, o in res["3-7"].items():
    P(f"| {name} | " + " | ".join(f"{loss(o,w):.1f}" for w in (1, 2, 3, 4)) + " |")
P()

alts = {"a = 0": prop(0)}
for s in (10, 20, 30, 45, 60): alts[f"fijo −{s} s"] = fixed(s)
for a, cap in ((0.10, 30), (0.15, 30), (0.15, 45), (0.20, 45), (0.20, 60)): alts[f"a = {str(a).replace('.',',')} con tope {cap} s"] = capped(a, cap)
P("#### Alternativas: descuento fijo en segundos y factor con tope")
P()
for band in ("3-7", "0-3", "7-15"):
    P(f"**Banda real {band} min**"); P()
    block(alts, band); P()

P("#### Curva por banda de ETA anunciada (ETA sin factor; el real puede estar en cualquier banda; media de 10 días)")
P()
ABANDS = {"anunciado < 3 min": (0, 180), "anunciado 3–7 min": (180, 420), "anunciado 7–15 min": (420, 900), "anunciado > 15 min": (900, 1e9)}
P("| banda anunciada | n | a | MAE (s) | llega antes % | llega después % | L (w=2) | L (w=3) |")
P("|---|---|---|---|---|---|---|---|")
best = {}
for bn, (lo, hi) in ABANDS.items():
    m = (ann >= lo) & (ann < hi)
    ls = {}
    for a in AS:
        p = ann*(1-a); rows = []
        for d in DAYS:
            k = m & (day == d); rows.append(met(real[k], p[k]))
        df = pd.DataFrame(rows)
        o = dict(mae=df.mae.mean(), antes=df.antes.mean(), desp=df.desp.mean())
        ls[a] = o
        P(f"| {bn} | {int(m.sum())} | {str(a).replace('.',',')} | {o['mae']:.0f} | {o['antes']:.1f} | {o['desp']:.1f} | {loss(o,2):.1f} | {loss(o,3):.1f} |")
    best[bn] = {w: min(AS, key=lambda a: loss(ls[a], w)) for w in (2, 3)}
P()
P("Mejor a de la grilla por banda anunciada según L: " + "; ".join(f"{b}: w=2 → {v[2]}, w=3 → {v[3]}" for b, v in best.items()))
P()

pol = {"a = 0": prop(0), "a fijo = 0,08": prop(0.08)}
for t in [(0.08, 0.08, 0.05), (0.10, 0.10, 0.05), (0.05, 0.10, 0.05), (0.10, 0.10, 0.10), (0.05, 0.08, 0.03), (0.12, 0.12, 0.05)]:
    pol["por banda (<3 / 3–7 / ≥7 min): " + " / ".join(str(x).replace(".", ",") for x in t)] = banded(*t)
P("#### Factor por banda de ETA anunciada (<3 / 3–7 / ≥7 min)")
P()
for band in ("3-7", "0-3", "7-15"):
    P(f"**Banda real {band} min**"); P()
    block(pol, band); P()

P(f"#### Por línea, banda real 3–7 min: a = 0 → a = {str(REC).replace('.',',')}")
P()
P("| línea | n | MAE (s) | llega antes % | llega después % | espera extra (s) | P90 (s) |")
P("|---|---|---|---|---|---|---|")
lo, hi = BANDS["3-7"]
for ln in sorted(set(line), key=int):
    m = (real >= lo) & (real <= hi) & (line == ln)
    a0 = met(real[m], ann[m]); a1 = met(real[m], (ann*(1-REC))[m])
    P(f"| {ln} | {a0['n']} | {a0['mae']:.0f} → {a1['mae']:.0f} | {a0['antes']:.1f} → {a1['antes']:.1f} | {a0['desp']:.1f} → {a1['desp']:.1f} | {a0['extra']:.0f} → {a1['extra']:.0f} | {a0['p90']:.0f} → {a1['p90']:.0f} |")
P()
open("tablas.md", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(out))
