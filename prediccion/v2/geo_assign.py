"""
Asignación geométrica de un ping a recorrido y sentido (`--assign geo3`; contrato de inferencia 2.0).

UN solo lugar para las constantes y las primitivas por ping. Las usan igual el pipeline (máscara `valid`, recorridos
activos del segmentador, filtro del recorrido elegido ex post) y la app (`prediccion/inference/path_reference.py`,
que importa este módulo; el cliente JS reproduce estas reglas con los valores del `manifest.json`).

Todo lo de este módulo es CAUSAL: depende solo del ping y de pings pasados del mismo coche. Qué recorrido tomó
finalmente el viaje y cuándo llegó a cada punto es información ex post: vive en el pipeline, se usa solo como
etiqueta y nunca decide qué pings son válidos ni cómo se proyectan.

Un "shape" es cualquier objeto con `project(lat, lon) -> (metros_desde_el_inicio, error_perpendicular_m)`
(`projector.ShapeIndex` en el pipeline, `path_reference.Shape` en la referencia de inferencia).

Reglas
  Compatibilidad de posición: un shape es compatible con un ping si su error perpendicular es <= TOL_M y además
    <= (mínimo error perpendicular entre TODOS los shapes de la línea) + MARGIN_M. La primera cota admite el ruido
    de GPS; la segunda descarta la calle paralela (a ~100-130 m) cuando otro shape explica mucho mejor el ping.
    Ida y vuelta por la misma calle tienen error casi igual: ambos son compatibles (el sentido sale del historial).
  Sentido por geometría (sin historial): si todos los shapes compatibles con la posición tienen ahí el mismo rumbo
    local (diferencias <= HEADING_TOL_DEG) y ninguno pasa por ese punto también en sentido opuesto, el coche va en ese
    sentido (`direction_from_geometry`). Calle de un solo sentido o tronco compartido en un solo sentido: sentido conocido
    desde el primer ping.
  Sentido por historial: cuando la geometría no alcanza (ida y vuelta por la misma calle, avenida de doble mano
    compartida, bucles), con los pings propios de los últimos HISTORY_WINDOW_S más el ping actual, proyectados sobre el
    shape (ver `direction_from_history`). Un historial que contradice un shape (`sentido_incoherente`) lo descarta
    aunque la geometría dé el sentido.
"""

from __future__ import annotations

import numpy as np

# ── Constantes (única fuente; el export las escribe en manifest.json["assignment"]) ──────────────────────────
TOL_M = 45.0                 # error perpendicular máximo de un ping respecto de un shape compatible
MARGIN_M = 20.0              # ... y a lo sumo este margen por encima del mejor shape de la línea
HISTORY_WINDOW_S = 900       # ventana de pings pasados para el sentido
MIN_NEAR_PINGS = 2           # pings (historial + actual) a <= TOL_M del shape para opinar sobre el sentido
MIN_NEAR_FRAC = 0.8          # fracción mínima de los pings de la ventana a <= TOL_M del shape
MIN_FORWARD_FRAC = 0.6       # fracción mínima del avance neto (m) que va en el sentido del shape
MIN_NET_FORWARD_M = 40.0     # avance neto mínimo (último menos primero de los pings cercanos) para dar el sentido
STEP_MOVING_M = 30.0         # pasos menores son ruido de proyección / coche detenido
STEP_JUMP_M = 5_000.0        # pasos mayores son saltos (recorridos con bucles) y no cuentan
HEADING_TOL_DEG = 45.0       # rumbos locales de shapes compatibles a <= este ángulo: misma orientación (sentido por geometría)
# Paradas (posición exacta, sin ruido de GPS): se asocian a recorridos por nombre
STOP_MAX_PERP_M = 100.0      # parada asociada por nombre: perp máximo al shape
STOP_FALLBACK_PERP_M = 25.0  # parada sin recorridos asociados por nombre: se asocia al shape a <= esta distancia
# Pipeline
MIN_COMPAT_FRAC = 0.5        # un shape es elegible como recorrido del viaje si >= esta fracción de sus pings es compatible

REASON_NO_DIRECTION = "sin_sentido"
REASON_INCOHERENT = "sentido_incoherente"


def manifest_params() -> dict:
    """Parámetros que el cliente necesita para reproducir la asignación (se escriben en manifest.json)."""
    return {
        "tol_m": TOL_M, "margin_m": MARGIN_M, "history_window_s": HISTORY_WINDOW_S,
        "min_near_pings": MIN_NEAR_PINGS, "min_near_frac": MIN_NEAR_FRAC, "min_forward_frac": MIN_FORWARD_FRAC,
        "min_net_forward_m": MIN_NET_FORWARD_M, "step_moving_m": STEP_MOVING_M, "step_jump_m": STEP_JUMP_M,
        "stop_max_perp_m": STOP_MAX_PERP_M, "stop_fallback_perp_m": STOP_FALLBACK_PERP_M,
        "heading_tol_deg": HEADING_TOL_DEG,
    }


# ── Posición: shapes compatibles ─────────────────────────────────────────────

def compat_limit(min_perp, tol_m: float = TOL_M, margin_m: float = MARGIN_M):
    """Error perpendicular máximo para ser compatible, dado el mínimo entre todos los shapes de la línea."""
    return np.minimum(tol_m, np.asarray(min_perp) + margin_m)


def compat_masks(perps: "dict[str, np.ndarray]", tol_m: float = TOL_M, margin_m: float = MARGIN_M) -> "dict[str, np.ndarray]":
    """
    Versión vectorizada para el pipeline. perps: {shape_id: (n,) error perpendicular de cada ping sobre ese shape},
    con TODOS los shapes de la línea. Devuelve {shape_id: (n,) bool}: el ping es compatible con ese shape.
    """
    if not perps:
        return {}
    lim = compat_limit(np.min(np.stack(list(perps.values())), axis=0), tol_m, margin_m)
    return {s: np.asarray(p) <= lim for s, p in perps.items()}


def project_all(lat: float, lon: float, shapes: dict) -> "dict[str, tuple[float, float]]":
    """{shape_id: (d_along_m, perp_m)} del punto sobre cada shape."""
    return {sid: sh.project(lat, lon) for sid, sh in shapes.items()}


def compatible_shapes(lat: float, lon: float, shapes: dict, tol_m: float = TOL_M,
                      margin_m: float = MARGIN_M) -> "list[tuple[str, float, float]]":
    """
    Shapes de la línea compatibles con la posición (lat, lon): [(shape_id, perp_m, d_along_m)] por perp creciente.
    Compatible = perp <= tol_m y perp <= (mínimo perp entre todos los shapes de `shapes`) + margin_m.
    """
    pr = project_all(lat, lon, shapes)
    if not pr:
        return []
    lim = float(compat_limit(min(p for _, p in pr.values()), tol_m, margin_m))
    out = [(sid, p, d) for sid, (d, p) in pr.items() if p <= lim]
    out.sort(key=lambda r: r[1])
    return out


# ── Sentido por geometría: sin historial ─────────────────────────────────────

M_PER_DEG_LAT = 111_320.0


def angle_diff_deg(a: float, b: float) -> float:
    """Diferencia entre dos rumbos en grados, en [0, 180]."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def shape_heading(shape, lat: float, lon: float, max_perp: float, tol_deg: float = HEADING_TOL_DEG) -> "tuple[float, bool]":
    """
    Rumbo local del shape en el punto (lat, lon): (rumbo en grados, 0 = norte, horario; doble_sentido).
    El rumbo es el del segmento no degenerado más cercano al punto (el primero si empatan). doble_sentido = True si
    otro segmento del mismo shape a <= max_perp del punto va en sentido opuesto (diferencia > 180 - tol_deg): el shape
    pasa por ahí en los dos sentidos (bucle, ida y vuelta dentro del mismo recorrido) y su orientación no es única.
    `shape` debe exponer `pts` ((n, 2) lat, lon); opcional `mpd` (metros por grado de latitud).
    """
    pts = np.asarray(shape.pts, dtype=np.float64)
    mpd = float(getattr(shape, "mpd", M_PER_DEG_LAT))
    a, b = pts[:-1], pts[1:]
    mlon = mpd * np.cos(np.radians((a[:, 0] + b[:, 0]) / 2.0))
    ab_y = (b[:, 0] - a[:, 0]) * mpd
    ab_x = (b[:, 1] - a[:, 1]) * mlon
    dot = ab_x * ab_x + ab_y * ab_y
    valid = dot > 1e-9
    ap_y = (lat - a[:, 0]) * mpd
    ap_x = (lon - a[:, 1]) * mlon
    t = np.clip(np.where(valid, (ap_x * ab_x + ap_y * ab_y) / np.where(valid, dot, 1.0), 0.0), 0.0, 1.0)
    perp = np.where(valid, np.hypot(ap_x - t * ab_x, ap_y - t * ab_y), np.inf)
    heading = np.degrees(np.arctan2(ab_x, ab_y)) % 360.0
    i = int(np.argmin(perp))
    h = float(heading[i])
    near = valid & (perp <= max_perp)
    two_way = bool(any(angle_diff_deg(h, float(x)) > 180.0 - tol_deg for x in heading[near]))
    return h, two_way


def direction_from_geometry(lat: float, lon: float, shapes: dict, tol_m: float = TOL_M, margin_m: float = MARGIN_M,
                            tol_deg: float = HEADING_TOL_DEG) -> bool:
    """
    True si el sentido del coche en (lat, lon) es conocido por geometría: hay al menos un shape compatible con la
    posición (`compatible_shapes`), ninguno pasa por ahí en los dos sentidos (`shape_heading`) y todos tienen el mismo
    rumbo local (diferencia entre cualquier par <= tol_deg). Entonces todos los shapes compatibles van hacia adelante
    sin necesidad de historial. False si hay orientaciones opuestas o cruzadas entre los compatibles (ida y vuelta por
    la misma calle, doble mano compartida, esquinas donde los recorridos doblan distinto): el sentido sale del historial.
    """
    pr = project_all(lat, lon, shapes)
    if not pr:
        return False
    lim = float(compat_limit(min(p for _, p in pr.values()), tol_m, margin_m))
    hs = []
    for sid, (_, p) in pr.items():
        if p > lim:
            continue
        h, two_way = shape_heading(shapes[sid], lat, lon, lim, tol_deg)
        if two_way:
            return False
        hs.append(h)
    if not hs:
        return False
    return all(angle_diff_deg(x, y) <= tol_deg for i, x in enumerate(hs) for y in hs[i + 1:])


# ── Sentido: a partir de pings pasados ───────────────────────────────────────

def forward_fraction(dists, perps, tol_m: float = TOL_M) -> float:
    """
    Fracción del avance neto (en metros) que va en el sentido del shape, sobre los pings a <= tol_m.
    1.0 = todo hacia adelante; 0.0 = el coche recorre el shape al revés. Sin información devuelve 1.0.
    """
    d = np.asarray(dists, dtype=np.float64)[np.asarray(perps) <= tol_m]
    if len(d) < 2:
        return 1.0
    steps = np.diff(d)
    mag = np.abs(steps)
    moving = (mag >= STEP_MOVING_M) & (mag <= STEP_JUMP_M)
    fwd = float(steps[moving & (steps > 0)].sum())
    bwd = float(-steps[moving & (steps < 0)].sum())
    total = fwd + bwd
    return fwd / total if total > 0 else 1.0


def _as_tuple(p):
    return (p["ts"], p["lat"], p["lon"]) if isinstance(p, dict) else (p[0], p[1], p[2])


def direction_from_history(pings, shape, tol_m: float = TOL_M) -> "tuple[bool, str | None]":
    """
    Sentido del coche sobre `shape`. pings: pings del coche en orden cronológico, el ÚLTIMO es el actual; cada uno
    `(ts, lat, lon)` o `{"ts", "lat", "lon"}`. Se usan los de los últimos HISTORY_WINDOW_S respecto del actual.
    Devuelve (True, None) si el sentido es hacia adelante, o (False, motivo):
      "sin_sentido"          menos de MIN_NEAR_PINGS a <= tol_m, o avance neto entre -MIN_NET_FORWARD_M y +MIN_NET_FORWARD_M
                             (coche quieto o historial insuficiente: no se sabe hacia dónde va)
      "sentido_incoherente"  se aleja del shape, retrocede o va al revés
    """
    ps = [_as_tuple(p) for p in pings]
    if not ps:
        return False, REASON_NO_DIRECTION
    t_now = ps[-1][0]
    ps = [p for p in ps[:-1] if t_now - p[0] <= HISTORY_WINDOW_S and p[0] < t_now] + [ps[-1]]
    pr = [shape.project(la, lo) for _, la, lo in ps]
    near = [x for x in pr if x[1] <= tol_m]
    if len(near) < MIN_NEAR_PINGS:
        return False, REASON_NO_DIRECTION
    if len(near) / len(pr) < MIN_NEAR_FRAC:
        return False, REASON_INCOHERENT
    if forward_fraction([x[0] for x in pr], [x[1] for x in pr], tol_m) < MIN_FORWARD_FRAC:
        return False, REASON_INCOHERENT
    net = near[-1][0] - near[0][0]
    if net <= -MIN_NET_FORWARD_M:
        return False, REASON_INCOHERENT
    if net < MIN_NET_FORWARD_M:
        return False, REASON_NO_DIRECTION
    return True, None
