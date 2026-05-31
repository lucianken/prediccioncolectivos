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
