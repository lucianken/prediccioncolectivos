import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[4]; sys.path.insert(0, str(ROOT))
from prediccion.v2.day import read_day
from prediccion.v2.shapes import LineShapes, DEFAULT_LABEL_MAP, DEFAULT_LINE_SHAPES_DIR
from red.label_map import load_label_line_data, resolve_label_line_index
from red import geo_assign as G
day = sys.argv[1]
b = pd.read_parquet(ROOT/f"data/ml/v2b/daily/{day}.trips.parquet"); c = pd.read_parquet(ROOT/f"data/ml/v2c/validation/daily/{day}.trips.parquet")
j = b.merge(c, on=["vehicle_id","start_ts"], suffixes=("_b","_c"))
j = j[(j.shape_id_b==j.shape_id_c)&(j.n_points_b==j.n_points_c)]
j["lost"] = j.n_valid_b-j.n_valid_c
j = j[(j.lost>=4)].sort_values("lost",ascending=False).head(60)
ld = load_label_line_data(DEFAULT_LABEL_MAP); li = resolve_label_line_index(ld, on_date=day); lm = {s:v["line"] for s,v in li.items()}
ls = LineShapes(DEFAULT_LINE_SHAPES_DIR)
for line, grp in j.groupby("line_b"):
    veh,_,_ = read_day(Path("//192.168.0.18/buffer/grabaciones")/f"{day}.ndjson.gz", lm, {line})
    sh = ls.indices(line)
    for r in grp.itertuples():
        obs = [o for o in veh[r.vehicle_id]["obs"] if r.start_ts <= o[0] <= r.start_ts + 60*r.n_points_b]
        lat = np.array([o[1] for o in obs]); lon = np.array([o[2] for o in obs]); sp = np.array([o[3] for o in obs])
        P = {s: ix.project_many(lat, lon) for s, ix in sh.items()}
        m = G.compat_masks({s: p for s,(_,p) in P.items()})
        ch = r.shape_id_b; no = ~m[ch]
        mn = np.min(np.stack([p for _,p in P.values()]),0)
        par = no & (P[ch][1] >= 45) & (P[ch][1] <= 150) & (mn <= 45)
        if par.sum() >= 3:
            i = np.flatnonzero(par)[0]
            print(day, line, r.vehicle_id, r.start_ts, "shape", ch, "lost", r.lost, "en_movimiento_con_otro_shape_mas_cerca", int(par.sum()), "ej ping idx", i, "ts", obs[i][0], "lat,lon %.5f,%.5f" % (obs[i][1], obs[i][2]), "perp_elegido %.0f" % P[ch][1][i], "perp_min_linea %.0f" % mn[i], "otro", [s for s,(_,p) in P.items() if p[i] <= mn[i]+1][:2])
