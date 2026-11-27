"""Piso del error de ETA por coche con gemelos (A, B) sobre el mismo tramo. Un día -> raw/cases_{day}.parquet (casos de B).

python experiments/piso_gemelos/gemelos.py --day 2026-09-16 [--lines 39] [--model-n 600] [--workers ...]
Ver INFORME.md para el método.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import equiv as EQ  # noqa: E402
from prediccion.v2 import geo_assign as G  # noqa: E402

SHAPES_DIR = ROOT.parent / "proyectoconsola" / "data" / "backup_line_shapes_2026-11-26"   # los shapes del export path_v4_l1_s1 (los actuales de line_shapes cambiaron el 2026-11-26)
LABEL_MAP = ROOT / "LABEL_LINE_MAP.json"
RAW = HERE / "raw"
DELTAS = (60, 120, 300)
TYPES = ("any", "same", "ramal", "line")        # any = cualquier gemelo; same = misma línea y recorrido; ramal = misma línea otro ramal; line = otra línea
PASS_MAX_DT_S, V_MAX, SLACK = 600.0, 25.0, 50.0
MODEL_DIR = ROOT / "data" / "ml" / "export" / "path_v4_l1_s1"


def cross_nodes(ts, d, ok, Dn_sorted, node_idx):
    """Cruces firmes (misma regla que replay.core.crossings_v2) de varios nodos a la vez. Devuelve (node, tc, t0, t1)."""
    idx = np.flatnonzero(ok)
    e = np.empty(0)
    if len(idx) < 2:
        return e.astype(int), e, e, e
    t, dd = ts[idx], d[idx]
    t0, t1, d0, d1 = t[:-1], t[1:], dd[:-1], dd[1:]
    dt = t1 - t0
    m = (dt > 0) & (dt <= PASS_MAX_DT_S) & (d1 > d0) & ((d1 - d0) <= V_MAX * dt + SLACK)
    if not m.any():
        return e.astype(int), e, e, e
    t0, t1, d0, d1, dt = t0[m], t1[m], d0[m], d1[m], dt[m]
    lo = np.searchsorted(Dn_sorted, d0, "left")
    hi = np.searchsorted(Dn_sorted, d1, "left")
    cnt = np.maximum(hi - lo, 0)
    if cnt.sum() == 0:
        return e.astype(int), e, e, e
    rep = np.repeat(np.arange(len(lo)), cnt)
    off = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    k = lo[rep] + off
    ds = Dn_sorted[k]
    tc = t0[rep] + (ds - d0[rep]) / (d1[rep] - d0[rep]) * dt[rep]
    return node_idx[k], tc, t0[rep], t1[rep]


def load_vehicles(day, lines):
    from prediccion.replay.run import load_day
    return load_day(day, set(lines), "Z:/grabaciones", str(LABEL_MAP), str(SHAPES_DIR))


def crossings_for_day(per_line, eq_all, ls, targets):
    """Para cada shape objetivo: DataFrame de cruces de nodos (via, vid, node, tc, t0, t1)."""
    shape_ix = {s.shape_id: s for ln in per_line for s in ls.get(ln)}
    # shapes objetivo por shape via s'
    by_via: dict[str, list[str]] = {}
    for s in targets:
        for sp in eq_all[s]:
            by_via.setdefault(sp, []).append(s)
    # preparar nodos por (s, s')
    prep = {}
    for s in targets:
        for sp, (Dp, node_ok, _) in eq_all[s].items():
            if sp not in shape_ix:
                continue
            L = shape_ix[sp].length_m
            nidx = np.flatnonzero(node_ok)
            Dn = np.minimum(Dp[nidx], max(L - EQ.END_TOL_M, 0.0))
            o = np.argsort(Dn, kind="stable")
            prep[(s, sp)] = (Dn[o], nidx[o])
    rows = {s: [] for s in targets}
    vid_codes: dict[str, int] = {}
    via_codes: dict[str, int] = {}
    for ln, vs in per_line.items():
        shs = ls.get(ln)
        if not shs or not any(x.shape_id in by_via for x in shs):
            continue
        ixs = {x.shape_id: x.index for x in shs}
        for vid, v in vs.items():
            if len(v.ts) < 3:
                continue
            proj = {sid: ix.project_many(v.lat, v.lon) for sid, ix in ixs.items()}
            masks = G.compat_masks({sid: p for sid, (_, p) in proj.items()})
            vc = vid_codes.setdefault(vid, len(vid_codes))
            for sp in ixs:
                if sp not in by_via:
                    continue
                d, _ = proj[sp]
                ok = masks[sp]
                if ok.sum() < 2:
                    continue
                for s in by_via[sp]:
                    pr = prep.get((s, sp))
                    if pr is None or len(pr[0]) == 0:
                        continue
                    node, tc, t0, t1 = cross_nodes(v.ts, d, ok, *pr)
                    if len(tc):
                        rows[s].append((np.full(len(tc), via_codes.setdefault(sp, len(via_codes))), np.full(len(tc), vc), node, tc, t0, t1))
    out = {}
    for s, lst in rows.items():
        if not lst:
            continue
        cols = [np.concatenate([r[i] for r in lst]) for i in range(6)]
        out[s] = pd.DataFrame(dict(via=cols[0].astype(np.int32), vid=cols[1].astype(np.int32), node=cols[2].astype(np.int32),
                                   tc=cols[3], t0=cols[4], t1=cols[5]))
    return out, vid_codes, via_codes


def passes_from_crossings(df, segok_by_via, ms=EQ.SEG_NODES):
    """Entrada en nodo k y salida en nodo k+m del mismo coche y recorrido-vía: una fila por pasada. segok_by_via {via: {m: bool[n]}}."""
    res = []
    df = df.sort_values(["via", "vid", "node", "tc"]).reset_index(drop=True)
    nxt = df.groupby(["via", "vid", "node"])["tc"].shift(-1)
    df["next_entry"] = nxt.fillna(np.inf)
    ex_all = df[["via", "vid", "node", "tc"]]
    for m in ms:
        ent = df
        ok = np.zeros(len(ent), bool)
        for via, sm in segok_by_via.items():
            sel = (ent["via"].to_numpy() == via)
            if not sel.any() or m not in sm:
                continue
            nd = ent["node"].to_numpy()[sel]
            arr = sm[m]
            good = np.zeros(sel.sum(), bool)
            inr = nd < len(arr)
            good[inr] = arr[nd[inr]]
            ok[np.flatnonzero(sel)] = good
        ent = ent[ok].copy()
        if ent.empty:
            continue
        ex = ex_all.rename(columns={"tc": "t_out"}).copy()
        ex["node"] = ex["node"] - m
        ent = ent.sort_values("tc")
        ex = ex.sort_values("t_out")
        mg = pd.merge_asof(ent, ex, left_on="tc", right_on="t_out", by=["via", "vid", "node"], direction="forward",
                           tolerance=2400, allow_exact_matches=False)
        mg = mg[mg["t_out"].notna() & (mg["next_entry"] > mg["t_out"])].copy()
        dur = mg["t_out"] - mg["tc"]
        mg = mg[(dur >= 30) & (m * EQ.NODE_M / dur <= V_MAX)]
        mg["m"] = m
        res.append(mg.rename(columns={"tc": "t_in"})[["via", "vid", "node", "m", "t_in", "t_out", "t0", "t1"]])
    return pd.concat(res, ignore_index=True) if res else pd.DataFrame()


def trip_shape_at(passes, per_line_flat):
    """Recorrido ex post del viaje que contiene [t_in, t_out] ('' si ninguno)."""
    sid = np.array([""] * len(passes), dtype=object)
    vids = passes["vid"].to_numpy()
    tin = passes["t_in"].to_numpy()
    tout = passes["t_out"].to_numpy()
    order = np.argsort(vids, kind="stable")
    bounds = np.flatnonzero(np.r_[True, vids[order][1:] != vids[order][:-1], True])
    for a, b in zip(bounds[:-1], bounds[1:]):
        ii = order[a:b]
        tr = per_line_flat.get(int(vids[ii[0]]))
        if not tr:
            continue
        A = np.array([x[0] for x in tr]); B = np.array([x[1] for x in tr]); S = np.array([x[2] for x in tr], dtype=object)
        j = np.searchsorted(A, tin[ii], "right") - 1
        jj = np.clip(j, 0, len(A) - 1)
        okk = (j >= 0) & (tin[ii] <= B[jj]) & (tout[ii] <= B[jj])
        sid[ii[okk]] = S[jj[okk]]
    return sid


def match_twins(P, line_of_target, s, day0):
    """P: pasadas con cls. Devuelve DataFrame de casos de B con las columnas de gemelos."""
    B = P[(P["cls"] == 0) & P["isvia_s"]].copy()
    hr = ((B["t_in"] - 3 * 3600) % 86400) / 3600.0
    B = B[(hr >= 6) & (hr < 23)]
    A = P.copy()
    # dedup de A: mismo coche, nodo y m con entradas a < 30 s
    A = A.sort_values(["vid", "m", "node", "t_in"])
    same = (A["vid"].shift() == A["vid"]) & (A["m"].shift() == A["m"]) & (A["node"].shift() == A["node"]) & ((A["t_in"] - A["t_in"].shift()) < 30)
    A = A[~same]
    keyA = (A["m"].to_numpy() * 1000 + A["node"].to_numpy()).astype(np.float64) * 200000.0 + (A["t_in"].to_numpy() - day0)
    oA = np.argsort(keyA)
    keyA = keyA[oA]
    tinA = A["t_in"].to_numpy()[oA]; vidA = A["vid"].to_numpy()[oA]; durA = (A["t_out"] - A["t_in"]).to_numpy()[oA]; clsA = A["cls"].to_numpy()[oA]
    keyB = (B["m"].to_numpy() * 1000 + B["node"].to_numpy()).astype(np.float64) * 200000.0 + (B["t_in"].to_numpy() - day0)
    lo = np.searchsorted(keyA, keyB - 300, "left")
    hi = np.searchsorted(keyA, keyB + 300, "right")
    has = np.flatnonzero(hi > lo)
    Bv = B.iloc[has]
    n = len(has)
    cols = {f"{k}_{t}_{D}": np.full(n, np.nan if k != "n" else 0.0) for k in ("n", "dur", "dt", "med", "vid") for t in TYPES for D in DELTAS}
    tinB = Bv["t_in"].to_numpy(); vidB = Bv["vid"].to_numpy()
    for r, i in enumerate(has):
        sl = slice(lo[i], hi[i])
        ok = vidA[sl] != vidB[r]
        if not ok.any():
            continue
        dt = tinA[sl][ok] - tinB[r]
        ad = np.abs(dt)
        du = durA[sl][ok]; cl = clsA[sl][ok]; vv = vidA[sl][ok]
        for t, cv in (("any", None), ("same", 0), ("ramal", 1), ("line", 2)):
            mt = np.ones(len(cl), bool) if cv is None else (cl == cv)
            for D in DELTAS:
                mm = mt & (ad <= D)
                if not mm.any():
                    continue
                j = np.argmin(np.where(mm, ad, np.inf))
                cols[f"n_{t}_{D}"][r] = mm.sum()
                cols[f"dur_{t}_{D}"][r] = du[j]
                cols[f"dt_{t}_{D}"][r] = dt[j]
                cols[f"med_{t}_{D}"][r] = np.median(du[mm])
                cols[f"vid_{t}_{D}"][r] = vv[j]
    out = Bv[["vid", "node", "m", "t_in", "t_out", "t0", "t1"]].reset_index(drop=True)
    out["dur"] = out["t_out"] - out["t_in"]
    out = pd.concat([out, pd.DataFrame(cols)], axis=1)
    out["line"] = line_of_target
    out["shape"] = s
    return out


def model_predictions(cases, per_line, bundle, vid_by_code, n_model, seed):
    """Predicción de path_v4_l1_s1 desde el último ping de B <= entrada (causal), hacia el nodo de salida. Columnas eta_model."""
    from prediccion.replay.pinned import path_reference as PR
    rng = np.random.default_rng(seed)
    cases = cases.copy()
    cases["eta_model"] = np.nan
    cases["model_status"] = ""
    cases["origin_t"] = np.nan
    if n_model <= 0 or cases.empty:
        return cases
    out_parts = []
    for ln, g in cases.groupby("line"):
        cand = g[(g["n_any_60"] >= 1) & ((g["t_in"] - g["t0"]) <= 90)]
        if cand.empty:
            continue
        hard = cand[(cand["n_line_60"] >= 1) | (cand["n_ramal_60"] >= 1)]
        easy = cand.drop(hard.index)
        take = pd.concat([hard.sample(min(len(hard), n_model // 2), random_state=int(rng.integers(1 << 30))),
                          easy.sample(min(len(easy), n_model - min(len(hard), n_model // 2)), random_state=int(rng.integers(1 << 30)))])
        out_parts.append(take)
    if not out_parts:
        return cases
    S = pd.concat(out_parts)
    vehs = per_line
    inv = {}
    for ln, d in vehs.items():
        for vid, v in d.items():
            inv[vid] = v
    res_eta, res_st, res_o = {}, {}, {}
    for idx, r in S.iterrows():
        ln = r["line"]; s = r["shape"]
        v = inv[vid_by_code[int(r["vid"])]]
        t0 = float(r["t0"])
        i = int(np.searchsorted(v.ts, t0))
        if i >= len(v.ts) or abs(v.ts[i] - t0) > 1e-6:
            res_st[idx] = "sin_ping"; continue
        hist = [dict(ts=float(v.ts[j]), lat=float(v.lat[j]), lon=float(v.lon[j])) for j in range(i) if t0 - v.ts[j] <= 900]
        others = []
        for ov in vehs[ln].values():
            if ov is v:
                continue
            a = np.searchsorted(ov.ts, t0 - 1200, "left"); b = np.searchsorted(ov.ts, t0, "right")
            if b - a >= 1:
                others.append({"pings": [(float(ov.ts[j]), float(ov.lat[j]), float(ov.lon[j])) for j in range(a, b)]})
        sh = bundle.lines[ln].get(s)
        if sh is None:
            res_st[idx] = "shape_fuera_del_modelo"; continue
        d_end = min(r["node"] * EQ.NODE_M + r["m"] * EQ.NODE_M, sh.length_m - 50)
        user = sh.latlon_at(d_end)
        veh = dict(lat=float(v.lat[i]), lon=float(v.lon[i]), speed_mps=float(v.speed[i]), ts=t0)
        out = PR.predict_from_raw(bundle, ln, veh, user, t0, history=hist, others=others, only_shapes=[s], user_kind="punto")
        res_st[idx] = out["status"]
        c = [x for x in out["candidates"] if x["shape_id"] == s]
        if c:
            res_eta[idx] = c[0]["eta_model_s"]; res_o[idx] = t0
    for idx, st in res_st.items():
        cases.loc[idx, "model_status"] = st
    for idx, e in res_eta.items():
        cases.loc[idx, "eta_model"] = e; cases.loc[idx, "origin_t"] = res_o[idx]
    return cases


def run_day(day, lines=EQ.TARGET_LINES, model_n=300, model_ms=(4, 6), seed=0, equiv_cache=RAW / "equiv.pkl", out_dir=RAW):
    t00 = time.time()
    from prediccion.v2.shapes import LineShapes
    eq = EQ.build(SHAPES_DIR, cache=equiv_cache)
    ls = LineShapes(SHAPES_DIR)
    targets = [s for s, t in eq["target"].items() if t["line"] in lines]
    cand_lines = set(lines)
    for s in targets:
        cand_lines |= {eq["shape_line"][sp] for sp in eq["eq"][s]}
    per_line = load_vehicles(day, cand_lines)
    print(day, "cargado", len(cand_lines), "lineas", sum(len(v) for v in per_line.values()), "coches", f"{time.time()-t00:.0f}s", flush=True)
    cross, vid_codes, via_codes = crossings_for_day(per_line, eq["eq"], ls, targets)
    print(day, "cruces", {s: len(d) for s, d in list(cross.items())[:3]}, f"{time.time()-t00:.0f}s", flush=True)
    code_vid = {c: v for v, c in vid_codes.items()}
    code_via = {c: v for v, c in via_codes.items()}
    vid_line = {}
    trips_by_code = {}
    for ln, d in per_line.items():
        for vid, v in d.items():
            c = vid_codes.get(vid)
            if c is not None:
                vid_line[c] = ln
                trips_by_code[c] = [(a, b, s) for a, b, s in v.trips if s]
    day0 = min(float(v.ts[0]) for d in per_line.values() for v in d.values() if len(v.ts))
    all_cases = []
    for s in targets:
        if s not in cross:
            continue
        L = eq["target"][s]["line"]
        segok = {via_codes[sp]: eq["eq"][s][sp][2] for sp in eq["eq"][s] if sp in via_codes}
        P = passes_from_crossings(cross[s], segok)
        if P.empty:
            continue
        P["trip"] = trip_shape_at(P, trips_by_code)
        P["line"] = P["vid"].map(vid_line)
        known = P["trip"] != ""
        P["cls"] = -1
        P.loc[known & (P["line"] == L) & (P["trip"] == s), "cls"] = 0
        P.loc[known & (P["line"] == L) & (P["trip"] != s), "cls"] = 1
        P.loc[known & (P["line"] != L), "cls"] = 2
        P = P[P["cls"] >= 0].copy()
        P["isvia_s"] = P["via"].map(code_via) == s
        c = match_twins(P, L, s, day0)
        all_cases.append(c)
        print(day, s, L, "pasadas", len(P), "casos B", len(c), f"{time.time()-t00:.0f}s", flush=True)
    if not all_cases:
        return
    cases = pd.concat(all_cases, ignore_index=True)
    cases["day"] = day
    cases.attrs["vid_by_code"] = code_vid
    if model_n:
        from prediccion.replay.pinned import path_reference as PR
        bundle = PR.load_bundle(MODEL_DIR)
        cases["eta_model"] = np.nan; cases["model_status"] = ""; cases["origin_t"] = np.nan
        for mm_ in model_ms:
            sub = cases[cases["m"] == mm_]
            mp = model_predictions(sub, per_line, bundle, code_vid, model_n, seed)
            cases.loc[mp.index, ["eta_model", "model_status", "origin_t"]] = mp[["eta_model", "model_status", "origin_t"]]
        mp = cases
        print(day, "modelo", int(mp["eta_model"].notna().sum()), f"{time.time()-t00:.0f}s", flush=True)
    cases["vid_name"] = cases["vid"].map(code_vid)
    cases = cases.drop(columns=[c for c in cases.columns if c.startswith("vid_") and c != "vid_name"])
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cases.to_parquet(Path(out_dir) / f"cases_{day}.parquet")
    print(day, "listo", len(cases), f"{time.time()-t00:.0f}s", flush=True)


def _worker(a):
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00000040)  # IDLE
    except Exception:
        pass
    day, kw = a
    run_day(day, **kw)
    return day


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", required=True)
    ap.add_argument("--lines", default=",".join(EQ.TARGET_LINES))
    ap.add_argument("--model-n", type=int, default=300)
    ap.add_argument("--model-ms", default="4,6")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", default=str(RAW))
    a = ap.parse_args()
    days = a.days.split(",")
    kw = dict(lines=tuple(a.lines.split(",")), model_n=a.model_n, model_ms=tuple(int(x) for x in a.model_ms.split(',')), out_dir=a.out)
    if a.workers <= 1:
        for d in days:
            _worker((d, kw))
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(a.workers) as ex:
            for d in ex.map(_worker, [(d, kw) for d in days]):
                print("hecho", d, flush=True)


if __name__ == "__main__":
    main()
