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

    def __init__(self, shape_points: list[tuple[float, float]]):
        pts = np.array(shape_points, dtype=np.float64)  # (N, 2): lat, lon
        self._pts = pts

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

        t = np.where(self._valid, ap_dot_ab / self._ab_dot, 0.0)
        t = np.clip(t, 0.0, 1.0)

        proj_lat = pts[:-1, 0] + t * (pts[1:, 0] - pts[:-1, 0])
        proj_lon = pts[:-1, 1] + t * (pts[1:, 1] - pts[:-1, 1])

        dp_y = (lat - proj_lat) * _M_PER_DEG_LAT
        dp_x = (lon - proj_lon) * self._m_per_deg_lon
        perp = np.sqrt(dp_x ** 2 + dp_y ** 2)               # (N-1,)

        best_i = int(np.argmin(perp))
        dist_along = float(self._cum_dist[best_i] + t[best_i] * self._seg_lens[best_i])
        return dist_along, float(perp[best_i])

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
    Proyecta todos los puntos del trip sobre el shape.
    Si se pasa shape_index pre-construido, lo reutiliza (más eficiente
    cuando se proyectan muchos trips del mismo ramal).
    """
    if shape_index is None:
        shape_index = ShapeIndex(shape_points)

    valid_points = []
    for pt in trip.points:
        dist_along, perp_error = shape_index.project(pt.lat, pt.lon)
        pt.dist_along_shape_m = dist_along
        pt.perp_error_m = perp_error
        if perp_error <= max_perp_error_m:
            valid_points.append(pt)
    trip.points = valid_points
    return trip
