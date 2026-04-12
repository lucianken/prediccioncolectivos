import gzip
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


# ── Shapes ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def mini_shapes_path() -> Path:
    return Path(__file__).parent / "fixtures" / "shapes_mini.json"


@pytest.fixture(scope="session")
def mini_shapes(mini_shapes_path) -> dict:
    with open(mini_shapes_path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def ramal_39_0_points(mini_shapes) -> list[tuple[float, float]]:
    for r in mini_shapes["39"]["ramales"]:
        if r["direction"] == 0:
            return [tuple(p) for p in r["points"]]
    raise ValueError("No ramal direction=0 found")


# ── NDJSON Frames ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_frames(ramal_39_0_points) -> list[dict]:
    """
    20 frames sintéticos deterministas.
    - Frame 0: keyframe con 3 vehículos sobre el ramal 39-0
    - Frames 1-4: deltas avanzando en el shape
    - Frame 5: keyframe forzado
    - Frames 6-8: más deltas
    - Frame 9: gap record
    - Frames 10-18: deltas post-gap
    """
    BASE_TS = 1773583200
    pts = ramal_39_0_points

    # Posiciones iniciales de los 3 vehículos (índices en el shape)
    v1_start, v2_start, v3_start = 3, 10, 16

    def make_vehicle(vid: str, idx: int, ts: int) -> dict:
        lat, lon = pts[min(idx, len(pts)-1)]
        return {
            "id": vid,
            "label": f"3124-{vid}",
            "license_plate": f"ABC{vid}",
            "route_id": "39",
            "trip_id": f"T{vid}",
            "direction_id": 0,
            "start_date": "20260328",
            "start_time": "08:00:00",
            "lat": lat,
            "lon": lon,
            "speed": 7.0,
            "odo": idx * 150,
            "stop_id": "12345",
            "seq": idx,
            "status": 2,
            "ts": ts,
        }

    frames = []

    # Frame 0: keyframe
    ts = BASE_TS
    frames.append({
        "t": ts,
        "keyframe": True,
        "new": [
            make_vehicle("v1", v1_start, ts),
            make_vehicle("v2", v2_start, ts),
            make_vehicle("v3", v3_start, ts),
        ],
        "del": [],
        "upd": [],
    })

    # Frames 1-4: deltas
    v1_idx, v2_idx, v3_idx = v1_start, v2_start, v3_start
    for i in range(1, 5):
        ts = BASE_TS + i * 30
        v1_idx = min(v1_idx + 1, len(pts) - 1)
        v2_idx = min(v2_idx + 1, len(pts) - 1)
        v3_idx = min(v3_idx + 1, len(pts) - 1)
        frames.append({
            "t": ts,
            "keyframe": False,
            "new": [],
            "del": [],
            "upd": [
                {"id": "v1", "ts": ts, "lat": pts[v1_idx][0], "lon": pts[v1_idx][1], "speed": 7.0},
                {"id": "v2", "ts": ts, "lat": pts[v2_idx][0], "lon": pts[v2_idx][1], "speed": 7.0},
                {"id": "v3", "ts": ts, "lat": pts[v3_idx][0], "lon": pts[v3_idx][1], "speed": 7.0},
            ],
        })

    # Frame 5: keyframe forzado (mismo estado)
    ts = BASE_TS + 5 * 30
    frames.append({
        "t": ts,
        "keyframe": True,
        "new": [
            make_vehicle("v1", v1_idx, ts),
            make_vehicle("v2", v2_idx, ts),
            make_vehicle("v3", v3_idx, ts),
        ],
        "del": [],
        "upd": [],
    })

    # Frames 6-8: deltas
    for i in range(6, 9):
        ts = BASE_TS + i * 30
        v1_idx = min(v1_idx + 1, len(pts) - 1)
        v2_idx = min(v2_idx + 1, len(pts) - 1)
        v3_idx = min(v3_idx + 1, len(pts) - 1)
        frames.append({
            "t": ts,
            "keyframe": False,
            "new": [],
            "del": [],
            "upd": [
                {"id": "v1", "ts": ts, "lat": pts[v1_idx][0], "lon": pts[v1_idx][1], "speed": 7.0},
                {"id": "v2", "ts": ts, "lat": pts[v2_idx][0], "lon": pts[v2_idx][1], "speed": 7.0},
                {"id": "v3", "ts": ts, "lat": pts[v3_idx][0], "lon": pts[v3_idx][1], "speed": 7.0},
            ],
        })

    # Frame 9: gap record
    ts = BASE_TS + 9 * 30
    frames.append({"t": ts, "gap": True, "gap_seconds": 700, "reason": "restart"})

    # Frames 10-18: deltas post-gap
    for i in range(10, 19):
        ts = BASE_TS + i * 30
        v1_idx = min(v1_idx + 1, len(pts) - 1)
        v2_idx = min(v2_idx + 1, len(pts) - 1)
        v3_idx = min(v3_idx + 1, len(pts) - 1)
        frames.append({
            "t": ts,
            "keyframe": False,
            "new": [],
            "del": [],
            "upd": [
                {"id": "v1", "ts": ts, "lat": pts[v1_idx][0], "lon": pts[v1_idx][1], "speed": 7.0},
                {"id": "v2", "ts": ts, "lat": pts[v2_idx][0], "lon": pts[v2_idx][1], "speed": 7.0},
                {"id": "v3", "ts": ts, "lat": pts[v3_idx][0], "lon": pts[v3_idx][1], "speed": 7.0},
            ],
        })

    return frames


@pytest.fixture(scope="session")
def sample_ndjson_gz(tmp_path_factory, sample_frames) -> Path:
    p = tmp_path_factory.mktemp("data") / "2026-03-28.ndjson.gz"
    with gzip.open(p, "wt") as f:
        for frame in sample_frames:
            f.write(json.dumps(frame) + "\n")
    return p


# ── Label map ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_label_line_map() -> dict:
    return {"39": "39", "42": "42"}


# ── Trips proyectados ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_trips_projected(sample_ndjson_gz, ramal_39_0_points, sample_label_line_map):
    """Pipeline reader→segmenter→projector sobre sample_ndjson_gz."""
    from prediccion.pipeline.reader import reconstruct_snapshots
    from prediccion.pipeline.segmenter import extract_trips_from_snapshots
    from prediccion.pipeline.projector import project_trip

    snapshots = list(reconstruct_snapshots(sample_ndjson_gz, interval_s=30))
    trips = extract_trips_from_snapshots(iter(snapshots), sample_label_line_map)

    projected = []
    for trip in trips:
        pt = project_trip(trip, ramal_39_0_points)
        if pt.points:
            projected.append(pt)
    return projected


# ── Mock de FleetCache ────────────────────────────────────────────────────

@pytest.fixture
def mock_fleet_cache():
    mock = MagicMock()
    mock.age_s = 15.0
    mock.vehicle_count = 2
    mock.is_loaded = True

    lv1 = MagicMock()
    lv1.id = "v1"; lv1.route_id = "39"; lv1.direction_id = 0
    lv1.lat = -34.617; lv1.lon = -58.461; lv1.speed = 7.0; lv1.ts = 1773583200
    lv1.label = "3124-923"; lv1.line_number = "39"

    lv2 = MagicMock()
    lv2.id = "v2"; lv2.route_id = "39"; lv2.direction_id = 0
    lv2.lat = -34.611; lv2.lon = -58.449; lv2.speed = 8.0; lv2.ts = 1773583200
    lv2.label = "3125-924"; lv2.line_number = "39"

    mock.get_line_vehicles = AsyncMock(return_value=[lv1, lv2])
    mock.get_vehicles = AsyncMock(return_value=[lv1, lv2])
    mock.get_agency_vehicles = AsyncMock(return_value=[lv1, lv2])
    return mock


# ── ShapeLoader mock ──────────────────────────────────────────────────────

@pytest.fixture
def shape_loader_mini(mini_shapes):
    mock = MagicMock()
    mock.is_loaded = True
    mock.available_lines = ["39"]
    return mock


# ── A1Baseline fitted ─────────────────────────────────────────────────────

@pytest.fixture
def a1_fitted(sample_trips_parquet):
    """A1Baseline entrenado con trips sintéticos. Implementado en Plan 02."""
    try:
        from prediccion.models.a1_baseline import A1Baseline
        if sample_trips_parquet is None:
            return None
        model = A1Baseline()
        return model.fit(sample_trips_parquet)
    except ImportError:
        return None


# ── Parquet de trips para Plan 02 ─────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_trips_parquet(tmp_path_factory, sample_trips_projected):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        from prediccion.pipeline.features import make_training_rows_eta

        rows = []
        for trip in sample_trips_projected:
            if trip.points:
                rows.extend(make_training_rows_eta(trip, "39-0", 3000.0))

        if not rows:
            return None

        p = tmp_path_factory.mktemp("parquet") / "train.parquet"
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, p)
        return p
    except ImportError:
        return None
