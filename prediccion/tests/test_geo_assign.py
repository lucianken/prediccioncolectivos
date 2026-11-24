"""Asignación geométrica geo3 (prediccion/v2/geo_assign.py): comportamiento de las primitivas y del pipeline."""

import math

import numpy as np

from prediccion.pipeline.projector import ShapeIndex
from prediccion.v2 import geo_assign as G
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


def _ids(res):
    return {r[0] for r in res}


def test_calle_paralela_a_100_m_no_es_compatible():
    la, lo = _pt(1000, 3)
    assert _ids(G.compatible_shapes(la, lo, _line())) == {"ida", "vuelta"}
    la, lo = _pt(1000, 107)          # el coche va por la calle paralela
    assert _ids(G.compatible_shapes(la, lo, _line())) == {"paralela"}


def test_el_margen_descarta_la_paralela_aunque_la_tolerancia_la_admita():
    # con una tolerancia amplia (150 m, la de antes) el coche sobre la calle de abajo igual se asigna solo a ella
    la, lo = _pt(1000, 30)
    assert _ids(G.compatible_shapes(la, lo, _line(), tol_m=150.0)) == {"ida", "vuelta"}
    # sin margen efectivo (margen enorme) la paralela, a 80 m, vuelve a ser compatible: el margen es lo que la saca
    assert "paralela" in _ids(G.compatible_shapes(la, lo, _line(), tol_m=150.0, margin_m=500.0))


def test_ruido_gps_de_10_m_sigue_siendo_compatible():
    for north in (-10, 10):
        la, lo = _pt(1500, north)
        res = G.compatible_shapes(la, lo, _line())
        assert {"ida", "vuelta"} <= _ids(res)
        assert all(p <= 10.5 for _, p, _ in res)


def test_ida_y_vuelta_por_la_misma_calle_son_ambas_compatibles_y_el_sentido_sale_del_historial():
    shapes = _line()
    # el coche avanza hacia el este: 5 pings cada 150 m, uno por minuto
    pings = [(1000 + 60 * i, *_pt(500 + 150 * i, 2)) for i in range(5)]
    la, lo = pings[-1][1:]
    assert _ids(G.compatible_shapes(la, lo, shapes)) >= {"ida", "vuelta"}
    assert G.direction_from_history(pings, shapes["ida"]) == (True, None)
    ok, why = G.direction_from_history(pings, shapes["vuelta"])
    assert not ok and why == "sentido_incoherente"


def test_sin_historial_o_coche_quieto_no_hay_sentido():
    shapes = _line()
    p = (1000, *_pt(800, 0))
    assert G.direction_from_history([p], shapes["ida"]) == (False, "sin_sentido")
    quieto = [(1000 + 60 * i, *_pt(800 + i, 0)) for i in range(5)]
    assert G.direction_from_history(quieto, shapes["ida"]) == (False, "sin_sentido")


def test_coche_recien_salido_de_cabecera_con_pings_viejos_fuera_del_shape_va_hacia_adelante():
    shapes = _line()
    fuera = [(1000 + 60 * i, *_pt(100, 300)) for i in range(4)]            # esperando en otra calle, a 300 m del shape
    sobre = [(1240 + 60 * i, *_pt(150 + 150 * i, 2)) for i in range(3)]    # ya sobre el shape, avanzando al este
    assert G.direction_from_history(fuera + sobre, shapes["ida"]) == (True, None)
    ok, why = G.direction_from_history(fuera + sobre, shapes["vuelta"])
    assert not ok and why == "sentido_incoherente"


def test_coche_que_retrocede_es_incoherente():
    shapes = _line()
    atras = [(1000 + 60 * i, *_pt(1500 - 150 * i, 2)) for i in range(5)]
    assert G.direction_from_history(atras, shapes["ida"]) == (False, "sentido_incoherente")
    assert G.direction_from_history(atras, shapes["vuelta"]) == (True, None)


def test_un_solo_ping_sobre_el_shape_no_alcanza_aunque_haya_pings_lejos():
    shapes = _line()
    pings = [(1000 + 60 * i, *_pt(500 + 150 * i, 300)) for i in range(4)] + [(1240, *_pt(1100, 2))]
    assert G.direction_from_history(pings, shapes["ida"]) == (False, "sin_sentido")


def test_ping_actual_fuera_del_shape_no_tiene_sentido_sobre_ese_shape():
    shapes = _line()
    pings = [(1000 + 60 * i, *_pt(500 + 150 * i, 2)) for i in range(4)] + [(1240, *_pt(1100, 300))]
    assert G.direction_from_history(pings, shapes["ida"]) == (False, "sin_sentido")


def test_mas_pings_consecutivos_validos_no_vuelven_incoherente_a_un_coche_que_va_hacia_adelante():
    shapes = _line()
    todos = [(1000 + 60 * i, *_pt(300 + 120 * i, 2 + (i % 3))) for i in range(12)]
    for n in range(2, 13):
        assert G.direction_from_history(todos[-n:], shapes["ida"]) == (True, None), n


def test_retroceso_real_tras_avanzar_se_detecta_con_mas_historial():
    shapes = _line()
    ida = [(1000 + 60 * i, *_pt(300 + 150 * i, 2)) for i in range(4)]
    vuelta = [(1240 + 60 * i, *_pt(750 - 150 * i, 2)) for i in range(1, 5)]
    assert G.direction_from_history(ida + vuelta, shapes["ida"]) == (False, "sentido_incoherente")


def test_el_historial_viejo_no_cuenta():
    shapes = _line()
    viejo = [(0, *_pt(100, 0)), (60, *_pt(250, 0)), (120, *_pt(400, 0))]
    actual = (5000, *_pt(405, 0))        # 80 min despues: los pings viejos quedan fuera de la ventana
    assert G.direction_from_history(viejo + [actual], shapes["ida"]) == (False, "sin_sentido")


def test_aceptar_pings_como_dict_o_tupla_da_lo_mismo():
    shapes = _line()
    t = [(60 * i, *_pt(500 + 150 * i, 0)) for i in range(5)]
    d = [{"ts": a, "lat": b, "lon": c} for a, b, c in t]
    assert G.direction_from_history(t, shapes["ida"]) == G.direction_from_history(d, shapes["ida"])


def test_mascaras_vectorizadas_coinciden_con_la_version_por_ping():
    shapes = _line()
    rng = np.random.default_rng(0)
    east = rng.uniform(100, 2800, 200)
    north = rng.uniform(-30, 140, 200)
    pts = [_pt(e, n) for e, n in zip(east, north)]
    lats = np.array([p[0] for p in pts])
    lons = np.array([p[1] for p in pts])
    perps = {sid: ix.project_many(lats, lons)[1] for sid, ix in shapes.items()}
    masks = G.compat_masks(perps)
    for i, (la, lo) in enumerate(pts):
        scalar = _ids(G.compatible_shapes(la, lo, shapes))
        assert scalar == {s for s, m in masks.items() if m[i]}


# ── sentido por geometría (sin historial) ───────────────────────────────────

def _ns(east_m: float, north_from: float, north_to: float):
    """Calle norte-sur a `east_m` metros al este de LON0, de north_from a north_to (en ese sentido), un punto cada 100 m."""
    step = 100.0 if north_to > north_from else -100.0
    return [_pt(east_m, n) for n in np.arange(north_from, north_to + step / 2, step)]


def test_calle_de_un_solo_sentido_da_el_sentido_por_geometria_sin_historial():
    # par de calles de mano única: la ida por una calle, la vuelta por la paralela a 110 m
    shapes = {"ida": ShapeIndex(_ew(0)), "vuelta": ShapeIndex(_ew(110, reverse=True))}
    la, lo = _pt(1500, 4)
    assert _ids(G.compatible_shapes(la, lo, shapes)) == {"ida"}
    assert G.direction_from_geometry(la, lo, shapes) is True
    # el mismo coche, sobre la calle de la vuelta
    la, lo = _pt(1500, 106)
    assert G.direction_from_geometry(la, lo, shapes) is True


def test_ida_y_vuelta_por_la_misma_calle_requiere_historial():
    shapes = _line()
    la, lo = _pt(1500, 2)
    assert G.direction_from_geometry(la, lo, shapes) is False
    # sin historial el sentido sigue desconocido en cada shape
    assert G.direction_from_history([(1000, la, lo)], shapes["ida"]) == (False, "sin_sentido")


def test_tronco_compartido_en_un_solo_sentido_da_el_sentido_aunque_despues_se_bifurquen():
    # dos ramales van juntos hacia el este por la misma calle y después uno dobla al norte
    tronco = _ew(0, length_m=2000)
    a = ShapeIndex(tronco + [_pt(2000 + x, 0) for x in (100.0, 200.0, 300.0)])
    b = ShapeIndex(tronco + _ns(2000, 100, 1000))
    shapes = {"a": a, "b": b}
    la, lo = _pt(1000, 3)
    assert _ids(G.compatible_shapes(la, lo, shapes)) == {"a", "b"}
    assert G.direction_from_geometry(la, lo, shapes) is True


def test_recorrido_que_pasa_dos_veces_por_la_misma_calle_en_sentidos_opuestos_requiere_historial():
    # un solo shape que va y vuelve por la misma calle (cabecera en el extremo): su orientación ahí no es única
    loop = ShapeIndex(_ew(0, length_m=2000) + _ew(5, reverse=True, length_m=2000))
    la, lo = _pt(1000, 2)
    assert G.direction_from_geometry(la, lo, {"x": loop}) is False


def test_recorridos_cruzados_no_dan_sentido_por_geometria():
    # en un cruce, un shape va al este y otro al norte: rumbos a 90 grados, no se decide por geometría
    shapes = {"este": ShapeIndex(_ew(0)), "norte": ShapeIndex(_ns(1500, -1500, 1500))}
    la, lo = _pt(1500, 0)
    assert _ids(G.compatible_shapes(la, lo, shapes)) == {"este", "norte"}
    assert G.direction_from_geometry(la, lo, shapes) is False


def test_coche_lejos_de_todo_recorrido_no_tiene_sentido_por_geometria():
    la, lo = _pt(1500, 400)
    assert G.direction_from_geometry(la, lo, _line()) is False


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


# ── contrato de inferencia ──────────────────────────────────────────────────

def test_un_export_con_otros_parametros_de_asignacion_se_rechaza(tmp_path):
    import json

    import pytest

    from prediccion.inference.path_reference import load_bundle
    man = {"contract_version": "2.0", "constants": {"m_per_deg_lat": M}, "lines": {},
           "assignment": {**G.manifest_params(), "tol_m": G.TOL_M + 100.0}}
    (tmp_path / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    with pytest.raises(ValueError, match="asignación"):
        load_bundle(tmp_path)
