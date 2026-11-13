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


def test_desglose_por_fase_separa_inicio_y_detenido_sin_tocar_las_metricas_globales():
    from prediccion.eval import compute_phase_breakdown, phase_masks
    tss = np.array([100.0, 100.0, 1000.0, 1000.0, np.nan])
    along = np.array([5000.0, 5000.0, 5000.0, 500.0, 5000.0])       # fila 3: <1 km del inicio aunque pasaron 1000 s
    speed = np.array([0.0, 8.0, 0.2, 8.0, 8.0])
    start, stopped = phase_masks(tss, along, speed)
    assert start.tolist() == [True, True, False, True, False]
    assert stopped.tolist() == [True, False, True, False, False]
    true = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    pred = np.array([200.0, 100.0, 130.0, 100.0, 100.0])
    ph = compute_phase_breakdown(pred, true, start, stopped)
    assert ph["inicio de viaje"]["n"] == 3 and ph["resto del viaje"]["n"] == 2
    assert ph["inicio de viaje"]["mae"] == pytest.approx(100.0 / 3)
    assert ph["P detenido"]["mae"] == pytest.approx(65.0)
    assert ph["global sin inicio de viaje"]["mae"] == pytest.approx(15.0)
    assert ph["global"]["mae"] == pytest.approx(compute_metrics(pred, true, along)["global"]["mae"])
    assert ph["inicio y detenido"]["n"] + ph["inicio y en movimiento"]["n"] == ph["inicio de viaje"]["n"]


def test_sobreestimacion_y_desgloses_por_linea_y_distancia_fina():
    import numpy as np
    from prediccion.eval import compute_metrics
    pred = np.array([200.0, 100.0, 100.0, 500.0])
    true = np.array([100.0, 100.0, 300.0, 100.0])
    dist = np.array([300.0, 700.0, 2500.0, 13000.0])
    line = np.array(["a", "a", "b", "b"])
    m = compute_metrics(pred, true, dist, line)
    assert m["global"]["pct_over_60s"] == 50.0       # filas 0 y 3
    assert m["global"]["pct_under_60s"] == 25.0      # fila 2
    assert m["by_dist_fine"]["0-0,5 km"]["n"] == 1
    assert m["by_dist_fine"]["12+ km"]["pct_over_60s"] == 100.0
    assert m["by_line"]["a"]["n"] == 2 and m["by_line"]["b"]["pct_under_60s"] == 50.0


def test_llega_antes_despues_y_espera_extra_media():
    import numpy as np
    from prediccion.eval import compute_metrics
    # real 300 s; anunciado 200 (llega después +100), 400 (llega antes 100), 280 (después 20), 300 (exacto)
    pred = np.array([200.0, 400.0, 280.0, 300.0])
    true = np.full(4, 300.0)
    g = compute_metrics(pred, true, np.full(4, 1000.0))["global"]
    assert g["pct_llega_antes_60s"] == pytest.approx(25.0)
    assert g["pct_llega_despues_60s"] == pytest.approx(25.0)
    assert g["espera_extra_media_s"] == pytest.approx(60.0)      # (100 + 20) / 2
    assert g["pct_llega_antes_60s"] == g["pct_over_60s"] and g["pct_llega_despues_60s"] == g["pct_under_60s"]


def test_tabla_por_bandas_de_eta_real():
    from prediccion.eval import compute_eta_bands
    true = np.array([60.0, 90.0, 250.0, 300.0, 420.0, 500.0, 1000.0])
    pred = true + np.array([100.0, -10.0, 0.0, 80.0, -100.0, 20.0, 5.0])   # + = llega antes de lo anunciado
    b = compute_eta_bands(pred, true)
    assert b["0-2 min"]["n"] == 2 and b["0-2 min"]["pct_llega_antes_60s"] == pytest.approx(50.0)
    assert b["0-2 min"]["mae"] == pytest.approx(55.0)
    # 3-7 min (principal) = reales en [180, 420): 250 y 300; el 420 cae en 7+ y queda afuera
    p = b["3-7 min (principal)"]
    assert p["n"] == 2 and p["mae"] == pytest.approx(40.0) and p["pct_llega_antes_60s"] == pytest.approx(50.0)
    b2 = compute_eta_bands(true + np.array([0, 0, 0, 0, -100.0, 0, 0]), true)
    assert b2["6-8 min"]["pct_llega_despues_60s"] == pytest.approx(100.0) and b2["6-8 min"]["espera_extra_media_s"] == pytest.approx(100.0)
    assert b2["2-4 min"]["n"] == 0 and b2["2-4 min"]["mae"] is None
