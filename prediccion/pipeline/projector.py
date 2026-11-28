from typing import TYPE_CHECKING

import numpy as np

# ShapeIndex y haversine_m viven en el paquete `red` (bondi/red, F1.5).
from red.geometria import ShapeIndex, haversine_m

if TYPE_CHECKING:
    from .segmenter import Trip

MAX_PERP_ERROR_M = 150.0


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


def _forward_fraction(dists: "np.ndarray", perps: "np.ndarray", max_perp_error_m: float) -> float:
    """Fracción del avance neto que va en el sentido del recorrido (definición única: red.geo_assign)."""
    from red.geo_assign import forward_fraction
    return forward_fraction(dists, perps, max_perp_error_m)


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
