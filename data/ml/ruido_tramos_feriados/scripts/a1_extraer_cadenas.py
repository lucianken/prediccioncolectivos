"""A (paso 1): cadenas de pings consecutivos validos (traj_flat de las filas de v4) -> errores de interpolacion.
Para cada cadena terminada en P y cada salto k (intervalos entre p0 y p2 = P): interpola con p0-p2 (lineal en la distancia, igual que
stop_targets.stop_crossings / replay.core.crossings_v2) y compara con la referencia por tramos usando los pings intermedios.
modo 'obj': objetivos uniformes f in (.2,.4,.6,.8) entre d0 y d2.  modo 'ping': objetivo = distancia de cada ping intermedio (verdad observada)."""
import sys, json, time
from pathlib import Path
import numpy as np, pyarrow.parquet as pq, pandas as pd
import psutil
p = psutil.Process(); p.nice(psutil.IDLE_PRIORITY_CLASS); p.cpu_affinity(list(range(8)))
sys.path.insert(0, ".")
from prediccion.models.stops import load_shape_stops
V4 = Path("data/ml/v4/daily"); OUT = Path("data/ml/ruido_tramos_feriados")
DAYS = ["2026-08-04", "2026-08-05", "2026-08-12", "2026-08-19", "2026-09-02", "2026-09-16", "2026-09-23", "2026-10-06", "2026-10-13",
        "2026-08-08", "2026-09-12", "2026-09-26", "2026-10-03", "2026-08-09", "2026-09-20", "2026-10-11"]
NCH = int(sys.argv[1]) if len(sys.argv) > 1 else 40_000
KS = (2, 3, 4, 6, 8); FS = (0.2, 0.4, 0.6, 0.8)
DT_MAX = 300.0; VMAX = 25.0; SLACK = 50.0
lengths = json.load(open("data/ml/v4_sub/shape_lengths.json", encoding="utf-8"))
t0 = time.time(); recs = []; consec = []
stops_cache = {}
for day in DAYS:
    t = pq.read_table(V4 / f"{day}.parquet", columns=["line", "shape_id", "traj_flat", "traj_len", "ts_p", "dist_along_m"])
    n = len(t)
    traj = t["traj_flat"].combine_chunks().values.to_numpy(zero_copy_only=False).reshape(n, 30).astype(np.float64)
    hl = t["traj_len"].to_numpy().astype(np.int64)
    ts_p = t["ts_p"].to_numpy(); da = t["dist_along_m"].to_numpy().astype(np.float64)
    line = t["line"].to_numpy(zero_copy_only=False); sid = t["shape_id"].to_numpy(zero_copy_only=False)
    # una cadena por ping P: dedup por (line, shape, ts_p, dist)
    key = pd.DataFrame({"l": line, "s": sid, "t": ts_p, "d": np.round(da, 1)})
    first = ~key.duplicated().to_numpy()
    idx = np.flatnonzero(first & (hl >= 3))
    rng = np.random.default_rng(int(day.replace("-", ""))); 
    if len(idx) > NCH: idx = np.sort(rng.choice(idx, NCH, replace=False))
    tr = traj[idx]; h = hl[idx]; L = np.array([lengths.get(str(s), np.nan) for s in sid[idx]])
    ok = np.isfinite(L); idx, tr, h, L = idx[ok], tr[ok], h[ok], L[ok]
    m = len(idx)
    slot = h[:, None] - 10 + np.arange(10)[None, :]            # alineado a la derecha: col 9 = P
    vs = slot >= 0; sc = np.clip(slot, 0, 9)
    Dn = np.take_along_axis(tr[:, 0::3], sc, 1) * L[:, None]
    DT = np.take_along_axis(tr[:, 2::3], sc, 1)
    T = np.zeros((m, 10)); T[:, 9] = ts_p[idx]
    for c in range(8, -1, -1): T[:, c] = T[:, c + 1] - DT[:, c + 1]
    # intervalos consecutivos (col c -> c+1)
    dd = np.diff(Dn, axis=1); dtt = np.diff(T, axis=1); vint = vs[:, :-1] & vs[:, 1:]
    okint = vint & (dtt > 0) & (dtt <= DT_MAX) & (dd >= 0) & (dd <= VMAX * dtt + SLACK)
    # estadistica de intervalos reales (k=1) con avance
    mm = vint & (dtt > 0) & (dtt <= 600)
    consec.append(pd.DataFrame({"dt": dtt[mm], "dd": dd[mm]}).sample(min(200000, int(mm.sum())), random_state=1))
    hour = ((ts_p[idx] - 3 * 3600) % 86400) / 3600.0
    dow = (((ts_p[idx] - 3 * 3600) // 86400) + 3) % 7
    for k in KS:
        c0 = 9 - k
        good = (vs[:, c0]) & okint[:, c0:9].all(1)
        d0, d2 = Dn[:, c0], Dn[:, 9]; t0_, t2_ = T[:, c0], T[:, 9]
        good &= (d2 - d0) >= 30.0
        gi = np.flatnonzero(good)
        if len(gi) == 0: continue
        base = dict(day=day, k=k, S=(t2_ - t0_)[gi], D=(d2 - d0)[gi], d0=d0[gi], d2=d2[gi], hour=hour[gi], dow=dow[gi], line=line[idx][gi], shape=sid[idx][gi])
        # modo obj
        for f in FS:
            ds = d0[gi] + f * (d2 - d0)[gi]
            that = t0_[gi] + f * (t2_ - t0_)[gi]
            ref = np.full(len(gi), np.nan)
            for c in range(c0, 9):
                a, b = Dn[gi, c], Dn[gi, c + 1]
                sel = (a <= ds) & (ds < b) & np.isnan(ref)
                ref[sel] = T[gi, c][sel] + (ds[sel] - a[sel]) / (b[sel] - a[sel]) * (T[gi, c + 1][sel] - T[gi, c][sel])
            e = that - ref
            r = pd.DataFrame(base); r["mode"] = "obj"; r["f"] = f; r["dstar"] = ds; r["e"] = e; r["dn"] = np.minimum(ds - d0[gi], d2[gi] - ds); recs.append(r)
        # modo ping (cada ping intermedio, solo si estrictamente entre d0 y d2)
        for c in range(c0 + 1, 9):
            ds = Dn[gi, c]; sel = (ds > d0[gi]) & (ds < d2[gi])
            if not sel.any(): continue
            f_ = (ds - d0[gi]) / (d2[gi] - d0[gi])
            that = t0_[gi] + f_ * (t2_ - t0_)[gi]
            r = pd.DataFrame(base)[sel.tolist()] if False else pd.DataFrame({kk: (v[sel] if isinstance(v, np.ndarray) else v) for kk, v in base.items()})
            r["mode"] = "ping"; r["f"] = f_[sel]; r["dstar"] = ds[sel]; r["e"] = (that - T[gi, c])[sel]; r["dn"] = np.minimum(ds - d0[gi], d2[gi] - ds)[sel]; recs.append(r)
    print(day, n, m, f"{time.time()-t0:.0f}s", flush=True)
R = pd.concat(recs, ignore_index=True)
for c in ("e", "S", "D", "d0", "d2", "dstar", "dn", "f", "hour"): R[c] = R[c].astype(np.float32)
R = R[np.isfinite(R.e)]
# paradas
sh = R["shape"].astype(str).unique()
lines_u = R["line"].astype(str).unique()
st = load_shape_stops(lines_u)
gap = np.full(len(R), np.nan, np.float32); nsp = np.full(len(R), np.nan, np.float32); nxt = np.full(len(R), np.nan, np.float32)
Rs = R["shape"].astype(str).to_numpy(); ds = R["dstar"].to_numpy(); d0 = R["d0"].to_numpy(); d2 = R["d2"].to_numpy()
order = np.argsort(Rs, kind="stable"); Rs_sorted = Rs[order]
bounds = np.flatnonzero(np.r_[True, Rs_sorted[1:] != Rs_sorted[:-1], True])
for a, b in zip(bounds[:-1], bounds[1:]):
    s = Rs_sorted[a]; arr = np.asarray(st.get(s, []), float); ii = order[a:b]
    if len(arr) < 2: continue
    j = np.searchsorted(arr, ds[ii]); lo = np.clip(j - 1, 0, len(arr) - 1); hi = np.clip(j, 0, len(arr) - 1)
    inside = (j > 0) & (j < len(arr))
    g = np.where(inside, arr[hi] - arr[lo], np.nan); gap[ii] = g; nxt[ii] = np.where(j < len(arr), arr[hi] - ds[ii], np.nan)
    nsp[ii] = np.searchsorted(arr, d2[ii], side="right") - np.searchsorted(arr, d0[ii], side="left")
R["gap_paradas"] = gap; R["n_paradas_tramo"] = nsp; R["a_prox_parada"] = nxt
R.to_parquet(OUT / "_errores_interp.parquet")
pd.concat(consec).to_parquet(OUT / "_intervalos.parquet")
print("filas", len(R), f"{time.time()-t0:.0f}s", flush=True)
