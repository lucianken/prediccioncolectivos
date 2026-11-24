"""Paso 1 de YA_PASO: extrae de los crudos v4 las filas listadas (una por coche listado en cada (linea, dia, parada, t)) con
eta0 <= 900 s a un parquet liviano para calibrar P(paso). No modifica nada del replay. Uso (desde prediccion colectivos/): python .../extrae.py"""
import ctypes, json, sys
from pathlib import Path
import pandas as pd
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x40)
try:
    import psutil; psutil.Process().cpu_affinity(list(range(8)))
except Exception: pass
ROOT = Path(__file__).resolve().parents[5]
SRC = ROOT / "data/ml/replay/v4prod/v4"
OUT = Path(__file__).resolve().parent
cfg = json.load(open(ROOT.parent / "proyectoconsola/public/config/prediccion.json", encoding="utf-8"))
LINES = [e["line"] for e in cfg["enabledLines"]]
print(len(LINES), "lineas habilitadas")
parts = []
for ln in LINES:
    for p in sorted(SRC.glob(f"*_{ln}.veh.parquet")):
        v = pd.read_parquet(p, columns=["variant", "line", "day", "stop_id", "t", "vehicle", "group", "eta_s", "eta0_s", "listed", "tp2_s", "unv", "past"])
        v = v[(v.variant == "base") & v.listed & (v.eta0_s <= 900)].drop(columns=["variant", "listed"])
        parts.append(v.drop_duplicates(["line", "day", "stop_id", "t", "vehicle"]))
    print(ln, flush=True)
df = pd.concat(parts, ignore_index=True)
df.to_parquet(OUT / "listados_eta900.parquet")
print(len(df), df.past.mean(), (df.eta_s == 0).mean())
