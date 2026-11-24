"""Feature de tránsito actual por tramo (ARQUITECTURA §11.1): causalidad, máscara de "sin dato", forma de tensores y checkpoint."""

import numpy as np
import pytest
import torch

from prediccion.models.path_eta import (N_STATE, PathETAModel, build_shape_table, table_to_batch)
from prediccion.v2.traffic.feature import (TRAFFIC_DIM, TrafficTable, abs_window, last_complete_window,
                                           traffic_features_np)
from prediccion.v2.traffic.grid import cell_index, grid_from_encoder

PTS = [(-34.60 + 0.0001 * i, -58.40) for i in range(0, 2000, 10)]      # ~2,2 km hacia el norte
T0 = 1789527600 + 11 * 3600 + 37 * 60 + 41          # 2026-09-16 11:37:41 BA -> ventana 11*30 + 18 = 348 (w0)
W0 = int(abs_window(T0))


def _model(traffic=True):
    ids, lat, lon, off = build_shape_table({"S1": PTS})
    return PathETAModel(ids, lat, lon, off, ["9"], hidden=16, traffic_feature=traffic), lat, lon


def _cells(lat, lon):
    return np.unique(cell_index(grid_from_encoder(500.0), lat, lon))


def _table(cells, fill):
    """Tabla de 12 ventanas (w0-6 .. w0+5). fill(w_rel_a_w0) -> (speed, n, n_stopped) escalares para todas las celdas."""
    W, C = 12, len(cells)
    sp = np.full((W, C), np.nan, np.float16)
    n = np.zeros((W, C), np.uint8)
    ns = np.zeros((W, C), np.uint8)
    for i in range(W):
        r = fill(i - 6)
        if r is not None:
            sp[i], n[i], ns[i] = r
    return TrafficTable(cells, W0 - 6, sp, n, ns)


def _inp(rem=(800.0, 1500.0), d0=(100.0, 300.0), ts=T0):
    B = len(rem)
    return dict(shape_idx=torch.zeros(B, dtype=torch.long), line_idx=torch.ones(B, dtype=torch.long),
                d0=torch.tensor(d0, dtype=torch.float32), rem=torch.tensor(rem, dtype=torch.float32),
                h_sin=torch.zeros(B, 1), h_cos=torch.ones(B, 1), dow=torch.zeros(B, 1, dtype=torch.long),
                state=torch.zeros(B, N_STATE),
                win=torch.as_tensor(last_complete_window(np.full(B, ts))))


# ── ancla causal ─────────────────────────────────────────────────────────────

def test_la_ultima_ventana_completa_termina_en_o_antes_de_t0_en_cualquier_segundo_de_la_ventana():
    start = (W0 * 120) + 3 * 3600                      # primer segundo (unix) de w0
    for ts in (start, start + 1, start + 59, start + 119):
        w = int(last_complete_window(ts))
        assert w == W0 - 1
        assert (w + 1) * 120 + 3 * 3600 <= ts           # la ventana usada terminó antes (o justo cuando empieza) t0
    assert int(last_complete_window(start - 1)) == W0 - 2


def test_una_fila_no_ve_ventanas_desde_t0_en_adelante_referencia_numpy():
    cells = np.array([10, 11, 12], np.int32)
    past = lambda r: (np.full(3, 6.0), np.full(3, 2), np.zeros(3)) if r < 0 else None  # noqa: E731
    leaky = lambda r: past(r) or (np.full(3, 30.0), np.full(3, 50), np.full(3, 50))  # noqa: E731  w0 y futuras: valores absurdos
    a = traffic_features_np(_table(cells, past), cells, T0)
    b = traffic_features_np(_table(cells, leaky), cells, T0)
    np.testing.assert_array_equal(a, b)                # lo que hay en w0 y después no cambia nada
    assert (a[:, 0] == 1).all() and a[0, 1] == pytest.approx(6.0 / 15.0)


def test_solo_cuentan_las_dos_ventanas_previas_no_las_anteriores():
    cells = np.array([10], np.int32)
    solo_hace_3 = lambda r: (np.full(1, 9.0), np.full(1, 4), np.zeros(1)) if r == -3 else None  # noqa: E731
    f = traffic_features_np(_table(cells, solo_hace_3), cells, T0)
    assert f[0, 0] == 0                                # w0-3 queda fuera: sin dato
    f = traffic_features_np(_table(cells, lambda r: (np.full(1, 9.0), np.full(1, 4), np.zeros(1)) if r == -2 else None), cells, T0)
    assert f[0, 0] == 1                                # w0-2 sí entra


def test_el_modelo_no_ve_el_futuro_y_si_ve_la_ventana_previa():
    m, lat, lon = _model()
    cells = _cells(lat, lon)
    past = lambda r: (np.full(len(cells), 6.0), np.full(len(cells), 3), np.zeros(len(cells))) if r < 0 else None  # noqa: E731
    fut = lambda r: past(r) or (np.full(len(cells), 1.0), np.full(len(cells), 40), np.full(len(cells), 40))  # noqa: E731
    other_prev = lambda r: (np.full(len(cells), 1.0), np.full(len(cells), 40), np.zeros(len(cells))) if r < 0 else None  # noqa: E731
    outs = []
    for fill in (past, fut, other_prev):
        m.attach_traffic(_table(cells, fill))
        with torch.no_grad():
            outs.append(m(**_inp())[0].numpy())
    np.testing.assert_allclose(outs[0], outs[1], rtol=0, atol=0)      # w0 y futuras no cambian el ETA
    assert not np.allclose(outs[0], outs[2])                          # w0-1 / w0-2 sí


# ── máscara "sin dato" ──────────────────────────────────────────────────────

def test_sin_dato_no_inventa_velocidad_todo_cero_y_hay_dato_en_cero():
    cells = np.array([10, 11], np.int32)
    tab = _table(cells, lambda r: (np.array([5.0, np.nan]), np.array([2, 0]), np.array([0, 0])) if r < 0 else None)
    f = traffic_features_np(tab, np.array([10, 11, 999]), T0)         # celda con dato, celda vacía, celda fuera de la tabla
    assert f[0].tolist()[0] == 1 and f[0, 1] > 0
    np.testing.assert_array_equal(f[1], 0.0)
    np.testing.assert_array_equal(f[2], 0.0)


def test_ventana_fuera_del_rango_de_la_tabla_es_sin_dato():
    cells = np.array([10], np.int32)
    tab = _table(cells, lambda r: (np.full(1, 5.0), np.full(1, 2), np.zeros(1)))
    assert traffic_features_np(tab, np.array([10]), T0 + 30 * 86400)[0, 0] == 0
    assert traffic_features_np(tab, np.array([10]), T0 - 30 * 86400)[0, 0] == 0


def test_celda_con_coches_todos_quietos_tiene_dato_pero_velocidad_cero():
    cells = np.array([10], np.int32)
    tab = _table(cells, lambda r: (np.full(1, np.nan), np.full(1, 3), np.full(1, 3)) if r < 0 else None)
    f = traffic_features_np(tab, np.array([10]), T0)[0]
    assert f[0] == 1 and f[1] == 0 and f[3] == 1.0 and f[2] > 0


def test_pooling_pondera_la_velocidad_por_coches_en_movimiento():
    cells = np.array([10], np.int32)
    vals = {-1: (4.0, 3, 0), -2: (10.0, 1, 0)}
    tab = _table(cells, lambda r: tuple(np.full(1, x) for x in vals[r]) if r in vals else None)
    f = traffic_features_np(tab, np.array([10]), T0)[0]
    assert f[1] == pytest.approx(((4.0 * 3 + 10.0 * 1) / 4) / 15.0, rel=1e-3)


# ── forma de tensores y paridad torch / referencia ──────────────────────────

def test_formas_de_los_tensores_y_forward():
    m, lat, lon = _model()
    cells = _cells(lat, lon)
    m.attach_traffic(_table(cells, lambda r: (np.full(len(cells), 5.0), np.full(len(cells), 2), np.zeros(len(cells)))))
    inp = _inp()
    f = m.traffic_inputs(torch.tensor([0, 1, -1]), torch.full((3,), W0 - 1))
    assert f.shape == (3, TRAFFIC_DIM) and f.dtype == torch.float32
    eta, total, adj = m(**inp)
    assert eta.shape == total.shape == adj.shape == (2,)
    n_seg, con_dato, con_vel = m.traffic_coverage(inp["shape_idx"], inp["d0"], inp["rem"], inp["win"])
    assert n_seg.shape == con_dato.shape == (2,) and (con_dato == n_seg).all()      # tabla llena: 100 % con dato


def test_modelo_con_tabla_de_tamano_distinto_mantiene_el_mismo_contrato_que_la_referencia_numpy():
    m, lat, lon = _model()
    cells = _cells(lat, lon)
    rng = np.random.default_rng(1)
    W, C = 12, len(cells)
    n = rng.integers(0, 6, (W, C)).astype(np.uint8)
    ns = np.minimum(n, rng.integers(0, 4, (W, C))).astype(np.uint8)
    sp = np.where(n - ns > 0, rng.uniform(1, 12, (W, C)), np.nan).astype(np.float16)
    tab = TrafficTable(cells, W0 - 6, sp, n, ns)
    m.attach_traffic(tab)
    tcol = torch.arange(C)
    got = m.traffic_inputs(tcol, torch.full((C,), W0 - 1)).numpy()
    want = traffic_features_np(tab, cells, T0)
    np.testing.assert_allclose(got, want, atol=1e-5)


def test_table_to_batch_trae_la_ventana_causal_y_exige_ts_p():
    m, lat, lon = _model()
    df = {"observed_eta_s": [100.0], "dist_remaining_m": [800.0], "dist_along_norm": [0.1], "shape_id": ["S1"],
          "dist_along_m": [100.0], "line": ["9"], "time_since_start": [np.nan], "speed_mps": [5.0], "ts_age_s": [1.0],
          "time_since_last_bus_s": [60.0], "last_bus_found": [1.0], "hour_sin": [0.0], "hour_cos": [1.0], "dow": [1],
          "ts_p": [T0]}
    b, v = table_to_batch(df, m)
    assert b["tw"].dtype == torch.int64 and b["tw"].tolist() == [W0 - 1]
    df.pop("ts_p")
    with pytest.raises(KeyError):
        table_to_batch(df, m)
    assert "tw" not in table_to_batch(df, _model(False)[0])[0]      # sin la feature el batch no cambia


# ── checkpoints y compatibilidad ─────────────────────────────────────────────

def test_checkpoint_roundtrip_con_tabla_y_rechazo_de_otra_tabla():
    m, lat, lon = _model()
    cells = _cells(lat, lon)
    tab = _table(cells, lambda r: (np.full(len(cells), 5.0), np.full(len(cells), 2), np.zeros(len(cells))) if r < 0 else None)
    m.attach_traffic(tab)
    m.eval()
    with torch.no_grad():
        want = m(**_inp())[0]
    ck = m.checkpoint_dict()
    assert "traffic_feature" in ck["cfg"] and ck["traffic"]["sha1"] == tab.sha1()
    assert not any(k.startswith("tr_") or k == "seg_tcell" for k in ck["model_state_dict"])     # la tabla no va en el checkpoint
    m2 = PathETAModel.from_checkpoint(ck, traffic_table=tab).eval()
    with torch.no_grad():
        np.testing.assert_allclose(m2(**_inp())[0].numpy(), want.numpy(), atol=1e-6)
    otra = _table(cells, lambda r: (np.full(len(cells), 9.0), np.full(len(cells), 7), np.zeros(len(cells))))
    with pytest.raises(ValueError):
        PathETAModel.from_checkpoint(ck, traffic_table=otra)


def test_sin_la_feature_el_modelo_es_el_de_antes():
    m, _, _ = _model(False)
    assert "traffic_feature" not in m.cfg
    assert not hasattr(m, "tr_speed")
    with pytest.raises(ValueError):
        _model()[0](**{k: v for k, v in _inp().items() if k != "win"})   # con la feature, sin ancla causal no corre


def test_tabla_densa_desde_los_daily_se_consulta_con_el_ts_unix_del_dia_correcto(tmp_path):
    """Un daily con una celda en la ventana 348 del 2026-09-16 (BA): una consulta de ese día en la ventana siguiente la ve, una del día anterior no."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from prediccion.v2.traffic.feature import build_dense
    (tmp_path / "daily").mkdir()
    pq.write_table(pa.table({"window": pa.array([348], pa.int16()), "cell": pa.array([77], pa.int32()),
                             "speed_mps": pa.array([np.float16(8.0)]), "n": pa.array([3], pa.uint16()),
                             "n_stopped": pa.array([1], pa.uint16())}), tmp_path / "daily" / "2026-09-16.parquet")
    tab, info = build_dense(tmp_path / "daily", "2026-09-15", "2026-09-17", [77, 78], 1000)
    assert info["days_present"] == 1 and info["days_missing"] == ["2026-09-15", "2026-09-17"]
    midnight_ba = 1789527600                              # 2026-09-16 00:00 BA
    t_next = midnight_ba + 349 * 120 + 5                  # dentro de la ventana 349: la 348 es la última completa
    assert traffic_features_np(tab, np.array([77]), t_next)[0, 0] == 1
    assert traffic_features_np(tab, np.array([77]), midnight_ba + 348 * 120 + 5)[0, 0] == 0      # misma ventana: no se ve
    assert traffic_features_np(tab, np.array([77]), midnight_ba - 86400 + 349 * 120)[0, 0] == 0  # el día anterior no tiene dato
    assert traffic_features_np(tab, np.array([78]), t_next)[0, 0] == 0                           # otra celda
