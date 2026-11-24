import gzip,json,sys,collections,statistics as st
p=sys.argv[1]
mod60=collections.Counter(); age=[]; distinct=[]; share=[]; topshare=[]; n=0; frames=0
gap_between_ts=collections.Counter()
for line in gzip.open(p,'rt'):
    r=json.loads(line)
    if r.get('gap'): continue
    t=r['t']; recs=[v for v in r.get('new',[])+r.get('upd',[]) if v.get('ts')]
    if r.get('keyframe') or not recs: continue
    frames+=1
    c=collections.Counter(v['ts'] for v in recs)
    distinct.append(len(c)/len(recs)); topshare.append(c.most_common(1)[0][1]/len(recs))
    for ts,k in c.items():
        mod60[int(ts)%60]+=k; age.extend([t-ts]*k); n+=k
    # separación entre valores de ts distintos en el frame
    s=sorted(c); 
    for a,b in zip(s,s[1:]): gap_between_ts[int(b-a)]+=1
q=lambda x:[round(v,1) for v in st.quantiles(x,n=20)]
print('frames',frames,'updates',n)
print('ts distintos / updates por frame p50',round(st.median(distinct),3),'| mayor grupo con mismo ts p50',round(st.median(topshare),3),'p90',round(st.quantiles(topshare,n=10)[8],3))
print('edad t_poll-ts (s) p5..p95:',q(age))
print('ts mod 60 (segundo del minuto), top 15:',mod60.most_common(15))
tot=sum(mod60.values()); print('uniforme esperaria %.1f%% por segundo'%(100/60))
print('saltos entre ts distintos del frame, top 10:',gap_between_ts.most_common(10))
