"""Tablas por parada y por día (desde 25/11) del replay de la 42. Uso: python experiments/recorridos_nuevos_42/tablas42.py <run_dir>"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from metricas42 import load, DESPUES, M
run = sys.argv[1]
I = {t: load(run, t) for t in ("old", "new")}
meta = pd.read_csv(Path(run) / "paradas.csv", dtype={"stop_id": str}).set_index("stop_id")
def stats(i, v):
    real = i.real_next2_s; unv = M._unverifiable(i, real); p = i[(real <= 600) & ~unv]
    return len(p), i.n_listed.mean(), 100 * (p.n_listed == 0).mean() if len(p) else np.nan
print("| parada | clase | perp al viejo (m) | inst. con paso <=10 min | viejo: coches/inst | viejo: sin lista % | reexport: coches/inst | reexport: sin lista % |\n|---|---|---|---|---|---|---|---|")
for sid, r in meta[meta.cls != "resto"].sort_values(["cls", "name"]).iterrows():
    o = I["old"][0]; n = I["new"][0]
    a = stats(o[(o.stop_id == sid) & o.day.isin(DESPUES)], None); b = stats(n[(n.stop_id == sid) & n.day.isin(DESPUES)], None)
    print(f"| {r['name']} ({sid[-4:]}) | {r['cls']} | {r['snap_perp']:.0f} | {a[0]} | {a[1]:.2f} | {a[2]:.0f} | {b[1]:.2f} | {b[2]:.0f} |")
print()
print("| día | instantes (tramo nuevo, de 15 paradas) | paso <=10 min | viejo sin lista % | reexport sin lista % |\n|---|---|---|---|---|")
for d in DESPUES:
    o = I["old"][0]; n = I["new"][0]
    o = o[(o.day == d) & o.cls.isin(["nueva_fuera", "nueva_cerca"])]; n = n[(n.day == d) & n.cls.isin(["nueva_fuera", "nueva_cerca"])]
    a, b = stats(o, None), stats(n, None)
    print(f"| {d} | {len(o)} | {a[0]} | {a[2]:.0f} | {b[2]:.0f} |")
