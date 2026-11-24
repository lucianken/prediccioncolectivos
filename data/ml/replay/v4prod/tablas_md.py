import sys, numpy as np, pandas as pd
sys.path.insert(0, ".")
from pathlib import Path
d = pd.read_pickle("data/ml/replay/v4prod/resumen.pkl"); r4, rp, agg = d["rows4"], d["rowsp"], d["agg"]
L118 = open("data/ml/replay/v4prod/lines_118.txt").read().split(","); OLD46 = L118[:46]; NEW72 = L118[46:]
EXTRA = ["49","97","119","153","154","163","185","193","164"]
f = lambda x, k=1: "—" if x is None or x != x else f"{x:.{k}f}"
MET = ["mae", "antes", "desp", "fa", "om", "vacio"]
NM = {"mae": "MAE", "antes": "llega antes", "desp": "llega después", "fa": "bondi fantasma", "om": "bondi no anunciado", "vacio": "sin aviso firme"}
def flags(ref_lines, lines):
    ref = pd.DataFrame({l: r4[l] for l in ref_lines if l in r4}).T[MET].astype(float)
    med = ref.median(); mad = (ref - med).abs().median() * 1.4826; thr = med + 1.5 * mad
    out = {}
    for l in lines:
        if l not in r4: continue
        fl = [m for m in MET if r4[l][m] > thr[m]]
        out[l] = (fl, ("mae" in fl) or len(fl) >= 2)
    return med, mad, thr, out
o = []
# 1. pareada
o += ["| línea | n banda | MAE v3 → v4 (s) | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % |", "|---|---:|---|---|---|---|---|---|"]
def pr(a, b, k=1): return f"{f(a,k)} → {f(b,k)}"
for l in OLD46:
    if l not in rp: continue
    a, b, n = rp[l]
    o.append(f"| {l} | {a['n']} | {pr(a['mae'],b['mae'],0)} | {pr(a['antes'],b['antes'])} | {pr(a['desp'],b['desp'])} | {pr(a['fa'],b['fa'])} | {pr(a['om'],b['om'])} | {pr(a['vacio'],b['vacio'])} |")
for g, nm in (("12", "12 líneas viejas"), ("34", "34 líneas (v3 nuevas)"), ("46", "46 líneas")):
    if g in agg:
        a, b, n = agg[g]
        o.append(f"| **{nm}** | {a['n']} | {pr(a['mae'],b['mae'],1)} | {pr(a['antes'],b['antes'])} | {pr(a['desp'],b['desp'])} | {pr(a['fa'],b['fa'])} | {pr(a['om'],b['om'])} | {pr(a['vacio'],b['vacio'])} |")
T_pair = "\n".join(o)
dm = np.array([rp[l][1]["mae"] - rp[l][0]["mae"] for l in OLD46 if l in rp])
pair_txt = f"Diferencia de MAE por línea (v4 − v3): mediana {np.median(dm):+.1f} s, rango {dm.min():+.1f} a {dm.max():+.1f} s; v4 mejor en {(dm<0).sum()} de {len(dm)} líneas."
# 2. nuevas 72
med, mad, thr, fl = flags(NEW72, NEW72)
o = ["| línea | n banda | MAE (s) | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | marca |", "|---|---:|---:|---|---|---|---|---|---|"]
for l in sorted(NEW72, key=lambda x: -r4[x]["mae"] if x in r4 else 0):
    if l not in r4: continue
    x = r4[l]; ff, bad = fl[l]
    o.append(f"| {l} | {x['n']} | {f(x['mae'],0)} | {f(x['antes'])} | {f(x['desp'])} | {f(x['fa'])} | {f(x['om'])} | {f(x['vacio'])} | {('**BAJA** ' if bad else '') + ','.join(NM[m] for m in ff)} |")
o.append(f"| **mediana** | | {f(med['mae'],0)} | {f(med['antes'])} | {f(med['desp'])} | {f(med['fa'])} | {f(med['om'])} | {f(med['vacio'])} | |")
o.append(f"| **MAD×1,4826** | | {f(mad['mae'],0)} | {f(mad['antes'])} | {f(mad['desp'])} | {f(mad['fa'])} | {f(mad['om'])} | {f(mad['vacio'])} | |")
o.append(f"| **umbral (mediana + 1,5·MAD)** | | {f(thr['mae'],0)} | {f(thr['antes'])} | {f(thr['desp'])} | {f(thr['fa'])} | {f(thr['om'])} | {f(thr['vacio'])} | |")
T_new = "\n".join(o); prop = [l for l in NEW72 if l in fl and fl[l][1]]
# 3. las 8 actuales con v4, referencia = 34 de v3
med2, mad2, thr2, fl2 = flags(OLD46[12:], OLD46[12:])
cur = ["7","28","29","98","180","188","194","197"]
o = ["| línea | MAE v4 (s) | marcas con v4 (referencia: las 34 líneas de v3) | marca |", "|---|---:|---|---|"]
for l in cur:
    if l in r4: o.append(f"| {l} | {f(r4[l]['mae'],0)} | {','.join(NM[m] for m in fl2[l][0])} | {'BAJA' if fl2[l][1] else 'ya no'} |")
o.append(f"\nUmbrales (34 líneas, v4): " + ", ".join(f"{NM[m]} {f(thr2[m],1 if m!='mae' else 0)}" for m in MET) + ". Líneas de esas 34 que hoy serían BAJA: " + ", ".join(l for l in OLD46[12:] if l in fl2 and fl2[l][1]) + ".")
T_cur = "\n".join(o)
# 4. extra
o = ["| línea | n banda | MAE (s) | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | n días / paradas |", "|---|---:|---:|---|---|---|---|---|---|"]
for l in EXTRA:
    if l in r4:
        x = r4[l]; o.append(f"| {l} | {x['n']} | {f(x['mae'],0)} | {f(x['antes'])} | {f(x['desp'])} | {f(x['fa'])} | {f(x['om'])} | {f(x['vacio'])} | {x['n_dias']} / {x['n_stops']} |")
T_ex = "\n".join(o)
# agregados v4 118
def wavg(ls, k):
    w = np.array([r4[l]["n"] for l in ls if l in r4], float); v = np.array([r4[l][k] for l in ls if l in r4], float); m = ~np.isnan(v)
    return (w[m] * v[m]).sum() / w[m].sum()
o = ["| grupo | líneas | n banda | MAE (s) | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % |", "|---|---:|---:|---|---|---|---|---|---|"]
for nm, ls in (("12 viejas", L118[:12]), ("34 de v3", L118[12:46]), ("72 nuevas", NEW72), ("118 habilitadas", L118), ("9 sin habilitar", EXTRA)):
    k = [l for l in ls if l in r4]
    o.append(f"| {nm} | {len(k)} | {sum(r4[l]['n'] for l in k)} | {f(wavg(k,'mae'),0)} | {f(wavg(k,'antes'))} | {f(wavg(k,'desp'))} | {f(wavg(k,'fa'))} | {f(wavg(k,'om'))} | {f(wavg(k,'vacio'))} |")
T_grp = "\n".join(o)
Path("data/ml/replay/v4prod/tablas.md").write_text("\n\n".join(["## Grupos (v4, ponderado por n; promedio de tasas por línea)", T_grp, "## Pareada", pair_txt, T_pair, "## 72 nuevas", T_new, "Propuesta: " + ", ".join(prop), "## 8 actuales", T_cur, "## Extra", T_ex]), encoding="utf-8")
print("ok", prop)
