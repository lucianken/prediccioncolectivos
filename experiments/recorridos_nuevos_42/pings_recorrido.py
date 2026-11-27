"""Tarea 2: ¿los coches de la 42 van por el recorrido nuevo? Fracción de pings en movimiento a <=45 m de algún recorrido
nuevo y >45 m de todos los viejos (y al revés), por día y por tramo. Entradas: cache de pings42.py + diff_shapes."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parents[2]
from diff_shapes import densify, xy, EXP, PC, T, KX, KY
OUT = ROOT / "data/ml/replay/recorridos_nuevos_42"
DAYS_ANT = ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-24"]
DAYS_NEW = ["2026-11-25", "2026-11-26", "2026-11-27"]
MOV = 2.0   # m/s
e = json.loads((EXP / "lines/42.json").read_text())
old = np.concatenate([densify(np.array(s["points"]).reshape(-1, 2), 5) for s in e["shapes"]])
nd = json.loads((PC / "data/line_shapes/42.json").read_text(encoding="utf-8"))
new = np.concatenate([densify(np.array(r["points"]), 5) for r in nd["ramales"]])
to, tn = cKDTree(old), cKDTree(new)
d42 = json.loads((OUT / "diff_42.json").read_text(encoding="utf-8"))
def lab(stops):
    return np.array([[s[0] * KY and s[1] * KX, s[0] * KY] for s in stops]), [s[2] for s in stops]
sn = [(a, b, n) for a, b, n in d42["stops_new"] + d42["stops_new_gt45"]]
sg = d42["stops_gone"]
tn_s, nn_s = cKDTree(xy([[a, b] for a, b, _ in sn])), [n for *_, n in sn]
tg_s, ng_s = cKDTree(xy([[a, b] for a, b, _ in sg])), [n for *_, n in sg]
rows, tram, first = [], [], []
for day in DAYS_ANT + DAYS_NEW:
    df = pd.read_parquet(OUT / "cache" / f"{day}_42.parquet")
    df = df[df.speed >= MOV]
    p = xy(df[["lat", "lon"]].values)
    do, dn = to.query(p)[0], tn.query(p)[0]
    near_o, near_n = do <= T, dn <= T
    cat = np.where(near_n & ~near_o, "nuevo_solo", np.where(near_o & ~near_n, "viejo_solo", np.where(near_o & near_n, "ambos", "ninguno")))
    df = df.assign(cat=cat)
    # solo en la zona de la desviación: bbox de los tramos que difieren
    box = (df.lat.between(-34.622, -34.594)) & (df.lon.between(-58.458, -58.434))
    z = df[box]
    rows.append(dict(day=day, n_mov=len(df), nuevo_solo=int((cat == "nuevo_solo").sum()), viejo_solo=int((cat == "viejo_solo").sum()),
                     ambos=int((cat == "ambos").sum()), ninguno=int((cat == "ninguno").sum()),
                     zona_n=len(z), zona_nuevo_solo=int((z.cat == "nuevo_solo").sum()), zona_viejo_solo=int((z.cat == "viejo_solo").sum()),
                     zona_ambos=int((z.cat == "ambos").sum()), zona_ninguno=int((z.cat == "ninguno").sum()),
                     coches_nuevo=df[df.cat == "nuevo_solo"].vid.nunique(), coches_viejo=df[df.cat == "viejo_solo"].vid.nunique()))
    for c, tree, names in (("nuevo_solo", tn_s, nn_s), ("viejo_solo", tg_s, ng_s)):
        s = df[df.cat == c]
        if len(s):
            nm = np.array(names)[tree.query(xy(s[["lat", "lon"]].values))[1]]
            for k, v in pd.Series(nm).value_counts().items():
                tram.append(dict(day=day, cat=c, tramo=k, n=int(v)))
    # hora de cambio
    hh = lambda t: pd.to_datetime(t - 3 * 3600, unit="s").strftime("%H:%M")
    for c in ("nuevo_solo", "viejo_solo"):
        s = df[df.cat == c]
        first.append(dict(day=day, cat=c, primero=hh(s.ts.min()) if len(s) else "", ultimo=hh(s.ts.max()) if len(s) else ""))
r = pd.DataFrame(rows); r["pct_nuevo_solo"] = 100 * r.nuevo_solo / r.n_mov; r["pct_viejo_solo"] = 100 * r.viejo_solo / r.n_mov
r["pct_ninguno"] = 100 * r.ninguno / r.n_mov
r["zona_pct_nuevo"] = 100 * r.zona_nuevo_solo / r.zona_n; r["zona_pct_viejo"] = 100 * r.zona_viejo_solo / r.zona_n
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(r.round(2).to_string())
print(pd.DataFrame(first).to_string())
t = pd.DataFrame(tram); t.to_csv(OUT / "pings_tramos.csv", index=False); r.to_csv(OUT / "pings_dias.csv", index=False)
pd.DataFrame(first).to_csv(OUT / "pings_horas.csv", index=False)
a = t.assign(per=np.where(t.day.isin(DAYS_NEW), "desde 25/11", "14-24/11"))
print(a.groupby(["per", "cat", "tramo"]).n.sum().sort_values(ascending=False).groupby(level=[0, 1]).head(8))
