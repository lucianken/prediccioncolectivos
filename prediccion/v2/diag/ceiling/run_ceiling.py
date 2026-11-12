"""
Techo del tránsito (ARQUITECTURA.md §6.2.1): por fila de eval, A1 simulado, oráculo y realista con la tabla de tránsito.

  PYTHONPATH=. python -m prediccion.v2.diag.ceiling.run_ceiling [--workers 4] [--days 2026-09-16,...] [--outdir ...]

Por día: lee el NDJSON de toda la flota UNA vez (misma lógica que prediccion/v2/traffic/day.py, pero conservando el
coche) y arma la tabla (ventana, celda) con acumuladores por coche, de modo que se puede restar el coche propio
(exclusión exacta) y separar coches de la misma línea de coches de otras líneas. Las ventanas de días vecinos salen
de la tabla diaria ya construida (sin exclusión del propio coche; solo importa cerca de medianoche).
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from array import array
from datetime import date
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.eval import _hours
from prediccion.models.a1_baseline import A1Baseline, SEGMENT_SIZE_M
from prediccion.pipeline.reader import iter_frames
from prediccion.v2.diag.ceiling import common as C
from prediccion.v2.traffic import day as tday
from prediccion.v2.traffic.grid import cell_index, _M_PER_DEG
from prediccion.v2.traffic.mask import cell_lookup

NCLS = 6                       # histograma de n por paso: 1, 2, 3, 4-5, 6-10, 11+
N_EDGES = [1.5, 2.5, 3.5, 5.5, 10.5]
MAX_OWN = 4


def read_pings_ids(fp: Path):
    """Igual que traffic.day.read_pings pero devuelve también el mapa id string -> vid entero."""
    vid_ids: dict[str, int] = {}
    state: dict[str, dict] = {}
    last_ts: dict[str, int] = {}
    a_vid, a_ts, a_lat, a_lon = array("i"), array("q"), array("d"), array("d")

    def emit(vid):
        f = state[vid]
        t, lat, lon = f.get("ts"), f.get("lat"), f.get("lon")
        if t is None or lat is None or lon is None or t <= last_ts.get(vid, -1):
            return
        last_ts[vid] = t
        k = vid_ids.get(vid)
        if k is None:
            k = vid_ids[vid] = len(vid_ids)
        a_vid.append(k); a_ts.append(t); a_lat.append(lat); a_lon.append(lon)

    for frame in iter_frames(fp):
        if frame.get("gap"):
            continue
        if frame.get("keyframe", False):
            state = {}
            for v in frame.get("new", []):
                state[v["id"]] = dict(v); emit(v["id"])
        else:
            for v in frame.get("new", []):
                state[v["id"]] = dict(v); emit(v["id"])
            for vid in frame.get("del", []):
                state.pop(vid, None)
            for u in frame.get("upd", []):
                vid = u["id"]
                if vid in state:
                    state[vid].update(u); emit(vid)
    return (np.frombuffer(a_vid, dtype=np.int32), np.frombuffer(a_ts, dtype=np.int64),
            np.frombuffer(a_lat, dtype=np.float64), np.frombuffer(a_lon, dtype=np.float64), vid_ids)


def vehicle_records(vid, ts, lat, lon, *, grid, cell_ok, tree, cos_route, window_min=2):
    """(ventana, celda, coche) -> (S = suma de velocidades en mov., Cn = intervalos en mov.). Mismo filtro que traffic.day.aggregate."""
    order = np.lexsort((ts, vid))
    vid, ts, lat, lon = vid[order], ts[order], lat[order], lon[order]
    dt = np.diff(ts)
    same = (vid[1:] == vid[:-1]) & (dt >= tday.MIN_DT_S) & (dt <= tday.MAX_DT_S)
    cos = math.cos(math.radians(float(np.mean(lat))))
    v = np.hypot((lon[1:] - lon[:-1]) * _M_PER_DEG * cos, (lat[1:] - lat[:-1]) * _M_PER_DEG) / np.maximum(dt, 1)
    keep = same & (v <= tday.MAX_MPS)
    idx = np.flatnonzero(keep) + 1
    v, b_vid, b_ts, b_lat, b_lon = v[idx - 1], vid[idx], ts[idx], lat[idx], lon[idx]
    cell = cell_index(grid, b_lat, b_lon)
    ok = cell_ok[cell]
    moving = v >= tday.MOVING_MPS
    ci = np.flatnonzero(ok & ~moving)
    depot = np.zeros(len(ok), dtype=bool)
    if len(ci):
        q = np.column_stack([b_lat[ci] * _M_PER_DEG, b_lon[ci] * _M_PER_DEG * cos_route])
        d, _ = tree.query(q, k=1, workers=1)
        depot[ci] = d > tday.DEPOT_FIT_M
    ok &= ~depot
    sel = np.flatnonzero(ok)
    v, b_vid, b_ts, cell, moving = v[sel], b_vid[sel], b_ts[sel], cell[sel], moving[sel]
    win = tday.window_of(b_ts, window_min)
    nc, nv = grid.n_ids, int(b_vid.max()) + 1
    key2 = (win * nc + cell) * nv + b_vid
    u2, inv2 = np.unique(key2, return_inverse=True)
    S = np.bincount(inv2, weights=np.where(moving, v, 0.0), minlength=len(u2))
    Cn = np.bincount(inv2, weights=moving, minlength=len(u2))
    kk = u2 // nv
    return (kk // nc).astype(np.int64), (kk % nc).astype(np.int64), (u2 % nv).astype(np.int64), S, Cn


class DayTable:
    """Acumuladores globales por (ventana absoluta, celda) y por coche, con exclusión del coche propio."""

    def __init__(self, nc, nv, pv, neighbors=None):
        self.nc, self.nv = nc, nv
        win, cell, vid, S, Cn = pv
        keyv = (win + C.WIN_PER_DAY) * nc + cell
        comp = keyv * nv + vid
        o = np.argsort(comp)
        self.pk, self.pS, self.pC = comp[o], S[o], Cn[o]
        self.pm = (self.pC > 0).astype(np.float64)
        pm0 = (Cn > 0).astype(np.float64)
        ks, Ss, Cs, ns, ms = [keyv], [S], [Cn], [np.ones(len(S))], [pm0]
        for off, (w, c, sp, n, nst) in (neighbors or {}).items():
            kk = (w.astype(np.int64) + off * C.WIN_PER_DAY + C.WIN_PER_DAY) * nc + c.astype(np.int64)
            nm = n.astype(np.float64) - nst
            ks.append(kk); Ss.append(np.nan_to_num(sp.astype(np.float64)) * nm); Cs.append(nm)
            ns.append(n.astype(np.float64)); ms.append(nm)
        uk, inv = np.unique(np.concatenate(ks), return_inverse=True)
        self.gk = uk
        self.gS = np.bincount(inv, weights=np.concatenate(Ss), minlength=len(uk))
        self.gC = np.bincount(inv, weights=np.concatenate(Cs), minlength=len(uk))
        self.gn = np.bincount(inv, weights=np.concatenate(ns), minlength=len(uk))
        self.gm = np.bincount(inv, weights=np.concatenate(ms), minlength=len(uk))

    def stats(self, keys, own=None):
        """keys int64 (m,), own (m, MAX_OWN) vid enteros o -1. Devuelve S, C, n, m (sin el coche propio)."""
        if len(keys) == 0 or len(self.gk) == 0:
            z = np.zeros(len(keys))
            return z, z.copy(), z.copy(), z.copy()
        gi = np.minimum(np.searchsorted(self.gk, keys), len(self.gk) - 1)
        f = self.gk[gi] == keys
        S = np.where(f, self.gS[gi], 0.0); Cc = np.where(f, self.gC[gi], 0.0)
        n = np.where(f, self.gn[gi], 0.0); m = np.where(f, self.gm[gi], 0.0)
        if own is not None and len(self.pk):
            for j in range(own.shape[1]):
                ov = own[:, j]
                ck = keys * self.nv + np.maximum(ov, 0)
                pi = np.minimum(np.searchsorted(self.pk, ck), len(self.pk) - 1)
                f2 = (ov >= 0) & (self.pk[pi] == ck)
                S = S - np.where(f2, self.pS[pi], 0.0); Cc = Cc - np.where(f2, self.pC[pi], 0.0)
                n = n - f2; m = m - np.where(f2, self.pm[pi], 0.0)
        return S, np.maximum(Cc, 0.0), np.maximum(n, 0.0), np.maximum(m, 0.0)


def v_variant(variant, v_obs, m, n, v_a1, typ=None):
    """Velocidad usada por paso (v_obs NaN = sin dato -> A1)."""
    has = ~np.isnan(v_obs)
    if variant in ("rel", "relmix"):   # A1 x (observada / típica de la celda a esa hora): solo la desviación respecto de lo habitual
        has = has & ~np.isnan(typ)
        ratio = np.clip(np.where(has, v_obs, 1.0) / np.where(has, typ, 1.0), 0.25, 3.0)
        if variant == "relmix":
            ratio = (m * ratio + C.MIX_K) / (m + C.MIX_K)
        return np.maximum(np.where(has, v_a1 * ratio, v_a1), C.MIN_SPEED)
    if variant == "raw":
        v = np.where(has, v_obs, v_a1)
    elif variant == "mix":       # A1 pesa como MIX_K coches en movimiento
        vo = np.where(has, v_obs, 0.0)
        v = np.where(has, (m * vo + C.MIX_K * v_a1) / (m + C.MIX_K), v_a1)
    elif variant == "adj":       # velocidad en mov. x fracción de coches en mov. (los detenidos aportan 0), piso 1 m/s
        vo = np.where(has, v_obs * m / np.maximum(n, 1.0), 0.0)
        v = np.where(has, np.maximum(vo, 1.0), v_a1)
    else:
        raise ValueError(variant)
    return np.maximum(v, C.MIN_SPEED)


def pool_prev(tab, w0, rows, cells, own):
    """Acumula las REAL_WINDOWS ventanas completas previas a la de t (sin futuro)."""
    n = len(rows)
    Sx, Cx, nx, mx = (np.zeros(n) for _ in range(4))
    for j in range(1, C.REAL_WINDOWS + 1):
        a, b, c, d = tab.stats((w0[rows] - j + C.WIN_PER_DAY) * tab.nc + cells,
                               None if own is None else own[rows])
        Sx += a; Cx += b; nx += c; mx += d
    return Sx, Cx, nx, mx


def process_day(args):
    day, sub, outdir = args
    t_start = time.time()
    grid = C.grid_spec()
    z = np.load(C.TRAFFIC / "route_mask.npz")
    cell_ok = cell_lookup(grid, z["cells"])
    tree, cos_route = tday.build_route_tree(z["points"])
    n60, n129 = C.cell_line_counts(grid)
    typ_tab = np.load(C.DIAG / "ceiling_typical.npz")["typ"]
    a1 = A1Baseline.load(C.A1_PKL)
    shapes = C.shapes_for(sorted(sub.line.unique()))

    vid, ts, lat, lon, vid_ids = read_pings_ids(C.NDJSON_DIR / f"{day}.ndjson.gz")
    pv = vehicle_records(vid, ts, lat, lon, grid=grid, cell_ok=cell_ok, tree=tree, cos_route=cos_route)
    nv = len(vid_ids) + 1
    import pyarrow.parquet as pq
    d0 = date.fromisoformat(day)
    neigh = {}
    for off in (-1, 1):
        p = C.TRAFFIC / "daily" / f"{date.fromordinal(d0.toordinal() + off).isoformat()}.parquet"
        if p.exists():
            t = pq.read_table(p).to_pandas()
            neigh[off] = (t.window.to_numpy(), t.cell.to_numpy(), t.speed_mps.to_numpy(), t.n.to_numpy(),
                          t.n_stopped.to_numpy())
    tab = DayTable(grid.n_ids, nv, pv, neigh)
    NC = grid.n_ids

    # control: la tabla recomputada del día coincide con la diaria
    t = pq.read_table(C.TRAFFIC / "daily" / f"{day}.parquet").to_pandas()
    kd = (t.window.to_numpy().astype(np.int64) + C.WIN_PER_DAY) * NC + t.cell.to_numpy()
    gi = np.minimum(np.searchsorted(tab.gk, kd), len(tab.gk) - 1)
    chk_found = float(np.mean(tab.gk[gi] == kd))
    chk_n = float(np.mean(tab.gn[gi] == t.n.to_numpy()))

    sub = sub.reset_index(drop=True)
    R = len(sub)
    own_ids, own_dt = C.own_vehicles(day, sub)
    own = np.full((R, MAX_OWN), -1, dtype=np.int64)
    for i, lst in enumerate(own_ids):
        for j, vv in enumerate(lst[:MAX_OWN]):
            own[i, j] = vid_ids.get(vv, -1)

    # geometría + A1 por paso
    dist = sub.dist_remaining_m.to_numpy(np.float64)
    d_al = sub.dist_along_m.to_numpy(np.float64)
    nst = np.maximum(1, np.rint(dist / C.STEP_M).astype(int))
    S = int(nst.max())
    stepL = dist / nst
    cell_m = np.zeros((R, S), dtype=np.int64)
    v_a1 = np.full((R, S), 7.0)
    hours = _hours(sub)
    dows = sub.dow.to_numpy().astype(int)
    rids = sub.ramal_id.tolist(); sids = sub.shape_id.astype(str).tolist()
    for i in range(R):
        n = nst[i]
        mids = d_al[i] + (np.arange(n) + 0.5) * stepL[i]
        si = shapes[sids[i]]
        cd = si._cum_dist
        mm = np.clip(mids, 0, cd[-1])
        cell_m[i, :n] = cell_index(grid, np.interp(mm, cd, si._pts[:, 0]), np.interp(mm, cd, si._pts[:, 1]))
        cache = {}
        for k, sg in enumerate((mids // SEGMENT_SIZE_M).astype(int)):
            if sg not in cache:
                cache[sg] = max(a1._get_speed(rids[i], int(sg), int(hours[i]), int(dows[i]))[0], C.MIN_SPEED)
            v_a1[i, k] = cache[sg]
    valid = np.arange(S)[None, :] < nst[:, None]
    single = n60[cell_m] <= 1          # celda recorrida solo por la línea de la fila (entre las 60 de la máscara)
    single129 = n129[cell_m] <= 1
    all_ok = np.ones((R, S), dtype=bool)

    dtype_day = 0 if d0.weekday() < 5 else (1 if d0.weekday() == 5 else 2)
    t0u = sub.ts_p.to_numpy(np.int64)
    day0 = (d0.toordinal() - date(1970, 1, 1).toordinal()) * 86400 - C.TZ_OFFSET_S   # medianoche BA, epoch UTC
    res = {"row_id": sub.row_id.to_numpy(), "own_dt": own_dt, "own_n": (own >= 0).sum(1),
           "chk_found": np.full(R, chk_found), "chk_n": np.full(R, chk_n)}
    res["eta_a1sim"] = np.minimum(np.where(valid, stepL[:, None] / v_a1, 0).sum(1), C.MAX_ETA)

    def oracle(variant, exclude, minn, allowed):
        """Coche virtual: en cada celda, al tiempo simulado tau, velocidad de la ventana de tau (luego +1, luego -1)."""
        tau = t0u.astype(np.float64).copy()
        n_obs = np.zeros(R); t_obs = np.zeros(R); elapsed = np.zeros(R)
        n_sg = np.zeros(R); n_sh = np.zeros(R)
        hist = np.zeros((R, 2, NCLS), dtype=np.int64)
        for s in range(S):
            act = np.flatnonzero(s < nst)
            if len(act) == 0:
                break
            cells = cell_m[act, s]
            w = np.floor((tau[act] - day0) / C.WIN_S).astype(np.int64)
            vobs = np.full(len(act), np.nan); mm = np.zeros(len(act)); nn = np.zeros(len(act))
            for off in (0, 1, -1):
                pend = np.flatnonzero(np.isnan(vobs) & allowed[act, s])
                if len(pend) == 0:
                    break
                Sx, Cx, nx, mx = tab.stats((w[pend] + off + C.WIN_PER_DAY) * NC + cells[pend],
                                           own[act[pend]] if exclude else None)
                ok = (Cx > 0.5) & (nx >= minn)
                sel = pend[ok]
                vobs[sel] = Sx[ok] / Cx[ok]; mm[sel] = mx[ok]; nn[sel] = nx[ok]
            hr = (((tau[act] - day0) // 3600) % 24).astype(int)
            v = v_variant(variant, vobs, mm, nn, v_a1[act, s], typ_tab[cells, hr, dtype_day])
            dtm = stepL[act] / v
            tau[act] += dtm
            has = ~np.isnan(vobs)
            n_obs[act] += has; t_obs[act] += np.where(has, dtm, 0); elapsed[act] += dtm
            sg = single[act, s]
            n_sg[act] += has & sg; n_sh[act] += has & ~sg
            for c in range(2):
                m_ = has & (sg if c == 0 else ~sg)
                np.add.at(hist, (act[m_], c, np.digitize(nn[m_], N_EDGES)), 1)
        return np.minimum(elapsed, C.MAX_ETA), n_obs, t_obs, n_sg, n_sh, hist

    for variant in ("raw", "mix", "adj", "rel", "relmix"):
        eta, n_obs, t_obs, nsg, nsh, hist = oracle(variant, True, 1, all_ok)
        res[f"eta_or_{variant}"] = eta
        if variant == "raw":
            res["cov_or"] = n_obs / nst
            res["tfrac_or"] = t_obs / np.maximum(eta, 1e-9)
            res["obs_or_single"] = nsg; res["obs_or_shared"] = nsh
            for c, nm_ in enumerate(("single", "shared")):
                for b in range(NCLS):
                    res[f"hist_or_{nm_}_{b}"] = hist[:, c, b]
    eta, n_obs, *_ = oracle("raw", False, 2, all_ok)
    res["eta_or_approx"] = eta; res["cov_or_approx"] = n_obs / nst
    res["eta_or_only_single"] = oracle("rel", True, 1, single)[0]
    res["eta_or_only_shared"] = oracle("rel", True, 1, ~single)[0]

    # --- realista: ventanas completas previas a la de t (sin futuro)
    w0 = np.floor((t0u - day0) / C.WIN_S).astype(np.int64)
    ii, kk = np.nonzero(valid)
    cells_f = cell_m[ii, kk]
    sg_f = single[ii, kk]
    Sx, Cx, nx, mx = pool_prev(tab, w0, ii, cells_f, own)
    has = Cx > 0.5
    vo = np.where(has, Sx / np.maximum(Cx, 1e-9), np.nan)
    hr0 = (((t0u - day0) // 3600) % 24).astype(int)
    typ_f = typ_tab[cells_f, hr0[ii], dtype_day]
    for variant in ("raw", "mix", "adj", "rel", "relmix"):
        v = v_variant(variant, vo, mx, nx, v_a1[ii, kk], typ_f)
        res[f"eta_re_{variant}"] = np.minimum(np.bincount(ii, weights=stepL[ii] / v, minlength=R), C.MAX_ETA)
    for nm_, allow in (("only_single", sg_f), ("only_shared", ~sg_f)):
        v = v_variant("rel", np.where(allow, vo, np.nan), mx, nx, v_a1[ii, kk], typ_f)
        res[f"eta_re_{nm_}"] = np.minimum(np.bincount(ii, weights=stepL[ii] / v, minlength=R), C.MAX_ETA)
    res["cov_re"] = np.bincount(ii, weights=has, minlength=R) / nst
    res["obs_re_single"] = np.bincount(ii, weights=has & sg_f, minlength=R)
    res["obs_re_shared"] = np.bincount(ii, weights=has & ~sg_f, minlength=R)
    b = np.digitize(nx, N_EDGES)
    for c, nm_ in enumerate(("single", "shared")):
        m_ = has & (sg_f if c == 0 else ~sg_f)
        for bb in range(NCLS):
            res[f"hist_re_{nm_}_{bb}"] = np.bincount(ii[m_ & (b == bb)], minlength=R)
    res["nsteps"] = nst
    res["nsteps_single"] = (single & valid).sum(1)
    res["nsteps_single129"] = (single129 & valid).sum(1)

    # --- realista: misma línea (coche de adelante y de atrás) vs otras líneas
    vl = C.vehicle_lines(day)
    same_ids: dict[str, np.ndarray] = {}
    for ln in sub.line.unique():
        same_ids[ln] = np.array([k for vv, ls_ in vl.items() if ln in ls_ for k in [vid_ids.get(vv, -1)] if k >= 0],
                                dtype=np.int64)
    eta_same = np.zeros(R); eta_oth = np.zeros(R)
    cov_same = np.zeros(R); cov_oth = np.zeros(R)
    line_arr = sub.line.to_numpy()
    n_same_all = np.zeros(R); n_oth_all = np.zeros(R)
    for ln, ids in same_ids.items():
        rows_l = np.flatnonzero(line_arr == ln)
        keep_v = np.isin(pv[2], ids)
        pv_l = tuple(a[keep_v] for a in pv)
        tab_s = DayTable(NC, nv, pv_l, None)
        sel = np.isin(ii, rows_l)
        iis, cs = ii[sel], cells_f[sel]
        a_ns = pool_prev(tab, w0, iis, cs, None)         # todos, sin excluir al propio (sale al restar `same`)
        s_ns = pool_prev(tab_s, w0, iis, cs, None)       # misma línea, con el propio
        s_ex = pool_prev(tab_s, w0, iis, cs, own)        # misma línea, sin el propio
        o_S, o_C, o_n, o_m = (a - b_ for a, b_ in zip(a_ns, s_ns))   # otras líneas (el propio queda fuera)
        for nm_, (SS, CC, nn_, mm_) in (("same", s_ex), ("oth", (o_S, o_C, o_n, o_m))):
            h = CC > 0.5
            vv = np.where(h, SS / np.maximum(CC, 1e-9), np.nan)
            vq = v_variant("rel", vv, mm_, nn_, v_a1[iis, kk[sel]], typ_f[sel])
            tgt_eta, tgt_cov = (eta_same, cov_same) if nm_ == "same" else (eta_oth, cov_oth)
            tgt_eta += np.bincount(iis, weights=stepL[iis] / vq, minlength=R)
            tgt_cov += np.bincount(iis, weights=h, minlength=R)
    res["eta_re_same"] = np.minimum(eta_same, C.MAX_ETA); res["eta_re_other"] = np.minimum(eta_oth, C.MAX_ETA)
    res["cov_re_same"] = cov_same / nst; res["cov_re_other"] = cov_oth / nst

    df = pd.DataFrame(res)
    df.to_parquet(Path(outdir) / f"ceiling_{day}.parquet")
    return (day, R, round(time.time() - t_start, 1), chk_found, chk_n, float((own_dt <= 60).mean()),
            float((own >= 0).any(1).mean()))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--days", default=None)
    ap.add_argument("--outdir", type=Path, default=Path(C.DIAG) / "ceiling_days")
    a = ap.parse_args(argv)
    a.outdir.mkdir(parents=True, exist_ok=True)
    df = C.load_eval_subset()
    days = sorted(df.day.unique())
    if a.days:
        days = [d for d in days if d in a.days.split(",")]
    days = [d for d in days if not (a.outdir / f"ceiling_{d}.parquet").exists()]
    C.cell_line_counts(C.grid_spec())     # cachea antes de lanzar los workers
    jobs = [(d, df[df.day == d], a.outdir) for d in days]
    print(f"{len(df)} filas, {len(days)} días por procesar", flush=True)
    with Pool(a.workers) as p:
        for r in p.imap_unordered(process_day, jobs):
            print("día %s filas=%d %.0fs  tabla: celdas halladas=%.3f n igual=%.3f  coche propio: match=%.3f en NDJSON=%.3f" % r,
                  flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
