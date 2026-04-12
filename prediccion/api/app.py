"""FastAPI application para predicción de ETA de colectivos."""
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from prediccion.api.schemas import (
    ETARequest, ETAResponse, Arrival, ResponseMeta,
    HealthResponse, LinesResponse, VehicleInfo, Location
)
from prediccion.inference.predictor import ETAPredictor, ArrivalPrediction
from prediccion.inference.fleet_cache import FleetCache
from prediccion.inference.shape_loader import ShapeLoader
from prediccion.models.a1_baseline import A1Baseline

logger = logging.getLogger(__name__)

_predictor: ETAPredictor | None = None
_fleet_cache: FleetCache | None = None
_shape_loader: ShapeLoader | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _predictor, _fleet_cache, _shape_loader

    config = app.state.config

    # Cargar shapes (requerido — falla si no disponible)
    _shape_loader = ShapeLoader(config["shapes_url"])
    await _shape_loader.load()

    # Arrancar fleet cache (puede fallar — modo degraded)
    _fleet_cache = FleetCache(config["fleet_url"])
    try:
        await _fleet_cache.start()
    except Exception as e:
        logger.critical(f"FleetCache no pudo arrancar: {e}")

    # Cargar modelo
    a1 = A1Baseline.load(config["model_path"])

    _predictor = ETAPredictor(
        a1_model=a1,
        shape_loader=_shape_loader,
        fleet_cache=_fleet_cache,
        a3_onnx_path=config.get("a3_model_path"),
    )

    yield

    if _fleet_cache:
        await _fleet_cache.stop()


app = FastAPI(
    title="Dondeestaelbondi — ETA Predictor",
    description="Predicción de tiempo de arribo para colectivos de Buenos Aires",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.post("/api/v1/eta", response_model=ETAResponse)
async def predict_eta(request: ETARequest) -> ETAResponse:
    if _predictor is None:
        raise HTTPException(503, "Predictor not initialized")

    try:
        predictions = await _predictor.predict(
            lat=request.location.lat,
            lon=request.location.lon,
            line=request.line,
            radius_m=request.radius_m,
            max_results=request.max_results,
        )
    except Exception as e:
        raise HTTPException(503, f"Prediction failed: {e}")

    arrivals = [_to_arrival(p) for p in predictions]

    return ETAResponse(
        location=request.location,
        arrivals=arrivals,
        meta=ResponseMeta(
            model_version=_predictor.model_version,
            fleet_age_s=_fleet_cache.age_s if _fleet_cache else float("inf"),
            shapes_loaded=_shape_loader.is_loaded if _shape_loader else False,
            timestamp=int(time.time()),
        )
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    fleet_age = _fleet_cache.age_s if _fleet_cache else float("inf")
    status = "ok" if fleet_age < 120 else "degraded"
    return HealthResponse(
        status=status,
        fleet_age_s=fleet_age,
        fleet_vehicle_count=_fleet_cache.vehicle_count if _fleet_cache else 0,
        model_version=_predictor.model_version if _predictor else "not_loaded",
        shapes_loaded=_shape_loader.is_loaded if _shape_loader else False,
    )


@app.get("/api/v1/lines", response_model=LinesResponse)
async def list_lines() -> LinesResponse:
    if _shape_loader is None:
        return LinesResponse(lines=[])
    return LinesResponse(lines=sorted(_shape_loader.available_lines))


def _to_arrival(p: ArrivalPrediction) -> Arrival:
    vehicle = None
    if p.vehicle_lat is not None:
        vehicle = VehicleInfo(
            lat=p.vehicle_lat,
            lon=p.vehicle_lon,
            speed_mps=p.vehicle_speed_mps or 0.0,
            dist_to_user_m=p.dist_to_user_m or 0.0,
        )
    return Arrival(
        vehicle_id=p.vehicle_id,
        line=p.line,
        ramal=p.ramal_id,
        ramal_name=p.ramal_name,
        direction=p.direction,
        eta_seconds=round(p.eta_seconds, 1),
        eta_minutes=round(p.eta_seconds / 60, 1),
        confidence=p.confidence,
        vehicle=vehicle,
        model_used=p.model_used,
    )
