"""Modelo por tramos (models/path_eta.py): cobertura exacta de P->T, suma con tiempos constantes y máscara."""

import numpy as np
import pytest
import torch

from prediccion.models.path_eta import (PathETAModel, build_path_segments, build_shape_table, state_features,
                                        N_STATE)


def _segs(d0, rem, max_seg=160):
    return build_path_segments(torch.tensor(d0, dtype=torch.float32), torch.tensor(rem, dtype=torch.float32), max_seg)


def test_los_tramos_cubren_exactamente_la_distancia_de_P_a_T():
    d0 = [0.0, 120.0, 250.0, 1234.5, 9990.0]
    rem = [100.0, 1000.0, 500.0, 3333.3, 250.0]
    k, step, length, mask = _segs(d0, rem)
    np.testing.assert_allclose(length.sum(dim=1).numpy(), rem, atol=0.05)
    assert (length[mask] > 0).all()                       # ningún tramo válido vacío
    assert (length <= 250.0 + 1e-3).all()                 # tramos de 250 m como máximo


def test_primer_y_ultimo_tramo_son_parciales_y_los_del_medio_completos():
    k, step, length, mask = _segs([100.0], [1000.0])      # P=100 m, T=1100 m -> celdas 0..4
    L = length[0][mask[0]].tolist()
    assert L == pytest.approx([150.0, 250.0, 250.0, 250.0, 100.0], abs=1e-3)
    assert k[0][mask[0]].tolist() == [0, 1, 2, 3, 4]


def test_camino_mas_largo_que_el_tope_sigue_cubriendo_P_T_con_a_lo_sumo_max_seg_tramos():
    k, step, length, mask = _segs([500.0], [60000.0], max_seg=160)
    assert mask.sum().item() <= 160
    assert length.sum().item() == pytest.approx(60000.0, abs=0.5)
    assert step[0].item() > 250.0


def _tiny_model():
    pts = [(-34.60 + 0.0001 * i, -58.40) for i in range(0, 2000, 10)]   # ~2,2 km hacia el norte
    ids, lat, lon, off = build_shape_table({"S1": pts})
    return PathETAModel(ids, lat, lon, off, ["9"], hidden=16)


def _inputs(rem, d0, B=None):
    B = len(rem)
    return dict(shape_idx=torch.zeros(B, dtype=torch.long), line_idx=torch.ones(B, dtype=torch.long),
                d0=torch.tensor(d0, dtype=torch.float32), rem=torch.tensor(rem, dtype=torch.float32),
                h_sin=torch.zeros(B, 1), h_cos=torch.ones(B, 1), dow=torch.zeros(B, 1, dtype=torch.long),
                state=torch.zeros(B, N_STATE))


def test_con_tiempo_por_metro_constante_el_eta_es_distancia_sobre_velocidad():
    m = _tiny_model()
    v = 5.0
    with torch.no_grad():
        m.seg_mlp[-1].weight.zero_()
        m.seg_mlp[-1].bias.fill_(float(np.log(np.expm1(1.0 / v))))     # softplus(b) = 1/v s/m
    inp = _inputs([800.0, 1500.0, 130.0], [100.0, 300.0, 0.0])
    eta, total, adj = m(**inp)
    np.testing.assert_allclose(total.detach().numpy(), [800 / v, 1500 / v, 130 / v], rtol=1e-4)
    np.testing.assert_allclose(adj.detach().numpy(), 0.0, atol=1e-6)       # arranca como suma pura de tramos
    np.testing.assert_allclose(eta.detach().numpy(), total.detach().numpy(), rtol=1e-5)


def test_la_mascara_anula_los_tramos_sobrantes():
    # una fila corta junto a una larga: el relleno de la corta no puede cambiar su ETA
    m = _tiny_model().eval()
    solo = _inputs([600.0], [100.0])
    junto = _inputs([600.0, 2000.0], [100.0, 0.0])
    with torch.no_grad():
        e1, t1, _ = m(**solo)
        e2, t2, _ = m(**junto)
    assert t1[0].item() == pytest.approx(t2[0].item(), rel=1e-5)
    times, length, mask = m.segment_times(junto["shape_idx"], junto["line_idx"], junto["d0"], junto["rem"],
                                          junto["h_sin"], junto["h_cos"], junto["dow"])
    assert (times[~mask] == 0).all() and (length[~mask] == 0).all()
    assert mask[0].sum() < mask[1].sum()


def test_el_ajuste_global_depende_del_estado_y_se_suma_al_total():
    m = _tiny_model().eval()
    with torch.no_grad():
        m.adj[-1].bias.fill_(30.0)
    eta, total, adj = m(**_inputs([800.0], [0.0]))
    assert eta.item() == pytest.approx(total.item() + 30.0, rel=1e-5)


def test_linea_desconocida_usa_el_indice_cero_y_shape_fuera_de_tabla_da_menos_uno():
    m = _tiny_model()
    assert m.line_index(["9", "999"]).tolist() == [1, 0]
    assert m.shape_index(["S1", "nope"]).tolist() == [0, -1]


def test_checkpoint_ida_y_vuelta_reproduce_las_predicciones():
    m = _tiny_model().eval()
    inp = _inputs([900.0, 400.0], [50.0, 700.0])
    with torch.no_grad():
        a = m(**inp)[0]
        b = PathETAModel.from_checkpoint(m.checkpoint_dict()).eval()(**inp)[0]
    torch.testing.assert_close(a, b)


def test_state_features_dimension_y_detenido():
    s = state_features([0.0, 8.0], [0.0, 30.0], [0.0, 600.0], [0.0, 100.0], [np.nan, 60.0], [0, 1], [500.0, 900.0])
    assert s.shape == (2, N_STATE) and np.isfinite(s).all()
    assert s[0, 1] == 1.0 and s[1, 1] == 0.0


def test_l1_simetrica_y_pinball_no():
    import torch
    from prediccion.models.path_eta import pinball
    dist = torch.tensor([200.0])
    mas = pinball(torch.tensor([90.0]), torch.tensor([100.0]), dist, "l1")     # llega después de lo anunciado
    menos = pinball(torch.tensor([110.0]), torch.tensor([100.0]), dist, "l1")  # llega antes de lo anunciado
    assert float(mas) == pytest.approx(float(menos)) == pytest.approx(5.0)
    pm = pinball(torch.tensor([90.0]), torch.tensor([100.0]), dist)
    pn = pinball(torch.tensor([110.0]), torch.tensor([100.0]), dist)
    assert float(pm) != pytest.approx(float(pn))


def test_pinball_inv_castiga_mas_llegar_antes_bajo_1km_y_igual_lejos():
    import torch
    from prediccion.models.path_eta import pinball
    real = torch.tensor([100.0])
    antes, despues = torch.tensor([130.0]), torch.tensor([70.0])      # anunciado 130 (llega antes) / 70 (llega después)
    cerca, lejos = torch.tensor([300.0]), torch.tensor([3000.0])
    assert float(pinball(antes, real, cerca, "pinball_inv")) > float(pinball(despues, real, cerca, "pinball_inv"))
    assert float(pinball(antes, real, lejos, "pinball_inv")) == pytest.approx(float(pinball(despues, real, lejos, "pinball_inv")))


def test_pinball_band_castiga_mas_llegar_antes_solo_dentro_de_la_banda():
    import torch
    from prediccion.models.path_eta import pinball
    band = (500.0, 2000.0)
    real = torch.tensor([100.0])
    antes, despues = torch.tensor([130.0]), torch.tensor([70.0])
    dentro = torch.tensor([1000.0])
    assert float(pinball(antes, real, dentro, "pinball_band", band)) > float(pinball(despues, real, dentro, "pinball_band", band))
    for fuera in (torch.tensor([100.0]), torch.tensor([150.0]), torch.tensor([2400.0]), torch.tensor([9000.0])):   # >300 m afuera de los bordes
        assert float(pinball(antes, real, fuera, "pinball_band", band)) == pytest.approx(float(pinball(despues, real, fuera, "pinball_band", band)))


def test_pinball_band_rampa_continua_entre_el_borde_y_los_300_m():
    import torch
    from prediccion.models.path_eta import band_quantile
    d = torch.tensor([150.0, 200.0, 350.0, 500.0, 1000.0, 2000.0, 2150.0, 2300.0, 2500.0])
    q = band_quantile(d, 500.0, 2000.0)
    assert q.tolist() == pytest.approx([0.5, 0.5, 0.4, 0.3, 0.3, 0.3, 0.4, 0.5, 0.5])


def test_band_calibration_usa_filas_de_3_a_10_min():
    from prediccion.models.path_eta import band_calibration
    dist = np.arange(1000.0, 11000.0, 100.0)                  # 100 filas
    eta = np.where(np.arange(100) % 2 == 0, 400.0, 3000.0)    # las pares caen en la franja 3-10 min
    lo, hi = band_calibration(dist, eta)
    en_franja = dist[eta == 400.0]
    assert lo == pytest.approx(np.percentile(en_franja, 10), abs=1) and hi == pytest.approx(np.percentile(en_franja, 90), abs=1)
