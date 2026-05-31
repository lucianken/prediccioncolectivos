import pytest
import torch
from prediccion.models.ramal_id import PerVehicleEncoder, CrossFleetTransformer, RamalIdModel
from prediccion.models import DataInsufficientError, check_data_sufficiency

N_VEHICLES = 5
SEQ_LEN = 40
N_RAMALES = 4
BATCH = 2
FLEET_DIM = 160  # vehicle_dim(128) + route_rank_embed(24) + dir_embed(8)


@pytest.fixture
def sample_ramal_inputs():
    histories = torch.randn(BATCH, N_VEHICLES, SEQ_LEN, 4)  # [lat_norm, lon_norm, speed_mps, dt_s]
    history_mask = torch.zeros(BATCH, N_VEHICLES, SEQ_LEN, dtype=torch.bool)
    history_mask[:, :, -10:] = True  # últimos 10 puntos son padding
    vehicle_mask = torch.zeros(BATCH, N_VEHICLES, dtype=torch.bool)
    route_id_ranks = torch.randint(0, 8, (BATCH, N_VEHICLES))
    direction_ids = torch.randint(0, 2, (BATCH, N_VEHICLES))
    return histories, history_mask, vehicle_mask, route_id_ranks, direction_ids


def test_per_vehicle_encoder_output_shape(sample_ramal_inputs):
    """(batch=2, n_vehicles=5, 40, 4) → (2, 5, 128)."""
    histories, history_mask, *_ = sample_ramal_inputs
    enc = PerVehicleEncoder()
    mask_flat = history_mask.reshape(BATCH * N_VEHICLES, SEQ_LEN)
    out = enc(histories, mask_flat)
    assert out.shape == (BATCH, N_VEHICLES, 128)


def test_cross_fleet_transformer_output_shape():
    """(2, 5, 160) → (2, 5, 160)."""
    x = torch.randn(BATCH, N_VEHICLES, FLEET_DIM)
    mask = torch.zeros(BATCH, N_VEHICLES, dtype=torch.bool)
    cft = CrossFleetTransformer()
    out = cft(x, mask)
    assert out.shape == (BATCH, N_VEHICLES, FLEET_DIM)


def test_ramal_id_full_forward(sample_ramal_inputs):
    """Forward completo: (batch, n_vehicles, n_ramales) logits."""
    histories, history_mask, vehicle_mask, route_id_ranks, direction_ids = sample_ramal_inputs
    model = RamalIdModel(n_ramales=N_RAMALES)
    out = model(histories, history_mask, vehicle_mask, route_id_ranks, direction_ids)
    assert out.shape == (BATCH, N_VEHICLES, N_RAMALES)


def test_ramal_id_output_is_raw_logits(sample_ramal_inputs):
    """Output son logits (no softmax)."""
    histories, history_mask, vehicle_mask, route_id_ranks, direction_ids = sample_ramal_inputs
    model = RamalIdModel(n_ramales=N_RAMALES)
    out = model(histories, history_mask, vehicle_mask, route_id_ranks, direction_ids)
    vals = out.detach().numpy().flatten()
    assert any(v < 0 or v > 1 for v in vals)


def test_ramal_id_padding_mask_no_nan(sample_ramal_inputs):
    """Sin NaN en output con mask normal."""
    histories, history_mask, vehicle_mask, route_id_ranks, direction_ids = sample_ramal_inputs
    model = RamalIdModel(n_ramales=N_RAMALES)
    out = model(histories, history_mask, vehicle_mask, route_id_ranks, direction_ids)
    assert not torch.isnan(out).any()


def test_check_data_sufficiency_raises(tmp_path):
    """16 días → DataInsufficientError."""
    for i in range(16):
        (tmp_path / f"2026-03-{i+1:02d}.ndjson.gz").touch()
    with pytest.raises(DataInsufficientError) as exc:
        check_data_sufficiency(tmp_path)
    assert "90" in str(exc.value)
    assert "16" in str(exc.value)
