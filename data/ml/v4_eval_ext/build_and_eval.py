"""Experimento 2: eval ampliado (filas de los 25 días de val de data/ml/v4, banda de ETA real 3-7 min) para las líneas sin habilitar.
No toca data/ml/v4/eval. Salida: data/ml/v4_eval_ext/ext_seen.parquet, ext_pred.npy, ext_meta.json, resultados.json"""
import json, sys, time
from pathlib import Path
import numpy as np, pyarrow as pa, pyarrow.parquet as pq
sys.path.insert(0, ".")
from prediccion.v2.make_eval import valid_mask
LINES = ["49", "97", "119", "153", "154", "163", "164", "185", "193"]
V4 = Path("data/ml/v4"); OUT = Path("data/ml/v4_eval_ext")
meta = json.load(open(V4 / "eval/eval_meta.json")); days = meta["val_days"]
t0 = time.time()
parts = []
for d in days:
    t = pq.read_table(V4 / "daily" / f"{d}.parquet", filters=[("line", "in", LINES)])
    if "fleet_flat" in t.column_names: t = t.drop(["fleet_flat", "n_fleet"])
    t = t.filter(pa.array(valid_mask(t)))
    eta = np.asarray(t["observed_eta_s"]); m = (eta >= 180) & (eta < 420)
    t = t.filter(pa.array(m))
    t = t.append_column("day", pa.array([d] * len(t)))
    parts.append(t); print(d, len(t), f"{time.time()-t0:.0f}s", flush=True)
full = pa.concat_tables(parts)
# marca de filas que ya están en el eval congelado
fz = pq.read_table(V4 / "eval/eval_seen.parquet", columns=["line", "ts_p", "shape_id", "dist_along_m", "observed_eta_s"]).to_pandas()
fz = fz[fz.line.isin(LINES)]
key = lambda df: set(zip(df.line, df.ts_p.round(3), df.shape_id, df.dist_along_m.round(2), df.observed_eta_s.round(2)))
fk = key(fz)
df = full.select(["line", "ts_p", "shape_id", "dist_along_m", "observed_eta_s"]).to_pandas()
infz = np.array([k in fk for k in zip(df.line, df.ts_p.round(3), df.shape_id, df.dist_along_m.round(2), df.observed_eta_s.round(2))])
full = full.append_column("in_frozen", pa.array(infz))
pq.write_table(full, OUT / "ext_seen.parquet", row_group_size=100_000)
print("filas", len(full), "en congelado", int(infz.sum()), flush=True)
from prediccion.models.path_eta import predict_path
ck = json.load(open("data/ml/export/path_v4_l1_s1/manifest.json"))["checkpoint"]["path"]
pred = predict_path(OUT / "ext_seen.parquet", Path(ck), len(full))
np.save(OUT / "ext_pred.npy", pred.astype(np.float32))
json.dump({"lines": LINES, "days": days, "n": len(full), "n_in_frozen": int(infz.sum()), "ckpt": ck, "elapsed_s": round(time.time() - t0)},
          open(OUT / "ext_meta.json", "w"), indent=1)
print("listo", f"{time.time()-t0:.0f}s")
