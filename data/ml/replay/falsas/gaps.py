import sys
from pathlib import Path
ROOT = Path(r"c:\Users\LK\Documents\Dondeestaelbondi\prediccion colectivos")
sys.path.insert(0, str(ROOT))
import numpy as np
from prediccion.replay import run as R
day, ln = sys.argv[1], sys.argv[2]
pl = R.load_day(day, {ln}, "//192.168.0.18/buffer/grabaciones", str(ROOT / "LABEL_LINE_MAP.json"), str(ROOT.parent / "proyectoconsola/data/line_shapes"), with_trips=False)
vs = pl[ln].values()
ev = []
tot = 0
for v in vs:
    g = np.diff(v.ts)
    tot += len(g)
    for i in np.nonzero(g > 600)[0]:
        ev.append((v.ts[i], g[i], v.vid))
print(day, ln, "vehiculos", len(pl[ln]), "pings", tot, "huecos>600s", len(ev), "frac de intervalos", len(ev)/tot)
g = np.array([e[1] for e in ev])
print("pct gaps 10-15,15-30,30-60,>60 min:", [(int(((g>=a*60)&(g<b*60)).sum())) for a,b in [(10,15),(15,30),(30,60),(60,1e9)]])
# cuantos huecos empiezan en la misma ventana de 5 min (globales)
st = np.array([e[0] for e in ev]); en = st + g
import collections
c = collections.Counter(int(x//300) for x in st)
print("ventanas 5 min con >=5 huecos iniciando:", sum(1 for k,v in c.items() if v>=5), "de", len(c))
# huecos con sus 2 extremos cerca de otros coches (outage global): ventanas del dia sin ningun ping de ningun coche > 10 min
allts = np.sort(np.concatenate([v.ts for v in vs]))
ag = np.diff(allts)
print("huecos globales (sin ping de ningun coche) > 5 min:", int((ag>300).sum()), "max min", ag.max()/60)
