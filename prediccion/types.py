"""
Tipos de dominio canónicos del sistema de predicción de ETAs.

Este módulo re-exporta todos los tipos de dominio desde sus módulos de origen
y define TypedDicts para estructuras de datos internas que circulan como dicts
sin forma declarada.

Importar desde aquí cuando se necesite referenciar varios tipos a la vez:

    from prediccion.types import Trip, TripPoint, TimeFeatures, ETATrainingRow

Para tipos del layer de inferencia (solo en anotaciones):

    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from prediccion.types import Ramal, LiveVehicle, ArrivalPrediction

Nota de diseño:
  TripPoint y Trip son tipos del pipeline (bajo nivel, sin dependencias pesadas)
  y se importan de forma incondicional.

  Ramal, LiveVehicle y ArrivalPrediction pertenecen al layer de inferencia y
  arrastran httpx, asyncio y lógica de modelo al importarse. Se re-exportan
  únicamente bajo TYPE_CHECKING para que este módulo siga siendo liviano y
  pueda ser importado por cualquier parte del pipeline sin efectos secundarios.
"""

# ---------------------------------------------------------------------------
# Re-exportaciones de tipos del pipeline (importación incondicional — liviana)
# ---------------------------------------------------------------------------

from prediccion.pipeline.segmenter import TripPoint, Trip          # noqa: F401

# ---------------------------------------------------------------------------
# Re-exportaciones de tipos del layer de inferencia (solo para anotaciones)
# Importar bajo TYPE_CHECKING evita que este módulo arrastre la pila de
# inferencia (shape_loader → projector, fleet_cache, predictor) cuando solo
# se necesitan los TypedDicts o los tipos del pipeline.
# ---------------------------------------------------------------------------

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from prediccion.inference.shape_loader import Ramal             # noqa: F401
    from prediccion.inference.fleet_cache import LiveVehicle        # noqa: F401
    from prediccion.inference.predictor import ArrivalPrediction    # noqa: F401


class TimeFeatures(TypedDict):
    """
    Salida de prediccion.pipeline.features.encode_time().
    Encoding cíclico de hora + día de semana en timezone Buenos Aires.
    """
    hour_sin: float   # sin(2π × hora_decimal / 24)
    hour_cos: float   # cos(2π × hora_decimal / 24)
    dow: int          # día de semana: 0=Lunes … 6=Domingo


class ETATrainingRow(TypedDict):
    """
    Una fila de entrenamiento para el modelo A1/A3 de ETA.
    Salida de prediccion.pipeline.features.make_training_rows_eta().
    """
    ramal_id: str
    seg_idx: int
    dist_remaining_m: float
    dist_along_norm: float
    speed_mps: float
    hour_sin: float
    hour_cos: float
    dow: int
    has_active_bus: bool
    observed_eta_s: float
    time_since_start: float
    traj_flat: list[float]       # 30 elementos (10 puntos × 3), paddeado con ceros
    traj_len: int                # longitud real (1–10)
    fleet_flat: list[float]      # N_FLEET*5 elementos, paddeado con ceros
    n_fleet: int
