"""Segunda ronda (v3): mismo metodo que load.py/prior.py/analisis.py sobre las 36 lineas nuevas de train de v3 + 12 de control.
Correr desde 'prediccion colectivos': python experiments/prior_ramal_cabecera/ronda2.py   (Python313).
Salidas: trips48.parquet, result48.pkl, ronda2_out.txt, ronda2_lineas.csv, ronda2_cs.csv"""
import json, glob, re, pickle, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(HERE))
import prior
from prior import ll, run_group, TRAIN, TEST
L = json.load(open(ROOT / 'data/ml/v3/lines.json'))
NEW, CTRL = L['new_lines'], L['heldout']; LINES = NEW + CTRL
ORIG = ['39', '42', '50', '106', '107', '132', '151', '168']; assert not set(LINES) & set(ORIG)
SH = ROOT.parent / 'proyectoconsola/data/line_shapes'


def shape_table():
    rows = []
    for l in LINES:
        d = json.load(open(SH / f'{l}.json', encoding='utf8'))
        for x in d['ramales']:
            tail = x['name'].split(':', 1)[1].strip(); origin = re.split(r'\s*→', tail)[0].strip()
            rows.append(dict(line=l, shape_id=str(x['shapeId']), ramal=x['shortName'].replace(' ', ''), origin=origin))
    return pd.DataFrame(rows)


def build():
    st = shape_table(); fr = []
    for f in sorted(glob.glob(str(ROOT / 'data/ml/v4/daily/*.trips.parquet'))):
        x = pd.read_parquet(f); x = x[x.line.isin(LINES)].copy(); x['day'] = Path(f).name[:10]; fr.append(x)
    x = pd.concat(fr); x['shape_id'] = x.shape_id.astype(str)
    x = x.merge(st, on=['line', 'shape_id'], how='inner'); x.to_parquet(HERE / 'trips48.parquet'); return x, st


def prep(x):
    x = x[~x.start_unknown].copy()
    t = pd.to_datetime(x.start_ts, unit='s', utc=True).dt.tz_convert('America/Argentina/Buenos_Aires')
    x['hour'] = t.dt.hour; wd = t.dt.weekday
    x['tipo'] = np.where(wd < 5, 0, np.where(wd == 5, 1, 2)); x.loc[x.day.isin(prior.FERIADOS), 'tipo'] = 2
    x['gkey'] = x.line + '|' + x.origin
    k = x.groupby('gkey').ramal.nunique(); x['multi'] = x.gkey.map(k) >= 2
    return x.sort_values(['gkey', 'start_ts']).reset_index(drop=True)


out = []; P_ = lambda *a: out.append(' '.join(str(i) for i in a))
raw, st = build(); allx = prep(raw)
te_all = allx[(allx.day >= TEST[0]) & (allx.day <= TEST[1])]
P_('trips', len(raw), 'start_unknown=0:', len(allx), 'test:', len(te_all))
info = []
for l in LINES:
    s = st[st.line == l]; a = allx[allx.line == l]; t = te_all[te_all.line == l]
    mg = sorted(a[a.multi].gkey.unique())
    info.append(dict(line=l, grp='ctrl' if l in CTRL else 'new', shapes=len(s), ramales=s.ramal.nunique(), ramales_obs=a.ramal.nunique(), n_test=len(t),
                     cab_multi=len(mg), cab_multi_names=';'.join(g.split('|', 1)[1] + '(' + str(a[a.gkey == g].ramal.nunique()) + ')' for g in mg),
                     peso_test=t.multi.mean() if len(t) else np.nan, peso_all=a.multi.mean() if len(a) else np.nan))
info = pd.DataFrame(info).set_index('line')
MINTR, MINTE = 150, 100
x = allx[allx.multi]; res = {}; skipped = []
for gk, g in x.groupby('gkey', sort=False):
    g = g.reset_index(drop=True); ram = sorted(g.ramal.unique())
    ntr = ((g.day >= TRAIN[0]) & (g.day <= TRAIN[1])).sum(); nte = ((g.day >= TEST[0]) & (g.day <= TEST[1])).sum()
    if ntr < MINTR or nte < MINTE: skipped.append((gk, int(ntr), int(nte))); continue
    r = run_group(g, ram); r['g'] = g.iloc[r['idx']][['line', 'origin', 'day', 'hour', 'tipo', 'start_ts', 'vehicle_id', 'ramal', 'route_id_diag']].reset_index(drop=True); res[gk] = r
pickle.dump(res, open(HERE / 'result48.pkl', 'wb'))
P_('grupos evaluados', len(res), 'omitidos (train<%d o test<%d):' % (MINTR, MINTE), skipped)
mods = ['unif', 'freq', 'a', 'b', 'c', 'cq']
rows = []
for gk, r in res.items():
    for m, P in r['P'].items():
        rows.append(dict(line=gk.split('|')[0], model=m, n=len(r['y']), llsum=ll(P, r['y']) * len(r['y']), c=int((P.argmax(1) == r['y']).sum())))
d = pd.DataFrame(rows).groupby(['line', 'model']).sum(); d['acc'] = d.c / d.n; d['ll'] = d.llsum / d.n


def reliability(Ps, ys, nb=10):
    p = np.concatenate([P.ravel() for P in Ps]); o = np.concatenate([(np.arange(P.shape[1])[None, :] == y[:, None]).ravel() for P, y in zip(Ps, ys)]).astype(float)
    q = pd.qcut(p, nb, duplicates='drop'); df = pd.DataFrame(dict(p=p, o=o, q=q)).groupby('q', observed=True).agg(p=('p', 'mean'), o=('o', 'mean'), n=('p', 'size'))
    return df, (abs(df.p - df.o) * df.n).sum() / df.n.sum()


tab = []
for l in sorted({k.split('|')[0] for k in res}, key=lambda s: int(s)):
    ks = [k for k in res if k.startswith(l + '|')]; z = d.loc[l]
    _, ece = reliability([res[k]['P']['cq'] for k in ks], [res[k]['y'] for k in ks]); _, ecef = reliability([res[k]['P']['freq'] for k in ks], [res[k]['y'] for k in ks])
    pm = np.concatenate([res[k]['P']['cq'].max(1) for k in ks]); ok = np.concatenate([res[k]['P']['cq'].argmax(1) == res[k]['y'] for k in ks])
    row = dict(line=l, grp=info.loc[l, 'grp'], n=int(z.n.iloc[0]), peso=info.loc[l, 'peso_test'])
    for m in mods: row['acc_' + m] = z.loc[m, 'acc']; row['ll_' + m] = z.loc[m, 'll']
    row.update(ece_cq=ece, ece_freq=ecef, p80=(pm >= .8).mean(), acc80=ok[pm >= .8].mean() if (pm >= .8).any() else np.nan, p60=(pm >= .6).mean(), acc60=ok[pm >= .6].mean() if (pm >= .6).any() else np.nan,
               dll=z.loc['freq', 'll'] - z.loc['cq', 'll'], dacc=z.loc['cq', 'acc'] - z.loc['freq', 'acc'])
    row['dll_pond'] = row['dll'] * (row['peso'] if not np.isnan(row['peso']) else 0); tab.append(row)
T = pd.DataFrame(tab).sort_values('dll_pond', ascending=False); T.to_csv(HERE / 'ronda2_lineas.csv', index=False)
pd.set_option('display.width', 400); pd.set_option('display.max_columns', 50)
P_('\n## Estructura por linea'); P_(info.to_string())
P_('\n## Tabla por linea ordenada por dll_pond'); P_(T.round(3).to_string())
allg = list(res); df, ece = reliability([res[k]['P']['cq'] for k in allg], [res[k]['y'] for k in allg])
_, ecef = reliability([res[k]['P']['freq'] for k in allg], [res[k]['y'] for k in allg])
P_(f'\n## Calibracion cq global ECE {ece:.3f} (freq {ecef:.3f})'); P_(df.round(3).to_string())
for nm, sel in (('new', NEW), ('ctrl', CTRL)):
    ks = [k for k in res if k.split('|')[0] in sel]
    if ks: P_(nm, 'ECE cq', round(reliability([res[k]['P']['cq'] for k in ks], [res[k]['y'] for k in ks])[1], 3))
n_all = sum(len(r['y']) for r in res.values()); pm = np.concatenate([r['P']['cq'].max(1) for r in res.values()]); ok = np.concatenate([r['P']['cq'].argmax(1) == r['y'] for r in res.values()])
for t in (.6, .8): P_(f'global P>={t}: {(pm >= t).mean():.3f} acierto {ok[pm >= t].mean():.3f}')
accs = {m: np.concatenate([r['P'][m].argmax(1) == r['y'] for r in res.values()]).mean() for m in mods}
lls = {m: sum(ll(r['P'][m], r['y']) * len(r['y']) for r in res.values()) / n_all for m in mods}
P_('global acc', {m: round(v, 3) for m, v in accs.items()}); P_('global ll', {m: round(v, 3) for m, v in lls.items()})
tot_te = info.n_test.sum(); mt = (info.peso_test * info.n_test).sum()
P_(f'\nlineas con cabecera multi-ramal: {(info.cab_multi > 0).sum()} de {len(info)}; despachos test en cabecera multi: {mt:.0f} de {tot_te} ({mt / tot_te:.3f}); evaluados: {n_all}')
P_('lineas evaluadas', len(T), ' dll>=0.05:', (T.dll >= .05).sum(), ' dll>=0.10:', (T.dll >= .10).sum(), ' dacc>=0.05:', (T.dacc >= .05).sum(), ' dacc>=0.10:', (T.dacc >= .10).sum())

routes = json.loads((ROOT.parent / 'proyectoconsola/ROUTE_AGENCY_MAP.json').read_text(encoding='utf-8'))['routes']
table = json.loads((ROOT.parent / 'proyectoconsola/public/config/ramal_cuandosubo.json').read_text(encoding='utf-8'))['ramales']
sh2r = {(a, b): c for a, b, c in zip(st.line, st.shape_id, st.ramal)}
n_ = lambda v: re.sub(r'\s+', ' ', str('' if v is None else v)).strip()
rid2r = {}
for rid, rr in routes.items():
    k = '|'.join(n_(rr.get(f)) for f in ('longName', 'shortName', 'description'))
    ids = table.get(k, {}).get('shape_ids') if k in table else None
    if not ids: continue
    rs = {sh2r[(l, str(i))] for i in ids for l in st.line.unique() if (l, str(i)) in sh2r}
    if len(rs) == 1: rid2r[str(rid)] = rs.pop()
P_('\n## CuandoSubo (2026-09-23 a 10-03), por linea (cabeceras evaluadas juntas; viajes con ramal CS unico resuelto y dentro de los ramales de la cabecera)')
P_('linea | n CS | (grupo,ramal CS) distintos | acuerdo ex post-CS | cq acc ex post / CS | freq acc CS | cq ll CS | freq ll CS')
cs = []
for l in sorted({k.split('|')[0] for k in res}, key=lambda s: int(s)):
    A = []
    for k in [k for k in res if k.startswith(l + '|')]:
        r = res[k]; g = r['g']; csr = g.route_id_diag.map(rid2r); m = (csr.notna() & (g.day >= '2026-09-23') & (g.day <= '2026-10-03') & csr.isin(r['ram'])).values
        if not m.any(): continue
        mp = {rm: i for i, rm in enumerate(r['ram'])}; yc = csr[m].map(mp).values.astype(int); ye = r['y'][m]
        A.append((yc, ye, r['P']['cq'][m], r['P']['freq'][m]))
    if not A: continue
    yc = np.concatenate([a[0] for a in A]); ye = np.concatenate([a[1] for a in A])
    acc_c = np.concatenate([a[2].argmax(1) == a[0] for a in A]); acc_e = np.concatenate([a[2].argmax(1) == a[1] for a in A]); acc_f = np.concatenate([a[3].argmax(1) == a[0] for a in A])
    llc = np.concatenate([-np.log(np.clip(a[2][np.arange(len(a[0])), a[0]], 1e-9, 1)) for a in A]); llf = np.concatenate([-np.log(np.clip(a[3][np.arange(len(a[0])), a[0]], 1e-9, 1)) for a in A])
    nd = len({(ai, v) for ai, a in enumerate(A) for v in set(a[0])})
    cs.append(dict(line=l, n=len(yc), ndist=nd, agree=(yc == ye).mean(), acc_cq_ep=acc_e.mean(), acc_cq_cs=acc_c.mean(), acc_f_cs=acc_f.mean(), ll_cq=llc.mean(), ll_f=llf.mean()))
    P_(f'{l} | {len(yc)} | {nd} | {(yc == ye).mean():.3f} | {acc_e.mean():.3f} / {acc_c.mean():.3f} | {acc_f.mean():.3f} | {llc.mean():.3f} | {llf.mean():.3f}')
pd.DataFrame(cs).to_csv(HERE / 'ronda2_cs.csv', index=False)
open(HERE / 'ronda2_out.txt', 'w', encoding='utf8').write('\n'.join(out)); print('\n'.join(out))
