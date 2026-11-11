"""Tabla de tránsito v2: celdas = las de CityGridEncoder, ventana en hora de BA, depósito, máscara de recorridos."""

import numpy as np
import pytest
import torch

from prediccion.models.a3_eta import CityGridEncoder
from prediccion.v2.traffic.day import aggregate, build_route_tree, window_of
from prediccion.v2.traffic.grid import cell_index, grid_from_encoder
from prediccion.v2.traffic.mask import cell_lookup, cells_of_polylines, densify

GRID = grid_from_encoder(500.0)


def test_cell_matches_city_grid_encoder():
    # Embedding de 1 dim con valor = id de vértice: en la esquina inferior de una celda el encoder devuelve su id.
    enc = CityGridEncoder(cell_m=500.0, dim=1)
    with torch.no_grad():
        enc.embed.weight[:, 0] = torch.arange(enc.embed.num_embeddings, dtype=torch.float32)
    assert (enc.n_lat, enc.n_lon) == (GRID.n_lat, GRID.n_lon)
    rng = np.random.default_rng(0)
    i = rng.integers(0, GRID.n_lat, 50)
    j = rng.integers(0, GRID.n_lon, 50)
    eps = 1e-3   # un poquito adentro de la celda
    lat = GRID.lat_min + (i + eps) * (GRID.lat_max - GRID.lat_min) / GRID.n_lat
    lon = GRID.lon_min + (j + eps) * (GRID.lon_max - GRID.lon_min) / GRID.n_lon
    with torch.no_grad():
        got = enc.encode(torch.tensor(lat), torch.tensor(lon))[:, 0].numpy()
    ids = cell_index(GRID, lat, lon)
    assert np.array_equal(ids, i * GRID.stride + j)
    assert np.allclose(got, ids, atol=0.5)   # interpolación casi en el vértice inferior


def test_window_uses_buenos_aires_time():
    # 2026-09-16 03:00 UTC = 00:00 BA -> ventana 0; 14:00 UTC = 11:00 BA = minuto 660 -> ventana 330 (2 min)
    midnight_ba = 1789527600
    assert window_of(midnight_ba, 2) == 0
    assert window_of(midnight_ba + 11 * 3600, 2) == 330
    assert window_of(midnight_ba + 11 * 3600 + 119, 1) == 660 + 1
    # 02:59 UTC es el día anterior (23:59 BA): ventana final, no 02:59 * 30
    assert window_of(midnight_ba - 60, 2) == 719


def _route():
    lat = np.full(200, -34.60)
    lon = np.linspace(-58.45, -58.35, 200)
    return np.column_stack([lat, lon])


def _args(window_min=2):
    route = densify(_route())
    cells = cells_of_polylines(GRID, [_route()])
    tree, cos = build_route_tree(route.astype(np.float32))
    return dict(grid=GRID, window_min=window_min, cell_ok=cell_lookup(GRID, cells), route_tree=tree, route_cos=cos)


def _car(vid, lat, lon, t0, step_m):
    """Coche con 4 pings cada 60 s, avanzando step_m metros hacia el este por ping."""
    n = 4
    ts = t0 + 60 * np.arange(n)
    return (np.full(n, vid, np.int32), ts, np.full(n, lat), lon + np.arange(n) * step_m / (111_320 * np.cos(np.radians(lat))))


def _cat(*cars):
    return tuple(np.concatenate(x) for x in zip(*cars))


def test_moving_car_speed_from_displacement():
    t0 = 1789527600 + 36000
    vid, ts, lat, lon = _car(1, -34.60, -58.40, t0, 600.0)    # 600 m / 60 s = 10 m/s
    win, cell, speed, n, n_stopped = aggregate(vid, ts, lat, lon, **_args())
    assert n.sum() >= 3 and n_stopped.sum() == 0
    assert np.nanmean(speed) == pytest.approx(10.0, rel=0.02)


def test_stopped_car_far_from_routes_is_depot_not_counted():
    t0 = 1789527600 + 36000
    # quieto a ~1 km al sur del recorrido, pero en una celda de la máscara (el recorrido pasa por la celda de al lado):
    # se cuenta como depósito sólo si está a > 150 m del recorrido.
    far = _car(1, -34.60 - 0.003, -58.40, t0, 0.0)
    on_route = _car(2, -34.60, -58.40, t0, 0.0)
    a = _args()
    assert a["cell_ok"][cell_index(GRID, -34.603, -58.40)]   # la celda del coche lejano SÍ está en la máscara
    win, cell, speed, n, n_stopped = aggregate(*_cat(far, on_route), **a)
    # 3 intervalos del coche sobre el recorrido caen en 2 ventanas de 2 min: 1 coche por ventana; el lejano no suma
    assert list(n) == [1, 1] and list(n_stopped) == [1, 1]
    # un coche quieto en una celda sin recorrido tampoco cuenta
    off = _car(3, -34.80, -58.40, t0, 0.0)
    out = aggregate(*off, **_args())
    assert out[3].sum() == 0


def test_mask_includes_intermediate_cells_of_long_segment():
    # un único segmento de ~20 km, solo dos vértices
    seg = [(-34.60, -58.50), (-34.60, -58.28)]
    cells = cells_of_polylines(GRID, [seg])
    j0 = cell_index(GRID, -34.60, -58.50) % GRID.stride
    j1 = cell_index(GRID, -34.60, -58.28) % GRID.stride
    assert j1 - j0 > 30
    assert len(cells) == j1 - j0 + 1                      # una celda por cada columna atravesada
    mid = cell_index(GRID, -34.60, -58.39)
    assert mid in cells
