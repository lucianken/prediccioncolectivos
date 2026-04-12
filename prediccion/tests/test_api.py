import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from prediccion.api.schemas import ETAResponse, HealthResponse
from prediccion.inference.predictor import ArrivalPrediction


def make_mock_prediction(
    vehicle_id="1839",
    line="39",
    ramal_id="39-0",
    eta_seconds=187.0,
    confidence="high",
) -> ArrivalPrediction:
    return ArrivalPrediction(
        vehicle_id=vehicle_id,
        line=line,
        ramal_id=ramal_id,
        ramal_name="Flores Sur - Retiro",
        direction=0,
        eta_seconds=eta_seconds,
        confidence=confidence,
        dist_to_user_m=1240.0 if vehicle_id else None,
        vehicle_lat=-34.621 if vehicle_id else None,
        vehicle_lon=-58.394 if vehicle_id else None,
        vehicle_speed_mps=7.2 if vehicle_id else None,
        model_used="a1_v1",
    )


@pytest.fixture
def client():
    """TestClient con estado inyectado via mocks (sin lifespan real)."""
    from contextlib import asynccontextmanager
    import prediccion.api.app as app_module
    from prediccion.api.app import app

    mock_predictor = AsyncMock()
    mock_predictor.predict.return_value = [
        make_mock_prediction("1839", eta_seconds=187.0, confidence="high"),
        make_mock_prediction(None, eta_seconds=720.0, confidence="low"),
    ]
    mock_predictor.model_version = "a1_v1"

    mock_fleet = MagicMock()
    mock_fleet.age_s = 15.0
    mock_fleet.vehicle_count = 847
    mock_fleet.is_loaded = True

    mock_shapes = MagicMock()
    mock_shapes.available_lines = ["39", "42"]
    mock_shapes.is_loaded = True

    # Parchear lifespan para que no arranque servicios reales
    @asynccontextmanager
    async def mock_lifespan(app):
        app_module._predictor = mock_predictor
        app_module._fleet_cache = mock_fleet
        app_module._shape_loader = mock_shapes
        yield
        app_module._predictor = None
        app_module._fleet_cache = None
        app_module._shape_loader = None

    original_router = app.router.lifespan_context
    app.router.lifespan_context = mock_lifespan

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.router.lifespan_context = original_router


def test_post_eta_returns_200(client):
    resp = client.post("/api/v1/eta", json={
        "location": {"lat": -34.6037, "lon": -58.3816},
        "line": "39"
    })
    assert resp.status_code == 200


def test_post_eta_response_valid_schema(client):
    resp = client.post("/api/v1/eta", json={
        "location": {"lat": -34.6037, "lon": -58.3816},
        "line": "39"
    })
    parsed = ETAResponse.model_validate(resp.json())
    assert len(parsed.arrivals) == 2


def test_post_eta_arrival_fields(client):
    resp = client.post("/api/v1/eta", json={
        "location": {"lat": -34.6037, "lon": -58.3816},
        "line": "39"
    })
    arrival = resp.json()["arrivals"][0]
    assert arrival["confidence"] == "high"
    assert arrival["vehicle_id"] == "1839"
    assert arrival["eta_seconds"] > 0
    assert arrival["vehicle"] is not None


def test_post_eta_second_arrival_is_prior(client):
    resp = client.post("/api/v1/eta", json={
        "location": {"lat": -34.6037, "lon": -58.3816}
    })
    arrival = resp.json()["arrivals"][1]
    assert arrival["confidence"] == "low"
    assert arrival["vehicle_id"] is None
    assert arrival["vehicle"] is None


def test_post_eta_invalid_lat_422(client):
    resp = client.post("/api/v1/eta", json={
        "location": {"lat": 0.0, "lon": -58.3816}
    })
    assert resp.status_code == 422


def test_post_eta_radius_too_large_422(client):
    resp = client.post("/api/v1/eta", json={
        "location": {"lat": -34.6037, "lon": -58.3816},
        "radius_m": 5000
    })
    assert resp.status_code == 422


def test_post_eta_predictor_error_503(client):
    import prediccion.api.app as app_module
    original = app_module._predictor
    mock_err = AsyncMock()
    mock_err.predict = AsyncMock(side_effect=RuntimeError("fleet offline"))
    app_module._predictor = mock_err
    try:
        resp = client.post("/api/v1/eta", json={
            "location": {"lat": -34.6037, "lon": -58.3816}
        })
        assert resp.status_code == 503
    finally:
        app_module._predictor = original


def test_get_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_get_lines_nonempty(client):
    resp = client.get("/api/v1/lines")
    assert resp.status_code == 200
    assert "39" in resp.json()["lines"]


def test_docs_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
