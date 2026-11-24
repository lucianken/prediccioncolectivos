"""T en paradas reales: asociación parada-recorrido, hora de paso interpolada y pares (P, parada)."""
import numpy as np
import pytest

from prediccion.v2 import stop_targets as ST
from prediccion.v2.rows import trip_rows

M = 1 / 111_320.0   # grados de latitud por metro


def _line(lat0, lon, length_m, n=11):
    return [(lat0 + i * length_m / (n - 1) * M, lon) for i in range(n)]


def test_hora_de_paso_interpolada_entre_los_dos_pings_que_encierran_la_parada():
    ts = np.array([0, 60, 120, 180], dtype=np.int64)
    dist = np.array([0.0, 500.0, 1000.0, 1500.0])
    k, tc = ST.stop_crossings(ts, dist, None, 750.0)
    assert k.tolist() == [1] and tc == pytest.approx([90.0])


def test_no_interpola_a_traves_de_un_hueco_largo_ni_de_un_salto_de_gps():
    dist = np.array([0.0, 500.0, 1000.0])
    assert len(ST.stop_crossings(np.array([0, 60, 900]), dist, None, 750.0)[0]) == 0     # 14 min entre pings
    assert len(ST.stop_crossings(np.array([0, 60, 70]), np.array([0.0, 500.0, 5000.0]), None, 2000.0)[0]) == 0  # salto
    seg = np.array([0, 0, 1])
    assert len(ST.stop_crossings(np.array([0, 60, 120]), dist, seg, 750.0)[0]) == 0     # tramos continuos distintos


def test_pares_solo_en_paradas_con_etiqueta_igual_a_la_hora_de_paso():
    ts = np.arange(0, 600, 30, dtype=np.int64)
    dist = ts * 10.0                                   # 10 m/s
    stops = np.array([1000.0, 2500.0, 5000.0])
    pi, d_t, t_t = ST.stop_pair_targets(dist, ts, stops, 10_000.0, 1000, 1)
    assert set(np.unique(d_t)) <= set(stops)
    assert np.all(d_t - dist[pi] >= 100.0)             # distancia mínima del pipeline
    assert t_t == pytest.approx(d_t / 10.0)            # la parada se cruza a 10 m/s
    assert np.all(t_t > ts[pi])


def test_no_hay_par_con_P_despues_de_la_parada_ni_parada_no_cruzada():
    ts = np.arange(0, 300, 30, dtype=np.int64)
    dist = ts * 10.0                                   # el coche llega hasta 2970 m
    r = ST.stop_pair_targets(dist, ts, np.array([500.0, 9000.0]), 20_000.0, 100, 0)
    assert set(np.unique(r[1])) == {500.0}
    assert dist[r[0]].max() <= 400.0


def test_muestreo_reproducible_y_tope_k():
    ts = np.arange(0, 1800, 30, dtype=np.int64)
    dist = ts * 8.0
    stops = np.arange(300.0, 14000.0, 300.0)
    a = ST.stop_pair_targets(dist, ts, stops, 20_000.0, 32, 7)
    b = ST.stop_pair_targets(dist, ts, stops, 20_000.0, 32, 7)
    assert len(a[0]) <= 32 and all(np.array_equal(x, y) for x, y in zip(a, b))


def test_mezcla_aporta_pares_en_paradas_y_en_puntos_cualquiera():
    ts = np.arange(0, 1800, 30, dtype=np.int64)
    dist = ts * 8.0
    stops = np.array([3000.0, 6000.0, 9000.0])
    pi, d_t, t_t = ST.mixed_targets(dist, ts, stops, 20_000.0, 32, 3, None, 0.5)
    en_parada = np.isin(d_t, stops)
    assert 0 < en_parada.sum() < len(pi)


def test_parada_se_asocia_solo_por_pertenencia_a_la_lista_del_propio_recorrido():
    ida = _line(-34.60, -58.40, 2000)
    ida2 = [(la, lo + 0.00005) for la, lo in ida]            # otro ramal del mismo sentido, a ~5 m
    s = {"id": "A", "lat": -34.60 + 1000 * M, "lng": -58.40 + 0.00005}
    r = ST.associate_stops({"ida": ida, "ida2": ida2}, {"ida2": [s]})
    assert len(r["ida"]) == 0                                  # pasa a 5 m pero no figura en su lista: no para ahí
    assert r["ida2"] == pytest.approx([1000.0], abs=3)


def test_paradas_duplicadas_del_mismo_poste_cuentan_una():
    ida = _line(-34.60, -58.40, 2000)
    st = [{"id": "A", "lat": -34.60 + 1000 * M, "lng": -58.40}, {"id": "B", "lat": -34.60 + 1003 * M, "lng": -58.40}]
    assert len(ST.associate_stops({"ida": ida}, {"ida": st})["ida"]) == 1


def test_ruido_de_interpolacion_es_cero_si_el_coche_va_a_velocidad_constante():
    ts = np.arange(0, 600, 60, dtype=np.int64)
    e = ST.interpolation_noise(ts, ts * 9.0)
    assert len(e) and np.abs(e).max() < 1e-6


def test_trip_rows_con_targets_usa_distancia_y_etiqueta_dados():
    ts = np.arange(0, 600, 30, dtype=np.int64)
    dist = ts * 10.0
    tg = ST.stop_pair_targets(dist, ts, np.array([2000.0]), 10_000.0, 50, 0)
    cols = trip_rows(line="1", shape_id="s", shape_length_m=10_000.0, vehicle_id="v", ts=ts, frame_ts=ts,
                     speed=np.full(len(ts), 10.0), dist=dist, k_pairs=50, seed=0, targets=tg)
    assert cols["dist_remaining_m"] == pytest.approx(2000.0 - dist[tg[0]])
    assert cols["observed_eta_s"] == pytest.approx(200.0 - ts[tg[0]])
