"""Ratios por dia / linea / agregado a partir de stats.csv (agrega.py). Uso: python tablas.py DIR  -> daily.csv, byline.csv, pooled.csv"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "out"
df = pd.read_csv(D / "stats.csv", dtype={"line": str})
SUMS = [c for c in df.columns if c not in ("day", "line", "cfg")]


def ratios(g):
    s = g[SUMS].sum()
    r = lambda a, b: 100 * s[a] / s[b] if s[b] else np.nan
    return pd.Series(dict(
        fa=r("fa_k", "fa_n"), faC=r("faC_k", "fa_n"), faI=r("faI_k", "fa_n"), om=r("om_k", "om_n"), om_b=r("omb_k", "omb_n"),
        om_1=r("om1_k", "om1_n"), vac=r("vac_k", "vac_n"), mae=s["nb_abs"] / s["nb_has"] if s["nb_has"] else np.nan,
        antes=r("nb_antes", "nb_has"), desp=r("nb_desp", "nb_has"), prov=r("lst_provisional", "fa_n"),
        fa_seg=r("seg_fa_k", "seg_n"), fa_old=r("fa_old_k", "fa_old_n"), n_fa=s["fa_n"]))


def by(keys):
    return df.groupby(keys).apply(ratios, include_groups=False)


if __name__ == "__main__":
    by(["cfg", "day"]).to_csv(D / "daily.csv")
    by(["cfg", "line"]).to_csv(D / "byline.csv")
    p = by(["cfg"])
    p.to_csv(D / "pooled.csv")
    print(p.round(2).to_string())
