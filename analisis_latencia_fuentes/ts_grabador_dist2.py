import gzip,json,sys,collections,statistics as st
even=0;tot=0;nd=[];nu=[];last={};step=collections.Counter();hour=collections.defaultdict(list)
for line in gzip.open(sys.argv[1],'rt'):
    r=json.loads(line)
    if r.get('gap'): continue
    recs=[v for v in r.get('new',[])+r.get('upd',[]) if v.get('ts')]
    if not recs: continue
    if not r.get('keyframe'):
        c=collections.Counter(v['ts'] for v in recs); nd.append(len(c)); nu.append(len(recs))
        hour[(int(r['t'])-3*3600)//3600%24].append((len(c),len(recs), max(c)-min(c)))
    for v in recs:
        ts=int(v['ts']); tot+=1; even+= ts%2==0
        if v['id'] in last and not r.get('keyframe'): step[ts-last[v['id']]]+=1
        last[v['id']]=ts
print('ts pares: %.1f%%'%(100*even/tot))
print('valores de ts distintos por frame p50',st.median(nd),'para',st.median(nu),'coches')
s=sum(step.values()); print('paso de ts por coche (top):',[(k,'%.1f%%'%(100*n/s)) for k,n in step.most_common(8)])
for h in (3,8,13,18,22):
    x=hour[h]; 
    if x: print('hora',h,'distintos p50',st.median(a for a,_,_ in x),'coches',st.median(b for _,b,_ in x),'rango ts en frame p50',st.median(c for _,_,c in x),'s')
