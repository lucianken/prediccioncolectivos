"""
Lógica de delta entre snapshots de vehículos.

prev_state: dict de vehicle_id (str) → dict de campos
curr_vehicles: lista de dicts con todos los campos del vehículo actual

Campos que se guardan completos en "new" (incluyendo estáticos):
  id, label, license_plate, route_id, trip_id, direction_id,
  start_date, start_time, lat, lon, speed, odo, stop_id, seq, status, ts

Campos que se omiten siempre (siempre 0 en la API BA):
  bearing, occupancy, congestion

En "upd" se incluyen: id + ts + solo los campos que cambiaron respecto a prev_state.
"""

from typing import Any, TypedDict


class VehicleDict(TypedDict, total=False):
    """Campos de un vehículo tal como vienen de parse_vehicles() / GTFS-RT."""
    id: str
    label: str
    license_plate: str
    route_id: str
    trip_id: str
    direction_id: int
    start_date: str
    start_time: str
    lat: float
    lon: float
    speed: float
    odo: int
    stop_id: str
    seq: int
    status: int
    ts: int


class DeltaFrame(TypedDict):
    """Frame de salida de compute_delta() o make_keyframe()."""
    t: int
    new: list[VehicleDict]
    del_: list[str]   # nota: la clave real en JSON es "del"
    upd: list[dict[str, Any]]


# Campos que pueden aparecer en un delta de actualización (además de id y ts)
_DYNAMIC = {'lat', 'lon', 'speed', 'odo', 'stop_id', 'seq', 'status',
            'trip_id', 'route_id', 'direction_id', 'start_time'}


def compute_delta(
    prev_state: dict[str, VehicleDict],
    curr_vehicles: list[VehicleDict],
) -> tuple[dict[str, Any], dict[str, VehicleDict]]:
    """
    Calcula el delta entre prev_state y curr_vehicles.

    Retorna (frame, new_prev_state) donde:
      frame = {"t": <ts>, "new": [...], "del": [...], "upd": [...]}
      new_prev_state = nuevo dict para usar como prev_state en el próximo ciclo

    Los timestamps del frame usan el máximo ts entre curr_vehicles.
    """
    curr_map = {v['id']: v for v in curr_vehicles}
    frame_ts = max((v['ts'] for v in curr_vehicles), default=0)

    new_vehicles = []
    updated_vehicles = []
    deleted_ids = []

    for vid, curr in curr_map.items():
        if vid not in prev_state:
            new_vehicles.append(curr)
        else:
            prev = prev_state[vid]
            changed = {k: curr[k] for k in _DYNAMIC if curr.get(k) != prev.get(k)}
            if changed:
                upd = {'id': vid, 'ts': curr['ts']}
                upd.update(changed)
                updated_vehicles.append(upd)

    for vid in prev_state:
        if vid not in curr_map:
            deleted_ids.append(vid)

    frame = {
        't': frame_ts,
        'new': new_vehicles,
        'del': deleted_ids,
        'upd': updated_vehicles,
    }

    return frame, curr_map


def make_keyframe(curr_vehicles: list[VehicleDict]) -> dict[str, Any]:  # keys: t, keyframe, new, del, upd
    """
    Genera un frame completo (keyframe) con todos los vehículos como nuevos.
    Usado en el primer ciclo y cada 20 ciclos.
    """
    frame_ts = max((v['ts'] for v in curr_vehicles), default=0)
    return {
        't': frame_ts,
        'keyframe': True,
        'new': curr_vehicles,
        'del': [],
        'upd': [],
    }
