"""Diferencia pareada por dia contra base (media, desvio, dias con diff>0, dias con diff<0) para todas las cfg -> out/pareado.csv"""
import pandas as pd, numpy as np
pd.set_option("display.width", 300)
d = pd.read_csv("out/daily.csv")
M = ["fa", "faC", "faI", "om", "om_b", "om_1", "vac", "mae", "antes", "desp", "prov"]
b = d[d.cfg == "base"].set_index("day")[M]
rows = []
for c, g in d.groupby("cfg"):
    if c == "base":
        continue
    x = g.set_index("day")[M] - b
    r = {"cfg": c}
    for m in M:
        r[m] = x[m].mean(); r[m + "_sd"] = x[m].std(); r[m + "_pos"] = int((x[m] > 0).sum()); r[m + "_neg"] = int((x[m] < 0).sum())
    rows.append(r)
p = pd.DataFrame(rows).set_index("cfg")
p.to_csv("out/pareado.csv")
cols = ["fa", "faC", "om", "om_b", "om_1", "vac", "mae", "antes", "desp", "prov"]
print(p[cols].round(2).to_string())
