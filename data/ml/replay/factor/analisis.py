import sys, glob, json
import numpy as np, pandas as pd
RUN = r"c:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos\data\ml\replay\factor\run"
inst = pd.concat([pd.read_parquet(p, columns=["day","line","stop_id","t","real_next_s","ann0_any_s","ann0_seguro_s","ann_any_s"]) for p in sorted(glob.glob(RUN+"/*.inst.parquet"))], ignore_index=True)
inst = inst[inst.real_next_s.notna() & inst.ann0_any_s.notna()].reset_index(drop=True)
real = inst.real_next_s.to_numpy(); ann = inst.ann0_any_s.to_numpy()
day = inst.day.to_numpy(); line = inst.line.to_numpy()
DAYS = sorted(set(day))
BANDS = {"3-7": (180, 420), "0-3": (0, 180), "7-15": (420, 900)}
AS = [0, .03, .05, .08, .10, .12, .15, .20]

def met(r, p):
    e = r - p
    n = len(e)
    if n == 0: return dict(n=0, mae=np.nan, antes=np.nan, desp=np.nan, extra=np.nan, p90=np.nan)
    pos = e[e > 0]
    return dict(n=n, mae=np.abs(e).mean(), antes=100*(e < -60).mean(), desp=100*(e > 60).mean(),
                extra=pos.mean() if len(pos) else np.nan, p90=np.percentile(np.abs(e), 90))

def table(fn, band, mask=None):
    lo, hi = BANDS[band]
    m = (real >= lo) & (real <= hi)
    if mask is not None: m &= mask
    p = fn(ann)
    rows = []
    for d in DAYS:
        k = m & (day == d)
        rows.append(met(real[k], p[k]))
    return pd.DataFrame(rows, index=DAYS), met(real[m], p[m])

def summarize(name, fn, band, base_df=None, mask=None):
    df, pooled = table(fn, band, mask)
    out = {"cfg": name, "n": pooled["n"]}
    for k in ("mae", "antes", "desp", "extra", "p90"):
        out[k] = df[k].mean(); out[k+"_sd"] = df[k].std()
        if base_df is not None:
            dd = df[k] - base_df[k]
            out["d_"+k] = dd.mean(); out["d_"+k+"_sd"] = dd.std()
            out["d_"+k+"_pos"] = int((dd > 0).sum())
    return out, df

def prop(a): return lambda x: x*(1-a)
def fixed(s): return lambda x: np.maximum(0, x-s)
def capped(a, cap): return lambda x: x - np.minimum(a*x, cap)
def banded(a1, a2, a3): 
    return lambda x: np.where(x < 180, x*(1-a1), np.where(x < 420, x*(1-a2), x*(1-a3)))

if __name__ == "__main__" and False:
    res = {}
    cfgs = {f"a={a}": prop(a) for a in AS}
    for band in BANDS:
        _, b0 = table(prop(0), band); base_df, _ = table(prop(0), band)
        rows = []
        for name, fn in cfgs.items():
            o, _ = summarize(name, fn, band, base_df); rows.append(o)
        res["prop_"+band] = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)
    for k, v in res.items():
        print(k); print(v.round(2).to_string(index=False))
    print(len(inst), "filas; cobertura ann/real", )
