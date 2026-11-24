"""Compara v2b (asignación legacy, 150 m) contra v2c (geo3) en los mismos días. Solo lectura."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
B, C = ROOT/"data/ml/v2b/daily", ROOT/"data/ml/v2c/validation/daily"
days = sys.argv[1].split(",")
def load(d):
    out = {}
    for tag, dd in (("b", B), ("c", C)):
        m = json.load(open(dd/f"{d}.meta.json")); t = pd.read_parquet(dd/f"{d}.trips.parquet")
        p = pd.read_parquet(dd/f"{d}.parquet", columns=["start_unknown"])
        out[tag] = (m, t, p)
    return out
rows = []
tot = {"b": dict(trips=0, shaped=0, rows=0, su_rows=0, su_trips=0, pings=0, valid=0), "c": dict(trips=0, shaped=0, rows=0, su_rows=0, su_trips=0, pings=0, valid=0)}
for d in days:
    for tag, (m, t, p) in load(d).items():
        s = t[t.shape_id != ""]
        a = tot[tag]
        a["trips"] += len(t); a["shaped"] += len(s); a["rows"] += m["n_rows"]
        a["su_rows"] += int(p.start_unknown.sum()); a["su_trips"] += int(t.start_unknown.sum())
        a["pings"] += int(s.n_points.sum()); a["valid"] += int(s.n_valid.sum())
for tag in "bc":
    a = tot[tag]
    print(tag, a, "| %%start_unknown filas %.2f, viajes %.2f | %% pings descartados (de viajes con recorrido) %.2f" % (
        100*a["su_rows"]/a["rows"], 100*a["su_trips"]/a["trips"], 100*(1-a["valid"]/a["pings"])))
# viajes emparejados (vehicle, start_ts): cambios de recorrido y pings perdidos
diff_shape = n_pair = 0; lost = []
for d in days:
    (_, tb, _), (_, tc, _) = load(d)["b"], load(d)["c"]
    j = tb.merge(tc, on=["vehicle_id", "start_ts"], suffixes=("_b", "_c"))
    n_pair += len(j); diff_shape += int((j.shape_id_b != j.shape_id_c).sum())
    j["lost"] = j.n_valid_b - j.n_valid_c; j["day"] = d
    lost.append(j)
L = pd.concat(lost)
print("viajes emparejados", n_pair, "con otro recorrido", diff_shape)
print("pings perdidos en viajes emparejados:", int(L.lost.sum()), "de", int(L.n_valid_b.sum()))
top = L.sort_values("lost", ascending=False).head(12)[["day", "line_b", "vehicle_id", "start_ts", "shape_id_b", "shape_id_c", "n_points_b", "n_valid_b", "n_valid_c", "lost"]]
print(top.to_string())
top.to_csv(Path(__file__).with_name("top_perdidos.csv"), index=False)
