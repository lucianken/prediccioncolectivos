"""Muestreo de K pares por viaje (ARQUITECTURA.md §4.2) y equivalencia con el generador viejo."""

import numpy as np

from prediccion.pipeline.features import encode_time, make_training_rows_eta
from prediccion.pipeline.segmenter import Trip, TripPoint
from prediccion.v2.pairs import DIST_EDGES_M, sample_pairs, trip_seed
from prediccion.v2.rows import encode_time_np, trip_rows


def _long_trip(n=120, step_m=150.0, dt=60):
    dist = np.arange(n) * step_m            # ~18 km
    ts = 1_790_000_000 + np.arange(n) * dt
    return dist, ts


def _bucket(d):
    return int(np.searchsorted(np.asarray(DIST_EDGES_M[1:]), d, side="right"))


def test_respeta_k_y_es_determinista():
    dist, ts = _long_trip()
    a = sample_pairs(dist, ts, 64, seed=7)
    b = sample_pairs(dist, ts, 64, seed=7)
    assert len(a[0]) == 64
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    c = sample_pairs(dist, ts, 64, seed=8)
    assert not (np.array_equal(a[0], c[0]) and np.array_equal(a[1], c[1]))


def test_pares_validos_p_antes_de_f_con_distancia_minima_y_eta_positivo():
    dist, ts = _long_trip()
    i, j = sample_pairs(dist, ts, 64, seed=1)
    assert np.all(j > i)
    assert np.all(dist[j] - dist[i] >= 100.0)
    assert np.all(ts[j] > ts[i])
    assert len(set(zip(i.tolist(), j.tolist()))) == len(i)       # sin repetidos


def test_cubre_todos_los_buckets_de_distancia_sin_sesgo_a_las_largas():
    dist, ts = _long_trip()
    i, j = sample_pairs(dist, ts, 64, seed=3)
    counts = np.bincount([_bucket(d) for d in dist[j] - dist[i]], minlength=5)
    assert (counts > 0).all()
    # con ~120 puntos y 18 km el bucket 5+ km tendría ~65 % de TODOS los pares; acá queda parejo (~k/5)
    assert counts.max() <= 2 * counts.min() + 4
    assert counts[4] < 0.4 * 64


def test_si_un_bucket_no_tiene_candidatos_el_resto_se_reparte():
    dist = np.arange(30) * 150.0            # 4,3 km: no hay pares de 5+ km
    ts = 1_790_000_000 + np.arange(30) * 60
    i, j = sample_pairs(dist, ts, 64, seed=0)
    assert len(i) == 64
    assert max(_bucket(d) for d in dist[j] - dist[i]) <= 3


def test_menos_candidatos_que_k_devuelve_todos():
    dist = np.array([0.0, 150.0, 300.0, 450.0, 600.0])
    ts = 1_790_000_000 + np.arange(5) * 60
    i, j = sample_pairs(dist, ts, 64, seed=0)
    all_pairs = {(a, b) for a in range(5) for b in range(a + 1, 5) if dist[b] - dist[a] >= 100}
    assert set(zip(i.tolist(), j.tolist())) == all_pairs


def test_semilla_por_viaje_depende_del_viaje():
    assert trip_seed("2026-09-16", "v1", 100) == trip_seed("2026-09-16", "v1", 100)
    assert trip_seed("2026-09-16", "v1", 100) != trip_seed("2026-09-16", "v2", 100)


def test_encode_time_vectorizado_igual_al_original():
    ts = np.array([1_790_000_000, 1_790_003_601, 1_790_050_000, 1_773_583_200])
    hs, hc, dow = encode_time_np(ts)
    for k, t in enumerate(ts):
        ref = encode_time(int(t))
        assert abs(hs[k] - ref["hour_sin"]) < 1e-9 and abs(hc[k] - ref["hour_cos"]) < 1e-9
        assert dow[k] == ref["dow"]


def test_cada_fila_muestreada_es_una_fila_del_generador_viejo():
    """El v2 solo submuestrea: valores por fila equivalentes a make_training_rows_eta."""
    n = 40
    dist, ts = _long_trip(n)
    speed = np.linspace(2, 9, n)
    pts = [TripPoint(ts=int(ts[k]), lat=-34.6, lon=-58.4, speed=float(speed[k]), odo=0,
                     dist_along_shape_m=float(dist[k]), perp_error_m=5.0, frame_ts=int(ts[k]) + 7)
           for k in range(n)]
    trip = Trip(vehicle_id="v", route_id="r", direction_id=0, start_time=int(ts[0]), points=pts, line_number="39")
    L = 9000.0
    old = make_training_rows_eta(trip, "S", L)
    cols = trip_rows(line="39", shape_id="S", shape_length_m=L, vehicle_id="v", ts=ts, frame_ts=ts + 7,
                     speed=speed, dist=dist, k_pairs=25, seed=5)
    assert len(cols["ts_p"]) == 25
    for r in range(25):
        found = any(
            abs(float(cols["dist_remaining_m"][r]) - o["dist_remaining_m"]) < 0.5
            and float(cols["observed_eta_s"][r]) == o["observed_eta_s"]
            and abs(float(cols["dist_along_norm"][r]) - o["dist_along_norm"]) < 1e-4
            and np.allclose(cols["traj_flat"][r], o["traj_flat"], atol=1e-2)
            and float(cols["time_since_start"][r]) == o["time_since_start"]
            and float(cols["ts_age_s"][r]) == o["ts_age_s"]
            and int(cols["traj_len"][r]) == o["traj_len"]
            and abs(float(cols["speed_mps"][r]) - o["speed_mps"]) < 1e-3
            for o in old)
        assert found, f"fila {r} no existe en el generador viejo"
