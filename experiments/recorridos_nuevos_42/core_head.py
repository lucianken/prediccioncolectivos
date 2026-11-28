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

from red import path_reference as PR
from red import geo_assign as G

# ── parámetros de producción (public/config/prediccion.json y app.js) ────────────────────────────────────────
MAX_PING_AGE_S = 600       # maxPingAgeS: un coche con el último ping más viejo no se predice
HISTORY_S = 900            # ventana de historial local de la app (15 min)
LIST_MAX = 5               # PRED_LIST_MAX
CABA_TS_OFFSET_S = 60.0    # public/prediccion/core.js: se descuenta del ETA anunciado (sello de CABA vs hora real del GPS)
HORIZON_S = 2400           # verdad: 40 min
PASS_MAX_DT_S = 600        # dos pings que encierran la parada deben distar a lo sumo esto para interpolar el paso
VARIANTS = ("base", "sentido", "ramal", "cs")   # cs: parche de producción (filtro de ramal CuandoSubo), ver FILTRO_RAMAL_CS.md
# vara corregida (2026-11-16, VARA_CORREGIDA.md): parámetros de la verdad
GAP_MAX_S = 2400           # un par de pings compatibles separados 10-40 min que encierra la parada = paso "no verificable"
V_MAX_MPS = 25.0           # velocidad media máxima plausible entre dos pings (90 km/h); más es salto de GPS
JUMP_SLACK_M = 50.0        # tolerancia de ruido de GPS en el chequeo de velocidad
END_TOL_M = 50.0           # una parada a menos de esto del final del shape se cruza al llegar a END_TOL_M del final
PAST_MAX_S = 600           # "ya pasó": cruce entre el último ping (<= t) y t
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
        self.geo: dict = {}

    def clear(self):
        for d in (self.project, self.sense, self.eta, self.lb_valid, self.lb_scan, self.geo):
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


def _geo_cached(lat, lon, shapes, *a, **k):
    key = (lat, lon, id(shapes), a, tuple(sorted(k.items())))
    r = MEMO.geo.get(key)
    if r is None:
        r = MEMO.geo[key] = _ORIG["geo"](lat, lon, shapes, *a, **k)
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
    _ORIG.update(project=PR.Shape.project, _sense=PR._sense, eta_on_shapes=PR.eta_on_shapes, last_bus=PR.last_bus,
                 geo=getattr(G, "direction_from_geometry", None))
    if _ORIG["geo"]:
        G.direction_from_geometry = _geo_cached
    PR.Shape.project, PR._sense, PR.eta_on_shapes, PR.last_bus = _project_cached, _sense_cached, _eta_cached, _last_bus_cached
    try:
        yield
    finally:
        PR.Shape.project, PR._sense = _ORIG["project"], _ORIG["_sense"]
        PR.eta_on_shapes, PR.last_bus = _ORIG["eta_on_shapes"], _ORIG["last_bus"]
        if _ORIG["geo"]:
            G.direction_from_geometry = _ORIG["geo"]
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
    eta0 = {vid: r.get("eta0_s", r["eta_s"]) for vid, r in preds.items() if r}   # ETA sin el descuento del corrimiento
    return {"shown": shown, "seguro": sure, "otros": others, "eta0": eta0}


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


def crossings_v2(ts, d, ok, d_stop: float, length_m: float | None = None):
    """
    Cruces de la vara corregida. Devuelve (tc, t0, t1, firm): instante interpolado del cruce, pings que lo encierran y
    si es firme. Cruce = par de pings CONSECUTIVOS ENTRE LOS COMPATIBLES con el shape (se saltean los no compatibles: aceptar
    pings intermedios fuera del shape) con d0 <= d_eff < d1, avance plausible (<= V_MAX_MPS de media más JUMP_SLACK_M) y
      firm  si distan <= PASS_MAX_DT_S: se interpola el instante;
      !firm si distan entre PASS_MAX_DT_S y GAP_MAX_S Y no hay ningún ping entre ellos (hueco de GPS): hubo paso pero no se
            sabe cuándo ("no verificable"). Si el coche transmitió fuera del shape en ese lapso, no hay evidencia de paso.
    d_eff = min(d_stop, largo - END_TOL_M): una parada en el último tramo del shape se cruza al llegar a END_TOL_M del final.
    """
    ts = np.asarray(ts, float)
    d = np.asarray(d, float)
    idx = np.flatnonzero(np.asarray(ok, bool))
    e = np.empty(0)
    if len(idx) < 2:
        return e, e, e, np.empty(0, bool)
    t, dd = ts[idx], d[idx]
    ds = d_stop if length_m is None else min(d_stop, max(length_m - END_TOL_M, 0.0))
    t0, t1, d0, d1 = t[:-1], t[1:], dd[:-1], dd[1:]
    dt = t1 - t0
    adj = np.diff(idx) == 1       # pings contiguos en la serie original (nada grabado entre ellos)
    m = (d0 <= ds) & (ds < d1) & (dt > 0) & (dt <= GAP_MAX_S) & ((d1 - d0) <= V_MAX_MPS * dt + JUMP_SLACK_M)
    m &= (dt <= PASS_MAX_DT_S) | adj   # un hueco de 10-40 min solo es "no verificable" si el coche no transmitió (no si transmitió fuera del shape)
    if not m.any():
        return e, e, e, np.empty(0, bool)
    tc = t0[m] + (ds - d0[m]) / (d1[m] - d0[m]) * dt[m]
    return tc, t0[m], t1[m], dt[m] <= PASS_MAX_DT_S


def merge_crossings(items: list, tol_s: float = 30.0):
    """items: [(tc, t0, t1, firm)] de varios shapes que sirven la parada; une cruces firmes a <= tol_s entre sí (el mismo paso
    visto por dos shapes compatibles). Devuelve (firmes, huecos no verificables)."""
    f = sorted((x for x in items if x[3]), key=lambda x: x[0])
    out = []
    for x in f:
        if out and x[0] - out[-1][0] <= tol_s:
            out[-1] = (out[-1][0], out[-1][1], out[-1][2], True)
        else:
            out.append(x)
    g = sorted((x for x in items if not x[3]), key=lambda x: x[0])
    return out, g


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
    rid: list = field(default_factory=list)     # route_id del feed CABA por ping (solo diagnóstico y variante cs)
    trips: list = field(default_factory=list)   # [(t_first, t_last, shape_id)] ex post, ascendente
    expost: bool = False                        # los viajes ex post se calcularon (load_day): la verdad los usa aunque trips esté vacío

    def true_shape(self, ts: float, wait_max_s: float = 1200.0):
        """Recorrido ex post del viaje en curso a la hora `ts` del ping, o el del próximo viaje si está en espera
        (<= wait_max_s antes de que arranque). None si no hay viaje con recorrido."""
        for a, b, sid in self.trips:
            if a <= ts <= b:
                return sid or None
            if ts < a:
                return (sid or None) if a - ts <= wait_max_s else None
        return None

    def trip_shape_between(self, t0: float, t1: float):
        """Recorrido ex post del viaje que cubre el tramo [t0, t1] (el de mayor solapamiento). None si ningún viaje lo cubre
        o el viaje no tiene recorrido asignado."""
        best, best_ov = None, 0.0
        for a, b, sid in self.trips:
            ov = min(b, t1) - max(a, t0)
            if ov >= 0 and (best is None or ov > best_ov):
                best, best_ov = (sid or None), ov
        return best


@dataclass
class Stop:
    id: str
    name: str
    lat: float
    lon: float
    recorridos: list
    cls: str = ""
    serving: dict = field(default_factory=dict)   # shape_id -> d_stop (m): shapes que sirven la parada por nombre (la app)


def _veh_arrays(vid, obs):
    a = np.array([(o[0], o[1], o[2], o[3]) for o in obs], dtype=np.float64)
    return Veh(vid, a[:, 0], a[:, 1], a[:, 2], a[:, 3], [str(o[10]) if len(o) > 10 and o[10] else "" for o in obs])


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

def _allowed(variant: str, veh: Veh, ts_ping: float, dirs: dict, all_ids: list, cs_only=None):
    """only_shapes para predict_from_raw según la variante; None = sin restricción (ramal desconocido).
    cs: `cs_only` ya viene resuelto (intersección de los shapes de la terna de CuandoSubo con los compatibles del coche)."""
    if variant == "base":
        return None, False
    if variant == "cs":
        return cs_only, False
    sid = veh.true_shape(ts_ping)
    if sid is None or sid not in dirs:
        return None, True               # sin recorrido ex post: sin información extra (cae a producción)
    if variant == "ramal":
        return [sid], False
    return [s for s in all_ids if dirs[s] == dirs[sid]], False


def _expost_filter(v: "Veh", st: "Stop", firm: list, gaps: list, stats: dict | None):
    """Verdad corregida por recorrido (2026-11-16): un cruce cuenta solo si el recorrido ex post del viaje del coche en ese
    tramo (segmentador geo2 + asignación geo3) tiene la parada en su lista (`st.serving`). Un recorrido que no la tiene no para
    ahí: el cruce se descarta (no es paso). Sin viaje ex post con recorrido en el tramo, el cruce firme pasa a "no verificable"
    (se trata como un hueco: sale del denominador de falsas alarmas y del MAE; no se inventa el recorrido). Solo medición."""
    st_ = stats if stats is not None else {}
    for k in ("firmes", "descartados_no_para", "sin_viaje_firmes", "huecos", "huecos_descartados", "huecos_sin_viaje"):
        st_.setdefault(k, 0)
    kept, ngaps = [], []
    st_["firmes"] += len(firm)
    st_["huecos"] += len(gaps)
    for x in firm:
        sid = v.trip_shape_between(x[1], x[2])
        if sid is None:
            st_["sin_viaje_firmes"] += 1
            ngaps.append((x[0], x[1], x[2], False))
        elif sid in st.serving:
            kept.append(x)
        else:
            st_["descartados_no_para"] += 1
    for x in gaps:
        sid = v.trip_shape_between(x[1], x[2])
        if sid is None:
            st_["huecos_sin_viaje"] += 1      # sigue siendo no verificable
        elif sid not in st.serving:
            st_["huecos_descartados"] += 1
            continue
        ngaps.append(x)
    return kept, ngaps


def _passes(vehicles, stops, shapes, compat_cache, stats: dict | None = None, expost: bool | None = None):
    """Verdad por (parada, coche): pasos de la definición anterior (`old`, sin filtro de recorrido) y de la corregida (`new`).
    expost: aplicar el filtro por recorrido ex post del viaje (`_expost_filter`); None = a los coches con viajes ex post
    calculados (`Veh.expost` o `trips` no vacío); los demás (sin segmentación) conservan el cruce por compatibilidad de shape.
    stats: contadores de lo descartado / no verificable por falta de viaje."""
    old, new = {}, {}
    for st in stops:
        for v in vehicles:
            ts_all = []
            for sid, ds in st.serving.items():
                d, ok = compat_cache[(v.vid, sid)]
                ts_all.append(crossing_times(v.ts, d, ok, ds))
            old[(st.id, v.vid)] = np.sort(np.concatenate(ts_all)) if ts_all else np.empty(0)
            items = []
            for sid, ds in st.serving.items():
                d, ok = compat_cache[(v.vid, sid)]
                tc, t0, t1, fm = crossings_v2(v.ts, d, ok, ds, float(shapes[sid].cum[-1]))
                items += [(float(a), float(b), float(c), bool(f)) for a, b, c, f in zip(tc, t0, t1, fm)]
            firm, gaps = merge_crossings(items)
            if (v.expost or bool(v.trips)) if expost is None else expost:
                firm, gaps = _expost_filter(v, st, firm, gaps, stats)
                firm.sort(key=lambda x: x[0])
            new[(st.id, v.vid)] = (np.array([x[0] for x in firm]), np.array([x[1] for x in gaps]), np.array([x[2] for x in gaps]))
    return old, new


def compat_for(vehicles, shapes) -> dict:
    """(coche, shape_id) -> (distancia a lo largo del shape por ping, ping compatible con el shape)."""
    all_ids = list(shapes)
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
    return compat_cache


def truth_at(vehicles, live, passes, passes2, stop_id, t):
    """Verdad en el instante t para una parada: {coche: segundos hasta su próximo paso} anterior (tp) y corregido (tp2),
    {coche: segundos hasta el inicio del hueco no verificable} (unv) y conjunto de coches que ya pasaron entre su último ping y t (past).
    live: {vid: (índice del último ping <= t, ...)}; passes/passes2: salida de `_passes`."""
    tp_by, tp2_by, unv_by, past_by = {}, {}, {}, set()
    for v in vehicles:
        p = passes[(stop_id, v.vid)]
        if len(p):
            k = int(np.searchsorted(p, t, side="right"))   # primer paso estrictamente posterior a t
            if k < len(p) and p[k] - t <= HORIZON_S:
                tp_by[v.vid] = float(p[k] - t)
        tcf, g0, g1 = passes2[(stop_id, v.vid)]
        if len(tcf):
            k = int(np.searchsorted(tcf, t, side="right"))
            if k < len(tcf) and tcf[k] - t <= HORIZON_S:
                tp2_by[v.vid] = float(tcf[k] - t)
            if k > 0 and v.vid in live and tcf[k - 1] > v.ts[live[v.vid][0]] and t - tcf[k - 1] <= PAST_MAX_S:
                past_by.add(v.vid)
        if len(g0) and v.vid not in tp2_by:
            mg = (g1 > t) & (g0 < t + HORIZON_S)
            if mg.any():
                unv_by[v.vid] = float(max(g0[mg].min(), t) - t)
    return tp_by, tp2_by, unv_by, past_by


def evaluate_line(bundle, line: str, vehicles: list[Veh], stops: list[Stop], instants: list[int],
                  variants=VARIANTS, day: str = "", progress=None, ts_offset_s: float = CABA_TS_OFFSET_S,
                  cs_rid: dict | None = None, cs_out: list | None = None, truth_stats: dict | None = None,
                  others_windows: dict | None = None, one_ping: tuple = ()):
    """
    Replay de una línea en un día. Devuelve (rows_veh, rows_inst): listas de dicts.
    rows_veh: un registro por (variante, parada, t, coche) para los coches listados o que cruzan la parada en 40 min.
      tp_s: paso de la definición anterior (cruce estricto, shapes por nombre); tp2_s: paso de la vara corregida (NaN si
      no hay cruce firme en (t, t+40 min]); unv: no verificable (hueco de GPS 10-40 min que encierra la parada, sin cruce firme);
      past: la parada se cruzó entre el último ping (<= t) y t.
    rows_inst: un registro por (variante, parada, t) (real_next_s / n_pass_*: anteriores; *2: corregidos; unv_first_s).
    cs_rid: {route_id: (terna, [shape_ids] | None)} para la variante cs (terna = csRamal que ve la app; shape_ids = los del
      archivo ramal_cuandosubo.json); cs_out recibe un registro por (t, coche con ping vigente) con lo que informa CuandoSubo.
    others_windows: {nombre: ventana_s | None} (experimento HISTORIAL_COCHE_ADELANTE.md; None = comportamiento de siempre). Si se da,
      las variantes son los nombres (todas con la lógica de `base`) y solo cambia el historial de los OTROS coches que recibe
      "coche de adelante" (pings en [t - ventana, t]; ventana None = todo el día hasta t). `others` pasa a ser una lista de
      {"vid","lo","j","t"} que entiende `historial_ca.install_fast_last_bus` (instalarlo antes).
    one_ping: nombres de `others_windows` que simulan la app recién abierta sin servicio (APP_CON_SERVICIO.md): cada coche trae solo
      su último ping, sin historial propio ni de los otros coches. Vacío = comportamiento de siempre.
    Debe llamarse dentro de `with memoized():`.
    """
    shapes = bundle.lines[line]
    all_ids = list(shapes)
    dirs = direction_groups(shapes)
    by_id = {v.vid: v for v in vehicles}
    use_cs = cs_rid is not None
    variants = tuple(v for v in variants if v != "cs" or use_cs)
    if others_windows:
        variants = tuple(others_windows)
    # verdad: pasos por cada parada (todos los coches con pings, estén o no visibles en t)
    compat_cache = compat_for(vehicles, shapes)
    passes, passes2 = _passes(vehicles, stops, shapes, compat_cache, truth_stats)

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
        # hora de la foto: máximo ts de la descarga (la app usa el max ts de los coches de la respuesta)
        snap = max((float(by_id[vid].ts[j]) for vid, (j, _) in live.items()), default=float(t))
        others_by_vid = {vid: {"pings": [(float(by_id[vid].ts[i]), float(by_id[vid].lat[i]), float(by_id[vid].lon[i]))
                                          for i in range(lo, j + 1)]} for vid, (j, lo) in live.items()}
        # variante cs: lo que informa CuandoSubo de cada coche vigente (una vez por t)
        ow_lists = {}
        if others_windows:
            for name, W in others_windows.items():
                lst_o = []
                for v in vehicles:
                    j = int(np.searchsorted(v.ts, t, side="right")) - 1
                    if j < 0:
                        continue
                    if W == "trip":   # viajes ex post del coche sobre cada recorrido, todo el día hasta t (análogo al entrenamiento)
                        lst_o.append({"vid": v.vid, "lo": 0, "j": j, "t": t, "trip": True})
                        continue
                    if W is not None and t - v.ts[j] > W:
                        continue
                    lo = 0 if W is None else int(np.searchsorted(v.ts, t - W, side="left"))
                    if name in one_ping:
                        lo = j
                    lst_o.append({"vid": v.vid, "lo": lo, "j": j, "t": t})
                ow_lists[name] = lst_o
        cs_only, cs_flag = {}, {}
        if use_cs:
            for vid, (j, _) in live.items():
                v = by_id[vid]
                if t - v.ts[j] > MAX_PING_AGE_S:
                    continue
                rid = v.rid[j] if v.rid else ""
                terna, ids = cs_rid.get(rid, (None, None))
                comp = [x[0] for x in G.compatible_shapes(float(v.lat[j]), float(v.lon[j]), shapes)]
                inter = [x for x in ids if x in comp] if ids else []
                true = v.true_shape(float(v.ts[j]))
                cs_only[vid] = inter or None
                cs_flag[vid] = (bool(inter), bool(inter) and true is not None and true not in inter)
                if cs_out is not None:
                    cs_out.append({"line": line, "day": day, "t": t, "vehicle": vid, "route_id": rid, "informado": terna is not None,
                                   "en_tabla": ids is not None, "aplicado": bool(inter), "n_compat": len(comp),
                                   "true_shape": true or "", "true_conocido": true is not None,
                                   "true_en_terna": bool(ids) and true in ids, "true_en_compat": true in comp if true else False,
                                   "true_en_inter": true in inter if true else False, "n_terna": len(ids) if ids else 0})
        for st in stops:
            # verdad por coche
            tp_by, tp2_by, unv_by, past_by = truth_at(vehicles, live, passes, passes2, st.id, t)
            for var in variants:
                preds = {}
                n_fixed = 0
                for vid, (j, lo) in live.items():
                    v = by_id[vid]
                    age = t - v.ts[j]
                    if age > MAX_PING_AGE_S:
                        continue
                    hist = [{"ts": float(v.ts[i]), "lat": float(v.lat[i]), "lon": float(v.lon[i])} for i in range(lo, j)]
                    if var in one_ping:
                        hist = []
                    veh = {"lat": float(v.lat[j]), "lon": float(v.lon[j]), "speed_mps": float(v.speed[j]), "ts": float(v.ts[j])}
                    only, nofix = _allowed("base" if others_windows else var, v, float(v.ts[j]), dirs, all_ids, cs_only.get(vid))
                    n_fixed += nofix
                    if others_windows:
                        others = [o for o in ow_lists[var] if o["vid"] != vid]
                    else:
                        others = [o for ovid, o in others_by_vid.items() if ovid != vid]
                    preds[vid] = PR.predict_from_raw(bundle, line, veh, (st.lat, st.lon), float(t), history=hist,
                                                     others=others, only_shapes=only, user_kind="parada",
                                                     stop_recorridos=st.recorridos, snapshot_ts=snap, ts_offset_s=ts_offset_s)
                lst = build_list(preds)
                shown_ids = {x[0] for x in lst["shown"]}
                grp = {x[0]: x for x in lst["seguro"] + lst["otros"]}
                visible = set(preds)
                for vid in set(shown_ids) | set(tp_by) | set(tp2_by):
                    g = grp.get(vid)
                    cf = cs_flag.get(vid, (False, False)) if var == "cs" else (False, False)
                    rows_veh.append({"variant": var, "line": line, "day": day, "stop_id": st.id, "t": t, "vehicle": vid,
                                     "visible": vid in visible, "group": g[1] if g else "", "eta_s": g[2] if g else np.nan,
                                     "eta0_s": lst["eta0"].get(vid, np.nan) if g else np.nan,
                                     "listed": vid in shown_ids, "tp_s": tp_by.get(vid, np.nan),
                                     "tp2_s": tp2_by.get(vid, np.nan), "unv": vid in unv_by, "past": vid in past_by,
                                     "cs_applied": cf[0], "cs_wrong": cf[1]})
                    if others_windows:   # last_bus_found del candidato que fija el ETA anunciado (-1: sin candidato evaluado)
                        pr_ = preds.get(vid) or {}
                        cd_ = [x for x in pr_.get("candidates", []) if x["shape_id"] == pr_.get("shape_id")]
                        rows_veh[-1]["lbf"] = int(cd_[0]["last_bus_found"]) if cd_ else -1
                first_sure = lst["seguro"][0][2] if lst["seguro"] else np.nan
                first_any = first_sure if lst["seguro"] else (lst["otros"][0][2] if lst["otros"] else np.nan)
                first_sure0 = lst["eta0"][lst["seguro"][0][0]] if lst["seguro"] else np.nan
                first_any0 = first_sure0 if lst["seguro"] else (lst["eta0"][lst["otros"][0][0]] if lst["otros"] else np.nan)
                real = sorted(tp_by.values())
                real2 = sorted(tp2_by.values())
                rows_inst.append({"variant": var, "line": line, "day": day, "stop_id": st.id, "stop_class": st.cls, "t": t,
                                  "n_vehicles": len(preds), "n_shown_status": len(lst["seguro"]) + len(lst["otros"]),
                                  "n_listed": len(lst["shown"]), "has_seguro": bool(lst["seguro"]),
                                  "ann_seguro_s": first_sure, "ann_any_s": first_any,
                                  "ann0_seguro_s": first_sure0, "ann0_any_s": first_any0,
                                  "real_next_s": real[0] if real else np.nan,
                                  "n_pass_10": sum(1 for x in real if x <= 600), "n_pass_20": sum(1 for x in real if x <= 1200),
                                  "real_next2_s": real2[0] if real2 else np.nan,
                                  "n_pass2_10": sum(1 for x in real2 if x <= 600), "n_pass2_20": sum(1 for x in real2 if x <= 1200),
                                  "unv_first_s": min(unv_by.values()) if unv_by else np.nan,
                                  "n_no_info": n_fixed})
        if progress:
            progress(ti + 1, len(instants))
    return rows_veh, rows_inst
