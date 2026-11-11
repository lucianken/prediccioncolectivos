import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .segmenter import Trip

MAX_PERP_ERROR_M = 150.0
_M_PER_DEG_LAT = 111_320.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def polyline_length_m(points: list[tuple[float, float]]) -> float:
    return sum(
        haversine_m(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )


class ShapeIndex:
    """
    Precomputa arrays numpy de un shape para proyectar puntos rápido.
    Crear una vez por trip (o reusar entre trips del mismo ramal).
    """

    def __init__(self, shape_points: list[tuple[float, float]], fast: bool = False):
        """
        fast=True (usado por el pipeline v2): project_many busca el segmento más cercano con un KD-tree sobre el
        recorrido densificado (cada 25 m) y calcula la proyección exacta solo en los segmentos vecinos, en vez de
        contra todos (O(M log S) en lugar de O(M x S)). Mismo resultado que el exacto para puntos a < 400 m
        (diferencias de centímetros); más lejos devuelve una aproximación (error perp. >= 400 m).
        fast=False (default) mantiene el comportamiento histórico, bit a bit.
        """
        pts = np.array(shape_points, dtype=np.float64)  # (N, 2): lat, lon
        self._pts = pts
        self._fast = fast
        self._tree = None

        # Vectores de segmentos en metros usando aproximación de ángulo pequeño
        lat_mid = (pts[:-1, 0] + pts[1:, 0]) / 2.0
        cos_lat = np.cos(np.radians(lat_mid))           # (N-1,)
        m_per_deg_lon = _M_PER_DEG_LAT * cos_lat

        self._ab_y = (pts[1:, 0] - pts[:-1, 0]) * _M_PER_DEG_LAT   # (N-1,)
        self._ab_x = (pts[1:, 1] - pts[:-1, 1]) * m_per_deg_lon     # (N-1,)
        self._m_per_deg_lon = m_per_deg_lon

        ab_dot = self._ab_x ** 2 + self._ab_y ** 2
        self._ab_dot = ab_dot                                         # (N-1,)
        self._seg_lens = np.sqrt(ab_dot)                             # (N-1,)
        self._cum_dist = np.concatenate([[0.0], np.cumsum(self._seg_lens)])  # (N,)

        # Mask de segmentos degenerados (< 1 mm)
        self._valid = ab_dot > 1e-9

    def project(self, lat: float, lon: float) -> tuple[float, float]:
        """
        Retorna (dist_along_shape_m, perp_error_m) para un punto.
        Proyecta sobre todos los segmentos vectorialmente.
        """
        pts = self._pts

        ap_y = (lat - pts[:-1, 0]) * _M_PER_DEG_LAT        # (N-1,)
        ap_x = (lon - pts[:-1, 1]) * self._m_per_deg_lon    # (N-1,)

        ap_dot_ab = ap_x * self._ab_x + ap_y * self._ab_y   # (N-1,)

        t = np.divide(ap_dot_ab, self._ab_dot, out=np.zeros_like(self._ab_dot), where=self._valid)
        t = np.clip(t, 0.0, 1.0)

        proj_lat = pts[:-1, 0] + t * (pts[1:, 0] - pts[:-1, 0])
        proj_lon = pts[:-1, 1] + t * (pts[1:, 1] - pts[:-1, 1])

        dp_y = (lat - proj_lat) * _M_PER_DEG_LAT
        dp_x = (lon - proj_lon) * self._m_per_deg_lon
        perp = np.sqrt(dp_x ** 2 + dp_y ** 2)               # (N-1,)

        best_i = int(np.argmin(perp))
        dist_along = float(self._cum_dist[best_i] + t[best_i] * self._seg_lens[best_i])
        return dist_along, float(perp[best_i])

    _FAST_STEP_M = 25.0
    _FAST_WINDOW = 3
    _FAST_FAR_M = 400.0

    def _build_tree(self) -> None:
        from scipy.spatial import cKDTree
        pts = self._pts
        self._lat0 = float(pts[:, 0].mean())
        self._mlon = _M_PER_DEG_LAT * math.cos(math.radians(self._lat0))
        xs, ys, seg, along = [], [], [], []
        for i in range(len(pts) - 1):
            n = max(1, int(math.ceil(self._seg_lens[i] / self._FAST_STEP_M)))
            t = np.arange(n + 1) / n
            xs.append(pts[i, 1] + t * (pts[i + 1, 1] - pts[i, 1]))
            ys.append(pts[i, 0] + t * (pts[i + 1, 0] - pts[i, 0]))
            seg.append(np.full(n + 1, i))
            along.append(self._cum_dist[i] + t * self._seg_lens[i])
        lon = np.concatenate(xs)
        lat = np.concatenate(ys)
        self._dense_seg = np.concatenate(seg)
        self._dense_along = np.concatenate(along)
        self._tree = cKDTree(np.column_stack([lon * self._mlon, lat * _M_PER_DEG_LAT]))

    def _project_many_fast(self, lats, lons):
        if self._tree is None:
            self._build_tree()
        lats = np.asarray(lats, dtype=np.float64)
        lons = np.asarray(lons, dtype=np.float64)
        M = len(lats)
        dist_q, nn = self._tree.query(np.column_stack([lons * self._mlon, lats * _M_PER_DEG_LAT]))
        s0 = self._dense_seg[nn]
        n_segs = len(self._ab_x)
        W = self._FAST_WINDOW
        cand = np.clip(s0[:, None] + np.arange(-W, W + 1)[None, :], 0, n_segs - 1)     # (M, 2W+1)
        a_lat = self._pts[cand, 0]
        a_lon = self._pts[cand, 1]
        ap_y = (lats[:, None] - a_lat) * _M_PER_DEG_LAT
        ap_x = (lons[:, None] - a_lon) * self._m_per_deg_lon[cand]
        abx, aby, abd = self._ab_x[cand], self._ab_y[cand], self._ab_dot[cand]
        valid = self._valid[cand]
        t = np.where(valid, (ap_x * abx + ap_y * aby) / np.where(valid, abd, 1.0), 0.0)
        t = np.clip(t, 0.0, 1.0)
        dp_y = ap_y - t * aby
        dp_x = ap_x - t * abx
        perp_all = np.sqrt(dp_x ** 2 + dp_y ** 2)
        best = np.argmin(perp_all, axis=1)
        rows = np.arange(M)
        bi = cand[rows, best]
        perp = perp_all[rows, best]
        along = self._cum_dist[bi] + t[rows, best] * self._seg_lens[bi]
        far = dist_q > self._FAST_FAR_M
        if far.any():
            perp = np.where(far, dist_q, perp)
            along = np.where(far, self._dense_along[nn], along)
        return along, perp

    def project_many(
        self,
        lats: "np.ndarray",
        lons: "np.ndarray",
    ) -> "tuple[np.ndarray, np.ndarray]":
        """
        Proyecta N puntos sobre el shape en una sola operación vectorizada.

        Parámetros
        ----------
        lats : array-like de shape (M,)  — latitudes
        lons : array-like de shape (M,)  — longitudes

        Retorna
        -------
        dist_along : ndarray (M,) — distancia acumulada sobre el shape en metros
        perp       : ndarray (M,) — error perpendicular en metros

        Equivalencia exacta con project():
          Para todo i: project_many(lats, lons)[0][i] == project(lats[i], lons[i])[0]
          (y lo mismo para perp).  Los resultados son idénticos bit-a-bit a los del
          loop porque usan la misma aritmética de punto flotante sobre los mismos arrays.

        Complejidad: O(M × S) donde S = nº segmentos del shape. Evita el overhead del
        loop Python por punto (~2.25M llamadas en el profiling → cuellos de botella
        del 20% del tiempo total de build_ramal_map).
        """
        if self._fast:
            return self._project_many_fast(lats, lons)
        lats_arr = np.asarray(lats, dtype=np.float64)   # (M,)
        lons_arr = np.asarray(lons, dtype=np.float64)   # (M,)
        M = len(lats_arr)
        pts = self._pts
        n_segs = len(self._ab_x)

        # Broadcast: (M, n_segs) para cada punto contra todos los segmentos
        # ap_* son los vectores desde el inicio de cada segmento al punto GPS
        ap_y = (lats_arr[:, None] - pts[:-1, 0][None, :]) * _M_PER_DEG_LAT   # (M, S)
        ap_x = (lons_arr[:, None] - pts[:-1, 1][None, :]) * self._m_per_deg_lon[None, :]  # (M, S)

        ap_dot_ab = ap_x * self._ab_x[None, :] + ap_y * self._ab_y[None, :]  # (M, S)

        # t clampeado a [0,1]: posición proyectada dentro del segmento
        ab_dot = self._ab_dot[None, :]                                         # (1, S)
        valid = self._valid[None, :]                                            # (1, S)
        t = np.where(valid, ap_dot_ab / np.where(valid, ab_dot, 1.0), 0.0)   # (M, S)
        t = np.clip(t, 0.0, 1.0)

        # Punto proyectado sobre el segmento
        proj_lat = pts[:-1, 0][None, :] + t * (pts[1:, 0] - pts[:-1, 0])[None, :]  # (M, S)
        proj_lon = pts[:-1, 1][None, :] + t * (pts[1:, 1] - pts[:-1, 1])[None, :]  # (M, S)

        dp_y = (lats_arr[:, None] - proj_lat) * _M_PER_DEG_LAT
        dp_x = (lons_arr[:, None] - proj_lon) * self._m_per_deg_lon[None, :]
        perp_all = np.sqrt(dp_x ** 2 + dp_y ** 2)                              # (M, S)

        # Para cada punto, el segmento con menor error perpendicular
        best_i = np.argmin(perp_all, axis=1)                                    # (M,)
        perp_out = perp_all[np.arange(M), best_i]                              # (M,)

        t_best = t[np.arange(M), best_i]                                       # (M,)
        seg_lens_best = self._seg_lens[best_i]                                  # (M,)
        dist_along_out = self._cum_dist[best_i] + t_best * seg_lens_best       # (M,)

        return dist_along_out, perp_out

    @property
    def total_length_m(self) -> float:
        return float(self._cum_dist[-1])


def project_to_shape(
    lat: float,
    lon: float,
    shape_points: list[tuple[float, float]],
) -> tuple[float, float]:
    """Interfaz compatible con código existente. Crea ShapeIndex on-the-fly."""
    if len(shape_points) == 1:
        return 0.0, haversine_m(lat, lon, shape_points[0][0], shape_points[0][1])
    return ShapeIndex(shape_points).project(lat, lon)


def project_trip(
    trip: "Trip",
    shape_points: list[tuple[float, float]],
    max_perp_error_m: float = MAX_PERP_ERROR_M,
    shape_index: "ShapeIndex | None" = None,
) -> "Trip":
    """
    Proyecta todos los puntos del trip sobre el shape de manera vectorizada.
    Si se pasa shape_index pre-construido, lo reutiliza.
    """
    if shape_index is None:
        shape_index = ShapeIndex(shape_points)

    if not trip.points:
        return trip

    lats = np.array([pt.lat for pt in trip.points], dtype=np.float64)
    lons = np.array([pt.lon for pt in trip.points], dtype=np.float64)
    dists, perps = shape_index.project_many(lats, lons)

    valid_points = []
    for i, pt in enumerate(trip.points):
        dist_along = float(dists[i])
        perp_error = float(perps[i])
        pt.dist_along_shape_m = dist_along
        pt.perp_error_m = perp_error
        if perp_error <= max_perp_error_m:
            valid_points.append(pt)
    trip.points = valid_points
    return trip


# ── Opción A (ARQUITECTURA.md §4.1): recorrido elegido por geometría ─────────

MIN_FORWARD_FRAC = 0.6        # fracción mínima de avance "hacia adelante" para aceptar un recorrido
_STEP_MOVING_M = 30.0         # pasos menores se consideran ruido de proyección / coche detenido
_STEP_JUMP_M = 5_000.0        # pasos mayores son saltos (recorridos con bucles), no cuentan


def _forward_fraction(dists: "np.ndarray", perps: "np.ndarray", max_perp_error_m: float) -> float:
    """
    Fracción del avance neto (en metros) que va en el sentido del recorrido.
    1.0 = todo hacia adelante; 0.0 = el coche recorre el shape al revés (vuelta
    proyectada sobre la ida, que comparte calles pero con sentido contrario).
    Sin información (coche detenido, <2 puntos válidos) devuelve 1.0.
    """
    ok = perps <= max_perp_error_m
    d = dists[ok]
    if len(d) < 2:
        return 1.0
    steps = np.diff(d)
    mag = np.abs(steps)
    moving = (mag >= _STEP_MOVING_M) & (mag <= _STEP_JUMP_M)
    fwd = float(steps[moving & (steps > 0)].sum())
    bwd = float(-steps[moving & (steps < 0)].sum())
    total = fwd + bwd
    return fwd / total if total > 0 else 1.0


def best_shape_for_trip(
    lats,
    lons,
    shape_indices: "dict[str, ShapeIndex]",
    max_perp_error_m: float = MAX_PERP_ERROR_M,
    min_forward_frac: float = MIN_FORWARD_FRAC,
    prescreen_points: int = 16,
    prescreen_keep: int = 3,
) -> "tuple[str | None, float]":
    """
    Elige, entre los recorridos de una línea, el que mejor explica el viaje COMPLETO.

    Criterio: menor error perpendicular mediano (sobre todos los puntos del viaje)
    entre los recorridos recorridos "hacia adelante" (>= min_forward_frac del avance
    neto en el sentido del shape). Empates (mediana igual en bins de 10 m) se resuelven por error medio
    acotado a 150 m. Si ninguno cumple, se devuelve el de menor error
    sin restricción de sentido. No usa route_id ni direction_id.

    Para líneas con muchos recorridos se hace un pre-filtro barato con
    `prescreen_points` puntos equiespaciados y solo los `prescreen_keep` mejores se
    proyectan con todos los puntos.

    Retorna (shape_id, median_perp_m). (None, inf) si no hay shapes o puntos.
    """
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    if len(lats) == 0 or not shape_indices:
        return None, float("inf")

    def _score(sub_lats, sub_lons, ids):
        out = []
        for sid in ids:
            d, p = shape_indices[sid].project_many(sub_lats, sub_lons)
            frac = _forward_fraction(d, p, max_perp_error_m)
            out.append((sid, float(np.median(p)), frac, float(np.minimum(p, max_perp_error_m).mean())))
        return out

    def _key(r):
        # error mediano en bins de 10 m (ruido GPS); si empatan (p.ej. tramo compartido > 50 % del viaje),
        # desempata el error medio acotado, que sí ve la parte donde los recorridos divergen
        return (round(r[1] / 10.0), r[3])

    ids = list(shape_indices.keys())
    if len(ids) > prescreen_keep and len(lats) > 2 * prescreen_points:
        sel = np.linspace(0, len(lats) - 1, prescreen_points).astype(int)
        pre = _score(lats[sel], lons[sel], ids)
        pre.sort(key=lambda r: (r[2] < min_forward_frac,) + _key(r))
        ids = [r[0] for r in pre[:prescreen_keep]]

    scored = _score(lats, lons, ids)
    ok = [r for r in scored if r[2] >= min_forward_frac]
    pool = ok if ok else scored
    best = min(pool, key=_key)
    return best[0], best[1]
