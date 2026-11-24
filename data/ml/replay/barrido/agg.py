import json, glob, re, sys
from pathlib import Path
import numpy as np, pandas as pd
D = Path(__file__).parent
rows = []
for f in glob.glob(str(D / "run" / "*.json")):
    day, ln = Path(f).stem.split("_")
    for cfg, s in json.load(open(f)).items():
        rows.append(dict(day=day, line=ln, cfg=cfg, **s))
df = pd.DataFrame(rows)
SUMS = [c for c in df.columns if c not in ("day", "line", "cfg")]

def ratios(g):
    s = g[SUMS].sum()
    r = lambda a, b: 100 * s[a] / s[b] if s[b] else np.nan
    return pd.Series(dict(
        om=r("om_k", "om_n"), om_b=r("omb_k", "omb_n"), om_1=r("om1_k", "om1_n"), desc=r("desc_k", "om_n"),
        fa=r("fa_k", "fa_n"), vac=r("vac_k", "vac_n"),
        mae=s["nb_abs"] / s["nb_has"] if s["nb_has"] else np.nan, antes=r("nb_antes", "nb_has"), desp=r("nb_desp", "nb_has"),
        sin_anuncio=100 * (1 - s["nb_has"] / s["nb_n"]) if s["nb_n"] else np.nan,
        prov=r("lst_provisional", "fa_n"), list_inst=s["inst_listed_sum"] / s["inst_n"] if s["inst_n"] else np.nan))

def by(keys, cfgs=None):
    d = df if cfgs is None else df[df.cfg.isin(cfgs)]
    return d.groupby(keys).apply(ratios, include_groups=False)

METR = ["om", "om_b", "om_1", "desc", "fa", "vac", "mae", "antes", "desp", "prov", "list_inst"]
if __name__ == "__main__":
    daily = by(["cfg", "day"])
    daily.to_csv(D / "daily.csv"); by(["cfg", "line"]).to_csv(D / "byline.csv"); by(["cfg"]).to_csv(D / "pooled.csv")
    print(df.day.nunique(), df.line.nunique(), df.cfg.nunique())
    print(by(["cfg"]).round(2).to_string())
