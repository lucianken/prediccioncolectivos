import pytest
import torch
from prediccion.models.a3_eta import TrajectoryEncoder, FleetEncoder, TimeEncoder, A3ETAModel
from prediccion.models import DataInsufficientError, check_data_sufficiency

BATCH = 2
SEQ = 15
N_FLEET = 80


@pytest.fixture
def sample_a3_inputs():
    return {
        "trajectory": torch.randn(BATCH, SEQ, 3),
        "trajectory_mask": torch.zeros(BATCH, SEQ, dtype=torch.bool),
        "fleet": torch.randn(BATCH, N_FLEET, 5),
        "fleet_mask": torch.zeros(BATCH, N_FLEET, dtype=torch.bool),
        "hour_sin": torch.randn(BATCH, 1),
        "hour_cos": torch.randn(BATCH, 1),
        "dow": torch.randint(0, 7, (BATCH,)),
        "dist_remaining_norm": torch.rand(BATCH, 1),
        "time_since_start": torch.randn(BATCH, 1),
        "ts_age_s": torch.zeros(BATCH, 1),
        "has_active_bus": torch.ones(BATCH, 1),
    }


def test_trajectory_encoder_output_shape():
    x = torch.randn(BATCH, SEQ, 3)
    mask = torch.zeros(BATCH, SEQ, dtype=torch.bool)
    enc = TrajectoryEncoder()
    out = enc(x, mask)
    assert out.shape == (BATCH, 64)


def test_fleet_encoder_output_shape():
    fleet = torch.randn(BATCH, N_FLEET, 5)
    mask = torch.zeros(BATCH, N_FLEET, dtype=torch.bool)
    enc = FleetEncoder()
    out = enc(fleet, mask)
    assert out.shape == (BATCH, 64)


def test_a3_full_forward_shape(sample_a3_inputs):
    """Output: (batch, 1)."""
    model = A3ETAModel()
    out = model(**sample_a3_inputs)
    assert out.shape == (BATCH, 1)


def test_a3_output_positive(sample_a3_inputs):
    """ETA siempre positivo (Softplus garantiza esto)."""
    model = A3ETAModel()
    out = model(**sample_a3_inputs)
    assert (out > 0).all()


def test_a3_has_active_bus_false_no_crash(sample_a3_inputs):
    """has_active_bus=0 → no crash, output positivo."""
    sample_a3_inputs["has_active_bus"] = torch.zeros(BATCH, 1)
    model = A3ETAModel()
    out = model(**sample_a3_inputs)
    assert out.shape == (BATCH, 1)
    assert (out > 0).all()


def test_check_data_sufficiency_raises(tmp_path):
    """16 días → DataInsufficientError."""
    for i in range(16):
        (tmp_path / f"2026-03-{i+1:02d}.ndjson.gz").touch()
    with pytest.raises(DataInsufficientError):
        check_data_sufficiency(tmp_path)
