import pandas as pd, numpy as np
d=pd.read_csv("daily.csv"); p=pd.read_csv("pooled.csv").set_index("cfg"); bl=pd.read_csv("byline.csv")
M=["om","om_b","om_1","fa","vac","mae","antes","desp"]
H=["omisión %","omisión 3–7 min %","omisión 1.er coche %","falsas alarmas %","«viene» vacío %","MAE próx. 3–7 (s)","llega antes >60 s %","llega después >60 s %"]
def cell(x,dg=1): return f"{x.mean():.{dg}f} ± {x.std():.{dg}f} [{x.min():.{dg}f}–{x.max():.{dg}f}]"
def dec(m): return 0 if m=="mae" else 1
def row(name,c):
    x=d[d.cfg==c]; return f"| {name} | "+" | ".join(cell(x[m],dec(m)) for m in M)+" |"
HEAD="| regla | "+" | ".join(H)+" |\n|---|"+"---|"*len(M)
out=[]
out.append("### Barrido (historial completo de 15 min)\n\nCada celda: media de los 10 días ± desvío día a día [mín–máx].\n\n"+HEAD)
out.append(row("base (≥80 % de la ventana)","base"))
for k in (2,3,4):
    for n in (20,40,80): out.append(row(f"racha final k={k}, avance ≥{n} m",f"t{k}n{n}f0.6"))
out.append(row("eje frac: k=2, 40 m, frac 0,5","t2n40f0.5")); out.append(row("eje frac: k=2, 40 m, frac 0,75","t2n40f0.75"))
b=d[d.cfg=="base"].set_index("day")[M]
out.append("\n### Diferencia pareada contra base (por día, luego media ± desvío; días con diferencia > 0)\n\n| regla | "+" | ".join(H)+" |\n|---|"+"---|"*len(M))
for c,nm in [(f"t{k}n{n}f0.6",f"k={k}, {n} m") for k in (2,3,4) for n in (20,40,80)]+[("t2n40f0.5","k=2, 40 m, f 0,5"),("t2n40f0.75","k=2, 40 m, f 0,75")]:
    x=d[d.cfg==c].set_index("day")[M]-b
    out.append(f"| {nm} | "+" | ".join(f"{x[m].mean():+.{dec(m)+1 if m!='mae' else 1}f} ± {x[m].std():.{dec(m)+1 if m!='mae' else 1}f} ({int((x[m]>0).sum())}/10)" for m in M)+" |")
# warm-up
out.append("\n### Curva de arranque (historial recortado a N pings usados por la regla de sentido; N = pings incluido el actual; 15 min = completo)\n\nAgregado de los 10 días (ponderado). «desc.» = coches que pasan en ≤ 10 min y no quedan ni en la cola (sin sentido); «prov.» = % de los listados en «sentido sin confirmar».\n")
out.append("| regla | N | omisión % | omisión 3–7 % | omisión 1.er coche % | desc. % | falsas alarmas % | «viene» vacío % | MAE 3–7 (s) | antes % | después % | prov. % |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
for r,nm in [("base","base"),("t2n20f0.6","k=2, 20 m"),("t2n40f0.6","k=2, 40 m"),("t3n40f0.6","k=3, 40 m")]:
    for N in ("1","2","3","5","15 min"):
        c=r if N=="15 min" else f"{r}@{N}"; q=p.loc[c]
        out.append(f"| {nm} | {N} | {q.om:.1f} | {q.om_b:.1f} | {q.om_1:.1f} | {q.desc:.1f} | {q.fa:.1f} | {q.vac:.1f} | {q.mae:.0f} | {q.antes:.1f} | {q.desp:.1f} | {q.prov:.1f} |")
out.append("\n### Por línea: base → k=2, 40 m, frac 0,6 (10 días; la 26 solo tiene 3)\n\n| línea | omisión % | omisión 3–7 % | falsas alarmas % | «viene» vacío % | MAE (s) | antes % | después % |\n|---|---|---|---|---|---|---|---|")
a=bl[bl.cfg=="base"].set_index("line"); z=bl[bl.cfg=="t2n40f0.6"].set_index("line")
for ln in sorted(a.index,key=lambda s:int(s)):
    f=lambda m,dg=1: f"{a.loc[ln,m]:.{dg}f} → {z.loc[ln,m]:.{dg}f}"
    out.append(f"| {ln} | {f('om')} | {f('om_b')} | {f('fa')} | {f('vac')} | {f('mae',0)} | {f('antes')} | {f('desp')} |")
open("tablas.md","w",encoding="utf-8").write("\n".join(out))
