"""
Implementación de referencia (numpy) de la inferencia del modelo por tramos desde datos crudos de producción.
Es la especificación ejecutable del cliente JS (INFERENCIA_PATH.md). Solo lee el directorio de exportación
(manifest.json, lines/*.json, path_eta.onnx); no importa nada del entrenamiento. La red corre con onnxruntime,
igual que en el navegador.

  predict_from_raw(bundle, line, vehicle, user, now_ts, history=..., others=...) -> dict

La línea sale solo del sufijo del label (LABEL_LINE_MAP); aquí entra ya resuelta. Nunca route_id/trip_id/start_time.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

STATE_FALLBACK_TLB_S = 3600.0
FALLBACK_M = 250.0       # radio del fallback de "coche de adelante" (ping más cercano a T)

# Reglas de candidatos (contrato 1.1, INFERENCIA_PATH.md §4). No viven en el manifest: son del cliente.
MIN_NET_FORWARD_M = 40.0        # avance neto mínimo del coche sobre el shape para dar por conocido su sentido
POINT_MAX_PERP_M = 40.0         # punto GPS / tocado en el mapa: distancia máxima a un shape para que "pase por ahí"
POINT_PARALLEL_MARGIN_M = 15.0  # entre los shapes que pasan, se conservan los de perp <= mínima + este margen
STOP_FALLBACK_PERP_M = 25.0     # parada sin recorridos asociados por nombre: se asocia al shape a <= esta distancia


# ── carga ────────────────────────────────────────────────────────────────────

class Shape:
    """Recorrido: puntos, distancia acumulada (ángulo pequeño, igual que el entrenamiento) y celdas de 250 m."""

    def __init__(self, d: dict, m_per_deg_lat: float):
        pts = np.asarray(d["points"], dtype=np.float64).reshape(-1, 2)
        self.id, self.name, self.length_m = d["id"], d.get("name", ""), d["length_m"]
        self.short_name = d.get("short_name", "")
        self.pts = pts
        self.cells = np.asarray(d["cells"], dtype=np.float64).reshape(-1, 2)
        lat_mid = (pts[:-1, 0] + pts[1:, 0]) / 2.0
        self.mlon = m_per_deg_lat * np.cos(np.radians(lat_mid))
        self.ab_y = (pts[1:, 0] - pts[:-1, 0]) * m_per_deg_lat
        self.ab_x = (pts[1:, 1] - pts[:-1, 1]) * self.mlon
        self.ab_dot = self.ab_x ** 2 + self.ab_y ** 2
        self.seg_len = np.sqrt(self.ab_dot)
        self.cum = np.concatenate([[0.0], np.cumsum(self.seg_len)])
        self.valid = self.ab_dot > 1e-9
        self.mpd = m_per_deg_lat

    def project(self, lat: float, lon: float) -> tuple[float, float]:
        """(metros desde el inicio del shape, error perpendicular en metros) sobre el segmento más cercano."""
        p = self.pts
        ap_y = (lat - p[:-1, 0]) * self.mpd
        ap_x = (lon - p[:-1, 1]) * self.mlon
        t = np.where(self.valid, (ap_x * self.ab_x + ap_y * self.ab_y) / np.where(self.valid, self.ab_dot, 1.0), 0.0)
        t = np.clip(t, 0.0, 1.0)
        dy = ap_y - t * self.ab_y
        dx = ap_x - t * self.ab_x
        perp = np.sqrt(dx * dx + dy * dy)
        i = int(np.argmin(perp))
        return float(self.cum[i] + t[i] * self.seg_len[i]), float(perp[i])

    def latlon_at(self, d: float) -> tuple[float, float]:
        return float(np.interp(d, self.cum, self.pts[:, 0])), float(np.interp(d, self.cum, self.pts[:, 1]))


@dataclass
class Bundle:
    root: Path
    manifest: dict
    lines: dict            # línea -> {shape_id: Shape}
    _session: object = None

    @property
    def const(self) -> dict:
        return self.manifest["constants"]

    @property
    def session(self):
        if self._session is None:
            import onnxruntime as ort
            self._session = ort.InferenceSession(str(self.root / "path_eta.onnx"), providers=["CPUExecutionProvider"])
        return self._session


def load_bundle(root) -> Bundle:
    root = Path(root)
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    mpd = man["constants"]["m_per_deg_lat"]
    lines = {}
    for ln in man["lines"]:
        d = json.loads((root / "lines" / f"{ln}.json").read_text(encoding="utf-8"))
        lines[ln] = {s["id"]: Shape(s, mpd) for s in d["shapes"]}
    return Bundle(root, man, lines)


# ── tiempo y estado ──────────────────────────────────────────────────────────

def encode_time(ts: float) -> tuple[float, float, int]:
    """(hour_sin, hour_cos, dow) en hora de Buenos Aires (UTC-3 fijo), dow 0 = lunes; ts = hora del PING."""
    local = float(ts) - 3 * 3600
    sec = local % 86400
    ang = 2.0 * math.pi * (sec / 3600.0) / 24.0
    return math.sin(ang), math.cos(ang), int((local // 86400 + 3) % 7)


def state_vector(c: dict, speed, ts_age, tss, d0, tlb, lbf, rem, start_unknown=True) -> np.ndarray:
    """Los 9 componentes que recibe el ONNX (ver manifest.onnx.state_columns). tss NaN/None cuenta como 0."""
    speed = float(speed or 0.0)
    ts_age = float(ts_age or 0.0)
    tss = 0.0 if tss is None or (isinstance(tss, float) and math.isnan(tss)) else float(tss)
    lg = math.log1p
    return np.array([
        min(max(speed / c["speed_norm_div"], 0.0), c["speed_norm_max"]),
        1.0 if speed < c["stopped_mps"] else 0.0,
        min(max(ts_age / c["ts_age_div"], 0.0), c["ts_age_max"]),
        min(max(tss / c["tss_div"], 0.0), c["tss_max"]),
        min(max(d0 / c["d0_div"], 0.0), c["d0_max"]),
        lg(min(max(tlb, 0.0), c["tlb_cap_s"])) / lg(c["tlb_cap_s"]),
        1.0 if lbf else 0.0,
        lg(min(max(rem, 0.0), c["rem_cap_m"])) / lg(c["rem_cap_m"]),
        1.0 if start_unknown else 0.0,
    ], dtype=np.float32)


# ── tramos ───────────────────────────────────────────────────────────────────

def build_segments(c: dict, shape: Shape, d0: float, rem: float) -> dict[str, np.ndarray]:
    """
    Tramos de 250 m alineados a una grilla fija desde el inicio del shape; el primero y el último son parciales.
    Si el camino excede max_seg - 2 tramos de 250 m, el paso pasa a un múltiplo de 250 m. Devuelve arrays (N,)
    seg_lat, seg_lon, seg_mid_m, seg_len (suma de seg_len == rem).
    """
    base, max_seg = c["seg_base_m"], c["max_seg"]
    rem = max(rem, 0.0)
    d1 = d0 + rem
    step = base * max(1.0, math.ceil(rem / (base * (max_seg - 2))))
    k0 = math.floor(d0 / step)
    k1 = max(k0, max(math.ceil(d1 / step) - 1.0, 0.0))
    k = k0 + np.arange(int(k1 - k0) + 1, dtype=np.float64)
    lo = np.maximum(k * step, d0)
    hi = np.minimum((k + 1.0) * step, d1)
    length = np.maximum(hi - lo, 0.0)
    mid_m = (k + 0.5) * step
    cell = np.clip(np.floor(mid_m / base), 0, len(shape.cells) - 1).astype(int)
    return {"seg_lat": shape.cells[cell, 0], "seg_lon": shape.cells[cell, 1], "seg_mid_m": mid_m, "seg_len": length}


def run_network(bundle: Bundle, rows: list[dict]) -> np.ndarray:
    """rows: dicts con seg_* (N,), line_idx, dow, h_sin, h_cos, state (9,). Rellena N con ceros y corre el ONNX."""
    n = max(len(r["seg_len"]) for r in rows)
    B = len(rows)
    pad = lambda key: np.stack([np.pad(np.asarray(r[key], np.float32), (0, n - len(r[key]))) for r in rows])  # noqa: E731
    feed = {
        "seg_lat": pad("seg_lat"), "seg_lon": pad("seg_lon"), "seg_mid_m": pad("seg_mid_m"), "seg_len": pad("seg_len"),
        "seg_mask": np.stack([np.pad(np.ones(len(r["seg_len"]), np.float32), (0, n - len(r["seg_len"]))) for r in rows]),
        "line_idx": np.array([r["line_idx"] for r in rows], np.int32), "dow": np.array([r["dow"] for r in rows], np.int32),
        "h_sin": np.array([r["h_sin"] for r in rows], np.float32), "h_cos": np.array([r["h_cos"] for r in rows], np.float32),
        "state": np.stack([r["state"] for r in rows]).astype(np.float32),
    }
    return bundle.session.run(["eta"], feed)[0].astype(np.float64)


def eta_on_shape(bundle: Bundle, line: str, shape: Shape, d0: float, rem: float, ts_ping: float, speed: float,
                 ts_age: float, tlb: float = STATE_FALLBACK_TLB_S, lbf: bool = False, tss=None,
                 start_unknown: bool = True) -> float:
    """ETA (s, >= 0) medido desde el instante del ping, para un shape ya elegido. rem debe ser >= min_rem_m."""
    return float(eta_on_shapes(bundle, line, [dict(shape=shape, d0=d0, rem=rem, tlb=tlb, lbf=lbf)], ts_ping, speed,
                               ts_age, tss, start_unknown)[0])


def eta_on_shapes(bundle: Bundle, line: str, cands: list[dict], ts_ping, speed, ts_age, tss=None, start_unknown=True):
    c = bundle.const
    hs, hc, dow = encode_time(ts_ping)
    li = bundle.manifest["lines"][line]
    rows = []
    for k in cands:
        seg = build_segments(c, k["shape"], k["d0"], k["rem"])
        rows.append({**seg, "line_idx": li, "dow": dow, "h_sin": hs, "h_cos": hc,
                     "state": state_vector(c, speed, ts_age, tss, k["d0"], k.get("tlb", STATE_FALLBACK_TLB_S),
                                           k.get("lbf", False), k["rem"], start_unknown)})
    return np.maximum(run_network(bundle, rows), 0.0)


# ── candidatos de ramal ──────────────────────────────────────────────────────

def forward_fraction(dists, perps, max_perp: float) -> float:
    """Fracción del avance neto (m) que va en el sentido del shape. Sin información (quieto, <2 puntos) = 1."""
    d = np.asarray(dists)[np.asarray(perps) <= max_perp]
    if len(d) < 2:
        return 1.0
    steps = np.diff(d)
    mag = np.abs(steps)
    mv = (mag >= 30.0) & (mag <= 5000.0)
    fwd, bwd = steps[mv & (steps > 0)].sum(), -steps[mv & (steps < 0)].sum()
    return float(fwd / (fwd + bwd)) if fwd + bwd > 0 else 1.0


def _sense(c: dict, shape: Shape, pings: list[dict], vehicle: dict, now_ts: float) -> tuple[bool, str | None]:
    """
    Sentido del coche sobre el shape, con sus pings de los últimos history_window_s más el ping actual. Devuelve
    (True, None) si es coherente y hacia adelante, o (False, motivo): "sin_sentido" (< 2 pings sobre el shape o avance
    neto < MIN_NET_FORWARD_M: no se sabe hacia dónde va) | "sentido_incoherente" (se aleja del shape, retrocede o va al revés).
    """
    ps = [p for p in pings if now_ts - p["ts"] <= c["history_window_s"] and p["ts"] < vehicle["ts"]]
    ps = sorted(ps, key=lambda p: p["ts"]) + [{"ts": vehicle["ts"], "lat": vehicle["lat"], "lon": vehicle["lon"]}]
    pr = [shape.project(p["lat"], p["lon"]) for p in ps]
    near = [x for x in pr if x[1] <= c["max_perp_m"]]
    if len(near) < 2:
        return False, "sin_sentido"
    if len(near) / len(pr) < 0.8:
        return False, "sentido_incoherente"
    if forward_fraction([x[0] for x in pr], [x[1] for x in pr], c["max_perp_m"]) < c["min_forward_frac"]:
        return False, "sentido_incoherente"
    net = near[-1][0] - near[0][0]
    if net <= -MIN_NET_FORWARD_M:
        return False, "sentido_incoherente"
    if net < MIN_NET_FORWARD_M:
        return False, "sin_sentido"
    return True, None


def user_shapes(bundle: Bundle, line: str, user: tuple[float, float], user_kind: str = "punto",
                stop_recorridos: list[str] | None = None) -> dict[str, tuple[bool, str | None]]:
    """
    Shapes de la línea que sirven el punto del usuario: {shape_id: (sirve, motivo si no)}.
    "parada": los shapes cuyo nombre está en stop_recorridos (y a <= user_max_perp_m); si ninguno coincide por nombre,
      los shapes a <= STOP_FALLBACK_PERP_M. Resto: "no_sirve_parada".
    "punto" (GPS o toque en el mapa): shapes a <= POINT_MAX_PERP_M; entre ellos solo los de perp <= mínima +
      POINT_PARALLEL_MARGIN_M (el resto: "paralela"); más lejos: "usuario_fuera_del_recorrido".
    """
    c = bundle.const
    perps = {sid: sh.project(*user)[1] for sid, sh in bundle.lines[line].items()}
    out: dict[str, tuple[bool, str | None]] = {}
    if user_kind == "parada":
        names = set(stop_recorridos or [])
        by_name = {sid for sid, sh in bundle.lines[line].items() if sh.name in names}
        for sid in perps:
            if by_name:
                if sid not in by_name:
                    out[sid] = (False, "no_sirve_parada")
                elif perps[sid] > c["user_max_perp_m"]:
                    out[sid] = (False, "usuario_fuera_del_recorrido")
                else:
                    out[sid] = (True, None)
            else:
                out[sid] = (True, None) if perps[sid] <= STOP_FALLBACK_PERP_M else (False, "no_sirve_parada")
        return out
    within = [p for p in perps.values() if p <= POINT_MAX_PERP_M]
    lim = (min(within) + POINT_PARALLEL_MARGIN_M) if within else None
    for sid, p in perps.items():
        if p > POINT_MAX_PERP_M:
            out[sid] = (False, "usuario_fuera_del_recorrido")
        elif p > lim:
            out[sid] = (False, "paralela")
        else:
            out[sid] = (True, None)
    return out


def last_bus(c: dict, shape: Shape, others: list[dict], d_t: float, ts_ping: float) -> tuple[float, bool]:
    """
    Coche de adelante: entre los otros coches de la línea (cada uno {"pings": [(ts, lat, lon), ...]}, ascendente),
    el que pasó más recientemente por T antes de ts_ping. Devuelve (segundos desde su paso, encontrado).
    Pasos por interpolación lineal entre pings consecutivos que encierran d_t; fallback: ping a <= 250 m de T.
    """
    best = None
    for o in others:
        pr = [(t, *shape.project(la, lo)) for t, la, lo in o["pings"]]
        pr = [(t, d, p) for t, d, p in pr if p <= c["max_perp_m"]]
        if len(pr) < 2 or forward_fraction([x[1] for x in pr], [x[2] for x in pr], c["max_perp_m"]) < c["min_forward_frac"]:
            continue
        tp = None
        for (t0, d0, _), (t1, d1, _) in zip(pr[:-1], pr[1:]):
            if d1 > d0 and d0 <= d_t < d1:
                tp = t0 + (d_t - d0) / (d1 - d0) * (t1 - t0)
                break
        if tp is None or tp >= ts_ping:
            near = [t for t, d, _ in pr if abs(d - d_t) <= FALLBACK_M and t < ts_ping]
            tp = max(near) if near else None
        if tp is not None and tp < ts_ping and (best is None or tp > best):
            best = tp
    if best is None:
        return STATE_FALLBACK_TLB_S, False
    return min(ts_ping - best, c["tlb_cap_s"]), True


# ── API principal ────────────────────────────────────────────────────────────

def predict_from_raw(bundle: Bundle, line: str, vehicle: dict, user: tuple[float, float], now_ts: float,
                     history: list[dict] | None = None, others: list[dict] | None = None,
                     only_shapes: list[str] | None = None, user_kind: str = "punto",
                     stop_recorridos: list[str] | None = None) -> dict:
    """
    line: línea ya resuelta por el sufijo del label. vehicle: {lat, lon, speed_mps, ts} (último ping del coche; ts = hora
    del ping, unix s). user: (lat, lon). now_ts: hora de la consulta (unix s). history: pings anteriores del mismo coche
    [{ts, lat, lon}] ascendentes (puede ser []). others: otros coches de la línea con historial (puede ser []).
    user_kind: "punto" (GPS o mapa) o "parada"; stop_recorridos: nombres de los recorridos que sirven la parada.

    Devuelve {"status", "eta_s", "shape_id", "candidates", "en_cabecera", "group", "depends_on", "compatible", "discarded"}.
      status: ok | llegando (rem < min_rem_m en algún shape que sirve el punto) | pasado (el coche ya pasó al usuario en
              todos sus shapes compatibles) | sin_sentido (sentido aún desconocido) | sin_candidatos | linea_fuera_del_modelo
      group: "seguro" (todos los shapes compatibles del coche sirven el punto y el usuario está adelante) |
             "puede_venir" (solo algunos: depends_on lista los shapes de los que depende) | None.
      compatible: [{shape_id, passes, reason}]; discarded: [{shape_id, reason}] de los shapes que no son candidatos.
    eta_s es el MÍNIMO entre los shapes que pasan por el punto, medido desde now_ts (eta del modelo − antigüedad del ping).
    """
    c = bundle.const
    empty = {"status": "linea_fuera_del_modelo", "eta_s": None, "shape_id": None, "candidates": [], "en_cabecera": False,
             "group": None, "depends_on": [], "compatible": [], "discarded": []}
    if line not in bundle.lines:
        return empty
    age = max(0.0, now_ts - vehicle["ts"])
    us = user_shapes(bundle, line, user, user_kind, stop_recorridos)
    cands, compat, discarded = [], [], []
    llegando = pasado = near_any = False
    for sid, sh in bundle.lines[line].items():
        if only_shapes is not None and sid not in only_shapes:
            continue
        d_p, perp_p = sh.project(vehicle["lat"], vehicle["lon"])
        if perp_p > c["max_perp_m"]:
            discarded.append({"shape_id": sid, "reason": "coche_fuera_del_recorrido"})
            continue
        near_any = True
        ok, why = _sense(c, sh, history or [], vehicle, now_ts)
        if not ok:
            discarded.append({"shape_id": sid, "reason": why})
            continue
        serves, why = us[sid]
        if not serves:
            compat.append({"shape_id": sid, "passes": False, "reason": why})
            discarded.append({"shape_id": sid, "reason": why})
            continue
        d_t, _ = sh.project(*user)
        rem = d_t - d_p
        if rem < 0:
            pasado = True
            compat.append({"shape_id": sid, "passes": False, "reason": "ya_paso"})
            discarded.append({"shape_id": sid, "reason": "ya_paso"})
            continue
        if rem < c["min_rem_m"]:
            llegando = True
            compat.append({"shape_id": sid, "passes": True, "reason": "llegando"})
            continue
        tlb, lbf = last_bus(c, sh, others or [], d_t, vehicle["ts"]) if others else (STATE_FALLBACK_TLB_S, False)
        cands.append({"shape": sh, "d0": d_p, "rem": rem, "tlb": tlb, "lbf": lbf})
        compat.append({"shape_id": sid, "passes": True, "reason": None})
    res = {**empty, "compatible": compat, "discarded": discarded}
    if not compat:
        res["status"] = "sin_sentido" if near_any else "sin_candidatos"
        return res
    if not any(k["passes"] for k in compat):
        res["status"] = "pasado" if pasado else "sin_candidatos"
        return res
    res["group"] = "seguro" if all(k["passes"] for k in compat) else "puede_venir"
    if res["group"] == "puede_venir":
        res["depends_on"] = [k["shape_id"] for k in compat if k["passes"]]
    out = []
    if cands:
        etas = eta_on_shapes(bundle, line, cands, vehicle["ts"], vehicle.get("speed_mps", 0.0), min(age, c["ts_age_cap_s"]))
        out = [{"shape_id": k["shape"].id, "d_p": k["d0"], "rem_m": k["rem"], "eta_model_s": float(e),
                "eta_s": max(0.0, float(e) - age), "last_bus_found": k["lbf"]} for k, e in zip(cands, etas)]
    res["candidates"] = out
    if llegando:
        res["status"], res["eta_s"] = "llegando", 0.0
        return res
    best = min(out, key=lambda r: r["eta_s"])
    res.update(status="ok", eta_s=best["eta_s"], shape_id=best["shape_id"],
               en_cabecera=(vehicle.get("speed_mps", 0.0) or 0.0) < c["stopped_mps"] and best["d_p"] < c["terminal_zone_m"])
    return res
