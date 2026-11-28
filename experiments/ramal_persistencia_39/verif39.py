"""Verificacion: calidad de etiqueta (tramo exclusivo) + contraste con route_id de CuandoSubo. Linea 39.
Correr desde 'prediccion colectivos' con PYTHONPATH=. : python experiments/ramal_persistencia_39/verif39.py"""
import sys, collections
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from prediccion.replay.run import build_cs_rid
from prediccion.v2.day import geometry_for_trip, read_day, segment_vehicles
from prediccion.v2.shapes import LineShapes
from red.label_map import load_label_line_data, resolve_label_line_index
DAYS = {'2026-09-24': 'H', '2026-09-25': 'H', '2026-09-26': 'S'}
RAM = {'382202': 'A', '382203': 'A', '382208': 'B', '382209': 'B', '382210': 'C', '382211': 'C'}
SEN = {'382202': 'ida', '382203': 'vuelta', '382208': 'ida', '382209': 'vuelta', '382210': 'ida', '382211': 'vuelta'}
EXC_NEAR, EXC_FAR, MINP = 40.0, 100.0, 3
shp = ROOT.parent / 'proyectoconsola/data/line_shapes'
shapes = LineShapes(shp); idx = shapes.indices('39')
cs = build_cs_rid(ROOT.parent / 'proyectoconsola/ROUTE_AGENCY_MAP.json', ROOT.parent / 'proyectoconsola/public/config/ramal_cuandosubo.json')
rows = []
for day, tipo in DAYS.items():
    li = resolve_label_line_index(load_label_line_data(str(ROOT / 'LABEL_LINE_MAP.json')), on_date=day)
    lm = {s: v['line'] for s, v in li.items()}
    veh, _, _ = read_day(Path('//192.168.0.18/buffer/grabaciones') / f'{day}.ndjson.gz', lm, {'39'}, None, 30, False)
    trips = segment_vehicles(veh, li, shapes, 'geo2')
    for tr in trips:
        if tr.line_number != '39' or not tr.points: continue
        g = geometry_for_trip(tr, idx, assign='geo3')
        if not g or str(g['shape_id']) not in RAM: continue
        sid = str(g['shape_id']); r = RAM[sid]
        lat = np.array([p.lat for p in tr.points]); lon = np.array([p.lon for p in tr.points]); ts = np.array([p.ts for p in tr.points])
        perp = {s: idx[s].project_many(lat, lon)[1] for s in RAM if s in idx}
        exc = {}
        for R in 'ABC':
            near = np.min([perp[s] for s in perp if RAM[s] == R], axis=0)
            far = np.min([perp[s] for s in perp if RAM[s] != R], axis=0)
            exc[R] = int(((near <= EXC_NEAR) & (far >= EXC_FAR)).sum())
        obs = veh[tr.vehicle_id]['obs']
        rids = [str(o[10]) for o in obs if ts[0] <= o[0] <= ts[-1] and len(o) > 10 and o[10]]
        csr = None
        if rids:
            rid = collections.Counter(rids).most_common(1)[0][0]
            terna, ids = cs.get(rid, (None, None))
            if ids:
                rs = {RAM[i] for i in ids if i in RAM}
                if len(rs) == 1: csr = rs.pop()
        other = max(exc[o] for o in 'ABC' if o != r)
        rows.append(dict(day=day, tipo=tipo, veh=tr.vehicle_id, t0=ts[0], n=len(ts), sid=sid, r=r, s=SEN[sid],
                         exc_own=exc[r], exc_other=other, csr=csr, n_rids=len(rids)))
x = pd.DataFrame(rows).sort_values(['day', 'veh', 't0'])
x['conf'] = x.exc_own >= MINP
x['frac_own'] = x.exc_own / x.n
x.to_parquet(Path(__file__).parent / 'verif39.parquet')
out = []; P = lambda *a: out.append(' '.join(str(i) for i in a))
P('dias', list(DAYS), '| viajes 39 con shape:', len(x), '| con ramal CuandoSubo resuelto a ramal unico:', int(x.csr.notna().sum()))
P(f'\n### 1 Calidad etiqueta (ping exclusivo = a <={EXC_NEAR:.0f} m del ramal y >={EXC_FAR:.0f} m de los otros; confirmado = >={MINP} pings exclusivos del ramal asignado)')
P('viajes confirmados:', int(x.conf.sum()), 'de', len(x), round(x.conf.mean(), 3))
P('confirmados por ramal (media, n):', x.groupby('r').conf.agg(['mean', 'size']).round(3).to_dict('index'))
P('fraccion de pings del viaje en tramo exclusivo propio: mediana', round(x.frac_own.median(), 3),
  '| viajes con >=3 pings exclusivos de OTRO ramal:', int((x.exc_other >= MINP).sum()))


def persist(d, key):
    d = d.sort_values(['day', 'veh', 't0']).copy(); g = d.groupby(['day', 'veh'])
    d['rp'] = g[key].shift(); d['cp'] = g.conf.shift(); d['sp'] = g.s.shift()
    return d


def rep(d, key, name, need_conf=False):
    d = persist(d, key); y = d.dropna(subset=['rp', key])
    if need_conf: y = y[y.conf & (y.cp == True)]  # noqa
    ok = y[key] == y.rp
    P(f'\n{name}: pares {len(y)} | P(igual previo) {ok.mean():.3f} | base mas frecuente {y[key].value_counts(normalize=True).iloc[0]:.3f} | '
      f'sentido opuesto {ok[y.s != y.sp].mean():.3f} (n {int((y.s != y.sp).sum())}) | mismo sentido {ok[y.s == y.sp].mean():.3f} (n {int((y.s == y.sp).sum())})')
    ct = pd.crosstab(y.rp, y[key]); P(ct.to_string()); P(ct.div(ct.sum(1), axis=0).round(3).to_string())


def cons(d, key, name):
    c = d.groupby(['day', 'veh'])[key].agg(['nunique', 'size']); c = c[c['size'] >= 2]
    P(f'{name}: coche-dias >=2 viajes {len(c)} | un solo ramal {(c["nunique"]==1).mean():.3f} | 3 ramales {(c["nunique"]==3).mean():.3f}')


rep(x, 'r', 'TODOS (pipeline, 3 dias)')
rep(x, 'r', 'PARES CONFIRMADOS (viaje y previo inmediato ambos confirmados)', need_conf=True)
cf = x[x.conf].copy()
cons(x, 'r', 'consistencia todos'); cons(cf, 'r', 'consistencia solo viajes confirmados')
P('\n### 2 Contraste CuandoSubo (route_id -> ramal)')
c = x[x.csr.notna()].copy()
P('viajes con ramal CS:', len(c), 'de', len(x), round(len(c) / len(x), 3), '| acuerdo pipeline-CS:', round((c.r == c.csr).mean(), 3),
  '| solo confirmados:', round((c[c.conf].r == c[c.conf].csr).mean(), 3), 'n', int(c.conf.sum()))
P('matriz pipeline (fila) vs CS (col):'); P(pd.crosstab(c.r, c.csr).to_string())
P('acuerdo por dia:', {k: round((z.r == z.csr).mean(), 3) for k, z in c.groupby('day')})
rep(c, 'csr', 'CUANDOSUBO como verdad (viajes con CS; previo = previo inmediato con CS)')
cons(c, 'csr', 'consistencia CS')
open(Path(__file__).parent / 'verif39_out.txt', 'w', encoding='utf8').write('\n'.join(out)); print('\n'.join(out))
