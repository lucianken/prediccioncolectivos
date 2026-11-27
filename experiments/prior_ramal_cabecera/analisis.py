"""Calibracion, traduccion a producto y validacion con CuandoSubo. Lee result.pkl de prior.py."""
import pickle, json, re
from pathlib import Path
import numpy as np, pandas as pd
import sys
HERE = Path(__file__).parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(HERE))
from load import shape_table
from prior import ll
res = pickle.load(open(HERE / 'result.pkl', 'rb'))
out = []; P_ = lambda *a: out.append(' '.join(str(i) for i in a))
BEST = 'cq'

# ---- 1. tabla por linea (todas las cabeceras multi-ramal juntas), con IC bootstrap simple de accuracy no; se reporta n
rows = []
for gk, r in res.items():
    for m, P in r['P'].items():
        rows.append(dict(line=gk.split('|')[0], model=m, n=len(r['y']), llsum=ll(P, r['y']) * len(r['y']), c=int((P.argmax(1) == r['y']).sum())))
d = pd.DataFrame(rows).groupby(['line', 'model']).sum(); d['acc'] = d.c / d.n; d['ll'] = d.llsum / d.n
P_('## Tabla por linea (test 2026-09-15 a 10-14; acc / logloss)')
mods = ['unif', 'freq', 'a', 'b', 'c', 'cq']
P_('linea | n | ' + ' | '.join(mods))
for l in ['39', '42', '50', '106', '107', '132', '151', '168']:
    z = d.loc[l]; P_(f'{l} | {int(z.n.iloc[0])} | ' + ' | '.join(f'{z.loc[m,"acc"]:.3f} / {z.loc[m,"ll"]:.3f}' for m in mods))

# ---- 2. calibracion (pares viaje-ramal), deciles de P predicha
def reliability(Ps, ys, nb=10):
    p = np.concatenate([P.ravel() for P in Ps]); o = np.concatenate([(np.arange(P.shape[1])[None, :] == y[:, None]).ravel() for P, y in zip(Ps, ys)]).astype(float)
    q = pd.qcut(p, nb, duplicates='drop'); df = pd.DataFrame(dict(p=p, o=o, q=q)).groupby('q', observed=True).agg(p=('p', 'mean'), o=('o', 'mean'), n=('p', 'size'))
    ece = (abs(df.p - df.o) * df.n).sum() / df.n.sum(); return df, ece
def show(name, keys):
    df, ece = reliability([res[k]['P'][BEST] for k in keys], [res[k]['y'] for k in keys])
    P_(f'\n### Calibracion {BEST}: {name} (deciles de P predicha por par viaje-ramal; ECE {ece:.3f})'); P_('P media | frecuencia real | n')
    for _, z in df.iterrows(): P_(f'{z.p:.3f} | {z.o:.3f} | {int(z.n)}')
P_('\n## Calibracion')
show('todas las lineas', list(res)); show('linea 39', [k for k in res if k.startswith('39|')]); show('linea 168', [k for k in res if k.startswith('168|')])
# calibracion de base (freq) para comparar
df, ece = reliability([res[k]['P']['freq'] for k in res], [res[k]['y'] for k in res]); P_(f'ECE base freq (todas): {ece:.3f}')

# ---- 3. producto: P(ramal R) del prior vs tasa real por franja, dia habil
P_('\n## Traduccion a producto: P(pasa por parada exclusiva de R) = P(ramal=R) del prior (modelo cq) contra tasa real, habiles de test')
fr = {'pico 7-9': (7, 9), 'valle 11-15': (11, 15), 'noche 21-23': (21, 23)}
P_('cabecera | ramal | franja | P media prior | P freq (base) | tasa real | n')
for gk, r in res.items():
    g = r['g']; K = r['K']
    for ki, rm in enumerate(r['ram']):
        for fn, (h0, h1) in fr.items():
            m = ((g.tipo == 0) & (g.hour >= h0) & (g.hour <= h1)).values
            if m.sum() < 50: continue
            P_(f'{gk} | {rm} | {fn} | {r["P"][BEST][m, ki].mean():.2f} | {r["P"]["freq"][m, ki].mean():.2f} | {(r["y"][m] == ki).mean():.2f} | {int(m.sum())}')
P_('\nFraccion de viajes de test donde el prior da P(ramal mas probable) >= umbral, y su tasa real de acierto')
P_('linea | >=0.6: % viajes / acierto | >=0.8: % viajes / acierto')
for l in ['39', '42', '50', '106', '107', '132', '151', '168']:
    pm = np.concatenate([res[k]['P'][BEST].max(1) for k in res if k.startswith(l + '|')]); ok = np.concatenate([res[k]['P'][BEST].argmax(1) == res[k]['y'] for k in res if k.startswith(l + '|')])
    P_(f'{l} | ' + ' | '.join(f'{(pm >= t).mean()*100:.0f}% / {ok[pm >= t].mean() if (pm >= t).any() else float("nan"):.3f}' for t in (0.6, 0.8)))

# ---- 4. matriz de transicion 39 (prev1 -> actual) en train+test, para leer el patron
x = pd.read_parquet(HERE / 'trips8.parquet'); x = x[~x.start_unknown & (x.line == '39')]
for org in ['Barracas', 'Chacarita']:
    z = x[x.origin == org].sort_values('start_ts').copy(); z['prev'] = z.ramal.shift(); z['gap'] = z.start_ts.diff()
    z = z[z.gap <= 5400]; ct = pd.crosstab(z.prev, z.ramal, normalize='index').round(3)
    P_(f'\n### 39 {org}: P(ramal | ramal del despacho anterior, mismo origen, cualquier coche), n={len(z)}'); P_(ct.to_string())
    P_('gap mediano entre despachos (min):', round(z.gap.median() / 60, 1))

# ---- 5. validacion con CuandoSubo
routes = json.loads((ROOT.parent / 'proyectoconsola/ROUTE_AGENCY_MAP.json').read_text(encoding='utf-8'))['routes']
table = json.loads((ROOT.parent / 'proyectoconsola/public/config/ramal_cuandosubo.json').read_text(encoding='utf-8'))['ramales']
st = shape_table(); sh2r = {(a, b): c for a, b, c in zip(st.line, st.shape_id, st.ramal)}
n_ = lambda v: re.sub(r'\s+', ' ', str('' if v is None else v)).strip()
rid2r = {}
for rid, rr in routes.items():
    k = '|'.join(n_(rr.get(f)) for f in ('longName', 'shortName', 'description'))
    ids = table.get(k, {}).get('shape_ids') if k in table else None
    if not ids: continue
    ln = str(rr.get('shortName', '')).split()[0] if False else None
    rs = {sh2r[(l, str(i))] for i in ids for l in st.line.unique() if (l, str(i)) in sh2r}
    if len(rs) == 1: rid2r[str(rid)] = rs.pop()
P_('\n## Validacion contra CuandoSubo (route_id grabado en el viaje -> ramal; dias 2026-09-23 a 10-03 con datos)')
P_('linea | cabecera | n con CS | acuerdo etiqueta ex post-CS | modelo: acc ex post / acc CS | logloss ex post / CS | base freq acc CS')
for gk, r in res.items():
    g = r['g']; csr = g.route_id_diag.map(rid2r); m = (csr.notna() & (g.day >= '2026-09-23') & (g.day <= '2026-10-03')).values
    if m.sum() < 30 or gk.split('|')[0] not in ('39', '168', '42', '50', '106', '107', '132', '151'): continue
    yc = csr[m].map({rm: i for i, rm in enumerate(r['ram'])}).values
    if np.isnan(yc.astype(float)).any(): continue
    yc = yc.astype(int); ye = r['y'][m]; Pb = r['P'][BEST][m]; Pf = r['P']['freq'][m]
    P_(f'{gk} | {m.sum()} | {(yc == ye).mean():.3f} | cq acc {(Pb.argmax(1) == ye).mean():.3f} / {(Pb.argmax(1) == yc).mean():.3f} | {ll(Pb, ye):.3f} / {ll(Pb, yc):.3f} | freq acc {(Pf.argmax(1) == yc).mean():.3f} ll {ll(Pf, yc):.3f}')
# sentido b/c con modelo (b) y (a) tambien para 39 y 168
P_('\nDetalle 39 y 168 por modelo contra CS (acc / logloss; viajes con CS, todas las cabeceras)')
for l in ['39', '168']:
    ks = [k for k in res if k.startswith(l + '|')]; acc = {m: [] for m in mods}; lls = {m: [] for m in mods}; ys = []
    for k in ks:
        r = res[k]; g = r['g']; csr = g.route_id_diag.map(rid2r); m = (csr.notna() & (g.day >= '2026-09-23') & (g.day <= '2026-10-03')).values
        yc = csr[m].map({rm: i for i, rm in enumerate(r['ram'])}).values.astype(int)
        for mm in mods: acc[mm].append((r['P'][mm][m].argmax(1) == yc)); lls[mm].append(-np.log(np.clip(r['P'][mm][m][np.arange(m.sum()), yc], 1e-9, 1)))
    P_(l, 'n', sum(len(a) for a in acc['a']), ' | '.join(f'{mm} {np.concatenate(acc[mm]).mean():.3f} / {np.concatenate(lls[mm]).mean():.3f}' for mm in mods))
open(HERE / 'analisis_out.txt', 'w', encoding='utf8').write('\n'.join(out)); print('\n'.join(out))
