"""Error del ETA por coche en el replay (sin volver a predecir ni entrenar). Reproducible sobre crudos nuevos.

Uso:
  python calcula.py [--runs RUN1,RUN2,...] [--days d1,d2,...] [--out DIR] [--workers 2]
Por defecto: runs = vara/run_base_sg + vara/run_cs_sg (variante base; el 3-oct sale de run_cs_sg; lo duplicado cuenta una vez),
los 10 dias de V3_PRODUCCION. Para los crudos con la verdad nueva (recorrido ex post): --runs data/ml/replay/vara/run_base_xp,...
Lee de los crudos: veh.parquet (listado, grupo, eta0_s = ETA anunciado en hora comun, tp2_s = paso firme propio, unv, past) e
inst.parquet. Edad del ping y cantidad de pings de historial NO estan en los crudos: se leen de los pings grabados
(//192.168.0.18/buffer/grabaciones, solo timestamps; sin segmentar ni predecir) con la misma regla que core.evaluate_line
(ultimo ping <= t; historial = pings en [t-900 s, t], incluido el actual).
Salidas en --out: filas.parquet (una fila por (dia, linea, parada, t, coche) listado con paso firme), instantes.parquet
(proximo coche anunciado y descomposicion), resumen.json con todas las tablas (lo usa el .md).
Convencion: err = ETA anunciado - tiempo real hasta SU propio paso; err > 0 = llega antes de lo anunciado, err < 0 = llega despues.
"""
from __future__ import annotations
import argparse, json, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]                      # .../prediccion colectivos
VARA = ROOT / "data/ml/replay/vara"
DATA = "//192.168.0.18/buffer/grabaciones"
LMAP = str(ROOT / "LABEL_LINE_MAP.json")
DAYS = ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19", "2026-09-20", "2026-10-03", "2026-10-04", "2026-10-06", "2026-10-08"]
HISTORY_S = 900
TOL = 60.0
BANDS = {"0-3": (0, 180), "3-7": (180, 420), "7-15": (420, 900)}
GROUPS = {"seguro": "Viene", "puede_venir": "Puede venir", "provisional": "Sentido sin confirmar"}


def load_runs(runs, days):
    vs, is_ = [], []
    for r in runs:
        d = Path(r)
        for p in sorted(d.glob("*.veh.parquet")):
            day = p.name[:10]
            if day not in days:
                continue
            v = pd.read_parquet(p)
            v = v[v.variant == "base"]
            i = pd.read_parquet(p.with_name(p.name.replace(".veh.", ".inst.")))
            i = i[i.variant == "base"]
            vs.append(v)
            is_.append(i)
    veh = pd.concat(vs, ignore_index=True).drop_duplicates(["line", "day", "stop_id", "t", "vehicle"])
    inst = pd.concat(is_, ignore_index=True).drop_duplicates(["line", "day", "stop_id", "t"])
    return inst, veh


def ping_meta(args):
    """Por (dia, linea): edad del ultimo ping y cantidad de pings en [t-900, t] para cada (vehiculo, t) pedido."""
    day, lines, need = args
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    sys.path.insert(0, str(ROOT))
    from prediccion.pipeline.shapes_io import load_label_line_data, resolve_label_line_index
    from prediccion.v2.day import read_day
    label_index = resolve_label_line_index(load_label_line_data(LMAP), on_date=day)
    lm = {s: v["line"] for s, v in label_index.items()}
    vehicles, _, _ = read_day(Path(DATA) / f"{day}.ndjson.gz", lm, set(lines), None, 30, False)
    ts = {}
    for vid, rec in vehicles.items():
        ln = lm.get(rec["label"].split("-")[-1]) if rec["label"] else None
        if ln in lines and rec["obs"]:
            ts[(ln, vid)] = np.sort(np.array([o[0] for o in rec["obs"]], dtype=np.float64))
    age = np.full(len(need), np.nan)
    npg = np.zeros(len(need), dtype=int)
    for (ln, vid), idx in need.groupby(["line", "vehicle"]).indices.items():
        a = ts.get((ln, vid))
        if a is None:
            continue
        t = need.t.values[idx].astype(float)
        j = np.searchsorted(a, t, side="right") - 1
        lo = np.searchsorted(a, t - HISTORY_S, side="left")
        ok = j >= 0
        age[idx[ok]] = t[ok] - a[j[ok]]
        npg[idx[ok]] = (j - lo + 1)[ok]
    out = need[["line", "vehicle", "t"]].copy()
    out["day"] = day
    out["age_s"] = age
    out["n_pings"] = npg
    return out


def stats(err):
    e = np.asarray(err, dtype=float)
    if len(e) == 0:
        return None
    return {"n": int(len(e)), "mae": float(np.abs(e).mean()), "p90": float(np.percentile(np.abs(e), 90)),
            "antes": float(100 * (e > TOL).mean()), "despues": float(100 * (e < -TOL).mean()), "sesgo": float(e.mean())}


def by_day(df, mask, min_n=20):
    """Estadisticos pooled y media +- desvio dia a dia (dias con >= min_n filas)."""
    s = df[mask]
    pooled = stats(s.err)
    if pooled is None:
        return None
    per = [stats(g.err) for _, g in s.groupby("day") if len(g) >= min_n]
    out = {"n": pooled["n"], "n_dias": len(per)}
    for k in ("mae", "p90", "antes", "despues", "sesgo"):
        v = np.array([p[k] for p in per]) if per else np.array([np.nan])
        out[k] = float(v.mean())
        out[k + "_sd"] = float(v.std(ddof=1)) if len(v) > 1 else float("nan")
        out[k + "_pooled"] = pooled[k]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=f"{VARA/'run_base_sg'},{VARA/'run_cs_sg'}")
    ap.add_argument("--days", default=",".join(DAYS))
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    days = set(a.days.split(","))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    inst, veh = load_runs(a.runs.split(","), days)
    print("cargado", len(inst), len(veh), f"{time.time()-t0:.0f}s", flush=True)

    # posicion en la lista (orden de pantalla: seguros por ETA, luego el resto por ETA) sobre todos los listados
    L = veh[veh.listed].copy()
    L["_o"] = (L.group != "seguro").astype(int)
    L = L.sort_values(["line", "day", "stop_id", "t", "_o", "eta_s"])
    key = ["line", "day", "stop_id", "t"]
    L["pos"] = L.groupby(key).cumcount() + 1

    # filas por coche: listados con paso firme propio
    lst = L[L.tp2_s.notna()].copy()
    lst["err"] = lst.eta0_s - lst.tp2_s
    lst = lst[lst.err.notna()]

    # edad del ping e historial (de los pings grabados)
    need = lst[["line", "day", "vehicle", "t"]].drop_duplicates()
    jobs = [(day, sorted(g.line.unique()), g[["line", "vehicle", "t"]].reset_index(drop=True)) for day, g in need.groupby("day")]
    metas = []
    with ProcessPoolExecutor(a.workers) as ex:
        for m in ex.map(ping_meta, jobs):
            metas.append(m)
            print("pings", m.day.iloc[0], f"{time.time()-t0:.0f}s", flush=True)
    meta = pd.concat(metas, ignore_index=True)
    lst = lst.merge(meta, on=["line", "day", "vehicle", "t"], how="left")
    lst["band"] = np.select([lst.tp2_s < 180, lst.tp2_s <= 420, lst.tp2_s <= 900], ["0-3", "3-7", "7-15"], "")
    lst["age_cat"] = pd.cut(lst.age_s, [-1, 30, 60, 120, 1e9], right=False, labels=["0-30", "30-60", "60-120", ">120"]).astype(object)
    lst["np_cat"] = np.where(lst.n_pings <= 1, "1", np.where(lst.n_pings == 2, "2", ">=3"))
    lst["pos_cat"] = np.where(lst.pos == 1, "1.o", "2.o-5.o")
    lst.drop(columns=["_o"]).to_parquet(out / "filas.parquet")

    res = {"n_filas_listadas_con_paso": int(len(lst)), "dias": sorted(lst.day.unique().tolist()), "runs": a.runs, "tablas": {}}
    T = res["tablas"]
    for b in BANDS:
        mb = lst.band == b
        T[f"total|{b}"] = by_day(lst, mb)
        for g in GROUPS:
            T[f"grupo:{g}|{b}"] = by_day(lst, mb & (lst.group == g))
        for p in ("1.o", "2.o-5.o"):
            T[f"pos:{p}|{b}"] = by_day(lst, mb & (lst.pos_cat == p))
        for g in GROUPS:
            for p in ("1.o", "2.o-5.o"):
                T[f"grupo:{g}+pos:{p}|{b}"] = by_day(lst, mb & (lst.group == g) & (lst.pos_cat == p))
        for c in ("0-30", "30-60", "60-120", ">120"):
            T[f"edad:{c}|{b}"] = by_day(lst, mb & (lst.age_cat == c))
        for c in ("1", "2", ">=3"):
            T[f"pings:{c}|{b}"] = by_day(lst, mb & (lst.np_cat == c))

    # proximo coche anunciado: descomposicion (banda 3-7 min de tiempo real al proximo paso)
    i = inst.copy()
    unv = i.unv_first_s.notna() & (i.unv_first_s < i.real_next2_s.fillna(np.inf)) & (i.unv_first_s <= 1200)
    n_unv = int(((i.real_next2_s >= 180) & (i.real_next2_s <= 420) & unv).sum())
    i = i[~unv & (i.real_next2_s >= 180) & (i.real_next2_s <= 420)].copy()
    first = L[L.pos == 1][key + ["vehicle", "tp2_s", "eta0_s", "group", "past", "unv"]].rename(
        columns={"vehicle": "ann_veh", "tp2_s": "ann_tp2", "eta0_s": "ann_eta0", "group": "ann_group", "past": "ann_past", "unv": "ann_unv"})
    v2 = veh[veh.tp2_s.notna()].sort_values(key + ["tp2_s"]).drop_duplicates(key)[key + ["vehicle"]].rename(columns={"vehicle": "real_veh"})
    L2 = L[key + ["vehicle", "pos"]].rename(columns={"vehicle": "real_veh", "pos": "real_pos"})
    i = i.merge(first, on=key, how="left").merge(v2, on=key, how="left").merge(L2, on=key + ["real_veh"], how="left")
    i["err_next"] = i.ann0_any_s - i.real_next2_s
    chk = i[i.ann0_any_s.notna()]
    res["check_ann0_igual_eta0_primero"] = float(np.isclose(chk.ann0_any_s, chk.ann_eta0).mean())

    def cat(r):
        if pd.isna(r.ann0_any_s):
            return "sin aviso"
        if r.ann_veh == r.real_veh:
            return "A. el anunciado 1.o es el primero en llegar"
        if pd.notna(r.ann_tp2):
            ap_ = "el anunciado 1.o llega despues"
        elif r.ann_past:
            ap_ = "el anunciado 1.o ya paso (entre su ultimo ping y t)"
        elif r.ann_unv:
            ap_ = "el anunciado 1.o no verificable"
        else:
            ap_ = "el anunciado 1.o es bondi fantasma (no pasa en 40 min)"
        where = "listado 2.o-5.o" if pd.notna(r.real_pos) else "bondi no anunciado"
        return f"B. el primero en llegar es {where}; {ap_}"
    i["cat"] = [cat(r) for r in i.itertuples()]
    i.to_parquet(out / "instantes.parquet")
    con = i[i.ann0_any_s.notna()]
    D = {"n_instantes_banda": int(len(i)), "n_excl_unv": n_unv, "n_con_anuncio": int(len(con)),
         "sin_anuncio_pct": float(100 * (1 - len(con) / max(len(i), 1))),
         "mae_total": float(con.err_next.abs().mean()), "antes": float(100 * (con.err_next > TOL).mean()),
         "despues": float(100 * (con.err_next < -TOL).mean()), "filas": []}
    for c, g in con.groupby("cat"):
        e = g.err_next
        own = (g.ann_eta0 - g.ann_tp2).dropna()
        D["filas"].append({"cat": c, "n": int(len(g)), "peso_pct": float(100 * len(g) / len(con)), "mae": float(e.abs().mean()),
                           "aporte_s": float(e.abs().sum() / len(con)), "antes": float(100 * (e > TOL).mean()),
                           "despues": float(100 * (e < -TOL).mean()), "sesgo": float(e.mean()),
                           "mae_propio_paso": float(own.abs().mean()) if len(own) else None, "n_propio": int(len(own))})
    D["filas"].sort(key=lambda x: x["cat"])
    isA = con.cat.str.startswith("A")
    D["por_dia"] = [{"day": d, "n": int(len(g)), "mae": float(g.err_next.abs().mean()), "pesoA": float(100 * isA[g.index].mean()),
                     "maeA": float(g[isA[g.index]].err_next.abs().mean())} for d, g in con.groupby("day")]
    res["proximo"] = D
    (out / "resumen.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print("hecho", f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
