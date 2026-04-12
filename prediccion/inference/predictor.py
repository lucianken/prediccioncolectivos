import logging
import time
from dataclasses import dataclass
from typing import Literal

from prediccion.inference.fleet_cache import FleetCache, LiveVehicle
from prediccion.inference.shape_loader import ShapeLoader, Ramal

logger = logging.getLogger(__name__)


@dataclass
class ArrivalPrediction:
    vehicle_id: str | None
    line: str
    ramal_id: str
    ramal_name: str
    direction: int
    eta_seconds: float
    confidence: Literal["high", "low"]
    dist_to_user_m: float | None
    vehicle_lat: float | None
    vehicle_lon: float | None
    vehicle_speed_mps: float | None
    model_used: str


class ETAPredictor:
    """Motor de predicción de ETA."""

    def __init__(
        self,
        a1_model,   # A1Baseline
        shape_loader: ShapeLoader,
        fleet_cache: FleetCache,
        a3_onnx_path: str | None = None,
        registry=None,
    ):
        self._a1 = a1_model
        self._shapes = shape_loader
        self._fleet = fleet_cache
        self._a3_session = self._load_a3_session(a3_onnx_path) if a3_onnx_path else None
        self._registry = registry
        self._model_version = getattr(a1_model, "model_version", "unknown") if a1_model else "unknown"

    @property
    def model_version(self) -> str:
        return self._model_version

    async def predict(
        self,
        lat: float,
        lon: float,
        line: str | None = None,
        radius_m: float = 300.0,
        max_results: int = 3,
    ) -> list[ArrivalPrediction]:
        """Predice arrivals para la ubicación dada."""
        lines_to_check = [line] if line else self._shapes.available_lines

        all_predictions: list[ArrivalPrediction] = []

        for target_line in lines_to_check:
            result = self._shapes.find_best_ramal(lat, lon, target_line)
            if result is None:
                continue

            ramal, dist_user, perp_error = result

            vehicles = await self._fleet.get_line_vehicles(target_line)
            projected = self._shapes.project_vehicles_to_ramal(vehicles, ramal)

            # Filtrar vehículos ADELANTE del usuario (dist_vehicle > dist_user = viene hacia el usuario)
            ahead_vehicles = [
                (v, dist_v) for v, dist_v in projected
                if dist_v > dist_user
            ]

            for v, dist_v in ahead_vehicles:
                pred = await self._predict_with_vehicle(v, ramal, dist_v, dist_user)
                all_predictions.append(pred)

            # Predicción de headway (sin bus visible)
            headway_pred = await self._predict_headway(ramal, dist_user)
            if headway_pred:
                all_predictions.append(headway_pred)

        # Ordenar por eta ASC
        all_predictions.sort(key=lambda p: p.eta_seconds)
        return all_predictions[:max_results]

    async def _predict_with_vehicle(
        self,
        vehicle: LiveVehicle,
        ramal: Ramal,
        dist_vehicle_m: float,
        dist_user_m: float,
    ) -> ArrivalPrediction:
        """Predicción basada en un bus activo visible."""
        now = int(time.time())

        if self._a3_session is not None:
            # A3 via ONNX — implementación completa en Phase 3
            # Por ahora fallback a A1
            eta, conf = self._a1.predict(ramal.ramal_id, dist_vehicle_m, dist_user_m, now)
            model_used = "a3_onnx"
        else:
            eta, conf = self._a1.predict(ramal.ramal_id, dist_vehicle_m, dist_user_m, now)
            model_used = self._a1.model_version if hasattr(self._a1, "model_version") else "a1"

        # Distancia del vehículo al usuario sobre el shape
        dist_to_user = dist_user_m - dist_vehicle_m

        return ArrivalPrediction(
            vehicle_id=vehicle.id,
            line=ramal.line,
            ramal_id=ramal.ramal_id,
            ramal_name=ramal.name,
            direction=ramal.direction,
            eta_seconds=max(eta, 0.0),
            confidence="high",
            dist_to_user_m=dist_to_user,
            vehicle_lat=vehicle.lat,
            vehicle_lon=vehicle.lon,
            vehicle_speed_mps=vehicle.speed,
            model_used=model_used,
        )

    async def _predict_headway(
        self,
        ramal: Ramal,
        dist_user_m: float,
    ) -> ArrivalPrediction | None:
        """Predicción sin bus visible (confidence='low')."""
        if self._a1 is None:
            return None

        now = int(time.time())
        try:
            headway, conf = self._a1.get_historical_headway(ramal.ramal_id, dist_user_m, now)
        except Exception:
            return None

        return ArrivalPrediction(
            vehicle_id=None,
            line=ramal.line,
            ramal_id=ramal.ramal_id,
            ramal_name=ramal.name,
            direction=ramal.direction,
            eta_seconds=headway,
            confidence="low",
            dist_to_user_m=None,
            vehicle_lat=None,
            vehicle_lon=None,
            vehicle_speed_mps=None,
            model_used="prior",
        )

    def _load_a3_session(self, onnx_path: str):
        """Carga onnxruntime.InferenceSession. None si no disponible."""
        try:
            import onnxruntime as ort
            from pathlib import Path
            if not Path(onnx_path).exists():
                logger.warning(f"ONNX model not found: {onnx_path}")
                return None
            return ort.InferenceSession(onnx_path)
        except ImportError:
            logger.info("onnxruntime not installed — using A1 only")
            return None
        except Exception as e:
            logger.warning(f"Error loading ONNX model: {e}")
            return None
