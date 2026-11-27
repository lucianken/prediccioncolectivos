"""Tablas del piso de gemelos. python experiments/piso_gemelos/analisis.py [raw_dir] -> raw/tablas.md + raw/resumen.json"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "raw"
TYPES = {"any": "cualquier gemelo", "same": "misma línea y recorrido", "ramal": "misma línea, otro ramal", "line": "otra línea (tronco compartido)"}
DELTAS = (60, 120, 300)
M_NODE = 250
BAND = (180, 420)
NOISE_M = 8.0   # MAE de interpolación por cruce (s), ruido_interp.py; rango 7-15 s (ARQUITECTURA §7)

c = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(RAW / "cases_*.parquet")))], ignore_index=True)
c["wk"] = pd.to_datetime(c["day"]).dt.dayofweek >= 5
c["dist"] = c["m"] * M_NODE


def stats(e):
    """e = predicho - real (s)."""
    a = np.abs(e)
    return dict(n=len(e), mae=a.mean(), p50=np.median(a), p90=np.quantile(a, .9), bias=-e.mean(),
                gt60=(a > 60).mean() * 100, antes60=(e > 60).mean() * 100, despues60=(e < -60).mean() * 100)


def fmt(d, extra=""):
    return f"{d['n']} | {d['mae']:.1f} | {d['p50']:.1f} | {d['p90']:.1f} | {d['bias']:+.1f} | {d['gt60']:.1f} | {d['antes60']:.1f}"


HDR = "| n | MAE | P50 | P90 | sesgo (real−pred) | % abs>60 s | % llega antes >60 s |\n|---|---|---|---|---|---|---|\n"
out = []
res = {}


def twin_err(x, t, D, kind="near"):
    col = f"dur_{t}_{D}" if kind == "near" else f"med_{t}_{D}"
    y = x[x[f"n_{t}_{D}"] > 0]
    return y, (y[col] - y["dur"]).to_numpy()


out.append(f"Casos B totales: {len(c)}; días: {c['day'].nunique()}; coches-día distintos: {c.groupby(['day','vid_name']).ngroups}\n")
# banda de 3-7 min por largo
rows = []
for m in sorted(c["m"].unique()):
    x = c[c["m"] == m]
    rows.append(f"| {m*M_NODE} m | {len(x)} | {x['dur'].median()/60:.1f} | {((x['dur']>=BAND[0])&(x['dur']<=BAND[1])).mean()*100:.0f} |")
out.append("## Largo de tramo y banda 3–7 min\n| largo | casos B | duración mediana (min) | % de B con t_B en 3–7 min |\n|---|---|---|---|\n" + "\n".join(rows) + "\n")

for m in (4, 6):
    x = c[(c["m"] == m) & c["dur"].between(*BAND)]
    out.append(f"## Piso por tipo de gemelo y Δ de entrada, tramo {m*M_NODE} m, B con t_B real en 3–7 min (gemelo más cercano en entrada)\n")
    out.append("| tipo | Δ | " + HDR.split("\n")[0][1:] + "\n|---|---|---|---|---|---|---|---|---|")
    for t, nm in TYPES.items():
        for D in DELTAS:
            y, e = twin_err(x, t, D)
            if len(e) == 0:
                continue
            s = stats(e); res[f"m{m}_{t}_{D}_near"] = s
            out[-1 + 0] += f"\n| {nm} | ≤{D} s | {fmt(s)} |"
    out.append(f"\n### Variante mediana de los A disponibles (mismo tramo {m*M_NODE} m)\n")
    out.append("| tipo | Δ | " + HDR.split("\n")[0][1:] + "\n|---|---|---|---|---|---|---|---|---|")
    for t, nm in TYPES.items():
        for D in DELTAS:
            y, e = twin_err(x, t, D, "med")
            if len(e) == 0:
                continue
            s = stats(e); res[f"m{m}_{t}_{D}_med"] = s
            n_a = y[f"n_{t}_{D}"].mean()
            out[-1] += f"\n| {nm} | ≤{D} s | {fmt(s)} (A medio por caso {n_a:.1f}) |"
    # n de A por caso
    out.append("")

# fin de semana vs hábil, tramo 1000 y 1500, Δ60 any
out.append("## Hábil contra fin de semana (cualquier gemelo, Δ ≤ 60 s)\n| tramo | día | " + HDR.split("\n")[0][1:] + "\n|---|---|---|---|---|---|---|---|---|")
for m in (4, 6):
    for wk, nm in ((False, "hábil"), (True, "fin de semana")):
        x = c[(c["m"] == m) & c["dur"].between(*BAND) & (c["wk"] == wk)]
        y, e = twin_err(x, "any", 60)
        if len(e):
            out[-1] += f"\n| {m*M_NODE} m | {nm} | {fmt(stats(e))} |"

# por línea
for m in (4, 6):
    out.append(f"\n## Por línea, tramo {m*M_NODE} m, B en 3–7 min, cualquier gemelo, Δ ≤ 60 s\n| línea | " + HDR.split("\n")[0][1:] + "\n|---|---|---|---|---|---|---|---|---|")
    for ln, g in c[(c["m"] == m) & c["dur"].between(*BAND)].groupby("line"):
        y, e = twin_err(g, "any", 60)
        if len(e):
            s = stats(e); res[f"m{m}_line{ln}"] = s
            out[-1] += f"\n| {ln} | {fmt(s)} |"

# bandas de ETA real
out.append("\n## Por banda de ETA real (t_B), tramos de 1000 y 1500 m juntos, cualquier gemelo, Δ ≤ 60 s\n| banda | " + HDR.split("\n")[0][1:] + "\n|---|---|---|---|---|---|---|---|---|")
x0 = c[c["m"].isin((4, 6))]
for lo, hi in ((60, 120), (120, 180), (180, 300), (300, 420), (420, 600), (600, 900)):
    x = x0[x0["dur"].between(lo, hi, inclusive="left")]
    y, e = twin_err(x, "any", 60)
    if len(e):
        out[-1] += f"\n| {lo//60}–{hi//60} min | {fmt(stats(e))} |"

# modelo
mm = c[c["eta_model"].notna()].copy()
mm["e_model"] = mm["origin_t"] + mm["eta_model"] - mm["t_out"]
out.append("\n## Comparación con `path_v4_l1_s1` en los mismos casos de B (predicción desde el último ping ≤ entrada; causal; ETA del modelo sin descuento de offset)\n")
out.append(f"Casos con predicción del modelo: {len(mm)} (muestra estratificada por línea y día).\n")
out.append("| tramo | tipo de gemelo (Δ ≤ 60 s) | n | gemelo MAE | gemelo P90 | modelo MAE | modelo P90 | modelo % llega antes >60 s | gemelo % llega antes >60 s |\n|---|---|---|---|---|---|---|---|---|")
for m in (4, 6):
    x = mm[(mm["m"] == m) & mm["dur"].between(*BAND)]
    for t, nm in TYPES.items():
        y = x[x[f"n_{t}_60"] > 0]
        if len(y) < 20:
            continue
        et = (y[f"dur_{t}_60"] - y["dur"]).to_numpy()
        em = y["e_model"].to_numpy()
        st, sm = stats(et), stats(em)
        res[f"model_m{m}_{t}"] = dict(n=len(y), twin=st, model=sm)
        out[-1] += f"\n| {m*M_NODE} m | {nm} | {len(y)} | {st['mae']:.1f} | {st['p90']:.1f} | {sm['mae']:.1f} | {sm['p90']:.1f} | {sm['antes60']:.1f} | {st['antes60']:.1f} |"
out.append("\nModelo por línea (tramo 1000 y 1500 m, B en 3–7 min, con gemelo cualquiera Δ ≤ 60 s):\n\n| línea | n | gemelo MAE | modelo MAE | modelo P90 | gemelo P90 |\n|---|---|---|---|---|---|")
x = mm[mm["m"].isin((4, 6)) & mm["dur"].between(*BAND) & (mm["n_any_60"] > 0)]
for ln, g in x.groupby("line"):
    et = (g["dur_any_60"] - g["dur"]).abs(); em = g["e_model"].abs()
    out[-1] += f"\n| {ln} | {len(g)} | {et.mean():.1f} | {em.mean():.1f} | {em.quantile(.9):.1f} | {et.quantile(.9):.1f} |"
# modelo con la banda definida por ETA real desde el ping
x = mm[mm["m"].isin((4, 6))].copy()
x["eta_real_ping"] = x["t_out"] - x["origin_t"]
x = x[x["eta_real_ping"].between(*BAND)]
out.append(f"\nModelo en la banda 3–7 min definida por el ETA real desde el ping (vara del modelo), todos los B de la muestra, 1000 y 1500 m: n={len(x)}, MAE {x['e_model'].abs().mean():.1f} s, P90 {x['e_model'].abs().quantile(.9):.1f} s, llega antes >60 s {(x['e_model']>60).mean()*100:.1f} %.\n")

# ruido
out.append("## Ruido de interpolación en el piso (tramos 1000 y 1500 m, B en 3–7 min, cualquier gemelo, Δ ≤ 60 s)\n")
x = c[c["m"].isin((4, 6)) & c["dur"].between(*BAND)]
y, e = twin_err(x, "any", 60)
mae = np.abs(e).mean()
out.append("| ruido por cruce (MAE, s) | ruido del gemelo (4 cruces, ≈ 2×) | piso neto (√(MAE² − ruido²)) | modelo neto (1 cruce, B salida) |\n|---|---|---|---|")
em = mm[mm["m"].isin((4, 6)) & mm["dur"].between(*BAND) & (mm["n_any_60"] > 0)]["e_model"].abs().mean()
for nz in (7.2, 8.0, 14.9):
    out.append(f"| {nz} | {2*nz:.1f} | {np.sqrt(max(mae**2-(2*nz)**2,0)):.1f} (observado {mae:.1f}) | {np.sqrt(max(em**2-nz**2,0)):.1f} (observado {em:.1f}) |")
res["noise_floor_mae_obs"] = float(mae)
(RAW / "tablas.md").write_text("\n".join(out), encoding="utf-8")
json.dump(res, open(RAW / "resumen.json", "w"), indent=1, default=float)
print("\n".join(out))
