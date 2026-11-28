"""Control de la regla iii: primer arribo = menor ETA entre los coches listados de «viene» y «puede venir» SIN usar el prior (P). Sobre las filas de base."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[4]; sys.path.insert(0, str(ROOT))
from prediccion.replay import metrics as MT
src = ROOT / "data/ml/replay/prior/run"; KEY = ["line", "day", "stop_id", "t"]
I, V = [], []
for f in sorted(src.glob("*.inst.parquet")):
    i = pd.read_parquet(f); v = pd.read_parquet(str(f).replace(".inst.", ".veh."))
    I.append(i[i.variant == "base"]); V.append(v[(v.variant == "base") & v.listed & v.group.isin(["seguro", "puede_venir"])][KEY + ["eta0_s"]])
inst = pd.concat(I, ignore_index=True); veh = pd.concat(V, ignore_index=True)
m = veh.groupby(KEY).eta0_s.min().rename("ctrl").reset_index()
inst = inst.merge(m, on=KEY, how="left"); inst["ann0_ctrl"] = inst.ctrl.fillna(inst.ann0_any_s)
for c in ("ann0_any_s", "ann0_ctrl"):
    r = MT.next_bus(inst, c, 180, 420, corrected=True); w = MT.within_tol(inst, c, (120.0,), 180, 420)
    print(c, round(r["mae_s"], 1), round(r["antes_pct"], 1), round(r["despues_pct"], 1), round(w["dentro_120_con_pct"], 1))
