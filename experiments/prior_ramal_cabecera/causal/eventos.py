"""Etapa 1 del prior causal: salidas de cabecera detectadas con pings <= t y ramal revelado por geometria (causal).

Por (dia, linea) de LINES: para cada cabecera multi-ramal (origen de shapes del export path_v4_l1_s1 con >= 2 ramales distintos)
detecta las SALIDAS de los coches con pings, y para cada salida el instante en que el coche revela su ramal. Escribe
{OUT}/{dia}.eventos.parquet. Correr desde 'prediccion colectivos' con Python313:
  python experiments/prior_ramal_cabecera/causal/eventos.py --days a,b --workers 3

Definiciones (todo con pings <= t; ver INFORME.md, "Prior causal"):
  Cabecera C = origen del shape (nombre entre ':' y '->' en `name` del export); centro = media de los primeros puntos de sus shapes.
  Salida (evento) = ping i con dist(C) > R_OUT cuyo ping anterior queda a <= R_OUT, separados <= GAP_MAX_S y con dist(C) <= FAR_M,
    habiendo tenido el coche un ping a <= R_IN de C en los 30 min previos y desde la salida anterior del mismo coche.
    det_ts = ts del ping i (cuando se detecta; el coche pasa a ser "despachado" desde ahi).
  Ramal revelado = primer ping desde i (hasta det_ts + REVEAL_WINDOW_S o la siguiente salida del coche) cuyos shapes compatibles
    (geo_assign: perp <= 45 m y <= minimo de la linea + 20 m) pertenecen a un solo ramal (short_name). Version principal: solo shapes
    con origen C (el coche acaba de salir de C); `_all`: todos los shapes de la linea.
"""
from __future__ import annotations
import argparse, glob, json, re, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
EXPORT = ROOT / "data/ml/export/path_v4_l1_s1/lines"
OUT = ROOT / "data/ml/replay/prior/eventos"
LINES = ["39", "168", "132", "106", "42", "33", "110", "181", "9", "20", "85", "180", "98", "188"]
R_IN, R_OUT, FAR_M, GAP_MAX_S, LOOKBACK_S = 150.0, 250.0, 2500.0, 600.0, 1800.0
REVEAL_WINDOW_S = 6000.0
TOL_M, MARGIN_M = 45.0, 20.0
M = 111_320.0


def origin_of(name: str) -> str:
    return re.split(r"\s*→", name.split(":", 1)[1].strip())[0].strip()


class LineGeo:
    def __init__(self, line: str):
        d = json.load(open(EXPORT / f"{line}.json", encoding="utf8"))
        self.line = line
        sh = d["shapes"]
        pts = [np.asarray(s["points"], float).reshape(-1, 2) for s in sh]
        self.lat0 = float(np.mean([p[:, 0].mean() for p in pts]))
        self.lon0 = float(np.mean([p[:, 1].mean() for p in pts]))
        self.sid = [str(s["id"]) for s in sh]
        self.ramal = [s["short_name"].replace(" ", "") for s in sh]
        self.origin = [origin_of(s["name"]) for s in sh]
        self.trees = []
        for p in pts:
            xy = self.xy(p[:, 0], p[:, 1])
            seg = np.hypot(*np.diff(xy, axis=0).T)
            n = np.maximum(np.ceil(seg / 2.0).astype(int), 1)
            dense = [xy[:1]] + [xy[i] + (xy[i + 1] - xy[i]) * (np.arange(1, k + 1) / k)[:, None] for i, k in enumerate(n)]
            self.trees.append(cKDTree(np.vstack(dense)))
        first = {}
        for i, o in enumerate(self.origin):
            first.setdefault(o, []).append(self.xy(pts[i][:1, 0], pts[i][:1, 1])[0])
        self.cab = {}
        for o in first:
            idx = [i for i, oo in enumerate(self.origin) if oo == o]
            if len({self.ramal[i] for i in idx}) >= 2:
                self.cab[o] = dict(center=np.mean(first[o], axis=0), shapes=idx, ramales=sorted({self.ramal[i] for i in idx}))

    def xy(self, lat, lon):
        return np.column_stack([(np.asarray(lon) - self.lon0) * M * np.cos(np.radians(self.lat0)), (np.asarray(lat) - self.lat0) * M])

    def perp(self, xy):
        """(n, n_shapes) error perpendicular aprox. (shape densificado a 2 m: error <= 1 m)."""
        return np.column_stack([t.query(xy)[0] for t in self.trees])


def detect(g: LineGeo, ts, xy):
    """Salidas de un coche: lista de (cabecera, indice de ping i)."""
    out = []
    for o, c in g.cab.items():
        dist = np.hypot(xy[:, 0] - c["center"][0], xy[:, 1] - c["center"][1])
        near = np.flatnonzero(dist <= R_IN)
        if not len(near):
            continue
        cand = np.flatnonzero((dist[:-1] <= R_OUT) & (dist[1:] > R_OUT) & (ts[1:] - ts[:-1] <= GAP_MAX_S) & (dist[1:] <= FAR_M)) + 1
        last_i = -1
        for i in cand:
            k = np.searchsorted(near, i) - 1
            if k < 0:
                continue
            j = near[k]
            if j <= last_i or ts[i] - ts[j] > LOOKBACK_S:
                continue
            out.append((o, int(i)))
            last_i = int(i)
    return out


def reveal(g: LineGeo, o, ts, xy, i, end_i):
    """[(ts, ramal) con solo shapes de la cabecera, (ts, ramal) con todos]: primer ping en [i, end_i) con un solo ramal compatible."""
    hi = min(int(np.searchsorted(ts, ts[i] + REVEAL_WINDOW_S, side="right")), end_i)
    P = g.perp(xy[i:hi])
    lim = np.minimum(TOL_M, P.min(axis=1) + MARGIN_M)
    comp = P <= lim[:, None]
    res = []
    for restrict in (True, False):
        m = comp.copy()
        if restrict:
            keep = np.zeros(m.shape[1], bool)
            keep[g.cab[o]["shapes"]] = True
            m &= keep
        found = (None, "")
        for r in range(m.shape[0]):
            rs = {g.ramal[k] for k in np.flatnonzero(m[r])}
            if len(rs) == 1:
                found = (float(ts[i + r]), next(iter(rs)))
                break
        res.append(found)
    return res


GEO = {}


def day_events(day: str, lines, data_dir: str, trips_dir: Path):
    from red.label_map import load_label_line_data, resolve_label_line_index
    from prediccion.v2.day import read_day
    li = resolve_label_line_index(load_label_line_data(str(ROOT / "LABEL_LINE_MAP.json")), on_date=day)
    lm = {s: v["line"] for s, v in li.items()}
    vehicles, _, _ = read_day(Path(data_dir) / f"{day}.ndjson.gz", lm, set(lines), None, 30, False)
    trips = pd.read_parquet(trips_dir / f"{day}.trips.parquet", columns=["line", "vehicle_id", "start_ts", "shape_id", "start_unknown"])
    trips = trips[trips.line.isin(lines)]
    rows = []
    for L in lines:
        g = GEO[L]
        if not g.cab:
            continue
        tl = trips[trips.line == L]
        tby = {v: x.sort_values("start_ts") for v, x in tl.groupby("vehicle_id")}
        sid2r = dict(zip(g.sid, g.ramal))
        sid2o = dict(zip(g.sid, g.origin))
        for vid, rec in vehicles.items():
            if not rec["label"] or lm.get(rec["label"].split("-")[-1]) != L or len(rec["obs"]) < 2:
                continue
            a = np.array([(o[0], o[1], o[2]) for o in rec["obs"]], float)
            ts = a[:, 0]
            xy = g.xy(a[:, 1], a[:, 2])
            ev = detect(g, ts, xy)
            ev.sort(key=lambda e: e[1])
            for n, (o, i) in enumerate(ev):
                end_i = ev[n + 1][1] if n + 1 < len(ev) else len(ts)
                (rt, rr), (rta, rra) = reveal(g, o, ts, xy, i, end_i)
                lab, lab_unk = "", True
                t = tby.get(str(vid)) if str(vid) in tby else tby.get(vid)
                if t is not None:
                    m = t[(t.start_ts <= ts[i] + 60) & (t.start_ts >= ts[i] - 900)]
                    m = m[[sid2o.get(str(s)) == o for s in m.shape_id]]
                    if len(m):
                        r = m.iloc[-1]
                        lab = sid2r.get(str(r.shape_id), "")
                        lab_unk = bool(r.start_unknown)
                rows.append(dict(day=day, line=L, cab=o, vid=str(vid), det_ts=float(ts[i]), reveal_ts=rt if rt is not None else np.nan, reveal_ramal=rr,
                                 reveal_ts_all=rta if rta is not None else np.nan, reveal_ramal_all=rra, label=lab, label_start_unknown=lab_unk))
    return pd.DataFrame(rows)


def work(a):
    day, lines, data_dir = a
    f = OUT / f"{day}.eventos.parquet"
    if f.exists():
        return day, 0, 0.0
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00000040)
    except Exception:
        pass
    t0 = time.time()
    for L in lines:
        GEO.setdefault(L, LineGeo(L))
    df = day_events(day, lines, data_dir, ROOT / "data/ml/v4/daily")
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(f)
    return day, len(df), time.time() - t0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default="")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--from", dest="d0", default="2026-07-20")
    ap.add_argument("--to", dest="d1", default="2026-10-14")
    ap.add_argument("--lines", default=",".join(LINES))
    ap.add_argument("--data-dir", default="//192.168.0.18/buffer/grabaciones")
    a = ap.parse_args()
    lines = a.lines.split(",")
    days = a.days.split(",") if a.days else sorted(Path(p).name[:10] for p in glob.glob(str(ROOT / "data/ml/v4/daily/*.trips.parquet")) if a.d0 <= Path(p).name[:10] <= a.d1)
    with ProcessPoolExecutor(a.workers) as ex:
        for day, n, el in ex.map(work, [(d, lines, a.data_dir) for d in days]):
            print(day, n, f"{el:.0f}s", flush=True)
