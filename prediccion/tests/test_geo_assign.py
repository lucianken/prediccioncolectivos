"""Asignación geo3 en el pipeline (`geometry_for_trip`). Las primitivas de asignación y sentido son de `red.geo_assign` y
se prueban en bondi/red/python/tests/test_geo_assign.py."""

import math

import numpy as np

from red.geometria import ShapeIndex
from prediccion.v2.day import geometry_for_trip

M = 111_320.0
LAT0 = -34.60
LON0 = -58.50
KM = 3000.0


def _ew(north_m: float, reverse: bool = False, length_m: float = KM):
    """Calle este-oeste a `north_m` metros al norte de LAT0, de ~3 km, con un punto cada ~100 m."""
    mlon = M * math.cos(math.radians(LAT0))
    pts = [(LAT0 + north_m / M, LON0 + x / mlon) for x in np.arange(0, length_m + 1, 100.0)]
    return pts[::-1] if reverse else pts


def _pt(east_m: float, north_m: float):
    return LAT0 + north_m / M, LON0 + east_m / (M * math.cos(math.radians(LAT0)))


def _line():
    return {"ida": ShapeIndex(_ew(0)), "vuelta": ShapeIndex(_ew(0, reverse=True)),
            "paralela": ShapeIndex(_ew(110))}


# ── pipeline: máscara `valid` de geometry_for_trip ──────────────────────────

class _P:
    def __init__(self, lat, lon):
        self.lat, self.lon = lat, lon


class _Trip:
    def __init__(self, pts):
        self.points = [_P(*p) for p in pts]


def _trip_ida(offsets):
    """Viaje por la ida, un ping cada 100 m; offsets[i] = desvío norte del ping i (m)."""
    return _Trip([_pt(100.0 * i, off) for i, off in enumerate(offsets)])


def test_geo3_los_pings_que_van_por_la_calle_paralela_no_generan_filas():
    idx = _line()
    offs = [2.0] * 30
    for i in range(10, 15):
        offs[i] = 107.0                  # cinco pings en la calle paralela (el coche dobla y vuelve)
    trip = _trip_ida(offs)
    legacy = geometry_for_trip(trip, idx)                       # tolerancia de 150 m (comportamiento anterior)
    geo3 = geometry_for_trip(trip, idx, assign="geo3")
    assert legacy["valid"].all()                                # antes entraban todos
    assert geo3["shape_id"] == "ida"
    assert not geo3["valid"][10:15].any()
    assert geo3["valid"].sum() == 25


def test_geo3_elige_el_recorrido_del_viaje_solo_entre_los_compatibles():
    idx = _line()
    trip = _Trip([_pt(100.0 * i, 108.0 + (i % 3)) for i in range(30)])   # todo el viaje por la paralela
    g = geometry_for_trip(trip, idx, assign="geo3")
    assert g["shape_id"] == "paralela"
    assert g["valid"].all()


def test_geo3_ida_y_vuelta_misma_calle_elige_el_sentido_del_viaje():
    idx = _line()
    ida = _trip_ida([1.0] * 30)
    assert geometry_for_trip(ida, idx, assign="geo3")["shape_id"] == "ida"
    vuelta = _Trip([_pt(KM - 100.0 * i, 1.0) for i in range(30)])
    assert geometry_for_trip(vuelta, idx, assign="geo3")["shape_id"] == "vuelta"
