import pandas as pd
pd.set_option("display.width", 250)
p = pd.read_csv("out/pooled.csv").set_index("cfg")
print(p.loc[["base"]].round(2).to_string())
print(p[p.index.str.startswith("N5_") & p.index.str.endswith("_all")].round(2).to_string())
print(p[p.index.str.startswith("N5_") & p.index.str.contains("_a_")].round(2).to_string())
f = pd.read_csv("out/flags.csv", dtype={"line": str}).groupby(["N", "A", "loc"]).sum(numeric_only=True)
for c in ("pass10", "pass37", "pass40", "fa", "faC", "immobile", "seguro", "rem_lt500"):
    f["p_" + c] = 100 * f[c] / f.n
print(f.round(1).to_string())
