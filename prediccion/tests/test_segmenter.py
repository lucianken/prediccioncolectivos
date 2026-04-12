import pytest
from prediccion.pipeline.segmenter import (
    segment_vehicle_history, extract_trips_from_snapshots,
    GAP_THRESHOLD_S, MIN_POINTS
)

BASE_TS = 1773583200


def make_obs(n: int, start_ts: int = BASE_TS, interval: int = 30, **overrides) -> list[dict]:
    obs = []
    for i in range(n):
        o = {
            "ts": start_ts + i * interval,
            "lat": -34.600 + i * 0.001,
            "lon": -58.380 + i * 0.001,
            "speed": 7.0,
            "odo": i * 150,
            "route_id": "39",
            "direction_id": 0,
            "start_date": "20260328",
            "start_time": "08:00:00",
        }
        o.update(overrides)
        obs.append(o)
    return obs


def test_segment_continuous_single_trip():
    obs = make_obs(10)
    trips = segment_vehicle_history("v1", obs)
    assert len(trips) == 1
    assert len(trips[0].points) == 10


def test_segment_gap_splits_into_two():
    obs = make_obs(5)
    # Agregar obs con gap mayor al threshold
    gap_ts = obs[-1]["ts"] + GAP_THRESHOLD_S + 10
    obs2 = make_obs(5, start_ts=gap_ts)
    trips = segment_vehicle_history("v1", obs + obs2)
    assert len(trips) == 2


def test_segment_start_time_change_splits():
    obs1 = make_obs(5, start_time="08:00:00")
    obs2 = make_obs(5, start_ts=BASE_TS + 5 * 30, start_time="10:00:00")
    trips = segment_vehicle_history("v1", obs1 + obs2)
    assert len(trips) == 2


def test_segment_direction_change_splits():
    obs1 = make_obs(5, direction_id=0)
    obs2 = make_obs(5, start_ts=BASE_TS + 5 * 30, direction_id=1)
    trips = segment_vehicle_history("v1", obs1 + obs2)
    assert len(trips) == 2


def test_segment_min_points_filter():
    obs = make_obs(3)  # < MIN_POINTS=5
    trips = segment_vehicle_history("v1", obs)
    assert len(trips) == 0


def test_extract_trips_assigns_line_number(sample_label_line_map):
    obs = make_obs(10)
    snapshots = [(BASE_TS + i * 30, {"v1": obs[i]}) for i in range(len(obs))]
    trips = extract_trips_from_snapshots(iter(snapshots), sample_label_line_map)
    assert any(t.line_number == "39" for t in trips)


def test_extract_trips_unknown_route_none(sample_label_line_map):
    obs = make_obs(10, route_id="9999")
    snapshots = [(BASE_TS + i * 30, {"v1": obs[i]}) for i in range(len(obs))]
    trips = extract_trips_from_snapshots(iter(snapshots), sample_label_line_map)
    assert all(t.line_number is None for t in trips)
