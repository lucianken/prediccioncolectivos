import json, numpy as np, pandas as pd, pyarrow.parquet as pq
O="data/ml/v4_eval_ext/"
t=pq.read_table(O+"ext_seen.parquet",columns=["line","shape_id","ts_p","observed_eta_s","day","in_frozen","dist_remaining_m","start_unknown"]).to_pandas()
t["pred"]=np.load(O+"ext_pred.npy").astype(float); t["ae"]=(t.pred-t.observed_eta_s).abs()
t["antes"]=(t.pred-t.observed_eta_s)>60; t["desp"]=(t.observed_eta_s-t.pred)>60
t["cl"]=t.day+"|"+t.line+"|"+t.shape_id.astype(str)+"|"+(t.ts_p//1800).astype(int).astype(str)
rng=np.random.default_rng(0); TH=71.1; res=[]
for ln,g in t.groupby("line"):
    codes,uni=pd.factorize(g.cl); k=len(uni)
    s=np.bincount(codes,weights=g.ae.values,minlength=k); c=np.bincount(codes,minlength=k)
    bs=[]
    for _ in range(2000):
        i=rng.integers(0,k,k); bs.append(s[i].sum()/c[i].sum())
    lo,hi=np.percentile(bs,[2.5,97.5])
    se=g.ae.std()/np.sqrt(len(g)); fz=g[g.in_frozen]; ad=g[~g.in_frozen]
    res.append(dict(line=ln,n=len(g),n_cl=k,mae=g.ae.mean(),ci_lo=lo,ci_hi=hi,iid_lo=g.ae.mean()-1.96*se,iid_hi=g.ae.mean()+1.96*se,
      p_below=float(np.mean(np.array(bs)<=TH)),n_frozen=len(fz),mae_frozen=fz.ae.mean() if len(fz) else np.nan,mae_add=ad.ae.mean(),n_dias=g.day.nunique(),
      antes=100*g.antes.mean(),desp=100*g.desp.mean(),su=100*g.start_unknown.mean()))
r=pd.DataFrame(res); r["pasa"]=(r.n>=100)&(r.mae<=TH); r["pasa_ic"]=(r.ci_hi<=TH)
pd.set_option("display.width",250); print(r.round(1).to_string()); r.to_csv(O+"resultados.csv",index=False)
