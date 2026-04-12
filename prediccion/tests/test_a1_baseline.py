import pytest
from pathlib import Path
from prediccion.models.a1_baseline import A1Baseline


def test_fit_no_crash(sample_trips_parquet):
    if sample_trips_parquet is None:
        pytest.skip("pyarrow not available")
    model = A1Baseline()
    model.fit(sample_trips_parquet)  # no debe lanzar excepción


def test_fit_nonempty_table(sample_trips_parquet):
    if sample_trips_parquet is None:
        pytest.skip("pyarrow not available")
    model = A1Baseline()
    model.fit(sample_trips_parquet)
    assert len(model.ramal_ids) > 0


def test_predict_known_ramal_eta_positive(sample_trips_parquet):
    if sample_trips_parquet is None:
        pytest.skip("pyarrow not available")
    model = A1Baseline()
    model.fit(sample_trips_parquet)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    # Lunes 8am Buenos Aires
    dt = datetime(2026, 3, 2, 8, 0, 0, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
    ts = int(dt.timestamp())
    eta, conf = model.predict("39-0", 500.0, 2000.0, ts)
    assert eta > 0


def test_predict_empty_slot_fallback(sample_trips_parquet):
    if sample_trips_parquet is None:
        pytest.skip("pyarrow not available")
    model = A1Baseline()
    model.fit(sample_trips_parquet)
    import time
    eta, conf = model.predict("99-0", 0.0, 1000.0, int(time.time()))
    assert conf in {"medium", "low"}
    assert eta >= 0


def test_predict_nonnegative(sample_trips_parquet):
    if sample_trips_parquet is None:
        pytest.skip("pyarrow not available")
    import time
    import random
    model = A1Baseline()
    model.fit(sample_trips_parquet)
    now = int(time.time())
    for _ in range(50):
        dist_v = random.uniform(0, 2000)
        dist_t = random.uniform(dist_v, 5000)
        eta, _ = model.predict("39-0", dist_v, dist_t, now)
        assert eta >= 0
    for _ in range(50):
        dist_v = random.uniform(0, 2000)
        dist_t = random.uniform(dist_v, 5000)
        eta, _ = model.predict("99-0", dist_v, dist_t, now)
        assert eta >= 0


def test_predict_zero_distance(sample_trips_parquet):
    if sample_trips_parquet is None:
        pytest.skip("pyarrow not available")
    model = A1Baseline()
    model.fit(sample_trips_parquet)
    import time
    eta, conf = model.predict("39-0", 1000.0, 1000.0, int(time.time()))
    assert eta == 0.0
    assert conf == "high"


def test_predict_target_behind_vehicle(sample_trips_parquet):
    if sample_trips_parquet is None:
        pytest.skip("pyarrow not available")
    model = A1Baseline()
    model.fit(sample_trips_parquet)
    import time
    eta, conf = model.predict("39-0", 2000.0, 500.0, int(time.time()))
    assert eta == 0.0
    assert conf == "high"


def test_save_load_roundtrip(sample_trips_parquet, tmp_path):
    if sample_trips_parquet is None:
        pytest.skip("pyarrow not available")
    import time
    model = A1Baseline()
    model.fit(sample_trips_parquet)
    now = int(time.time())
    eta_before, conf_before = model.predict("39-0", 500.0, 2000.0, now)

    path = tmp_path / "model.pkl"
    model.save(path)

    loaded = A1Baseline.load(path)
    eta_after, conf_after = loaded.predict("39-0", 500.0, 2000.0, now)

    assert eta_before == eta_after
    assert conf_before == conf_after
