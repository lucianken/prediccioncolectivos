from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class TripPoint:
    ts: int                           # unix timestamp
    lat: float
    lon: float
    speed: float                      # m/s
    odo: int                          # odómetro del viaje (metros)
    dist_along_shape_m: float = -1.0  # -1 = no proyectado aún
    perp_error_m: float = -1.0        # -1 = no proyectado aún
    frame_ts: int = 0                 # frame["t"] global del ciclo de captura


@dataclass
class Trip:
    vehicle_id: str
    route_id: str
    direction_id: int
    start_time: int                   # unix ts del primer punto
    points: list[TripPoint] = field(default_factory=list)
    line_number: str | None = None    # resuelto de LABEL_LINE_MAP


GAP_THRESHOLD_S = 600   # segundos sin observación → corte de trip
MIN_POINTS = 5          # trips con menos puntos se descartan


def segment_vehicle_history(
    vehicle_id: str,
    observations: list[dict[str, object]],
    gap_threshold_s: int = GAP_THRESHOLD_S,
    min_points: int = MIN_POINTS,
) -> list[Trip]:
    """
    Divide la historia de un vehículo en trips.
    Corta en nuevo trip cuando:
    1. gap > gap_threshold_s entre observaciones consecutivas
    2. start_time o start_date cambia (viaje nuevo en la API)
    3. direction_id cambia

    Descarta trips con < min_points puntos.

    observation dict: {ts, lat, lon, speed, odo, route_id, direction_id,
                       start_date, start_time, ...}
    start_time en observation es string "HH:MM:SS" — comparar como string.
    """
    if not observations:
        return []

    trips: list[Trip] = []
    current_trip: Trip | None = None

    for obs in observations:
        ts = obs["ts"]
        lat = obs["lat"]
        lon = obs["lon"]
        speed = obs.get("speed", 0.0)
        odo = obs.get("odo", 0)
        route_id = obs.get("route_id", "")
        direction_id = obs.get("direction_id", 0)
        start_date = obs.get("start_date", "")
        start_time_str = obs.get("start_time", "")

        point = TripPoint(
            ts=ts,
            lat=lat,
            lon=lon,
            speed=speed,
            odo=odo,
            frame_ts=obs.get("frame_ts", ts),
        )

        if current_trip is None:
            current_trip = Trip(
                vehicle_id=vehicle_id,
                route_id=route_id,
                direction_id=direction_id,
                start_time=ts,
            )
            current_trip.points.append(point)
            current_trip._start_time_str = start_time_str  # type: ignore[attr-defined]
            current_trip._start_date = start_date  # type: ignore[attr-defined]
        else:
            prev_point = current_trip.points[-1]
            prev_start_time_str = current_trip._start_time_str  # type: ignore[attr-defined]
            prev_start_date = current_trip._start_date  # type: ignore[attr-defined]

            gap = ts - prev_point.ts
            time_changed = (
                start_time_str != prev_start_time_str
                or start_date != prev_start_date
            )
            direction_changed = direction_id != current_trip.direction_id

            if gap > gap_threshold_s or time_changed or direction_changed:
                # Save current trip if enough points
                if len(current_trip.points) >= min_points:
                    trips.append(current_trip)
                # Start new trip
                current_trip = Trip(
                    vehicle_id=vehicle_id,
                    route_id=route_id,
                    direction_id=direction_id,
                    start_time=ts,
                )
                current_trip.points.append(point)
                current_trip._start_time_str = start_time_str  # type: ignore[attr-defined]
                current_trip._start_date = start_date  # type: ignore[attr-defined]
            else:
                current_trip.points.append(point)

    if current_trip is not None and len(current_trip.points) >= min_points:
        trips.append(current_trip)

    return trips


def extract_trips_from_snapshots(
    snapshots: Iterable[tuple[int, dict[str, dict]]],
    label_line_map: dict[str, str],
) -> list[Trip]:
    """Recolecta observaciones por vehículo, segmenta en trips y resuelve line_number."""
    vehicle_obs: dict[str, list[dict]] = {}

    for ts, state in snapshots:
        for vid, fields in state.items():
            obs = dict(fields)
            obs["ts"] = obs.get("ts", ts)
            if vid not in vehicle_obs:
                vehicle_obs[vid] = []
            vehicle_obs[vid].append(obs)

    all_trips: list[Trip] = []
    for vehicle_id, observations in vehicle_obs.items():
        observations.sort(key=lambda o: o["ts"])
        trips = segment_vehicle_history(vehicle_id, observations)
        for trip in trips:
            trip.line_number = label_line_map.get(trip.route_id)
            all_trips.append(trip)

    return all_trips
