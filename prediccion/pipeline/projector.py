import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .segmenter import Trip

MAX_PERP_ERROR_M = 150.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distancia entre dos puntos geográficos en metros.
    Fórmula Haversine. Radio de la Tierra = 6_371_000m.
    """
    R = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def polyline_length_m(points: list[tuple[float, float]]) -> float:
    """Longitud total de una polilínea en metros (suma de segmentos haversine)."""
    return sum(
        haversine_m(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )


def project_to_shape(
    lat: float,
    lon: float,
    shape_points: list[tuple[float, float]],   # [(lat, lon), ...]
) -> tuple[float, float]:
    """
    Proyecta (lat, lon) sobre la polilínea del shape.

    Returns (dist_along_shape_m, perp_error_m):
      dist_along_shape_m: metros desde el inicio de la polilínea al punto proyectado
      perp_error_m: distancia perpendicular desde el punto al shape (calidad)

    Algoritmo:
    - Para cada segmento consecutivo del shape:
        - Proyectar (lat, lon) al segmento (clamp t ∈ [0,1])
        - Calcular distancia perpendicular
    - Tomar el segmento con menor distancia perpendicular
    - dist_along = sum de longitudes de segmentos anteriores + t * longitud del segmento ganador
    """
    if len(shape_points) == 1:
        perp = haversine_m(lat, lon, shape_points[0][0], shape_points[0][1])
        return (0.0, perp)

    best_perp = float("inf")
    best_dist_along = 0.0
    cumulative_dist = 0.0

    for i in range(len(shape_points) - 1):
        a_lat, a_lon = shape_points[i]
        b_lat, b_lon = shape_points[i + 1]

        seg_len = haversine_m(a_lat, a_lon, b_lat, b_lon)

        if seg_len < 1e-9:
            # Degenerate segment: treat as point
            perp = haversine_m(lat, lon, a_lat, a_lon)
            if perp < best_perp:
                best_perp = perp
                best_dist_along = cumulative_dist
            cumulative_dist += seg_len
            continue

        # Use small-angle approximation in meters
        # Scale lon by cos(lat_mean) to convert degree increments to roughly equal-length
        lat_mean = (a_lat + b_lat) / 2.0
        cos_lat = math.cos(math.radians(lat_mean))
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * cos_lat

        # Vector AB in meters
        ab_x = (b_lon - a_lon) * m_per_deg_lon
        ab_y = (b_lat - a_lat) * m_per_deg_lat

        # Vector AP in meters
        ap_x = (lon - a_lon) * m_per_deg_lon
        ap_y = (lat - a_lat) * m_per_deg_lat

        ab_dot_ab = ab_x * ab_x + ab_y * ab_y
        ap_dot_ab = ap_x * ab_x + ap_y * ab_y

        t = ap_dot_ab / ab_dot_ab
        t = max(0.0, min(1.0, t))

        # Projected point in lat/lon
        proj_lat = a_lat + t * (b_lat - a_lat)
        proj_lon = a_lon + t * (b_lon - a_lon)

        perp = haversine_m(lat, lon, proj_lat, proj_lon)

        if perp < best_perp:
            best_perp = perp
            best_dist_along = cumulative_dist + t * seg_len

        cumulative_dist += seg_len

    return (best_dist_along, best_perp)


def project_trip(
    trip: "Trip",
    shape_points: list[tuple[float, float]],
    max_perp_error_m: float = MAX_PERP_ERROR_M,
) -> "Trip":
    """
    Proyecta todos los puntos del trip sobre el shape.
    Rellena dist_along_shape_m y perp_error_m en cada TripPoint.
    Descarta (elimina de trip.points) los puntos donde perp_error_m > max_perp_error_m.
    Retorna el trip modificado.
    """
    valid_points = []
    for pt in trip.points:
        dist_along, perp_error = project_to_shape(pt.lat, pt.lon, shape_points)
        pt.dist_along_shape_m = dist_along
        pt.perp_error_m = perp_error
        if perp_error <= max_perp_error_m:
            valid_points.append(pt)
    trip.points = valid_points
    return trip
