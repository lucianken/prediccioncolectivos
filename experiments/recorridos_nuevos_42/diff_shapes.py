"""Diferencias entre el export congelado (path_v4_l1_s1) y los line_shapes actuales de proyectoconsola (solo lectura).
Viejo = points del export (+ paradas de git fec1e65 de proyectoconsola, mismo recorrido que el export).
Salida: data/ml/replay/recorridos_nuevos_42/diff_lineas.json  y  diff_42.json"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
ROOT = Path(__file__).resolve().parents[2]
PC = ROOT.parent / "proyectoconsola"
EXP = ROOT / "data/ml/export/path_v4_l1_s1"
OUT = ROOT / "data/ml/replay/recorridos_nuevos_42"
T = 45.0
LAT0 = -34.6
KX = 111320.0 * np.cos(np.radians(LAT0)); KY = 111320.0

def xy(latlon):
    a = np.asarray(latlon, float).reshape(-1, 2)
    return np.stack([a[:, 1] * KX, a[:, 0] * KY], 1)

def densify(pts, step):
    p = xy(pts); out = [p[:1]]
    for a, b in zip(p[:-1], p[1:]):
        n = max(1, int(np.ceil(np.hypot(*(b - a)) / step)))
        out.append(a + (b - a) * (np.arange(1, n + 1) / n)[:, None])
    return np.concatenate(out)

def far_km(src_pts_list, tree_pts, thr=T, step=10.0):
    """km de las polilíneas src a > thr de tree_pts; devuelve (km, lista de (x,y) lejanos)."""
    tree = cKDTree(tree_pts); km = 0.0; far = []
    for pts in src_pts_list:
        d = densify(pts, step)
        dist, _ = tree.query(d)
        seg = np.hypot(*np.diff(d, axis=0).T)
        f = (dist[:-1] > thr) & (dist[1:] > thr)
        km += seg[f].sum() / 1000; far.append(d[:-1][f])
    return km, (np.concatenate(far) if far else np.zeros((0, 2)))

def old_lines_stops(ln):
    r = subprocess.run(["git", "-C", str(PC), "show", f"fec1e65:data/line_shapes/{ln}.json"], capture_output=True)
    if r.returncode: return {}
    d = json.loads(r.stdout.decode("utf-8"))
    return {str(x["shapeId"]): x for x in d["ramales"]}

def main():
    man = json.loads((EXP / "manifest.json").read_text())
    res = {}; det42 = None
    for ln in man["lines"]:
        e = json.loads((EXP / "lines" / f"{ln}.json").read_text())
        old = {s["id"]: s for s in e["shapes"]}
        nd = json.loads((PC / "data/line_shapes" / f"{ln}.json").read_text(encoding="utf-8"))
        new = {str(r["shapeId"]): r for r in nd["ramales"] if r.get("shapeId") is not None and len(r.get("points", [])) >= 2}
        oldpts = [np.array(s["points"]).reshape(-1, 2) for s in old.values()]
        newpts = [np.array(r["points"]) for r in new.values()]
        old_all = np.concatenate([densify(p, 5.0) for p in oldpts])
        new_all = np.concatenate([densify(p, 5.0) for p in newpts]) if newpts else np.zeros((0, 2))
        km_new, far_new = far_km(newpts, old_all) if newpts else (0, np.zeros((0, 2)))
        km_gone, far_gone = far_km(oldpts, new_all) if len(new_all) else (sum(s["length_m"] for s in old.values()) / 1000, np.zeros((0, 2)))
        # por shape
        per = {}
        for sid, r in new.items():
            k, _ = far_km([np.array(r["points"])], old_all)
            lo = old.get(sid)
            kk, _ = far_km([np.array(r["points"])], densify(np.array(lo["points"]).reshape(-1, 2), 5.0)) if lo else (None, None)
            per[sid] = dict(name=r.get("name"), en_export=lo is not None, km_nuevo_vs_todo_viejo=round(k, 3),
                            km_nuevo_vs_mismo_shape=None if kk is None else round(kk, 3),
                            n_paradas=len(r.get("stops", [])), n_paradas_viejo=None if lo is None else len(lo["stops_m"]))
        # paradas
        ostops = old_lines_stops(ln)
        os_ll = np.array([[s["lat"], s["lng"]] for x in ostops.values() for s in x.get("stops", [])]).reshape(-1, 2)
        ns = {}
        for r in new.values():
            for s in r.get("stops", []): ns[(round(s["lat"], 6), round(s["lng"], 6))] = s
        ns_ll = np.array(list(ns.keys())).reshape(-1, 2)
        ost = {(round(s["lat"], 6), round(s["lng"], 6)): s for x in ostops.values() for s in x.get("stops", [])}
        os_ll = np.array(list(ost.keys())).reshape(-1, 2)
        def unmatched(a, b, thr):
            if len(a) == 0: return np.zeros(0, bool)
            if len(b) == 0: return np.ones(len(a), bool)
            return cKDTree(xy(b)).query(xy(a))[0] > thr
        p_new = unmatched(ns_ll, os_ll, 25.0)
        p_gone = unmatched(os_ll, ns_ll, 25.0)
        p_new_far = (cKDTree(old_all).query(xy(ns_ll))[0] > T) if len(ns_ll) else np.zeros(0, bool)
        res[ln] = dict(shapes_export=sorted(old), shapes_nuevo=sorted(new), shapes_nuevos=sorted(set(new) - set(old)),
                       shapes_fuera=sorted(set(old) - set(new)), km_nuevo_gt45=round(km_new, 3), km_viejo_gt45_de_lo_nuevo=round(km_gone, 3),
                       km_total_nuevo=round(sum(float(np.hypot(*np.diff(xy(p), axis=0).T).sum()) for p in newpts) / 1000, 1),
                       paradas_nuevas=int(p_new.sum()), paradas_desaparecidas=int(p_gone.sum()), paradas_nuevas_gt45=int(p_new_far.sum()),
                       n_paradas_nuevo=len(ns_ll), n_paradas_viejo=len(os_ll), por_shape=per)
        if ln == "42":
            inv = lambda d: [[round(y / KY, 6), round(x / KX, 6)] for x, y in d]
            det42 = dict(far_new=inv(far_new[::5]), far_gone=inv(far_gone[::5]),
                         stops_new=[list(k) + [ns[k].get("name")] for k, f in zip(ns, p_new) if f],
                         stops_gone=[list(k) + [ost[k].get("name")] for k, f in zip(ost, p_gone) if f],
                         stops_new_gt45=[list(k) + [ns[k].get("name")] for k, f in zip(ns, p_new_far) if f])
        print(ln, res[ln]["km_nuevo_gt45"], res[ln]["paradas_nuevas"], flush=True)
    (OUT / "diff_lineas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "diff_42.json").write_text(json.dumps(det42, ensure_ascii=False, indent=1), encoding="utf-8")
if __name__ == "__main__":
    main()
