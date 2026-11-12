"""
Seguimiento E2: el sesgo por linea se explica por el largo del shape (el A3 solo ve distancias normalizadas)?
Solo lectura; sin entrenar. Salidas: data/ml/v2/diag/heldout_length_*.{json,png}.
Uso: PYTHONPATH=. python -m prediccion.v2.diag.heldout_length
"""
from __future__ import annotations

import json

import numpy as np
import pyarrow.parquet as pq
import torch
from scipy import stats
from torch.utils.data import DataLoader

from prediccion.eval import compute_metrics
from prediccion.models.a3_eta import A3ETAModel
from prediccion.models.eta_dataset import ETADataset, collate_identity
from prediccion.v2.diag.common import DIAG, V2

CKPT = V2 / "models_e2_geo" / "e2_geo.pt"
SDN = V2 / "models_e2_geo" / "schedule_dev_medians.json"
HELD, SEEN = V2 / "eval" / "eval_heldout.parquet", V2 / "eval" / "eval_seen.parquet"
LENGTHS = json.load(open(V2 / "shape_lengths.json", encoding="utf-8"))


def predict(path, l_typ=None, sdn=SDN, bs=4096):
    """Como prediccion.eval.predict_a3; con l_typ renormaliza dist_remaining_norm y la columna 0 de la trayectoria
    (dist_along_norm) como si el shape midiera l_typ metros (el largo real sale de dist_remaining_m / norm)."""
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    sd = torch.load(str(CKPT), map_location="cpu", weights_only=False)["model_state_dict"]
    model = A3ETAModel(d_model=int(sd["trajectory_enc.input_proj.weight"].shape[0]), city_grid=True)
    model.load_state_dict(sd)
    model.to(dev).eval()
    ds = ETADataset(path, shape_lengths=LENGTHS, shuffle=False, yield_batch_size=bs, use_fleet=False,
                    schedule_dev_medians=str(sdn), use_geo=True)
    out = []
    with torch.no_grad():
        for b in DataLoader(ds, batch_size=1, shuffle=False, collate_fn=collate_identity, num_workers=0):
            if l_typ is not None:
                L = b["dist_remaining_m"] / b["dist_remaining_norm"].clamp_min(1e-9)   # (b,1) largo real
                f = L / l_typ
                b["dist_remaining_norm"] = b["dist_remaining_norm"] * f
                tr = b["trajectory"].clone()
                tr[:, :, 0] = (tr[:, :, 0] * f).clamp(0, 1)
                b["trajectory"] = tr
            g = lambda k: b[k].to(dev)  # noqa: E731
            p = model(g("trajectory"), g("trajectory_mask"), g("fleet"), g("fleet_mask"), g("hour_sin"), g("hour_cos"),
                      g("dow"), g("dist_remaining_norm"), g("time_since_start"), g("ts_age_s"), g("has_active_bus"),
                      g("schedule_dev_norm"), g("time_since_last_bus_s"), g("last_bus_found"), g("geo"))
            out.append(p.squeeze(-1).cpu().numpy())
    return np.concatenate(out).astype(np.float64)


def load(path):
    d = pq.read_table(path, columns=["line", "ramal_id", "dist_remaining_m", "observed_eta_s"]).to_pandas()
    d["L"] = d.ramal_id.astype(str).map(lambda r: LENGTHS.get(r, np.nan))
    d["true"] = d.observed_eta_s.astype(float)
    return d


def line_table(d, col):
    rows = {}
    for ln, s in d.groupby("line"):
        rows[ln] = {"n": len(s), "L_km": float(s.L.mean() / 1000), "bias": float((s[col] - s.true).mean()),
                    "mae": float((s[col] - s.true).abs().mean())}
    return rows


def corr(rows):
    x = np.array([v["L_km"] for v in rows.values()])
    y = np.array([v["bias"] for v in rows.values()])
    return {"n": len(x), "pearson": float(stats.pearsonr(x, y)[0]), "spearman": float(stats.spearmanr(x, y)[0])}


def main():
    res = {}
    held, seen = load(HELD), load(SEEN)
    held["pred"] = predict(HELD)
    seen["pred"] = predict(SEEN)
    l_typ = float(seen.L.mean())   # largo tipico: media por fila de las lineas vistas
    res["l_typ_m"] = l_typ
    seen["pred_typ"] = predict(SEEN, l_typ)
    held["pred_typ"] = predict(HELD, l_typ)
    th, ts, tt, tht = (line_table(held, "pred"), line_table(seen, "pred"), line_table(seen, "pred_typ"),
                       line_table(held, "pred_typ"))
    res["held_lines"], res["seen_lines"], res["seen_lines_typ"], res["held_lines_typ"] = th, ts, tt, tht
    res["corr"] = {"held": corr(th), "seen": corr(ts), "seen_typ": corr(tt), "held_typ": corr(tht)}
    x = np.array([ts[k]["L_km"] * 1000 / l_typ for k in ts])
    y = np.array([tt[k]["bias"] - ts[k]["bias"] for k in ts])
    res["corr"]["seen_cambio_sesgo_vs_L"] = {"pearson": float(stats.pearsonr(x, y)[0]),
                                             "spearman": float(stats.spearmanr(x, y)[0])}
    res["metrics_seen"] = {c: compute_metrics(seen[c], seen.true, seen.dist_remaining_m)["global"] for c in ("pred", "pred_typ")}
    res["metrics_held"] = {c: compute_metrics(held[c], held.true, held.dist_remaining_m)["global"] for c in ("pred", "pred_typ")}
    held["err"] = held.pred - held.true
    held["Lbin"] = np.digitize(held.L / 1000, [12, 15, 20, 30, 40])
    held["Dbin"] = np.digitize(held.dist_remaining_m, [500, 1000, 2000, 5000, 10000])
    held["frac"] = held.dist_remaining_m / held.L
    held["Fbin"] = np.digitize(held.frac, [.1, .25, .5, .75])

    def agg(col):
        return {int(k): {"n": len(s), "bias": float(s.err.mean()), "mae": float(s.err.abs().mean()),
                         "L_km": float(s.L.mean() / 1000), "d_km": float(s.dist_remaining_m.mean() / 1000),
                         "rel_bias_median": float(((s.pred - s.true) / s.true).median())}
                for k, s in held.groupby(col)}
    res["held_by_Lbin"], res["held_by_Dbin"], res["held_by_Fbin"] = agg("Lbin"), agg("Dbin"), agg("Fbin")
    res["held_row_spearman"] = {k: float(stats.spearmanr(held[k], held.err)[0]) for k in ("L", "dist_remaining_m", "frac")}
    json.dump(res, open(DIAG / "heldout_length_results.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False,
              default=float)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 3, figsize=(20, 6))
    for ax, (tab_s, tab_h, ttl) in zip(axs[:2], [(ts, th, "E2 real"),
                                                 (tt, tht, "E2 con largo = %.0f km para todas" % (l_typ / 1000))]):
        ax.scatter([v["L_km"] for v in tab_s.values()], [v["bias"] for v in tab_s.values()], c="#888", label="vistas (48)")
        for k, v in tab_s.items():
            ax.annotate(k, (v["L_km"], v["bias"]), fontsize=6, color="#666")
        ax.scatter([v["L_km"] for v in tab_h.values()], [v["bias"] for v in tab_h.values()], c="#d33", s=60, label="control (12)")
        for k, v in tab_h.items():
            ax.annotate(k, (v["L_km"], v["bias"]), fontsize=8, color="#d33")
        ax.axhline(0, c="k", lw=.5)
        ax.set_xlabel("largo medio del shape (km, ponderado por filas)")
        ax.set_ylabel("sesgo medio (s)")
        ax.set_title(ttl)
        ax.legend()
    axs[2].scatter(x, y, c="#36c")
    axs[2].axhline(0, c="k", lw=.5)
    axs[2].set_xlabel("L / L_tipico")
    axs[2].set_ylabel("cambio de sesgo por sustituir el largo (s), vistas")
    fig.savefig(DIAG / "heldout_length_scatter.png", dpi=100, bbox_inches="tight")
    print(json.dumps({k: res[k] for k in ("l_typ_m", "corr", "metrics_seen", "metrics_held", "held_by_Lbin",
                                          "held_by_Dbin", "held_by_Fbin", "held_row_spearman")}, indent=1, default=float))
    print("seen (L km, bias, bias_typ):", {k: (round(v["L_km"], 1), round(v["bias"]), round(tt[k]["bias"])) for k, v in ts.items()})
    print("held (L km, bias, bias_typ):", {k: (round(v["L_km"], 1), round(v["bias"]), round(tht[k]["bias"])) for k, v in th.items()})


if __name__ == "__main__":
    main()
