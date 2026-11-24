import pandas as pd, numpy as np
D='c:/Users/LK/Documents/Dondeestaelbondi/prediccion colectivos/data/ml/v4/daily/'
days={'2026-09-15':'H','2026-09-16':'H','2026-09-17':'H','2026-09-18':'H','2026-09-21':'H','2026-09-19':'S','2026-09-20':'D'}
ram={382202:'A',382203:'A',382208:'B',382209:'B',382210:'C',382211:'C'}
sen={382202:'ida',382203:'vuelta',382208:'ida',382209:'vuelta',382210:'ida',382211:'vuelta'}
fr=[]
for d,t in days.items():
    x=pd.read_parquet(D+d+'.trips.parquet');x=x[x.line=='39'].copy();x['day']=d;x['tipo']=t;fr.append(x)
x=pd.concat(fr);x['sid']=pd.to_numeric(x.shape_id,errors='coerce')
x=x[x.sid.isin(ram)].copy()
x['r']=x.sid.map(ram);x['s']=x.sid.map(sen)
x['h']=pd.to_datetime(x.start_ts,unit='s',utc=True).dt.tz_convert('America/Argentina/Buenos_Aires').dt.hour
x['fr']=pd.cut(x.h,[-1,5,9,15,20,24],labels=['0-5','6-9','10-15','16-20','21-23'])
x=x.sort_values(['day','vehicle_id','start_ts']);x['pos']=x.groupby(['day','vehicle_id']).cumcount()+1
g=x.groupby(['day','vehicle_id'])
x['rp']=g.r.shift();x['sp']=g.s.shift()
out=[];P=lambda *a:out.append(' '.join(str(i) for i in a))
P('n viajes 39 con shape:',len(x),'| coche-dias:',g.ngroups,'| por dia:',x.groupby('day').size().to_dict())
P('\n## 1 Base');P('dist ramal global:',x.r.value_counts(normalize=True).round(3).to_dict())
mg=x.r.value_counts(normalize=True).iloc[0];P('acierto global (ramal mas frecuente):',round(mg,3),'n',len(x))
b=x.groupby(['s','fr'],observed=True).r.agg(lambda v:v.value_counts().iloc[0]/len(v));n=x.groupby(['s','fr'],observed=True).size()
P('por sentido x franja (acierto, n):');tot=0
for k in b.index:P(' ',k,round(b[k],3),n[k]);tot+=b[k]*n[k]
P('acierto ponderado sentido x franja (in-sample):',round(tot/len(x),3))
y=x.dropna(subset=['rp']).copy();y['ok']=y.r==y.rp
def t(name,key):
    P('\n##',name);r=y.groupby(key,observed=True).ok.agg(['mean','size']);P(r.round(3).to_string())
P('\n## 2 Persistencia: P(ramal=ramal previo)');P('general',round(y.ok.mean(),3),'n',len(y))
y['opuesto']=np.where(y.s!=y.sp,'opuesto','mismo')
t('sentido previo vs actual','opuesto')
y['posb']=y.pos.clip(upper=8);t('posicion del viaje (8=8+)','posb')
t('habil/sabado/domingo','tipo');y['fin']=np.where(y.tipo=='H','habil','finde');t('habil vs finde','fin')
t('opuesto x habil/finde',['opuesto','fin'])
# base para los mismos viajes (ramal mas frecuente) 
P('\nbase mismos viajes (A mas frec):',round((y.r==x.r.value_counts().index[0]).mean(),3))
P('\n## 3 Consistencia intra-dia')
c=g.r.agg(['nunique','size']);c=c[c['size']>=2];P('coche-dias con >=2 viajes:',len(c),'| un solo ramal:',round((c['nunique']==1).mean(),3))
P('coche-dias >=4 viajes:',(c['size']>=4).sum(),'un solo ramal:',round((c[c['size']>=4]['nunique']==1).mean(),3))
P('distrib ramales distintos/coche-dia:',c['nunique'].value_counts().sort_index().to_dict())
ch=g.r.apply(lambda v:(v!=v.shift()).sum()-1);ch=ch[c.index]
P('cambios de ramal por coche-dia: media',round(ch.mean(),2),'dist',ch.value_counts().sort_index().to_dict())
P('cambios por transicion: ',round((~y.ok).mean(),3))
# expected con asignacion aleatoria segun base: sum p^2
p=x.r.value_counts(normalize=True);P('P(igual) si independiente (sum p^2):',round((p**2).sum(),3))
P('\n## 4 Transicion ramal previo -> siguiente (n; fila %)')
ct=pd.crosstab(y.rp,y.r);P(ct.to_string());P((ct.div(ct.sum(1),axis=0)).round(3).to_string())
open('c:/Users/LK/Documents/Dondeestaelbondi/prediccion colectivos/experiments/ramal_persistencia_39/INFORME.md','w',encoding='utf8').write('# Persistencia de ramal, linea 39 (7 dias: 15-18,21 sep habiles; 19 sab; 20 dom)\nVerdad: shape asignado ex post por pipeline (v4 trips). ramal A=382202/3, B=382208/9, C=382210/11; sentido por nombre del shape (Barracas->=ida).\n```\n'+'\n'.join(out)+'\n```\n')
print('\n'.join(out))
