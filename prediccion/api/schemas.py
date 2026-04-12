from pydantic import BaseModel, Field
from typing import Literal
import time


class Location(BaseModel):
    lat: float = Field(..., ge=-35.5, le=-34.0)
    lon: float = Field(..., ge=-59.5, le=-57.5)


class ETARequest(BaseModel):
    location: Location
    line: str | None = Field(None, pattern=r"^\d{1,4}$")
    radius_m: float = Field(300.0, ge=50.0, le=2000.0)
    max_results: int = Field(3, ge=1, le=10)


class VehicleInfo(BaseModel):
    lat: float
    lon: float
    speed_mps: float
    dist_to_user_m: float


class Arrival(BaseModel):
    vehicle_id: str | None = None
    line: str
    ramal: str
    ramal_name: str
    direction: int
    eta_seconds: float
    eta_minutes: float
    confidence: Literal["high", "low"]
    vehicle: VehicleInfo | None = None
    model_used: str


class ResponseMeta(BaseModel):
    model_version: str
    fleet_age_s: float
    shapes_loaded: bool
    timestamp: int


class ETAResponse(BaseModel):
    location: Location
    arrivals: list[Arrival]
    meta: ResponseMeta


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    fleet_age_s: float
    fleet_vehicle_count: int
    model_version: str
    shapes_loaded: bool


class LinesResponse(BaseModel):
    lines: list[str]
