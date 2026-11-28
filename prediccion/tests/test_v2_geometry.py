"""best_shape_for_trip (opción A, ARQUITECTURA.md §4.1)."""

import numpy as np

from prediccion.pipeline.projector import best_shape_for_trip
from red.geometria import ShapeIndex

LON = -58.40
DLAT = 0.0015


def _stem(n=30):
    return [(-34.70 + i * DLAT, LON) for i in range(n)]


def _branch_north(n_stem=30, n=30):
    s = _stem(n_stem)
    last = s[-1]
    return s + [(last[0] + i * DLAT, LON) for i in range(1, n)]


def _branch_east(n_stem=30, n=30):
    s = _stem(n_stem)
    last = s[-1]
    return s + [(last[0], LON + i * 0.0017) for i in range(1, n)]


def _indices():
    return {"north": ShapeIndex(_branch_north()), "east": ShapeIndex(_branch_east())}


def _trip(points):
    pts = np.array(points)
    return pts[:, 0], pts[:, 1]


def test_elige_el_ramal_correcto_tras_la_divergencia():
    idx = _indices()
    lats, lons = _trip(_branch_east())
    sid, med = best_shape_for_trip(lats, lons, idx)
    assert sid == "east"
    assert med < 5.0
    lats, lons = _trip(_branch_north())
    assert best_shape_for_trip(lats, lons, idx)[0] == "north"


def test_tramo_compartido_no_se_rompe_y_devuelve_un_ramal_valido_con_error_bajo():
    idx = _indices()
    lats, lons = _trip(_stem())
    sid, med = best_shape_for_trip(lats, lons, idx)
    assert sid in idx
    assert med < 5.0           # ambos recorridos explican el viaje: la elección es arbitraria pero válida


def test_sin_recorridos_o_sin_puntos():
    assert best_shape_for_trip([-34.6], [-58.4], {}) == (None, float("inf"))
    assert best_shape_for_trip([], [], _indices()) == (None, float("inf"))


def test_prefiltro_con_muchos_recorridos_elige_lo_mismo_que_el_completo():
    idx = _indices()
    # 4 recorridos más, lejanos, para activar el prefiltro (prescreen_keep=3)
    for k in range(4):
        idx[f"far{k}"] = ShapeIndex([(-34.5 + i * DLAT, -58.20 + k * 0.05) for i in range(40)])
    lats, lons = _trip(_branch_east())
    assert best_shape_for_trip(lats, lons, idx)[0] == "east"


def test_viaje_de_vuelta_no_se_proyecta_sobre_la_ida_aunque_compartan_calles():
    ida = ShapeIndex(_stem(40))
    vuelta = ShapeIndex(list(reversed(_stem(40))))
    idx = {"ida": ida, "vuelta": vuelta}
    # el coche baja por la misma calle: perp ~0 en ambos, pero solo "vuelta" avanza hacia adelante
    lats, lons = _trip(list(reversed(_stem(40))))
    assert best_shape_for_trip(lats, lons, idx)[0] == "vuelta"
    lats, lons = _trip(_stem(40))
    assert best_shape_for_trip(lats, lons, idx)[0] == "ida"


def test_si_ningun_recorrido_es_valido_igual_devuelve_el_de_menor_error():
    idx = {"a": ShapeIndex(_stem(40))}
    lats, lons = _trip(list(reversed(_stem(40))))       # va al revés y no hay alternativa
    sid, med = best_shape_for_trip(lats, lons, idx)
    assert sid == "a" and med < 5.0
