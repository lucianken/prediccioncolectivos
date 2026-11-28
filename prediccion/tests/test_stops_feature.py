"""Paradas por tramo (ARQUITECTURA §6.2): conteo por tramo, compatibilidad de checkpoints y paridad ONNX / PyTorch / referencia."""

import numpy as np
import pytest
import torch

from prediccion.models.path_eta import (N_STATE, PathETAModel, build_path_segments, build_shape_table, build_stop_key,
                                        stop_features)
from red.stops import stop_features_np

PTS = [(-34.60 + 0.0001 * i, -58.40) for i in range(0, 2000, 10)]      # ~2,2 km hacia el norte
STOPS_M = [300.0, 420.0, 1010.0, 1500.0]


def _feats(stops, lo, hi, n_shapes=1, s=0):
    key = build_stop_key([str(i) for i in range(n_shapes)], {str(s): stops})
    t = lambda v: torch.tensor(v, dtype=torch.float64)  # noqa: E731
    c, n = stop_features(torch.as_tensor(key), torch.full((len(lo),), s, dtype=torch.long), t(lo), t(hi))
    return c.tolist(), n.tolist()


def test_la_referencia_numpy_coincide_con_la_version_torch():
    rng = np.random.default_rng(0)
    stops = sorted(rng.uniform(0, 5000, 20).round(2).tolist())
    lo = rng.uniform(0, 4500, 200)
    hi = lo + rng.uniform(1, 250, 200)
    c, n = _feats(stops, lo.tolist(), hi.tolist())
    c2, n2 = stop_features_np(stops, lo, hi)
    np.testing.assert_allclose(c, c2)
    np.testing.assert_allclose(n, n2, atol=1e-6)


def _model(stops_feature, hidden=16):
    ids, lat, lon, off = build_shape_table({"S1": PTS})
    key = build_stop_key(ids, {"S1": STOPS_M}) if stops_feature else None
    return PathETAModel(ids, lat, lon, off, ["9", "10"], hidden=hidden, stops_feature=stops_feature, stop_key=key)


def _inputs(rem, d0):
    B = len(rem)
    return dict(shape_idx=torch.zeros(B, dtype=torch.long), line_idx=torch.ones(B, dtype=torch.long),
                d0=torch.tensor(d0, dtype=torch.float32), rem=torch.tensor(rem, dtype=torch.float32),
                h_sin=torch.zeros(B, 1), h_cos=torch.ones(B, 1), dow=torch.zeros(B, 1, dtype=torch.long),
                state=torch.zeros(B, N_STATE))


def test_checkpoint_viejo_sin_la_feature_sigue_cargando_y_no_guarda_la_clave():
    m = _model(False).eval()
    ck = m.checkpoint_dict()
    assert "stops_feature" not in ck["cfg"] and "stop_key" not in ck["model_state_dict"]
    m2 = PathETAModel.from_checkpoint(ck).eval()
    assert not m2.stops_feature
    inp = _inputs([900.0], [50.0])
    with torch.no_grad():
        torch.testing.assert_close(m(**inp)[0], m2(**inp)[0])


def test_checkpoint_con_la_feature_guarda_config_y_paradas_y_reproduce_predicciones():
    m = _model(True).eval()
    ck = m.checkpoint_dict()
    assert ck["cfg"]["stops_feature"] is True and "stop_key" in ck["model_state_dict"]
    m2 = PathETAModel.from_checkpoint(ck).eval()
    inp = _inputs([1200.0, 400.0], [50.0, 700.0])
    with torch.no_grad():
        torch.testing.assert_close(m(**inp)[0], m2(**inp)[0])


def test_la_prediccion_depende_de_las_paradas_solo_cuando_la_feature_esta_activa():
    torch.manual_seed(0)
    m = _model(True).eval()
    inp = _inputs([1500.0], [0.0])
    with torch.no_grad():
        a = m(**inp)[1].item()
        m.stop_key = torch.as_tensor(build_stop_key(["S1"], {"S1": []}))
        b = m(**inp)[1].item()
    assert a != pytest.approx(b)


@pytest.mark.parametrize("stops_feature", [True, False])
def test_onnx_coincide_con_pytorch(tmp_path, stops_feature):
    import onnxruntime as ort
    from prediccion.inference.path_onnx import export_onnx, run_onnx, segment_inputs_from_rows
    torch.manual_seed(1)
    m = _model(stops_feature).eval()
    export_onnx(m, tmp_path / "m.onnx")
    rng = np.random.default_rng(0)
    d0 = rng.uniform(0, 800, 30)
    rem = rng.uniform(100, 1300, 30)
    inp = _inputs(rem.tolist(), d0.tolist())
    inp["state"] = torch.rand(30, N_STATE)
    inp["state"][:, -1] = 0.0
    with torch.no_grad():
        ref = m(**inp)[0].numpy()
    seg = segment_inputs_from_rows(m, inp["shape_idx"], inp["d0"], inp["rem"])
    assert ("seg_stop_n" in seg) == stops_feature
    sess = ort.InferenceSession(str(tmp_path / "m.onnx"), providers=["CPUExecutionProvider"])
    got = run_onnx(sess, {**seg, "line_idx": inp["line_idx"].numpy(), "dow": inp["dow"][:, 0].numpy(),
                          "h_sin": inp["h_sin"][:, 0].numpy(), "h_cos": inp["h_cos"][:, 0].numpy(),
                          "state": inp["state"][:, :-1].numpy()})[0]
    np.testing.assert_allclose(got, ref, atol=0.05)


def test_la_referencia_del_cliente_arma_las_mismas_entradas_de_paradas_que_el_entrenamiento():
    from red.path_reference import Shape, build_segments
    m = _model(True)
    d0, rem = 130.0, 1400.0
    from prediccion.inference.path_onnx import segment_inputs_from_rows
    ref = segment_inputs_from_rows(m, torch.zeros(1, dtype=torch.long), torch.tensor([d0]), torch.tensor([rem]))
    sh = Shape({"id": "S1", "length_m": 2200.0, "points": np.asarray(PTS).reshape(-1).tolist(),
                "cells": np.stack([m.seg_lat.numpy(), m.seg_lon.numpy()], 1).reshape(-1).tolist(), "stops_m": STOPS_M},
               111320.0)
    const = {"seg_base_m": 250.0, "max_seg": 160}
    seg = build_segments(const, sh, d0, rem)
    n = len(seg["seg_len"])
    np.testing.assert_allclose(seg["seg_stop_n"], ref["seg_stop_n"][0][:n])
    np.testing.assert_allclose(seg["seg_stop_next"], ref["seg_stop_next"][0][:n], atol=1e-3)
    assert seg["seg_stop_n"].sum() == 4           # las 4 paradas caen en [130, 1530)
    assert seg["seg_stop_n"].tolist() == [0, 2, 0, 0, 1, 0, 1]
