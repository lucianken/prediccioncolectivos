"""Segmentador geométrico de viajes (sin trip_id, start_time ni route_id)."""

import numpy as np

from red.geometria import ShapeIndex
from prediccion.v2.segmenter import segment_geometric

LON = -58.40
STEP = 0.0015          # ~167 m
M_PER_DEG = 111_320.0


def _shape(n=60):
    return [(-34.70 + i * STEP, LON) for i in range(n)]


IDX = {"ida": ShapeIndex(_shape()), "vuelta": ShapeIndex(list(reversed(_shape())))}


def _lat(i):
    return -34.70 + i * STEP


def _pings(path_idx, t0=1_790_000_000, dt=60, jitter=0.0, seed=0):
    """path_idx: posiciones en 'pasos de shape' (float). Pings sin trip_id/start_time (strings vacíos)."""
    rng = np.random.default_rng(seed)
    out = []
    for k, p in enumerate(path_idx):
        lat = _lat(p) + rng.normal(0, jitter) / M_PER_DEG
        out.append((t0 + k * dt, lat, LON, 5.0, 0, 0, "", "", t0 + k * dt, False, ""))
    return out


def _ts(trip):
    return [p.ts for p in trip.points]


def test_ida_y_vuelta_corta_en_el_punto_de_inversion():
    up = list(np.arange(0, 36, 1.0))               # sube 36 pasos (~6 km), sin llegar al final del shape
    down = list(np.arange(35, -1, -1.0))           # y baja por la misma calle
    trips = segment_geometric("v", _pings(up + down), IDX)
    assert len(trips) == 2
    peak_ts = 1_790_000_000 + 35 * 60
    assert abs(trips[0].points[-1].ts - peak_ts) <= 60              # el primero termina en la inversión
    assert abs(trips[1].points[0].ts - peak_ts) <= 60               # el segundo arranca ahí
    assert trips[0].points[-1].lat > trips[0].points[0].lat         # primero sube
    assert trips[1].points[-1].lat < trips[1].points[0].lat         # segundo baja


def test_parada_larga_en_terminal_no_genera_viaje_fantasma():
    ida = list(np.arange(0, 60, 1.0))                              # llega al final del recorrido
    parked = [59.0] * 20                                           # 20 min detenido en la terminal
    vuelta = list(np.arange(58, 5, -1.0))
    trips = segment_geometric("v", _pings(ida + parked + vuelta, jitter=3.0), IDX)
    assert len(trips) == 2                                         # ida y vuelta; los 20 pings parados no son un viaje
    t0 = 1_790_000_000
    last_parked_ts = t0 + (60 + 19) * 60
    # el segundo viaje arranca en la salida de la cabecera (último ping parado), no en el primero parado
    assert trips[1].points[0].ts >= last_parked_ts - 60
    # y no arrastra pings parados al inicio
    lats = [p.lat for p in trips[1].points]
    assert sum(abs(a - b) * M_PER_DEG < 25 for a, b in zip(lats, lats[1:])) <= 2


def test_ruido_gps_y_retrocesos_chicos_no_cortan():
    path = list(np.arange(0, 50, 1.0))
    path[10] -= 0.5                                                # retroceso de ~80 m
    path[20] -= 1.0                                                # ~170 m, un solo ping
    path[30] -= 1.7                                                # ~280 m, un solo ping (no sostenido)
    trips = segment_geometric("v", _pings(path, jitter=4.0), IDX)
    assert len(trips) == 1
    assert len(trips[0].points) >= 48


def test_un_hueco_de_datos_corta():
    a = _pings(list(np.arange(0, 20, 1.0)))
    b = _pings(list(np.arange(20, 40, 1.0)), t0=a[-1][0] + 6 * 60)  # 6 min sin datos
    trips = segment_geometric("v", a + b, IDX)
    assert len(trips) == 2
    assert trips[0].points[-1].ts == a[-1][0] and trips[1].points[0].ts == b[0][0]


def test_no_usa_trip_id_ni_start_time():
    path = list(np.arange(0, 40, 1.0))
    sin = _pings(path)
    con = [o[:6] + ("20260916", f"0{k % 7}:00:00") + o[8:] for k, o in enumerate(sin)]   # start_time caótico
    a = segment_geometric("v", sin, IDX)
    b = segment_geometric("v", con, IDX)
    assert [(_ts(t)[0], _ts(t)[-1]) for t in a] == [(_ts(t)[0], _ts(t)[-1]) for t in b]


def test_coche_fuera_de_todo_recorrido_no_genera_viajes():
    far = [(1_790_000_000 + k * 60, -34.2 + k * STEP, -58.0, 5.0, 0, 0, "", "", 0, False, "") for k in range(30)]
    assert segment_geometric("v", far, IDX) == []


def test_coche_horas_quieto_en_el_deposito_y_luego_un_viaje_da_un_solo_viaje():
    t0 = 1_790_000_000
    rng = np.random.default_rng(1)
    depot_lon = LON + 800 / (M_PER_DEG * np.cos(np.radians(-34.7)))      # 800 m al costado del recorrido
    pings = [(t0 + k * 60, -34.70 + rng.normal(0, 3) / M_PER_DEG, depot_lon + rng.normal(0, 3e-5), 0.0, 0, 0,
              "", "", t0 + k * 60, False, "") for k in range(240)]       # 4 h quieto en el depósito
    tt = t0 + 240 * 60
    # sale del depósito: 3 pings hasta el recorrido y luego recorre 40 pasos
    for k, (la, lo) in enumerate([(-34.7, depot_lon), (-34.7, LON + 4e-4), (-34.7, LON)]):
        pings.append((tt + k * 60, la, lo, 3.0, 0, 0, "", "", tt + k * 60, False, ""))
    t_enter = tt + 2 * 60
    for k in range(1, 41):
        pings.append((t_enter + k * 60, _lat(k), LON, 6.0, 0, 0, "", "", t_enter + k * 60, False, ""))
    trips = segment_geometric("v", pings, IDX)
    assert len(trips) == 1
    # el viaje empieza al entrar al recorrido (no hay pings del depósito) y time_since_start se cuenta desde ahí
    assert trips[0].points[0].ts >= t_enter - 60
    assert all(abs(p.lon - depot_lon) * M_PER_DEG * 0.82 > 100 for p in trips[0].points)
    from prediccion.v2.segmenter import segment_geometric as sg
    _, st = sg("v", pings, IDX, return_stats=True)
    assert st["depot"] >= 230
