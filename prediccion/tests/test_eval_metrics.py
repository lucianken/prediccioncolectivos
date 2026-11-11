"""Métricas de la vara de medir (prediccion.eval) con casos sintéticos de error conocido."""

import numpy as np
import pytest

from prediccion.eval import compute_metrics, metrics_to_markdown, predict_a0, predict_a0_const
from prediccion.v2.make_eval import eta_bucket


def test_error_conocido_global_y_por_bucket():
    true = np.array([100.0, 200.0, 400.0, 700.0, 1500.0])
    err = np.array([10.0, -30.0, 70.0, -90.0, 0.0])           # pred = true + err
    pred = true + err
    dist = np.array([300.0, 800.0, 1500.0, 3000.0, 9000.0])
    m = compute_metrics(pred, true, dist)

    g = m["global"]
    assert g["n"] == 5
    assert g["mae"] == pytest.approx(40.0)                      # (10+30+70+90+0)/5
    assert g["bias"] == pytest.approx(-8.0)                     # (10-30+70-90+0)/5
    assert g["p50"] == pytest.approx(30.0)
    assert g["p90"] == pytest.approx(np.percentile(np.abs(err), 90))
    # subestimaciones > 60 s: pred - true = -90 (1 de 5). El -30 no alcanza el umbral.
    assert g["pct_under_60s"] == pytest.approx(20.0)

    # buckets de ETA real [lo, hi): 0-5 min = {100, 200}; 5-10 = {400}; 10-20 = {700}; 20+ = {1500}
    assert m["by_eta"]["0-5 min"]["n"] == 2 and m["by_eta"]["0-5 min"]["mae"] == pytest.approx(20.0)
    assert m["by_eta"]["5-10 min"]["mae"] == pytest.approx(70.0)
    assert m["by_eta"]["10-20 min"]["bias"] == pytest.approx(-90.0)
    assert m["by_eta"]["10-20 min"]["pct_under_60s"] == pytest.approx(100.0)
    assert m["by_eta"]["20+ min"]["mae"] == pytest.approx(0.0)
    # distancia: <500 {300}, 0,5-2 km {800, 1500}, 2-5 km {3000}, 5+ km {9000}
    assert m["by_dist"]["<500 m"]["n"] == 1
    assert m["by_dist"]["0,5-2 km"]["mae"] == pytest.approx(50.0)
    assert m["by_dist"]["2-5 km"]["bias"] == pytest.approx(-90.0)
    assert m["by_dist"]["5+ km"]["mae"] == pytest.approx(0.0)


def test_bucket_vacio_no_rompe():
    m = compute_metrics([100.0], [110.0], [300.0])
    assert m["by_eta"]["20+ min"]["n"] == 0 and m["by_eta"]["20+ min"]["mae"] is None
    assert "-" in metrics_to_markdown("x", m)


def test_sobreestimar_no_cuenta_como_subestimacion_y_el_signo_del_sesgo():
    m = compute_metrics([500.0, 500.0], [100.0, 100.0], [1000.0, 1000.0])
    assert m["global"]["bias"] == pytest.approx(400.0)
    assert m["global"]["pct_under_60s"] == 0.0


def test_limites_de_bucket_son_cerrado_abierto():
    m = compute_metrics([0.0, 0.0], [300.0, 299.0], [500.0, 499.0])
    assert m["by_eta"]["0-5 min"]["n"] == 1 and m["by_eta"]["5-10 min"]["n"] == 1
    assert m["by_dist"]["<500 m"]["n"] == 1 and m["by_dist"]["0,5-2 km"]["n"] == 1


def test_a0_usa_piso_de_velocidad():
    import pandas as pd
    df = pd.DataFrame({"dist_remaining_m": [3000.0, 3000.0, 3000.0], "speed_mps": [0.0, 10.0, 1.0]})
    np.testing.assert_allclose(predict_a0(df, v_floor=3.0), [1000.0, 300.0, 1000.0])
    np.testing.assert_allclose(predict_a0_const(df, 6.0), [500.0] * 3)


def test_eta_bucket_de_make_eval_coincide_con_los_buckets_de_la_tabla():
    assert eta_bucket(np.array([1.0, 299.9, 300.0, 599.0, 600.0, 1199.0, 1200.0, 7000.0])).tolist() == \
        [0, 0, 1, 1, 2, 2, 3, 3]
