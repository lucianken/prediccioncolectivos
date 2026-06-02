import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .segmenter import Trip
    from prediccion.types import ETATrainingRow, TimeFeatures

TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")
SEGMENT_SIZE_M = 500.0   # granulado para A1 lookup table
N_FLEET = 60             # cap de vehículos de flota (ajustar con medir_fleet_max.py)


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
    ramal_id: str | None,
    shape_length_m: float,
    fleet_by_line_at_ts: dict[tuple[str, int], list[dict]] | None = None,
) -> "list[ETATrainingRow]":
    """
    Genera filas de entrenamiento enriquecidas para el modelo de ETA.

    Para cada par (punto_actual P, punto_futuro F) del trip donde F está adelante de P:
    - dist_remaining_m = F.dist_along_shape_m - P.dist_along_shape_m
    - observed_eta_s = F.ts - P.ts
    - seg_idx = get_segment_index(P.dist_along_shape_m)
    - time_enc = encode_time(P.ts)
    - time_since_start = P.ts - points[0].ts
    - traj_flat (30,), traj_len = historial de hasta 10 posiciones (FixedSizeList, paddeado)
    - fleet_flat (N_FLEET*5,), n_fleet = estado de la flota (FixedSizeList, paddeado)
    """
    rows = []
    points = [pt for pt in trip.points if pt.dist_along_shape_m >= 0]

    if shape_length_m <= 0:
        shape_length_m = 1.0

    for i, p in enumerate(points):
        time_enc = encode_time(p.ts)
        seg_idx = get_segment_index(p.dist_along_shape_m)
        dist_along_norm = p.dist_along_shape_m / shape_length_m

        # 1. Historia de trayectoria → traj_flat (30,) float32-compatible, paddeado
        K = 10
        hist_pts = points[max(0, i - K + 1):i + 1]
        traj_actual_len = len(hist_pts)

        traj_flat = [0.0] * 30
        for j, hp in enumerate(hist_pts):
            traj_flat[j * 3 + 0] = hp.dist_along_shape_m / shape_length_m
            traj_flat[j * 3 + 1] = float(hp.speed)
            traj_flat[j * 3 + 2] = 0.0 if j == 0 else float(hp.ts - hist_pts[j - 1].ts)

        # 2. Estado de la flota → fleet_flat (N_FLEET*5,) float32-compatible, paddeado
        fleet_rows = []
        if fleet_by_line_at_ts and trip.line_number:
            fleet_list = fleet_by_line_at_ts.get((trip.line_number, p.ts), [])
            fleet_other = [f for f in fleet_list if f.get("vehicle_id") != trip.vehicle_id]
            for f in fleet_other:
                lat_norm = (f["lat"] - (-34.6)) * 10.0
                lon_norm = (f["lon"] - (-58.4)) * 10.0
                is_same_dir = 1.0 if f["direction_id"] == trip.direction_id else 0.0
                fleet_rows.append([
                    float(lat_norm),
                    float(lon_norm),
                    float(f["speed"]),
                    float(f["direction_id"]),
                    is_same_dir,
                ])
            fleet_rows = fleet_rows[:N_FLEET]

        n_fleet = len(fleet_rows)
        fleet_flat = [0.0] * (N_FLEET * 5)
        for j, row in enumerate(fleet_rows):
            for k, v in enumerate(row[:5]):
                fleet_flat[j * 5 + k] = v

        # 3. Segundos desde el inicio del viaje
        time_since_start = float(p.ts - points[0].ts)

        for f in points[i + 1:]:
            dist_remaining_m = f.dist_along_shape_m - p.dist_along_shape_m
            observed_eta_s = f.ts - p.ts

            if dist_remaining_m < 100.0 or observed_eta_s <= 0:
                continue

            rows.append({
                "ramal_id": ramal_id,
                "seg_idx": seg_idx,
                "dist_remaining_m": float(dist_remaining_m),
                "dist_along_norm": float(dist_along_norm),
                "speed_mps": float(p.speed),
                "hour_sin": time_enc["hour_sin"],
                "hour_cos": time_enc["hour_cos"],
                "dow": time_enc["dow"],
                "has_active_bus": True,
                "observed_eta_s": float(observed_eta_s),
                "time_since_start": time_since_start,
                "traj_flat": traj_flat,
                "traj_len": traj_actual_len,
                "fleet_flat": fleet_flat,
                "n_fleet": n_fleet,
            })

    return rows

