import pytest
from pathlib import Path

pytestmark = pytest.mark.regression


def test_a1_mae_below_5_minutes(real_a1_model, real_val_parquet):
    from prediccion.models.trainer import evaluate_a1
    metrics = evaluate_a1(real_a1_model, real_val_parquet)
    assert metrics["mae_min"] is not None
    assert metrics["mae_min"] < 5.0


def test_a1_no_negative_predictions(real_a1_model, real_val_parquet):
    from prediccion.models.trainer import evaluate_a1
    metrics = evaluate_a1(real_a1_model, real_val_parquet)
    assert metrics.get("n_negative", 0) == 0


def test_a1_mae_by_distance_bucket(real_a1_model, real_val_parquet):
    from prediccion.models.trainer import evaluate_a1
    metrics = evaluate_a1(real_a1_model, real_val_parquet)
    by_bucket = metrics.get("by_bucket", {})
    if by_bucket.get("0_500m") is not None:
        assert by_bucket["0_500m"] < 90
    if by_bucket.get("500m_2km") is not None:
        assert by_bucket["500m_2km"] < 180
    if by_bucket.get("2km_plus") is not None:
        assert by_bucket["2km_plus"] < 360


def test_a1_confidence_distribution(real_a1_model, real_val_parquet):
    import duckdb
    import time
    path = str(real_val_parquet)
    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT ramal_id, dist_remaining_m
        FROM read_parquet('{path}')
        LIMIT 1000
    """).fetchall()
    con.close()

    now = int(time.time())
    high_count = sum(
        1 for ramal_id, dist in rows
        if real_a1_model.predict(ramal_id, 0.0, dist, now)[1] == "high"
    )
    assert high_count / len(rows) >= 0.5


@pytest.fixture
def real_a1_model():
    model_paths = sorted(Path("data/models").glob("a1_v*.pkl"))
    if not model_paths:
        pytest.skip("No trained A1 model found. Run train.py --phase 1 first.")
    from prediccion.models.a1_baseline import A1Baseline
    return A1Baseline.load(model_paths[-1])


@pytest.fixture
def real_val_parquet():
    p = Path("data/ml/training/model2_eta/val.parquet")
    if not p.exists():
        pytest.skip("No val parquet found. Run build_dataset first.")
    return p
