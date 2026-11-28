import sys, json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[4]; sys.path.insert(0, str(ROOT))
from prediccion.v2.day import read_day, prev_day
from prediccion.v2.shapes import LineShapes, DEFAULT_LABEL_MAP, DEFAULT_LINE_SHAPES_DIR
from red.label_map import load_label_line_data, resolve_label_line_index
from red import geo_assign as G
day, line, vid, t0 = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
ld = load_label_line_data(DEFAULT_LABEL_MAP); li = resolve_label_line_index(ld, on_date=day)
lm = {s: v["line"] for s, v in li.items()}
veh, _, _ = read_day(Path("//192.168.0.18/buffer/grabaciones")/f"{day}.ndjson.gz", lm, {line})
obs = [o for o in veh[vid]["obs"] if t0 - 60 <= o[0] <= t0 + 12000]
sh = LineShapes(DEFAULT_LINE_SHAPES_DIR).indices(line)
lat = np.array([o[1] for o in obs]); lon = np.array([o[2] for o in obs])
P = {s: ix.project_many(lat, lon) for s, ix in sh.items()}
m = G.compat_masks({s: p for s, (_, p) in P.items()})
sid = sys.argv[5]
print("n", len(obs), "shape", sid, "compat", m[sid].sum())
mn = np.min(np.stack([p for _, p in P.values()]), 0)
for i in range(0, len(obs), 6):
    print(i, obs[i][0], "v=%.1f" % obs[i][3], "perp_elegido=%.0f" % P[sid][1][i], "min_linea=%.0f" % mn[i], "d=%.0f" % P[sid][0][i], "otros:", {s[-4:]: int(p[i]) for s, (_, p) in P.items() if s != sid and p[i] < 120}, "ok" if m[sid][i] else "NO")
print("".join("." if m[sid][i] else "X" for i in range(len(obs))))
