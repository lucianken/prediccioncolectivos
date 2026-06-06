import bisect
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

_FALLBACK_M = 250.0      # radio de fallback para time_since_last_bus_s (metros)
_CAP_S = 3600.0          # cap máximo de time_since_last_bus_s (segundos)


def _find_prev_trip(cache: dict, ramal_id: str, vehicle_id: str, p_ts: int):
    """
    Retorna (dist_list, ts_list) del trip más reciente del ramal (excluyendo vehicle_id)
    que tenga al menos un punto antes de p_ts. O (None, None) si no hay.
    Cache entries: (vehicle_id, dist_list, ts_list, min_ts) — dist_list sorted ascending.
    """
    for entry in reversed(cache.get(ramal_id, [])):
        vid, dl, tl, min_ts = entry
        if vid == vehicle_id or min_ts >= p_ts:
            continue
        return dl, tl
    return None, None


def _interp_passage(dist_list: list, ts_list: list, f_dist: float, p_ts: int) -> tuple:
    """
    Estima cuándo el bus de (dist_list, ts_list) pasó por f_dist.
    Retorna (time_since_last_bus_s, last_bus_found).
    """
    n = len(dist_list)
    if n == 0:
        return _CAP_S, False

    idx = bisect.bisect_left(dist_list, f_dist)

    # Bracket exacto: interpolación lineal
    if 0 < idx < n:
        d0, t0 = dist_list[idx - 1], ts_list[idx - 1]
        d1, t1 = dist_list[idx], ts_list[idx]
        if d1 > d0:
            t_passage = t0 + (f_dist - d0) / (d1 - d0) * (t1 - t0)
            if t_passage < p_ts:
                return min(p_ts - t_passage, _CAP_S), True

    # Fallback: ping más cercano dentro de _FALLBACK_M
    for j in (idx - 1, idx):
        if 0 <= j < n and abs(dist_list[j] - f_dist) <= _FALLBACK_M and ts_list[j] < p_ts:
            return min(p_ts - ts_list[j], _CAP_S), True

    return _CAP_S, False


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
    ramal_passage_cache: dict | None = None,
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
        ts_age_s = float(min(p.frame_ts - p.ts, 600))

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

        # 4. Previous bus lookup — O(k) once per P, reused for all F
        prev_dist = prev_ts = None
        use_rpc = ramal_passage_cache is not None and ramal_id
        if use_rpc:
            prev_dist, prev_ts = _find_prev_trip(ramal_passage_cache, ramal_id, trip.vehicle_id, p.ts)

        for f in points[i + 1:]:
            dist_remaining_m = f.dist_along_shape_m - p.dist_along_shape_m
            observed_eta_s = f.ts - p.ts

            if dist_remaining_m < 100.0 or observed_eta_s <= 0:
                continue

            if prev_dist is not None:
                tlb_s, lbf = _interp_passage(prev_dist, prev_ts, f.dist_along_shape_m, p.ts)
            else:
                tlb_s, lbf = _CAP_S, False

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
                "ts_age_s": ts_age_s,
                "traj_flat": traj_flat,
                "traj_len": traj_actual_len,
                "fleet_flat": fleet_flat,
                "n_fleet": n_fleet,
                "time_since_last_bus_s": float(tlb_s),
                "last_bus_found": lbf,
            })

    return rows

