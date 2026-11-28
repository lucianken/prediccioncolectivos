"""E1c: CityGridEncoder, coordenadas de P/T sobre el shape y compatibilidad hacia atrás del A3."""
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from prediccion.models.a3_eta import (A3ETAModel, CityGridEncoder, GRID_LAT_MIN, GRID_LON_MIN)
from prediccion.models.geo import ShapeGeoStore, geo_coords
from red.geometria import ShapeGeo

FIX = Path(__file__).parent / "fixtures"


def _legacy_inputs(B=4):
    g = torch.Generator().manual_seed(99)
    return dict(
        trajectory=torch.randn(B, 10, 3, generator=g), trajectory_mask=torch.zeros(B, 10, dtype=torch.bool),
        fleet=torch.zeros(B, 0, 5), fleet_mask=torch.zeros(B, 0, dtype=torch.bool),
        hour_sin=torch.randn(B, 1, generator=g), hour_cos=torch.randn(B, 1, generator=g),
        dow=torch.randint(0, 7, (B, 1), generator=g), dist_remaining_norm=torch.rand(B, 1, generator=g),
        time_since_start=torch.randn(B, 1, generator=g), ts_age_s=torch.zeros(B, 1),
        has_active_bus=torch.ones(B, 1), schedule_dev_norm=torch.zeros(B, 1),
        time_since_last_bus_s=torch.zeros(B, 1), last_bus_found=torch.zeros(B, 1))


def test_flag_off_matches_pre_e1c_outputs_and_checkpoint_layout():
    """Salidas de referencia generadas con el código anterior a E1c (semilla 1234, d_model=32)."""
    gold = json.loads((FIX / "a3_legacy_golden.json").read_text())
    torch.manual_seed(1234)
    model = A3ETAModel(d_model=32).eval()
    with torch.no_grad():
        out = model(**_legacy_inputs()).squeeze(-1)
    np.testing.assert_allclose(out.numpy(), gold["out"], atol=1e-6)
    assert sum(p.numel() for p in model.parameters()) == gold["n_params"]
    # un checkpoint viejo (mismas claves y formas) carga en modo estricto
    assert list(model.state_dict().keys()) == gold["keys"]
    legacy_sd = {k: torch.zeros_like(v) for k, v in model.state_dict().items()}
    A3ETAModel(d_model=32).load_state_dict(legacy_sd, strict=True)


REAL_CKPT = Path(__file__).resolve().parents[2] / "data/ml/v2_39_k32/models/eta_a3_best.pt"


@pytest.mark.skipif(not REAL_CKPT.exists(), reason="checkpoint E1 K=32 no disponible")
def test_real_e1_checkpoint_still_loads():
    ck = torch.load(REAL_CKPT, map_location="cpu", weights_only=False)
    sd = ck["model_state_dict"]
    model = A3ETAModel(d_model=int(sd["trajectory_enc.input_proj.weight"].shape[0]))
    model.load_state_dict(sd, strict=True)


def test_city_grid_model_requires_geo_and_uses_it():
    torch.manual_seed(0)
    model = A3ETAModel(d_model=16, city_grid=True).eval()
    inp = _legacy_inputs(3)
    with pytest.raises(ValueError):
        model(**inp)
    geo_a = torch.tensor([[-34.60, -58.40, -34.62, -58.38]] * 3)
    geo_b = torch.tensor([[-34.50, -58.60, -34.70, -58.20]] * 3)
    with torch.no_grad():
        a, b = model(**inp, geo=geo_a), model(**inp, geo=geo_b)
    assert a.shape == (3, 1) and not torch.allclose(a, b)


def test_interpolation_on_synthetic_shape():
    # recorrido en L: 1 km hacia el norte y luego 1 km hacia el este (aprox., ángulo pequeño)
    lat0, lon0 = -34.60, -58.40
    dlat = 1000.0 / 111_320.0
    dlon = 1000.0 / (111_320.0 * np.cos(np.radians(lat0)))
    sg = ShapeGeo([(lat0, lon0), (lat0 + dlat, lon0), (lat0 + dlat, lon0 + dlon)])
    assert sg.length_m == pytest.approx(2000.0, rel=1e-3)
    lat, lon = sg.latlon_at(np.array([0.0, 500.0, 1000.0, 1500.0, 2000.0, 9999.0]))
    np.testing.assert_allclose(lat, [lat0, lat0 + dlat / 2, lat0 + dlat, lat0 + dlat, lat0 + dlat, lat0 + dlat], atol=1e-7)
    np.testing.assert_allclose(lon, [lon0, lon0, lon0, lon0 + dlon / 2, lon0 + dlon, lon0 + dlon], atol=1e-7)


def test_geo_coords_p_and_t_from_parquet_columns(tmp_path):
    pts = [[-34.60, -58.40], [-34.59, -58.40], [-34.59, -58.39]]
    (tmp_path / "7.json").write_text(json.dumps({"ramales": [{"shapeId": "S1", "points": pts}]}))
    store = ShapeGeoStore(tmp_path)
    leg1 = ShapeGeo(pts[:2]).length_m  # tramo norte
    out = geo_coords(["7", "7", "7"], ["S1", "S1", "NOPE"], [0.0, leg1 / 2, 10.0], [leg1, 100.0, 100.0], store)
    assert out.shape == (3, 4) and out.dtype == np.float32
    np.testing.assert_allclose(out[0, :2], pts[0], atol=1e-5)               # P en el inicio
    assert out[0, 2] == pytest.approx(-34.59, abs=1e-4)                     # T al final del primer tramo
    np.testing.assert_allclose(out[1, :2], [-34.595, -58.40], atol=1e-4)    # P a mitad del primer tramo
    assert np.isnan(out[2]).all()                                           # shape inexistente


def test_city_grid_is_bilinear_and_continuous():
    enc = CityGridEncoder(cell_m=500.0, dim=2)
    assert 170 <= enc.n_lat <= 185 and 210 <= enc.n_lon <= 230
    # embedding = función lineal de la posición del vértice => la interpolación bilineal la reproduce exacto
    w = enc.n_lon + 1
    idx = torch.arange((enc.n_lat + 1) * w)
    with torch.no_grad():
        enc.embed.weight[:, 0] = (idx // w).float()
        enc.embed.weight[:, 1] = (idx % w).float()
    lat = torch.tensor([-34.9, -34.55, -34.5500001])
    lon = torch.tensor([-58.7, -58.4, -58.4000001])
    out = enc.encode(lat, lon)
    u = (lat - GRID_LAT_MIN) / 0.8 * enc.n_lat
    v = (lon - GRID_LON_MIN) / 1.2 * enc.n_lon
    np.testing.assert_allclose(out[:, 0].detach().numpy(), u.numpy(), atol=1e-2)
    np.testing.assert_allclose(out[:, 1].detach().numpy(), v.numpy(), atol=1e-2)
    assert torch.allclose(out[1], out[2], atol=1e-3)                        # continuidad
    far = enc.encode(torch.tensor([10.0]), torch.tensor([10.0]))            # fuera del bbox: satura, no revienta
    assert torch.isfinite(far).all()
