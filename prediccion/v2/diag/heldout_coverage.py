"""
Diagnostico E2: el sesgo/error en las lineas de control (eval_heldout) viene de vertices de la grilla de ciudad que
ninguna linea de train recorre (embeddings sin entrenar)? Solo lectura: no entrena ni toca modelo/pipeline/datos.
Salidas: data/ml/v2/diag/heldout_cov_*.{npz,json,parquet} (cache/resultados) y heldout_cobertura_mapa.png.
Uso: PYTHONPATH=. python -m prediccion.v2.diag.heldout_coverage [--stride 3]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from prediccion.eval import compute_metrics, predict_a3
from prediccion.models.a3_eta import (GRID_LAT_MAX, GRID_LAT_MIN, GRID_LON_MAX, GRID_LON_MIN, CityGridEncoder)
from prediccion.models.geo import ShapeGeoStore, geo_coords
from prediccion.v2.diag.common import DIAG, V2

CKPT = V2 / "models_e2_geo" / "e2_geo.pt"
TRAIN = V2 / "training" / "eta_train.parquet"
HELD = V2 / "eval" / "eval_heldout.parquet"
LOW = 100  # "poco cubierto": < LOW pasadas
GRID = CityGridEncoder(cell_m=500.0, dim=1)
NLAT, NLON = GRID.n_lat, GRID.n_lon
W = NLON + 1
NV = (NLAT + 1) * W


def corners(lat, lon):
    """Mismo calculo que CityGridEncoder.encode: (N,4) indices de vertice y (N,4) pesos bilineales."""
    u = np.clip((lat - GRID_LAT_MIN) / (GRID_LAT_MAX - GRID_LAT_MIN) * NLAT, 0, NLAT - 1e-4)
    v = np.clip((lon - GRID_LON_MIN) / (GRID_LON_MAX - GRID_LON_MIN) * NLON, 0, NLON - 1e-4)
    i0, j0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fu, fv = u - i0, v - j0
    idx = np.stack([i0 * W + j0, i0 * W + j0 + 1, (i0 + 1) * W + j0, (i0 + 1) * W + j0 + 1], 1)
    w = np.stack([(1 - fu) * (1 - fv), (1 - fu) * fv, fu * (1 - fv), fu * fv], 1)
    return idx, w


def train_counts(stride: int, store):
    """Conteo por vertice (filas cuyo P o T lo tiene entre sus 4 vecinos; P y T suman por separado), escalado por stride."""
    pf = pq.ParquetFile(TRAIN)
    cnt = np.zeros(NV, np.float64)
    n = 0
    cols = ["line", "shape_id", "dist_along_m", "dist_remaining_m", "dist_along_norm", "observed_eta_s"]
    for g in range(0, pf.metadata.num_row_groups, stride):
        t = pf.read_row_group(g, columns=cols)
        da = t["dist_along_m"].to_numpy().astype(np.float64)
        dr = t["dist_remaining_m"].to_numpy().astype(np.float32)
        dn = t["dist_along_norm"].to_numpy()
        eta = t["observed_eta_s"].to_numpy()
        m = (eta > 0) & (dr >= 100) & (dn >= 0) & (dn <= 1)       # mismo filtro que ETADataset
        geo = geo_coords(t["line"].to_pylist(), t["shape_id"].to_pylist(), da, dr, store)
        m &= np.isfinite(geo).all(1)
        geo = geo[m]
        for a in (0, 2):
            idx, _ = corners(geo[:, a].astype(np.float64), geo[:, a + 1].astype(np.float64))
            cnt += np.bincount(idx.ravel(), minlength=NV)
        n += int(m.sum())
    return cnt * stride, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=3)
    a = ap.parse_args()
    t0 = time.time()
    store = ShapeGeoStore()
    cache = DIAG / "heldout_cov_train_counts.npz"
    if cache.exists():
        z = np.load(cache)
        cnt, ntr = z["cnt"], int(z["n"])
    else:
        cnt, ntr = train_counts(a.stride, store)
        np.savez(cache, cnt=cnt, n=ntr)
    print(f"train: {ntr:,} filas usadas (stride {a.stride}), {time.time()-t0:.0f}s", flush=True)
    touched = cnt > 0
    res = {"n_vertices": NV, "n_lat": NLAT, "n_lon": NLON, "stride": a.stride, "train_rows_used": ntr,
           "touched": int(touched.sum()), "lt100_touched": int(((cnt < LOW) & touched).sum())}

    # 2. checkpoint
    import torch
    ck = torch.load(str(CKPT), map_location="cpu", weights_only=False)
    sd = ck["model_state_dict"]
    E = sd["city_grid.embed.weight"].numpy()
    rms = np.sqrt((E ** 2).mean(1))
    c = {"untouched_rms_mean": float(rms[~touched].mean()), "untouched_rms_std": float(rms[~touched].std()),
         "untouched_elem_std": float(E[~touched].std()), "untouched_elem_mean": float(E[~touched].mean()),
         "touched_rms_mean": float(rms[touched].mean()), "touched_rms_std": float(rms[touched].std()),
         "touched_elem_std": float(E[touched].std()), "init_expected_rms": 0.1}
    for name, lo, hi in [("1-99", 1, LOW), ("100-9999", LOW, 10000), (">=10000", 10000, np.inf)]:
        mm = (cnt >= lo) & (cnt < hi)
        c[f"rms_mean_{name}"] = float(rms[mm].mean()) if mm.any() else None
        c[f"n_{name}"] = int(mm.sum())
    res["ckpt"] = c
    print(json.dumps(c, indent=1), flush=True)

    # 3. cobertura de heldout
    h = pq.read_table(HELD, columns=["line", "shape_id", "ramal_id", "dist_along_m", "dist_remaining_m",
                                     "observed_eta_s"]).to_pandas()
    geo = geo_coords(h["line"], h["shape_id"], h["dist_along_m"], h["dist_remaining_m"].astype(np.float32), store)
    assert np.isfinite(geo).all()
    for nm, a0 in (("P", 0), ("T", 2)):
        idx, w = corners(geo[:, a0].astype(np.float64), geo[:, a0 + 1].astype(np.float64))
        cc = cnt[idx]
        h[f"{nm}_w_unt"] = (w * (cc == 0)).sum(1)
        h[f"{nm}_w_low"] = (w * (cc < LOW)).sum(1)  # incluye no tocados
        h[f"{nm}_cls"] = np.where(h[f"{nm}_w_unt"] > 0.5, "no cubierta",
                                  np.where(h[f"{nm}_w_low"] > 0.5, "poco cubierta", "bien cubierta"))
    h["any_unc"] = (h.P_cls != "bien cubierta") | (h.T_cls != "bien cubierta")
    h["cov_cls"] = np.where((h.P_cls == "no cubierta") | (h.T_cls == "no cubierta"), "no cubierta",
                            np.where(h.any_unc, "poco cubierta", "bien cubierta"))
    res["held_weight"] = {f"{nm}_{k}": float(h[f"{nm}_w_{k}"].mean()) for nm in "PT" for k in ("unt", "low")}
    res["held_weight_any_gt0_unt"] = {nm: float((h[f"{nm}_w_unt"] > 0).mean()) for nm in "PT"}

    # 4. predicciones: base, sdn=0, vertices poco cubiertos en cero
    n = len(h)
    lengths = json.load(open(V2 / "shape_lengths.json", encoding="utf-8"))
    sdn = V2 / "models_e2_geo" / "schedule_dev_medians.json"
    sdn2 = V2 / "schedule_dev_medians.json"
    res["sdn_files_identical"] = (sdn.read_bytes() == sdn2.read_bytes()) if sdn.exists() and sdn2.exists() else None
    meds = json.load(open(sdn, encoding="utf-8"))
    res["sdn_ramal_in_medians_heldout"] = float(h["ramal_id"].astype(str).isin(set(meds)).mean())
    res["sdn_ramal_in_medians_train_lines"] = None
    p_base = predict_a3(HELD, CKPT, lengths, sdn, n)
    p_nosdn = predict_a3(HELD, CKPT, lengths, None, n)
    E2 = E.copy()
    E2[cnt < LOW] = 0.0
    sd2 = dict(sd)
    sd2["city_grid.embed.weight"] = torch.from_numpy(E2)
    tmp = DIAG / "_tmp_ck_zero.pt"
    torch.save({"model_state_dict": sd2}, tmp)
    p_zero = predict_a3(HELD, tmp, lengths, sdn, n)
    tmp.unlink()
    h["true"] = h["observed_eta_s"].to_numpy(np.float64)
    h["pred"], h["pred_nosdn"], h["pred_zero"] = p_base, p_nosdn, p_zero

    def table(sub, col="pred"):
        return compute_metrics(sub[col].to_numpy(), sub["true"].to_numpy(), sub["dist_remaining_m"].to_numpy())

    def breakdown(sub):
        return {col: table(sub, col) for col in ("pred", "pred_nosdn", "pred_zero")}

    res["metrics"] = breakdown(h)
    res["by_cov"] = {k: {"n": int((h.cov_cls == k).sum()), **breakdown(h[h.cov_cls == k])}
                     for k in ("bien cubierta", "poco cubierta", "no cubierta")}
    for nm in "PT":
        res[f"by_{nm}"] = {k: {"n": int((h[f"{nm}_cls"] == k).sum()), **breakdown(h[h[f"{nm}_cls"] == k])}
                           for k in ("bien cubierta", "poco cubierta", "no cubierta")}
    res["by_line"] = {}
    for ln, s in h.groupby("line"):
        good = s[~s.any_unc]
        res["by_line"][ln] = {
            "n": len(s), "pct_unc": float(100 * s.any_unc.mean()),
            "pct_P_unc": float(100 * (s.P_cls != "bien cubierta").mean()),
            "pct_T_unc": float(100 * (s.T_cls != "bien cubierta").mean()),
            "pct_no": float(100 * (s.cov_cls == "no cubierta").mean()),
            "w_low_mean": float(((s.P_w_low + s.T_w_low) / 2).mean()),
            "m": table(s)["global"], "m_good": table(good)["global"] if len(good) else None, "n_good": len(good),
            "m_nosdn": table(s, "pred_nosdn")["global"], "m_zero": table(s, "pred_zero")["global"],
            "mean_len_km": float(np.mean([lengths.get(str(r), np.nan) for r in s.ramal_id.unique()]) / 1000),
            "ramales_en_sdn": float(s.ramal_id.astype(str).isin(set(meds)).mean())}
    res["sdn_effect_mean_pred_diff_s"] = float((p_base - p_nosdn).mean())
    json.dump(res, open(DIAG / "heldout_cov_results.json", "w", encoding="utf-8"), indent=1, default=float,
              ensure_ascii=False)
    h.to_parquet(DIAG / "heldout_cov_rows.parquet")

    # 5. mapa
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import TwoSlopeNorm
    fig, axs = plt.subplots(1, 2, figsize=(20, 11))
    vi, vj = np.divmod(np.arange(NV), W)
    vlat = GRID_LAT_MIN + vi / NLAT * (GRID_LAT_MAX - GRID_LAT_MIN)
    vlon = GRID_LON_MIN + vj / NLON * (GRID_LON_MAX - GRID_LON_MIN)
    held_lines = [str(x) for x in json.load(open(V2 / "lines.json"))["heldout"]]
    line_bias = {ln: res["by_line"][ln]["m"]["bias"] for ln in res["by_line"]}
    norm = TwoSlopeNorm(vmin=-150, vcenter=0, vmax=300)
    sm = ScalarMappable(norm=norm, cmap="coolwarm")
    for ax, mode in zip(axs, ("zoom", "ctx")):
        box = (vlon > -58.9) & (vlon < -58.0) & (vlat > -35.0) & (vlat < -34.4)
        ax.scatter(vlon[~touched & box], vlat[~touched & box], s=1, c="#9ad0a0", zorder=0, label="no tocado por train")
        im = ax.scatter(vlon[touched], vlat[touched], c=np.log10(cnt[touched]), s=6, cmap="Greys", vmin=0,
                        vmax=np.log10(cnt.max()), zorder=1)
        for ln in held_lines:
            for sg in store.shapes_of(ln).values():
                ax.plot(sg.lon, sg.lat, color=sm.to_rgba(line_bias.get(ln, 0)), lw=1.8, zorder=3, alpha=.9)
        ax.set_aspect(1 / np.cos(np.radians(34.65)))
        if mode == "zoom":
            ax.set_xlim(-58.75, -58.2)
            ax.set_ylim(-34.85, -34.45)
        else:
            ax.set_xlim(-59.1, -57.9)
            ax.set_ylim(-35.1, -34.3)
    fig.colorbar(sm, ax=axs, shrink=.5, label="sesgo E2 por linea de control (s, + = sobreestima)")
    fig.colorbar(im, ax=axs, shrink=.5, label="log10 conteo de pasadas de train por vertice", location="left")
    axs[0].set_title("Vertices tocados por train (gris; verde = no tocados) + recorridos de control por sesgo")
    axs[1].set_title("Bbox completo")
    fig.savefig(DIAG / "heldout_cobertura_mapa.png", dpi=100, bbox_inches="tight")
    print("listo", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
