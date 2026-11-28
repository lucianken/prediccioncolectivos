"""Etapa 2 del prior causal: mismas tablas que prior.py (a hora x dia, b secuencia de 3 despachos, q cuotas de los ultimos 6, cq) pero
con contexto CAUSAL. Entrada: data/ml/replay/prior/eventos/*.eventos.parquet (eventos.py).

Modos, en el instante de consulta Tq = det_ts del despacho + D (D en DGRID), contexto = despachos previos de la cabecera (<= 90 min):
  techo    contexto = ramal ex post (etiqueta) de los previos: lo que midio el informe (con las salidas detectadas por eventos.py).
  token    contexto = ramal REVELADO por el previo con pings <= Tq (reveal_ts <= Tq); si no, token "desconocido". Tablas entrenadas con el
           mismo contexto causal (token) para cada D.
  cadena   tablas del techo; el previo no revelado entra con su propia P predicha (cadena) en vez de la etiqueta (marginaliza la
           secuencia con la P encadenada; el experto de cuotas usa conteos esperados).
  freq     ramal mas frecuente de la cabecera en train (base).
Train 2026-07-20 a 09-14, test 2026-09-15 a 10-14. Salidas en data/ml/replay/prior/: P_eventos.parquet (P por evento y D, modos token y
cadena), meta.json; y experiments/prior_ramal_cabecera/causal/modelo_out.txt.
Correr desde 'prediccion colectivos': python experiments/prior_ramal_cabecera/causal/modelo.py
"""
from __future__ import annotations
import glob, json, sys, time
from pathlib import Path
import numpy as np, pandas as pd
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import prior as PRI                                   # noqa: E402
from prior import sm, pred_a, pred_b, pred_q, ll, comb, GRID, TRAIN, TEST, FERIADOS, predict   # noqa: E402
import eventos as EV                                  # noqa: E402

DGRID = [0, 120, 300, 600, 1200, 2400]
GAP = PRI.GAP
OUT = ROOT / "data/ml/replay/prior"
MODES = ("techo", "token", "cadena")


class Tabs2:
    """Como prior.Tabs, con nt fichas de contexto (K ramales, K = sin dato, K+1 = desconocido)."""
    def __init__(s, K, nt, y, hour, tipo, prev, mask):
        s.K = K
        yy = y[mask]
        s.g = np.bincount(yy, minlength=K).astype(float)
        s.t = np.zeros((3, K)); np.add.at(s.t, (tipo[mask], yy), 1)
        s.h = np.zeros((3, 24, K)); np.add.at(s.h, (tipo[mask], hour[mask], yy), 1)
        s.c1 = np.zeros((nt, K)); np.add.at(s.c1, (prev[mask, 0], yy), 1)
        s.c2 = np.zeros((nt, nt, K)); np.add.at(s.c2, (prev[mask, 0], prev[mask, 1], yy), 1)
        s.c3 = np.zeros((nt, nt, nt, K)); np.add.at(s.c3, (prev[mask, 0], prev[mask, 1], prev[mask, 2], yy), 1)
        s.pg = (s.g + 1) / (s.g.sum() + K)


def load_events():
    fs = sorted(glob.glob(str(OUT / "eventos/*.eventos.parquet")))
    x = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    t = pd.to_datetime(x.det_ts, unit="s", utc=True).dt.tz_convert("America/Argentina/Buenos_Aires")
    x["hour"] = t.dt.hour
    wd = t.dt.weekday
    x["tipo"] = np.where(wd < 5, 0, np.where(wd == 5, 1, 2))
    x.loc[x.day.isin(FERIADOS), "tipo"] = 2
    x["gkey"] = x.line + "|" + x.cab
    return x.sort_values(["gkey", "det_ts"]).reset_index(drop=True)


def group_arrays(g, ram):
    ix = {r: i for i, r in enumerate(ram)}
    y = g.label.map(ix).fillna(-1).astype(int).values
    tgt = (y >= 0) & (~g.label_start_unknown.values)
    lab = np.where(tgt, y, -1)                                   # etiqueta usable como contexto del techo
    rv = g.reveal_ramal.map(ix).fillna(-1).astype(int).values
    rvts = np.where(rv >= 0, g.reveal_ts.fillna(np.inf).values, np.inf)
    return dict(ts=g.det_ts.values, y=np.where(tgt, y, 0), tgt=tgt, lab=lab, rv=rv, rvts=rvts, hour=g.hour.values, tipo=g.tipo.values,
                day=g.day.values)


def hard_ctx(A, K, mode, D):
    """prev (n,3) y rec (n,K) con contexto duro. Fichas: 0..K-1 ramal, K sin dato (hueco > 90 min o sin etiqueta), K+1 desconocido."""
    ts = A["ts"]; n = len(ts)
    prev = np.full((n, 3), K); rec = np.zeros((n, K))
    for j in range(1, 7):
        idx = np.arange(j, n); p = idx - j; ok = (ts[idx] - ts[p]) <= GAP
        if mode == "techo":
            known = A["lab"][p] >= 0; s = np.where(known, A["lab"][p], K); r = A["lab"][p]
        else:
            known = A["rvts"][p] <= ts[idx] + D; s = np.where(known, A["rv"][p], K + 1); r = A["rv"][p]
        if j <= 3:
            prev[idx[ok], j - 1] = s[ok]
        m = ok & known
        np.add.at(rec, (idx[m], r[m]), 1)
    return prev, rec


def fit(A, K, prev, rec, nt):
    y, hour, tipo, day, tgt = A["y"], A["hour"], A["tipo"], A["day"], A["tgt"]
    tr = (day >= TRAIN[0]) & (day <= TRAIN[1]) & tgt
    tr_days = sorted(set(day[tr])); fold = {d: i % 6 for i, d in enumerate(tr_days)}
    fo = np.array([fold.get(d, -1) for d in day])
    pairs = [((tr & (fo != f)), (tr & (fo == f))) for f in range(6)]
    pairs = [(a, b) for a, b in pairs if b.sum() > 0]
    Tf = [Tabs2(K, nt, y, hour, tipo, prev, a) for a, _ in pairs]
    best = {}; oof = {k: np.zeros((len(y), K)) for k in GRID}
    for name, grid in GRID.items():
        sc = []
        for hp in grid:
            tot = 0; n = 0
            for T, (_, va) in zip(Tf, pairs):
                P = predict(name, T, hp, hour[va], tipo[va], prev[va], rec[va])
                tot += -np.log(np.clip(P[np.arange(va.sum()), y[va]], PRI.EPS, 1)).sum(); n += va.sum()
            sc.append(tot / n)
        best[name] = grid[int(np.argmin(sc))]
        for T, (_, va) in zip(Tf, pairs):
            oof[name][va] = predict(name, T, best[name], hour[va], tipo[va], prev[va], rec[va])
    ws = {}
    for nm, ks in (("abq", ("a", "b", "q")),):
        f = lambda w: ll(comb(w, [oof[k][tr] for k in ks]), y[tr])
        ws[nm] = minimize(f, np.ones(len(ks)) * 0.5, method="Nelder-Mead").x
    T = Tabs2(K, nt, y, hour, tipo, prev, tr)
    return T, best, ws["abq"]


def predict_all(T, best, w, A, prev, rec):
    Ps = {k: predict(k, T, best[k], A["hour"], A["tipo"], prev, rec) for k in GRID}
    return comb(w, [Ps["a"], Ps["b"], Ps["q"]]), Ps


def chain(A, K, nt, T, best, w, D):
    """P encadenada: el previo revelado en Tq = det + D entra como ficha; el no revelado, con su propia P (ya calculada)."""
    ts = A["ts"]; n = len(ts)
    Pa = pred_a(T, A["hour"], A["tipo"], *best["a"])
    allp = np.array(np.meshgrid(*[np.arange(nt)] * 3, indexing="ij")).reshape(3, -1).T
    PB = pred_b(T, allp, *best["b"]).reshape(nt, nt, nt, K)
    aq = best["q"]
    P = np.zeros((n, K)); eye = np.eye(nt)
    for i in range(n):
        Qs = []
        for j in range(1, 7):
            p = i - j
            if p < 0 or ts[i] - ts[p] > GAP:
                Qs.append(eye[K])
            elif A["rvts"][p] <= ts[i] + D:
                Qs.append(eye[A["rv"][p]])
            else:
                q = np.zeros(nt); q[:K] = P[p]; Qs.append(q)
        pb = np.einsum("a,b,c,abcy->y", Qs[0], Qs[1], Qs[2], PB)
        r = sum(q[:K] for q in Qs)
        pq = (r + aq * T.pg) / (r.sum() + aq)
        P[i] = comb(w, [Pa[i:i + 1], pb[None], pq[None]])[0]
    return P


def reliability(P, y, nb=10):
    p = P.ravel(); o = (np.arange(P.shape[1])[None, :] == y[:, None]).ravel().astype(float)
    q = pd.qcut(p, nb, duplicates="drop")
    d = pd.DataFrame(dict(p=p, o=o, q=q)).groupby("q", observed=True).agg(p=("p", "mean"), o=("o", "mean"), n=("p", "size"))
    return d, float((abs(d.p - d.o) * d.n).sum() / d.n.sum())


def main():
    t0 = time.time()
    x = load_events()
    GEO = {L: EV.LineGeo(L) for L in EV.LINES}
    res = {}      # (gkey, modo, D) -> dict(P (n,K), idx)
    allP = []
    meta = {}
    for gk, g in x.groupby("gkey", sort=False):
        L, cab = gk.split("|", 1)
        ram = GEO[L].cab[cab]["ramales"]; K = len(ram); nt = K + 2
        g = g.reset_index(drop=True); A = group_arrays(g, ram)
        te = (A["day"] >= TEST[0]) & (A["day"] <= TEST[1]) & A["tgt"]
        tr = (A["day"] >= TRAIN[0]) & (A["day"] <= TRAIN[1]) & A["tgt"]
        if tr.sum() < 150 or te.sum() < 100:
            print("omitido", gk, int(tr.sum()), int(te.sum())); continue
        meta[gk] = dict(ramales=ram, ntr=int(tr.sum()), nte=int(te.sum()))
        pre, rec0 = hard_ctx(A, K, "techo", 0)
        Tt, bt, wt = fit(A, K, pre, rec0, nt)
        Ptecho, _ = predict_all(Tt, bt, wt, A, pre, rec0)
        res[(gk, "techo", 0)] = dict(P=Ptecho)
        for D in DGRID:
            pv, rc = hard_ctx(A, K, "token", D)
            Tk, bk, wk = fit(A, K, pv, rc, nt)
            Ptok, _ = predict_all(Tk, bk, wk, A, pv, rc)
            res[(gk, "token", D)] = dict(P=Ptok)
            res[(gk, "cadena", D)] = dict(P=chain(A, K, nt, Tt, bt, wt, D))
        res[(gk, "freq", 0)] = dict(P=np.tile(Tt.pg, (len(g), 1)))
        meta[gk]["A"] = A
        # tabla de P por evento (token y cadena) para el replay
        row = g[["day", "line", "cab", "vid", "det_ts", "reveal_ts", "reveal_ramal", "label", "label_start_unknown"]].copy()
        for D in DGRID:
            row[f"P_token_{D}"] = list(res[(gk, "token", D)]["P"].round(5)); row[f"P_cadena_{D}"] = list(res[(gk, "cadena", D)]["P"].round(5))
        row["P_techo"] = list(Ptecho.round(5)); row["gkey"] = gk
        allP.append(row)
        print(gk, "K", K, "ntr", int(tr.sum()), "nte", int(te.sum()), f"{time.time() - t0:.0f}s", flush=True)
    pd.concat(allP, ignore_index=True).to_parquet(OUT / "P_eventos.parquet")
    json.dump({k: dict(ramales=v["ramales"], ntr=v["ntr"], nte=v["nte"]) for k, v in meta.items()}, open(OUT / "meta.json", "w"), indent=1)
    import pickle
    pickle.dump({k: v["P"] for k, v in res.items()}, open(OUT / "res_P.pkl", "wb"))
    pickle.dump({k: v["A"] for k, v in meta.items()}, open(OUT / "res_A.pkl", "wb"))
    print("listo", f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
