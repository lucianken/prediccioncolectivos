import sys, re, json
sys.path.insert(0, "data/ml/ruido_tramos_feriados/scripts")
import pandas as pd
from mdutil import to_md
O = "data/ml/ruido_tramos_feriados/"
txt = open(O + "A_tablas.md", encoding="utf-8").read()
secs = re.split(r"\n### ", txt)[1:]
tabs = {}
for s in secs:
    head, _, body = s.partition("\n\n")
    if "cruce" in head: continue
    lines = [l for l in body.split("\n") if l.startswith("|")]
    cols = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = [[c.strip() for c in l.strip("|").split("|")] for l in lines[2:]]
    tabs[head] = pd.DataFrame(rows, columns=cols)
out = {}
for key in sorted({h.split(" | ")[0] for h in tabs}):
    o, p = tabs[key + " | modo obj"], tabs[key + " | modo ping"]
    m = pd.DataFrame({"estrato": o.estrato, "n (k=2, obj)": o["n (k=2)"], "obj MAE k=2": o["MAE k=2 (s)"], "obj P90 k=2": o["P90 k=2 (s)"], "obj MAE extrap.": o["MAE extrap. 1 intervalo (s)"], "obj P90 extrap.": o["P90 extrap. 1 intervalo (s)"]})
    pp = p.set_index("estrato")
    m["ping MAE k=2"] = m.estrato.map(pp["MAE k=2 (s)"]); m["ping P90 k=2"] = m.estrato.map(pp["P90 k=2 (s)"])
    m["ping MAE extrap."] = m.estrato.map(pp["MAE extrap. 1 intervalo (s)"]); m["ping P90 extrap."] = m.estrato.map(pp["P90 extrap. 1 intervalo (s)"])
    m["ping % >30 s (k=2)"] = m.estrato.map(pp["% >30 s (k=2)"])
    out[key] = m
with open(O + "A_tablas_merge.md", "w", encoding="utf-8") as f:
    for k, m in out.items():
        f.write(f"\n#### {k}\n\n" + "| " + " | ".join(m.columns) + " |\n|" + "|".join("---" for _ in m.columns) + "|\n" + "\n".join("| " + " | ".join(map(str, r)) + " |" for r in m.itertuples(index=False)) + "\n")
print(open(O + "A_tablas_merge.md", encoding="utf-8").read())
