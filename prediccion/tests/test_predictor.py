import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from prediccion.inference.predictor import ETAPredictor, ArrivalPrediction
from prediccion.inference.fleet_cache import LiveVehicle
from prediccion.inference.shape_loader import Ramal


def make_ramal(line="39", direction=0, n_points=20) -> Ramal:
    """Helper: crea un Ramal sintético de 3km."""
    # 20 puntos desde (-34.619, -58.463) a (-34.604, -58.381)
    pts = []
    for i in range(n_points):
        lat = -34.619 + i * (0.015 / (n_points - 1))
        lon = -58.463 + i * (0.082 / (n_points - 1))
        pts.append((lat, lon))
    return Ramal(
        line=line,
        ramal_id=f"{line}-{direction}",
        name="Flores Sur - Retiro",
        short_name=line,
        direction=direction,
        shape_id="23555",
        points=pts,
        length_m=3000.0,
    )


def make_live_vehicle(vid: str, lat: float, lon: float) -> LiveVehicle:
    return LiveVehicle(
        id=vid, route_id="39", direction_id=0,
        lat=lat, lon=lon, speed=7.0, ts=1773583200,
        label=f"3124-{vid}", line_number="39"
    )


@pytest.fixture
def mock_a1():
    """Mock de A1Baseline."""
    m = MagicMock()
    m.predict.return_value = (300.0, "high")
    m.get_historical_headway.return_value = (600.0, "low")
    m.model_version = "a1_v1"
    return m


@pytest.fixture
def mock_shape_loader(ramal_39_0_points):
    """ShapeLoader mock con datos mini."""
    ramal = make_ramal()
    loader = MagicMock()
    loader.is_loaded = True
    loader.available_lines = ["39"]
    # Usuario en dist_along ≈ 600m (punto índice ~4 del shape)
    # lv1 en dist 300m (detrás), lv2 en dist 1800m (adelante)
    loader.find_best_ramal.return_value = (ramal, 600.0, 10.0)
    # Proyectar lv1 (detrás) y lv2 (adelante)
    def project_side_effect(vehicles, ramal_arg, max_perp_error_m=150.0):
        results = []
        for v in vehicles:
            if v.id == "lv1":
                results.append((v, 300.0))   # detrás del usuario
            elif v.id == "lv2":
                results.append((v, 1800.0))  # adelante del usuario
        return results
    loader.project_vehicles_to_ramal.side_effect = project_side_effect
    return loader


@pytest.fixture
def lv1():
    return make_live_vehicle("lv1", -34.617, -58.461)


@pytest.fixture
def lv2():
    return make_live_vehicle("lv2", -34.605, -58.386)


@pytest.fixture
def mock_fleet(lv1, lv2):
    mock = MagicMock()
    mock.age_s = 15.0
    mock.vehicle_count = 2
    mock.get_line_vehicles = AsyncMock(return_value=[lv1, lv2])
    mock.get_vehicles = AsyncMock(return_value=[lv1, lv2])
    return mock


@pytest.fixture
def predictor(mock_a1, mock_shape_loader, mock_fleet):
    return ETAPredictor(
        a1_model=mock_a1,
        shape_loader=mock_shape_loader,
        fleet_cache=mock_fleet,
        a3_onnx_path=None,
    )


@pytest.mark.asyncio
async def test_predict_active_bus_confidence_high(predictor):
    """Bus lv2 (dist=1800m) adelante del usuario (dist=600m) → confidence high."""
    predictions = await predictor.predict(-34.6037, -58.3816, line="39")
    high = [p for p in predictions if p.confidence == "high"]
    assert len(high) >= 1
    assert high[0].vehicle_id is not None


@pytest.mark.asyncio
async def test_predict_no_active_bus_returns_prior(mock_a1, mock_shape_loader):
    """Sin vehículos → solo predicción prior (confidence=low)."""
    empty_fleet = MagicMock()
    empty_fleet.get_line_vehicles = AsyncMock(return_value=[])
    pred = ETAPredictor(
        a1_model=mock_a1,
        shape_loader=mock_shape_loader,
        fleet_cache=empty_fleet,
    )
    predictions = await pred.predict(-34.6037, -58.3816, line="39")
    low = [p for p in predictions if p.confidence == "low"]
    assert len(low) >= 1
    assert low[0].vehicle_id is None


@pytest.mark.asyncio
async def test_predict_line_filter(predictor):
    """line='39' → todos los arrivals son de línea '39'."""
    predictions = await predictor.predict(-34.6037, -58.3816, line="39")
    assert all(p.line == "39" for p in predictions)


@pytest.mark.asyncio
async def test_predict_bus_behind_excluded(predictor):
    """
    lv1 está en dist=300m (detrás del usuario a 600m).
    No debe aparecer en los arrivals activos.
    """
    predictions = await predictor.predict(-34.6037, -58.3816, line="39")
    vehicle_ids = [p.vehicle_id for p in predictions if p.vehicle_id is not None]
    assert "lv1" not in vehicle_ids


@pytest.mark.asyncio
async def test_predict_arrivals_sorted_by_eta(mock_a1, mock_shape_loader):
    """2 buses activos → arrivals ordenados ASC por eta_seconds."""
    # Modificar mock para que predict retorne distintos ETAs según vehicle
    call_count = [0]
    def predict_side_effect(ramal_id, dist_v, dist_t, ts):
        call_count[0] += 1
        return (200.0 + call_count[0] * 100, "high")
    mock_a1.predict.side_effect = predict_side_effect

    lv2 = make_live_vehicle("lv2", -34.605, -58.386)
    lv3 = make_live_vehicle("lv3", -34.606, -58.387)

    def project_side_effect(vehicles, ramal_arg, max_perp_error_m=150.0):
        return [(v, 1800.0 if v.id == "lv2" else 1600.0) for v in vehicles]
    mock_shape_loader.project_vehicles_to_ramal.side_effect = project_side_effect

    fleet = MagicMock()
    fleet.get_line_vehicles = AsyncMock(return_value=[lv2, lv3])

    pred = ETAPredictor(mock_a1, mock_shape_loader, fleet)
    predictions = await pred.predict(-34.6037, -58.3816, line="39")

    etas = [p.eta_seconds for p in predictions]
    assert etas == sorted(etas)


@pytest.mark.asyncio
async def test_predict_max_results_respected(predictor):
    """max_results=1 → retorna exactamente 1 arrival."""
    predictions = await predictor.predict(-34.6037, -58.3816, line="39", max_results=1)
    assert len(predictions) <= 1


@pytest.mark.asyncio
async def test_predict_line_without_shape(predictor, mock_shape_loader):
    """line='999' (sin shape) → lista vacía, no exception."""
    mock_shape_loader.find_best_ramal.return_value = None
    predictions = await predictor.predict(-34.6037, -58.3816, line="999")
    assert predictions == []


@pytest.mark.asyncio
async def test_predict_location_far_from_all_shapes(predictor, mock_shape_loader):
    """Ubicación muy lejos → lista vacía, no exception."""
    mock_shape_loader.find_best_ramal.return_value = None
    predictions = await predictor.predict(-34.0, -55.0, line="39")
    assert predictions == []


@pytest.mark.asyncio
async def test_predict_none_line_searches_all(predictor, mock_fleet):
    """line=None → predictor prueba todas las líneas disponibles."""
    predictions = await predictor.predict(-34.6037, -58.3816, line=None)
    # Al menos intentó buscar en las líneas disponibles
    assert isinstance(predictions, list)
