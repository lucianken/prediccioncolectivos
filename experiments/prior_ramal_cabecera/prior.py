"""Prior de ramal por cabecera: (a) hora x tipo de dia, (b) secuencia de despachos, (c) combinacion.
Medicion; no entrena modelos del pipeline.
Correr desde 'prediccion colectivos': python experiments/prior_ramal_cabecera/prior.py  (requiere trips8.parquet de load.py)"""
import pickle
from pathlib import Path
import numpy as np, pandas as pd
from scipy.optimize import minimize
HERE = Path(__file__).parent
TRAIN = ('2026-07-20', '2026-09-14'); TEST = ('2026-09-15', '2026-10-14')
FERIADOS = {'2026-08-17', '2026-10-12'}
EPS = 1e-9
GAP = 90 * 60


def load():
    x = pd.read_parquet(HERE / 'trips8.parquet')
    x = x[~x.start_unknown].copy()
    t = pd.to_datetime(x.start_ts, unit='s', utc=True).dt.tz_convert('America/Argentina/Buenos_Aires')
    x['hour'] = t.dt.hour; wd = t.dt.weekday
    x['tipo'] = np.where(wd < 5, 0, np.where(wd == 5, 1, 2)); x.loc[x.day.isin(FERIADOS), 'tipo'] = 2
    x['gkey'] = x.line + '|' + x.origin
    k = x.groupby('gkey').ramal.nunique(); x = x[x.gkey.isin(k[k >= 2].index)].copy()
    return x.sort_values(['gkey', 'start_ts']).reset_index(drop=True)


def encode(g, ram):
    """g: viajes de un grupo (cabecera) ordenados por salida. y, ramales previos 1..3 (K = sin dato), conteo de los ultimos 6."""
    K = len(ram); y = g.ramal.map({r: i for i, r in enumerate(ram)}).values
    ts = g.start_ts.values; n = len(g)
    prev = np.full((n, 3), K)
    for j in range(1, 4):
        pj = np.full(n, K); pj[j:] = y[:-j]
        gap = np.full(n, 1e12); gap[j:] = ts[j:] - ts[:-j]
        pj[gap > GAP] = K; prev[:, j - 1] = pj
    rec = np.zeros((n, K))
    for j in range(1, 7):
        idx = np.arange(j, n); ok = (ts[idx] - ts[idx - j]) <= GAP
        rec[idx[ok], y[idx[ok] - j]] += 1
    return y, prev, rec


class Tabs:
    def __init__(s, K, y, hour, tipo, prev, mask):
        s.K = K; yy = y[mask]
        s.g = np.bincount(yy, minlength=K).astype(float)
        s.t = np.zeros((3, K)); np.add.at(s.t, (tipo[mask], yy), 1)
        s.h = np.zeros((3, 24, K)); np.add.at(s.h, (tipo[mask], hour[mask], yy), 1)
        s.c1 = np.zeros((K + 1, K)); np.add.at(s.c1, (prev[mask, 0], yy), 1)
        s.c2 = np.zeros((K + 1, K + 1, K)); np.add.at(s.c2, (prev[mask, 0], prev[mask, 1], yy), 1)
        s.c3 = np.zeros((K + 1, K + 1, K + 1, K)); np.add.at(s.c3, (prev[mask, 0], prev[mask, 1], prev[mask, 2], yy), 1)
        s.pg = (s.g + 1) / (s.g.sum() + K)


def sm(counts, back, a):
    return (counts + a * back) / (counts.sum(-1, keepdims=True) + a)


def pred_a(T, hour, tipo, a, b):
    pt = sm(T.t[tipo], T.pg, b); return sm(T.h[tipo, hour], pt, a)


def pred_b(T, prev, k, c):
    p = sm(T.c1[prev[:, 0]], T.pg, c)
    if k >= 2: p = sm(T.c2[prev[:, 0], prev[:, 1]], p, c)
    if k >= 3: p = sm(T.c3[prev[:, 0], prev[:, 1], prev[:, 2]], p, c)
    return p


def pred_q(rec, T, a):
    return (rec + a * T.pg) / (rec.sum(1, keepdims=True) + a)


def ll(P, y): return -np.mean(np.log(np.clip(P[np.arange(len(y)), y], EPS, 1)))


def comb(w, Ps):
    z = sum(wi * np.log(np.clip(p, EPS, 1)) for wi, p in zip(w, Ps)); z = z - z.max(1, keepdims=True)
    e = np.exp(z); return e / e.sum(1, keepdims=True)


GRID = {'a': [(a, b) for a in (2, 5, 10, 25, 60) for b in (5, 20, 80)],
        'b': [(k, c) for k in (1, 2, 3) for c in (2, 5, 15, 40)],
        'q': [1, 3, 8, 20]}


def predict(name, T, hp, hour, tipo, prev, rec):
    if name == 'a': return pred_a(T, hour, tipo, *hp)
    if name == 'b': return pred_b(T, prev, *hp)
    return pred_q(rec, T, hp)


def run_group(g, ram):
    K = len(ram); y, prev, rec = encode(g, ram); hour = g.hour.values; tipo = g.tipo.values; day = g.day.values
    tr = (day >= TRAIN[0]) & (day <= TRAIN[1]); te = (day >= TEST[0]) & (day <= TEST[1])
    tr_days = sorted(set(day[tr])); fold = {d: i % 6 for i, d in enumerate(tr_days)}
    fo = np.array([fold.get(d, -1) for d in day])
    pairs = [((tr & (fo != f)), (tr & (fo == f))) for f in range(6)]
    pairs = [(a, b) for a, b in pairs if b.sum() > 0]
    Tf = [Tabs(K, y, hour, tipo, prev, a) for a, _ in pairs]
    best = {}; oof = {k: np.zeros((len(y), K)) for k in GRID}
    for name, grid in GRID.items():
        sc = []
        for hp in grid:
            tot = 0; n = 0
            for T, (_, va) in zip(Tf, pairs):
                P = predict(name, T, hp, hour[va], tipo[va], prev[va], rec[va])
                tot += -np.log(np.clip(P[np.arange(va.sum()), y[va]], EPS, 1)).sum(); n += va.sum()
            sc.append(tot / n)
        best[name] = grid[int(np.argmin(sc))]
        for T, (_, va) in zip(Tf, pairs):
            oof[name][va] = predict(name, T, best[name], hour[va], tipo[va], prev[va], rec[va])
    ws = {}
    for nm, ks in (('ab', ('a', 'b')), ('abq', ('a', 'b', 'q'))):
        f = lambda w: ll(comb(w, [oof[k][tr] for k in ks]), y[tr])
        ws[nm] = minimize(f, np.ones(len(ks)) * 0.5, method='Nelder-Mead').x
    T = Tabs(K, y, hour, tipo, prev, tr); nte = int(te.sum())
    P = {'unif': np.full((nte, K), 1 / K), 'freq': np.tile(T.pg, (nte, 1))}
    for k in GRID: P[k] = predict(k, T, best[k], hour[te], tipo[te], prev[te], rec[te])
    P['c'] = comb(ws['ab'], [P['a'], P['b']]); P['cq'] = comb(ws['abq'], [P['a'], P['b'], P['q']])
    return dict(K=K, ram=ram, y=y[te], P=P, best=best, ws=ws, idx=np.where(te)[0], ntr=int(tr.sum()), gfreq=int(np.argmax(T.g)))


def main():
    x = load(); out = {}
    for gk, g in x.groupby('gkey', sort=False):
        g = g.reset_index(drop=True); ram = sorted(g.ramal.unique()); r = run_group(g, ram)
        r['g'] = g.iloc[r['idx']][['line', 'origin', 'day', 'hour', 'tipo', 'start_ts', 'vehicle_id', 'ramal', 'route_id_diag']].reset_index(drop=True)
        out[gk] = r
    pickle.dump(out, open(HERE / 'result.pkl', 'wb'))
    rows = []
    for gk, r in out.items():
        for m, P in r['P'].items():
            rows.append(dict(gkey=gk, line=gk.split('|')[0], model=m, n=len(r['y']), logloss=ll(P, r['y']), correct=int((P.argmax(1) == r['y']).sum())))
    d = pd.DataFrame(rows); d.to_csv(HERE / 'por_grupo.csv', index=False)
    for gk, r in out.items():
        print(gk, r['ram'], 'ntr', r['ntr'], 'best', r['best'], 'w', {k: np.round(v, 2).tolist() for k, v in r['ws'].items()})
    t = d.assign(ll_sum=d.logloss * d.n).groupby(['line', 'model']).agg(n=('n', 'sum'), ll=('ll_sum', 'sum'), c=('correct', 'sum'))
    t['logloss'] = t.ll / t.n; t['acc'] = t.c / t.n
    print(t[['acc']].round(3).unstack('model').to_string()); print(t[['logloss']].round(3).unstack('model').to_string())


if __name__ == '__main__':
    main()
