"""Métricas de producto del replay por línea (viejo vs reexport), desde el 25/11, por clase de parada (nuevas lejos/cerca del
recorrido viejo, resto) y total. Reusa metricas42 (misma métrica y bootstrap por cluster parada x 30 min).
  python -m experiments.recorridos_nuevos_lineas.metricas_lineas <run_dir> 84,7,... [B]"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parents[1] / "recorridos_nuevos_42"))
import metricas42 as M42

def main():
    run, lines = Path(sys.argv[1]), sys.argv[2].split(","); B = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    out = []
    for ln in lines:
        for tag, nombre in (("old", "viejo"), ("new", "reexport")):
            try:
                inst, veh = M42.load(run / ln, tag)
            except Exception as e:
                print(ln, tag, "sin datos", e); continue
            for grp, cl in (("todas", None), ("nuevas (lejos+cerca)", ["nueva_fuera", "nueva_cerca"]), ("  lejos >45 m", ["nueva_fuera"]),
                            ("  cerca <=45 m", ["nueva_cerca"]), ("resto", ["resto"])):
                i = inst if cl is None else inst[inst.cls.isin(cl)]
                v = veh if cl is None else veh[veh.cls.isin(cl)]
                i, v = i.reset_index(drop=True), v.reset_index(drop=True)
                if not len(i): continue
                r = M42.one(i, v); ci = M42.boot(i, v, B)
                out.append(dict(line=ln, bundle=nombre, grupo=grp, n_stops=int(i.stop_id.nunique()), **r, ci=ci))
    (run / "metricas.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    f = lambda x, nd=1: "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"
    for r in out:
        c = r["ci"]; g = lambda k, nd=1: f"{f(r[k], nd)} [{f(c[k][0], nd)}, {f(c[k][1], nd)}]" if k in c else f(r[k], nd)
        print(f"{r['line']:>4s} {r['bundle']:8s} {r['grupo']:22s} par={r['n_stops']:3d} inst={r['n_inst']:5d} paso10={r['n_paso10']:5d} list/inst={g('listados_x_inst',2)} "
              f"sinlista={g('sin_lista_pct')} noanun={g('no_anunciado_pct')} (n={r['n_pasan10']}) fant={g('fantasma_pct')} (n={r['n_listados_eval']}) "
              f"mae37={g('mae_3_7_s',0)} (n={r['n_3_7']})")
main()
