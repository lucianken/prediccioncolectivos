"""
Arnés de replay en condiciones de producción (vara de producto).

Para cada (parada, instante t) reconstruye la lista que vería el usuario con la lógica de la app
(`prediccion/inference/path_reference.predict_from_raw` + presentación de `proyectoconsola/public/app.js`:
grupos "pasa seguro" / "pueden venir" / provisionales, orden por ETA, tope de 5) usando solo pings hasta t, y la
compara con la verdad: cuándo cada coche cruza realmente la parada (pings futuros).

Variantes (qué recorridos candidatos se le dan a la referencia para cada coche):
  base      ramal y sentido desconocidos (producción).
  sentido   solo el sentido es conocido (se restringe a los shapes del mismo sentido que el recorrido ex post).
  ramal     oráculo: ramal y sentido verdaderos (el recorrido ex post del viaje en curso).
Todo lo demás (modelo, presentación, historial) es idéntico. Las memoizaciones de este módulo son exactas: las
funciones que envuelven son puras, y los tests comprueban la equivalencia con la original.
"""

from __future__ import annotations

import json
import math
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from prediccion.replay.pinned import path_reference as PR
from prediccion.replay.pinned import geo_assign as G

# ── parámetros de producción (public/config/prediccion.json y app.js) ────────────────────────────────────────
MAX_PING_AGE_S = 600       # maxPingAgeS: un coche con el último ping más viejo no se predice
HISTORY_S = 900            # ventana de historial local de la app (15 min)
LIST_MAX = 5               # PRED_LIST_MAX
HORIZON_S = 2400           # verdad: 40 min
PASS_MAX_DT_S = 600        # dos pings que encierran la parada deben distar a lo sumo esto para interpolar el paso
VARIANTS = ("base", "sentido", "ramal")
SHOWN_STATUS = ("ok", "llegando", "provisional")   # lo que Prediccion.describe muestra; el resto no aparece


# ── memoizaciones exactas ────────────────────────────────────────────────────────────────────────────────────

class _Memo:
    """Caches de una sesión de replay; se vacían al cambiar de día/línea."""

    def __init__(self):
        self.project: dict = {}
        self.sense: dict = {}
        self.eta: dict = {}
        self.lb_valid: dict = {}
        self.lb_scan: dict = {}

    def clear(self):
        for d in (self.project, self.sense, self.eta, self.lb_valid, self.lb_scan):
            d.clear()


MEMO = _Memo()
_ORIG = {}


def _last_bus_cached(c: dict, shape, others: list, d_t: float, ts_ping: float):
    """Igual que `path_reference.last_bus`, con el recorrido por cada otro coche memoizado por (shape, coche, d_t).
    Los dicts de `others` deben ser los mismos objetos entre llamadas del mismo instante (la clave es su id)."""
    best = None
    for o in others:
        kv = (shape.id, id(o))
        v = MEMO.lb_valid.get(kv)
        if v is None:
            pr = [(t, *shape.project(la, lo)) for t, la, lo in o["pings"]]
            pr = [(t, d, p) for t, d, p in pr if p <= G.TOL_M]
            if len(pr) < 2 or G.forward_fraction([x[1] for x in pr], [x[2] for x in pr], G.TOL_M) < G.MIN_FORWARD_FRAC:
                v = False
            else:
                v = pr
            MEMO.lb_valid[kv] = (v, o)  # se guarda o para que su id no se reutilice
        else:
            v = v[0]
        if v is False:
            continue
        ks = (shape.id, id(o), d_t)
        sc = MEMO.lb_scan.get(ks)
        if sc is None:
            tp = None
            for (t0, d0, _), (t1, d1, _) in zip(v[:-1], v[1:]):
                if d1 > d0 and d0 <= d_t < d1:
                    tp = t0 + (d_t - d0) / (d1 - d0) * (t1 - t0)
                    break
            near = [t for t, d, _ in v if abs(d - d_t) <= PR.FALLBACK_M]
            sc = MEMO.lb_scan[ks] = (tp, near)
        tp, near = sc
        if tp is None or tp >= ts_ping:
            nr = [t for t in near if t < ts_ping]
            tp = max(nr) if nr else None
        if tp is not None and tp < ts_ping and (best is None or tp > best):
            best = tp
    if best is None:
        return PR.STATE_FALLBACK_TLB_S, False
    return min(ts_ping - best, c["tlb_cap_s"]), True


def _eta_cached(bundle, line, cands, ts_ping, speed, ts_age, tss=None, start_unknown=True):
    keys = [(line, k["shape"].id, k["d0"], k["rem"], k.get("tlb", PR.STATE_FALLBACK_TLB_S), k.get("lbf", False),
             ts_ping, speed, ts_age, tss, start_unknown) for k in cands]
    miss = [i for i, k in enumerate(keys) if k not in MEMO.eta]
    if miss:
        vals = _ORIG["eta_on_shapes"](bundle, line, [cands[i] for i in miss], ts_ping, speed, ts_age, tss, start_unknown)
        for i, v in zip(miss, vals):
            MEMO.eta[keys[i]] = float(v)
    return np.array([MEMO.eta[k] for k in keys])


def _sense_cached(shape, pings, vehicle):
    key = (shape.id, vehicle["ts"], vehicle["lat"], vehicle["lon"], len(pings), pings[0]["ts"] if pings else None)
    r = MEMO.sense.get(key)
    if r is None:
        r = MEMO.sense[key] = _ORIG["_sense"](shape, pings, vehicle)
    return r


def _project_cached(self, lat, lon):
    key = (id(self), lat, lon)
    r = MEMO.project.get(key)
    if r is None:
        r = MEMO.project[key] = _ORIG["project"](self, lat, lon)
    return r


@contextmanager
def memoized():
    """Instala las memoizaciones en `path_reference` (y las quita al salir). Resultados idénticos a los originales."""
    if _ORIG:
        yield
        return
    _ORIG.update(project=PR.Shape.project, _sense=PR._sense, eta_on_shapes=PR.eta_on_shapes, last_bus=PR.last_bus)
    PR.Shape.project, PR._sense, PR.eta_on_shapes, PR.last_bus = _project_cached, _sense_cached, _eta_cached, _last_bus_cached
    try:
        yield
    finally:
        PR.Shape.project, PR._sense = _ORIG["project"], _ORIG["_sense"]
        PR.eta_on_shapes, PR.last_bus = _ORIG["eta_on_shapes"], _ORIG["last_bus"]
        _ORIG.clear()
        MEMO.clear()


# ── presentación de la lista (app.js: renderPredList + Prediccion.describe) ────────────────────────────────

def build_list(preds: dict) -> dict:
    """
    preds: {vehicle_id: resultado de predict_from_raw}. Devuelve la lista que ve el usuario:
      shown: [(vehicle_id, grupo, eta_s)] en el orden de pantalla (seguros por ETA, luego pueden venir + provisionales
             por ETA hasta completar LIST_MAX en total); grupo en {"seguro", "puede_venir", "provisional"}.
      seguro / otros: todos los seguros y todos los de "pueden venir"/provisionales (sin tope), ordenados por ETA.
    Solo se muestran los coches con status ok / llegando / provisional (lo que describe() no oculta).
    """
    sure, others = [], []
    for vid, r in preds.items():
        if not r or r.get("status") not in SHOWN_STATUS or r.get("eta_s") is None:
            continue
        g = r.get("group")
        if g == "seguro":
            sure.append((vid, "seguro", r["eta_s"]))
        elif g in ("puede_venir", "provisional"):
            others.append((vid, g, r["eta_s"]))
    sure.sort(key=lambda x: x[2])
    others.sort(key=lambda x: x[2])
    shown = sure[:LIST_MAX]
    shown = shown + others[:LIST_MAX - len(shown)]
    return {"shown": shown, "seguro": sure, "otros": others}


# ── verdad: pasos por la parada ──────────────────────────────────────────────────────────────────────────────

def crossing_times(ts, d, ok, d_stop: float) -> np.ndarray:
    """
    Instantes (ascendentes) en que un coche cruza la posición `d_stop` (metros desde el inicio de un shape) hacia
    adelante. ts, d: pings en orden cronológico y su distancia a lo largo del shape; ok: el ping es compatible con el shape
    (geo_assign). Un cruce es un par de pings consecutivos compatibles con d0 <= d_stop < d1 que distan a lo sumo
    PASS_MAX_DT_S y G.STEP_JUMP_M; el instante se interpola linealmente.
    """
    ts = np.asarray(ts, float)
    d = np.asarray(d, float)
    ok = np.asarray(ok, bool)
    if len(ts) < 2:
        return np.empty(0)
    d0, d1, t0, t1 = d[:-1], d[1:], ts[:-1], ts[1:]
    m = ok[:-1] & ok[1:] & (d0 <= d_stop) & (d_stop < d1) & ((t1 - t0) <= PASS_MAX_DT_S) & ((d1 - d0) <= G.STEP_JUMP_M)
    if not m.any():
        return np.empty(0)
    return t0[m] + (d_stop - d0[m]) / (d1[m] - d0[m]) * (t1[m] - t0[m])


def direction_groups(shapes: dict, radius_m: float = 400.0) -> dict[str, int]:
    """Sentido de cada shape: shapes cuyo primer punto está a <= radius_m entre sí comparten sentido (misma cabecera de salida)."""
    ids = list(shapes)
    grp: dict[str, int] = {}
    reps: list[tuple[float, float]] = []
    for sid in ids:
        la, lo = shapes[sid].pts[0]
        for gi, (rl, ro) in enumerate(reps):
            dy = (la - rl) * 111_320.0
            dx = (lo - ro) * 111_320.0 * math.cos(math.radians(la))
            if math.hypot(dx, dy) <= radius_m:
                grp[sid] = gi
                break
        else:
            reps.append((la, lo))
            grp[sid] = len(reps) - 1
    return grp


def classify_stop(serving: list[str], dirs: dict[str, int]) -> str:
    """
    Tipo de parada según cuántos shapes del mismo sentido la sirven:
      "unico"       el sentido tiene un solo shape (no hay ramal que desambiguar),
      "compartido"  la sirven >= 2 shapes del mismo sentido (tronco compartido),
      "exclusivo"   la sirve 1 shape, habiendo otros shapes en su sentido (tramo exclusivo de un ramal).
    """
    per_dir: dict[int, int] = {}
    for s in serving:
        per_dir[dirs[s]] = per_dir.get(dirs[s], 0) + 1
    if not per_dir:
        return "unico"
    g, n = max(per_dir.items(), key=lambda kv: kv[1])
    n_dir = sum(1 for s, gi in dirs.items() if gi == g)
    if n_dir <= 1:
        return "unico"
    return "compartido" if n >= 2 else "exclusivo"


# ── estado por línea y día ───────────────────────────────────────────────────────────────────────────────────

@dataclass
class Veh:
    vid: str
    ts: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    speed: np.ndarray
    trips: list = field(default_factory=list)   # [(t_first, t_last, shape_id)] ex post, ascendente

    def true_shape(self, ts: float, wait_max_s: float = 1200.0):
        """Recorrido ex post del viaje en curso a la hora `ts` del ping, o el del próximo viaje si está en espera
        (<= wait_max_s antes de que arranque). None si no hay viaje con recorrido."""
        for a, b, sid in self.trips:
            if a <= ts <= b:
                return sid or None
            if ts < a:
                return (sid or None) if a - ts <= wait_max_s else None
        return None


@dataclass
class Stop:
    id: str
    name: str
    lat: float
    lon: float
    recorridos: list
    cls: str = ""
    serving: dict = field(default_factory=dict)   # shape_id -> d_stop (m)


def _veh_arrays(vid, obs):
    a = np.array([(o[0], o[1], o[2], o[3]) for o in obs], dtype=np.float64)
    return Veh(vid, a[:, 0], a[:, 1], a[:, 2], a[:, 3])


def prepare_stops(bundle, line: str, line_shapes_dir, per_line: int = 40, seed: int = 0) -> list[Stop]:
    """
    Paradas de `ramales[].stops` (proyectoconsola/data/line_shapes/{line}.json), unidas por id; recorridos = nombres de los
    ramales que la contienen (igual que la app). Se descartan las que quedan a < 300 m del inicio de todos sus shapes (nadie
    las cruza desde antes). Muestreo estratificado: mitad compartidas y mitad exclusivas (o únicas si la línea no tiene
    ramales), parejo a lo largo de la línea.
    """
    d = json.loads((Path(line_shapes_dir) / f"{line}.json").read_text(encoding="utf-8"))
    by_id: dict[str, Stop] = {}
    for r in d.get("ramales", []):
        for s in r.get("stops", []):
            st = by_id.setdefault(s["id"], Stop(s["id"], s.get("name", ""), s["lat"], s["lng"], []))
            if r["name"] not in st.recorridos:
                st.recorridos.append(r["name"])
    shapes = bundle.lines[line]
    dirs = direction_groups(shapes)
    out = []
    for st in by_id.values():
        us = PR.user_shapes(bundle, line, (st.lat, st.lon), "parada", st.recorridos)
        st.serving = {sid: shapes[sid].project(st.lat, st.lon)[0] for sid, (ok, _) in us.items() if ok}
        if not st.serving or max(st.serving.values()) < 300.0:
            continue
        st.cls = classify_stop(list(st.serving), dirs)
        out.append(st)
    out.sort(key=lambda s: (s.id))
    rng = np.random.default_rng(seed)
    cls_order = ["compartido", "exclusivo", "unico"]
    pools = {c: [s for s in out if s.cls == c] for c in cls_order}
    want = per_line
    if pools["unico"] and not (pools["compartido"] or pools["exclusivo"]):
        quotas = {"unico": want, "compartido": 0, "exclusivo": 0}
    else:
        half = want // 2
        quotas = {"compartido": min(half, len(pools["compartido"])), "exclusivo": min(want - half, len(pools["exclusivo"])), "unico": 0}
        rest = want - quotas["compartido"] - quotas["exclusivo"]
        for c in ("compartido", "exclusivo", "unico"):
            extra = min(rest, len(pools[c]) - quotas[c])
            quotas[c] += extra
            rest -= extra
    chosen = []
    for c in cls_order:
        p = pools[c]
        k = quotas[c]
        if k <= 0 or not p:
            continue
        idx = np.unique(np.round(np.linspace(0, len(p) - 1, k)).astype(int)) if k < len(p) else np.arange(len(p))
        chosen += [p[i] for i in idx]
    _ = rng
    return sorted(chosen, key=lambda s: s.id)


def instants_for_day(day: str, start_h: int = 6, end_h: int = 23, step_min: int = 10) -> list[int]:
    """Instantes unix (s) de `day` en hora de Buenos Aires (UTC-3 fijo), cada `step_min` entre start_h y end_h inclusive."""
    from datetime import datetime, timezone
    base = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) + 3 * 3600
    return [base + h * 3600 + m * 60 for h in range(start_h, end_h + 1) for m in range(0, 60, step_min)
            if h * 60 + m <= end_h * 60]


# ── evaluación ───────────────────────────────────────────────────────────────────────────────────────────────

def _allowed(variant: str, veh: Veh, ts_ping: float, dirs: dict, all_ids: list):
    """only_shapes para predict_from_raw según la variante; None = sin restricción (ramal desconocido)."""
    if variant == "base":
        return None, False
    sid = veh.true_shape(ts_ping)
    if sid is None or sid not in dirs:
        return None, True               # sin recorrido ex post: sin información extra (cae a producción)
    if variant == "ramal":
        return [sid], False
    return [s for s in all_ids if dirs[s] == dirs[sid]], False


def evaluate_line(bundle, line: str, vehicles: list[Veh], stops: list[Stop], instants: list[int],
                  variants=VARIANTS, day: str = "", progress=None):
    """
    Replay de una línea en un día. Devuelve (rows_veh, rows_inst): listas de dicts.
    rows_veh: un registro por (variante, parada, t, coche) para los coches listados o que cruzan la parada en 40 min.
    rows_inst: un registro por (variante, parada, t).
    Debe llamarse dentro de `with memoized():`.
    """
    shapes = bundle.lines[line]
    all_ids = list(shapes)
    dirs = direction_groups(shapes)
    by_id = {v.vid: v for v in vehicles}
    # verdad: pasos por cada parada (todos los coches con pings, estén o no visibles en t)
    compat_cache: dict[tuple[str, str], tuple] = {}
    for v in vehicles:
        n = len(v.ts)
        perp = np.empty((len(all_ids), n))
        dist = np.empty((len(all_ids), n))
        for k, sid in enumerate(all_ids):
            sh = shapes[sid]
            for i in range(n):
                dist[k, i], perp[k, i] = sh.project(float(v.lat[i]), float(v.lon[i]))
        lim = G.compat_limit(perp.min(axis=0))
        for k, sid in enumerate(all_ids):
            compat_cache[(v.vid, sid)] = (dist[k], perp[k] <= lim)
    passes: dict[tuple[str, str], np.ndarray] = {}
    for st in stops:
        for v in vehicles:
            ts_all = []
            for sid, ds in st.serving.items():
                d, ok = compat_cache[(v.vid, sid)]
                ts_all.append(crossing_times(v.ts, d, ok, ds))
            passes[(st.id, v.vid)] = np.sort(np.concatenate(ts_all)) if ts_all else np.empty(0)

    rows_veh, rows_inst = [], []
    for ti, t in enumerate(instants):
        # estado causal en t: coches con ping <= t; historial de 15 min
        live = {}
        for v in vehicles:
            j = int(np.searchsorted(v.ts, t, side="right")) - 1
            if j < 0 or t - v.ts[j] > HISTORY_S:
                continue
            lo = int(np.searchsorted(v.ts, t - HISTORY_S, side="left"))
            live[v.vid] = (j, lo)
        others_by_vid = {vid: {"pings": [(float(by_id[vid].ts[i]), float(by_id[vid].lat[i]), float(by_id[vid].lon[i]))
                                          for i in range(lo, j + 1)]} for vid, (j, lo) in live.items()}
        for st in stops:
            # verdad por coche
            tp_by = {}
            for v in vehicles:
                p = passes[(st.id, v.vid)]
                if len(p):
                    k = int(np.searchsorted(p, t, side="right"))   # primer paso estrictamente posterior a t
                    if k < len(p) and p[k] - t <= HORIZON_S:
                        tp_by[v.vid] = float(p[k] - t)
            for var in variants:
                preds = {}
                n_fixed = 0
                for vid, (j, lo) in live.items():
                    v = by_id[vid]
                    age = t - v.ts[j]
                    if age > MAX_PING_AGE_S:
                        continue
                    hist = [{"ts": float(v.ts[i]), "lat": float(v.lat[i]), "lon": float(v.lon[i])} for i in range(lo, j)]
                    veh = {"lat": float(v.lat[j]), "lon": float(v.lon[j]), "speed_mps": float(v.speed[j]), "ts": float(v.ts[j])}
                    only, nofix = _allowed(var, v, float(v.ts[j]), dirs, all_ids)
                    n_fixed += nofix
                    others = [o for ovid, o in others_by_vid.items() if ovid != vid]
                    preds[vid] = PR.predict_from_raw(bundle, line, veh, (st.lat, st.lon), float(t), history=hist,
                                                     others=others, only_shapes=only, user_kind="parada",
                                                     stop_recorridos=st.recorridos)
                lst = build_list(preds)
                shown_ids = {x[0] for x in lst["shown"]}
                grp = {x[0]: x for x in lst["seguro"] + lst["otros"]}
                visible = set(preds)
                for vid in set(shown_ids) | set(tp_by):
                    g = grp.get(vid)
                    rows_veh.append({"variant": var, "line": line, "day": day, "stop_id": st.id, "t": t, "vehicle": vid,
                                     "visible": vid in visible, "group": g[1] if g else "", "eta_s": g[2] if g else np.nan,
                                     "listed": vid in shown_ids, "tp_s": tp_by.get(vid, np.nan)})
                first_sure = lst["seguro"][0][2] if lst["seguro"] else np.nan
                first_any = first_sure if lst["seguro"] else (lst["otros"][0][2] if lst["otros"] else np.nan)
                real = sorted(tp_by.values())
                rows_inst.append({"variant": var, "line": line, "day": day, "stop_id": st.id, "stop_class": st.cls, "t": t,
                                  "n_vehicles": len(preds), "n_shown_status": len(lst["seguro"]) + len(lst["otros"]),
                                  "n_listed": len(lst["shown"]), "has_seguro": bool(lst["seguro"]),
                                  "ann_seguro_s": first_sure, "ann_any_s": first_any,
                                  "real_next_s": real[0] if real else np.nan,
                                  "n_pass_10": sum(1 for x in real if x <= 600), "n_pass_20": sum(1 for x in real if x <= 1200),
                                  "n_no_info": n_fixed})
        if progress:
            progress(ti + 1, len(instants))
    return rows_veh, rows_inst
