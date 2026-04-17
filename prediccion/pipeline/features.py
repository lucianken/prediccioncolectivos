import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .segmenter import Trip
    from prediccion.types import ETATrainingRow, TimeFeatures

TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")
SEGMENT_SIZE_M = 500.0   # granulado para A1 lookup table


def encode_time(timestamp_unix: int) -> "TimeFeatures":
    """
    Convierte unix timestamp a features temporales cíclicas.
    Returns: {
      "hour_sin": float,   # sin(2π × hora / 24)
      "hour_cos": float,   # cos(2π × hora / 24)
      "dow": int,          # día de semana 0=Lunes ... 6=Domingo
    }
    Usa timezone America/Argentina/Buenos_Aires (UTC-3, sin DST).
    """
    dt = datetime.fromtimestamp(timestamp_unix, tz=TZ_BA)
    hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    angle = 2 * math.pi * hour / 24.0
    return {
        "hour_sin": math.sin(angle),
        "hour_cos": math.cos(angle),
        "dow": dt.weekday(),  # 0=Monday ... 6=Sunday
    }


def get_segment_index(dist_m: float, segment_size_m: float = SEGMENT_SIZE_M) -> int:
    """
    Convierte distancia (metros) a índice de segmento.
    Ejemplo: dist=0 → 0, dist=499 → 0, dist=500 → 1, dist=1200 → 2
    """
    return int(dist_m // segment_size_m)


def make_training_rows_eta(
    trip: "Trip",
    ramal_id: str,
    shape_length_m: float,
) -> "list[ETATrainingRow]":
    """
    Genera filas de entrenamiento para el modelo de ETA.

    Para cada par (punto_actual P, punto_futuro F) del trip donde F está adelante de P:
    - dist_remaining_m = F.dist_along_shape_m - P.dist_along_shape_m  (debe ser > 0)
    - observed_eta_s = F.ts - P.ts  (debe ser > 0)
    - seg_idx = get_segment_index(P.dist_along_shape_m)
    - time_enc = encode_time(P.ts)

    Retorna lista de dicts con keys:
      ramal_id, seg_idx, dist_remaining_m, dist_along_norm,
      speed_mps, hour_sin, hour_cos, dow, has_active_bus (siempre True),
      observed_eta_s

    dist_along_norm = P.dist_along_shape_m / shape_length_m
    Filtra pares donde observed_eta_s <= 0 o dist_remaining_m <= 0.
    Solo puntos con dist_along_shape_m >= 0 (proyectados).
    """
    rows = []
    points = [pt for pt in trip.points if pt.dist_along_shape_m >= 0]

    if shape_length_m <= 0:
        shape_length_m = 1.0

    for i, p in enumerate(points):
        time_enc = encode_time(p.ts)
        seg_idx = get_segment_index(p.dist_along_shape_m)
        dist_along_norm = p.dist_along_shape_m / shape_length_m

        for f in points[i + 1:]:
            dist_remaining_m = f.dist_along_shape_m - p.dist_along_shape_m
            observed_eta_s = f.ts - p.ts

            if dist_remaining_m <= 0 or observed_eta_s <= 0:
                continue

            rows.append({
                "ramal_id": ramal_id,
                "seg_idx": seg_idx,
                "dist_remaining_m": dist_remaining_m,
                "dist_along_norm": dist_along_norm,
                "speed_mps": p.speed,
                "hour_sin": time_enc["hour_sin"],
                "hour_cos": time_enc["hour_cos"],
                "dow": time_enc["dow"],
                "has_active_bus": True,
                "observed_eta_s": observed_eta_s,
            })

    return rows

