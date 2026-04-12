import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .segmenter import Trip

TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")
SEGMENT_SIZE_M = 500.0   # granulado para A1 lookup table


def encode_time(timestamp_unix: int) -> dict:
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
) -> list[dict]:
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


def make_training_rows_ramal(
    trips_by_vehicle: dict[str, list["Trip"]],
    snapshot_ts: int,
    ramal_labels: dict[str, str],   # {vehicle_id: ramal_id} — de RamalEngine
    route_id_ranks: dict[str, int], # {route_id: rank} — del RouteIdRegistry
) -> dict | None:
    """
    Genera un ejemplo de entrenamiento para el modelo de ramal ID.

    Input: snapshot de todos los vehículos de una línea en snapshot_ts.
    Para cada vehículo: toma los últimos 40 puntos de su trip activo.

    Returns dict (o None si < 3 vehículos etiquetados):
      {
        "fleet": [[lat_norm, lon_norm, speed, route_id_rank, direction_id], ...],
        "histories": [[[dist_norm, speed, dt], ...], ...],  # (n_vehicles, ≤40, 3)
        "labels": [ramal_idx, ...]  # entero, índice de ramal
      }

    lat_norm = lat - lat_mean_linea (centrar elimina drift geográfico)
    dist_norm = dist_along_shape_m / shape_length_m (normalizar 0-1)
    Si no hay shape_length_m disponible, usar 1.0 como fallback.
    """
    # Collect labeled vehicles
    labeled_vehicles = []
    for vehicle_id, trips in trips_by_vehicle.items():
        if vehicle_id not in ramal_labels:
            continue
        # Find the active trip at snapshot_ts
        active_trip = None
        for trip in trips:
            if not trip.points:
                continue
            if trip.points[0].ts <= snapshot_ts <= trip.points[-1].ts:
                active_trip = trip
                break
        if active_trip is None:
            # Use the most recent trip before snapshot_ts
            for trip in reversed(trips):
                if trip.points and trip.points[-1].ts <= snapshot_ts:
                    active_trip = trip
                    break
        if active_trip is None:
            continue
        labeled_vehicles.append((vehicle_id, active_trip, ramal_labels[vehicle_id]))

    if len(labeled_vehicles) < 3:
        return None

    # Compute lat mean for normalization
    all_lats = []
    for _, trip, _ in labeled_vehicles:
        for pt in trip.points[-40:]:
            all_lats.append(pt.lat)
    lat_mean = sum(all_lats) / len(all_lats) if all_lats else 0.0

    # Collect unique ramal ids and create index
    ramal_ids_seen = sorted(set(ramal_id for _, _, ramal_id in labeled_vehicles))
    ramal_idx_map = {rid: i for i, rid in enumerate(ramal_ids_seen)}

    fleet = []
    histories = []
    labels = []

    for vehicle_id, trip, ramal_id in labeled_vehicles:
        last_points = trip.points[-40:]
        if not last_points:
            continue

        # Fleet feature: use last point
        last_pt = last_points[-1]
        route_rank = route_id_ranks.get(trip.route_id, 0)
        lat_norm = last_pt.lat - lat_mean
        # Use last point's lon as-is (could also center, but spec says lat_norm)
        fleet.append([lat_norm, last_pt.lon, last_pt.speed, route_rank, trip.direction_id])

        # History features
        hist = []
        shape_length = 1.0  # fallback
        for pt in last_points:
            dist_norm = pt.dist_along_shape_m / shape_length if pt.dist_along_shape_m >= 0 else 0.0
            dt = snapshot_ts - pt.ts
            hist.append([dist_norm, pt.speed, dt])
        histories.append(hist)

        labels.append(ramal_idx_map[ramal_id])

    if len(labels) < 3:
        return None

    return {
        "fleet": fleet,
        "histories": histories,
        "labels": labels,
    }
