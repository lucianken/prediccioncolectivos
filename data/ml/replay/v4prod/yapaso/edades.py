"""Paso 2 de YA_PASO: edad del ultimo ping (s) de cada (linea, dia, coche, t) listado con eta0 <= 300 s, leida de los pings grabados
(misma regla que porcoche/calcula.py::ping_meta, que se importa sin modificar). Salida: edades.parquet."""
import ctypes, sys, time, importlib.util
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pandas as pd
ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x40)
ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data/ml/replay/porcoche"))
import calcula
if __name__ == "__main__":
    d = pd.read_parquet(HERE / "listados_eta900.parquet", columns=["line", "day", "vehicle", "t", "eta0_s"])
    d = d[d.eta0_s <= 300][["line", "day", "vehicle", "t"]].drop_duplicates()
    jobs = [(day, sorted(g.line.unique()), g[["line", "vehicle", "t"]].reset_index(drop=True)) for day, g in d.groupby("day")]
    t0 = time.time(); out = []
    with ProcessPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 2) as ex:
        for m in ex.map(calcula.ping_meta, jobs):
            out.append(m); print(m.day.iloc[0], len(m), f"{time.time()-t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(HERE / "edades.parquet")
    print("hecho")
