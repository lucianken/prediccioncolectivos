"""C (paso 1): muestra por dia de filas validas de data/ml/v4/daily + prediccion de path_v4_l1_s1.
Salida: <out>/muestra_dias.parquet (columnas livianas). Prioridad Idle, afinidad 8 nucleos."""
import sys, json, time, os
from pathlib import Path
import numpy as np, pyarrow as pa, pyarrow.parquet as pq
import psutil
p = psutil.Process(); p.nice(psutil.IDLE_PRIORITY_CLASS); p.cpu_affinity(list(range(8)))
sys.path.insert(0, "."); 
import torch; torch.set_num_threads(4)
from prediccion.v2.make_eval import valid_mask
from prediccion.models.path_eta import predict_path
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
V4 = Path("data/ml/v4/daily"); OUT = Path("data/ml/ruido_tramos_feriados"); TMP = OUT / "_tmp"; TMP.mkdir(exist_ok=True)
CK = Path("data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt")
days = sorted(f.name[:10] for f in V4.glob("????-??-??.parquet"))
keep = ["line", "shape_id", "dist_along_m", "dist_remaining_m", "observed_eta_s", "time_since_start", "start_unknown", "speed_mps", "ts_p", "dow"]
parts = []; t0 = time.time()
for d in days:
    t = pq.read_table(V4 / f"{d}.parquet")
    n0 = len(t)
    ok = np.flatnonzero(valid_mask(t))
    rng = np.random.default_rng(int(d.replace("-", "")))
    sel = np.sort(rng.choice(ok, size=min(N, len(ok)), replace=False))
    s = t.take(pa.array(sel))
    tmp = TMP / "s.parquet"; pq.write_table(s, tmp)
    pred = predict_path(tmp, CK, len(s))
    o = s.select(keep).append_column("pred", pa.array(pred.astype(np.float32))).append_column("day", pa.array([d] * len(s)))
    o = o.append_column("n_valid_day", pa.array(np.full(len(s), len(ok), np.int64)))
    parts.append(o); print(d, n0, len(ok), len(s), f"{time.time()-t0:.0f}s", flush=True)
pq.write_table(pa.concat_tables(parts), OUT / "muestra_dias.parquet")
print("listo", f"{time.time()-t0:.0f}s", flush=True)
