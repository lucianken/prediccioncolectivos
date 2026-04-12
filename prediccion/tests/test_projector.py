import math
import pytest
from prediccion.pipeline.projector import haversine_m, project_to_shape, project_trip
from prediccion.pipeline.segmenter import Trip, TripPoint


def test_haversine_bsas_montevideo():
    # Buenos Aires (-34.61, -58.37) → Montevideo (-34.90, -56.19)
    dist = haversine_m(-34.61, -58.37, -34.90, -56.19)
    assert 195_000 < dist < 205_000


def test_haversine_same_point():
    dist = haversine_m(-34.60, -58.38, -34.60, -58.38)
    assert dist == pytest.approx(0.0, abs=0.01)


def test_project_to_shape_first_point(ramal_39_0_points):
    lat, lon = ramal_39_0_points[0]
    dist, perp = project_to_shape(lat, lon, ramal_39_0_points)
    assert dist == pytest.approx(0.0, abs=10.0)
    assert perp == pytest.approx(0.0, abs=5.0)


def test_project_to_shape_last_point(ramal_39_0_points):
    lat, lon = ramal_39_0_points[-1]
    dist, perp = project_to_shape(lat, lon, ramal_39_0_points)
    # Calcular longitud total del shape
    total = sum(
        haversine_m(ramal_39_0_points[i][0], ramal_39_0_points[i][1],
                    ramal_39_0_points[i+1][0], ramal_39_0_points[i+1][1])
        for i in range(len(ramal_39_0_points)-1)
    )
    assert dist == pytest.approx(total, rel=0.05)
    assert perp == pytest.approx(0.0, abs=5.0)


def test_project_to_shape_midpoint(ramal_39_0_points):
    # Punto en el medio del shape
    mid = len(ramal_39_0_points) // 2
    lat, lon = ramal_39_0_points[mid]
    dist, perp = project_to_shape(lat, lon, ramal_39_0_points)
    total = sum(
        haversine_m(ramal_39_0_points[i][0], ramal_39_0_points[i][1],
                    ramal_39_0_points[i+1][0], ramal_39_0_points[i+1][1])
        for i in range(len(ramal_39_0_points)-1)
    )
    assert dist == pytest.approx(total / 2, rel=0.15)
    assert perp < 20.0


def test_project_to_shape_perpendicular_error(ramal_39_0_points):
    # Tomar punto en el medio y desplazarlo ~50m perpendicularmente
    mid = len(ramal_39_0_points) // 2
    lat, lon = ramal_39_0_points[mid]
    # Desplazar ~50m en latitud (1 grado ≈ 111km → 50m ≈ 0.00045°)
    offset_lat = lat + 0.00045
    _, perp = project_to_shape(offset_lat, lon, ramal_39_0_points)
    assert 30.0 < perp < 100.0


def test_project_to_shape_monotonic(sample_trips_projected):
    """dist_along_shape_m debe ser mayormente creciente."""
    for trip in sample_trips_projected:
        if len(trip.points) < 3:
            continue
        dists = [p.dist_along_shape_m for p in trip.points]
        # Contar descensos > 50m
        big_decreases = sum(
            1 for i in range(1, len(dists))
            if dists[i] < dists[i-1] - 50
        )
        total = len(dists) - 1
        assert big_decreases / total < 0.3  # menos del 30% de descensos grandes


def test_project_trip_filters_high_error(ramal_39_0_points):
    # Trip con puntos muy lejos del shape (200m de error)
    far_trip = Trip(vehicle_id="test", route_id="39", direction_id=0, start_time=0)
    # Punto a ~200m del shape (desplazar mucho en lat)
    base_lat, base_lon = ramal_39_0_points[5]
    for i in range(5):
        far_trip.points.append(TripPoint(
            ts=i*30, lat=base_lat + 0.002, lon=base_lon, speed=7.0, odo=i*150
        ))

    # Trip con puntos dentro del shape
    near_trip = Trip(vehicle_id="test2", route_id="39", direction_id=0, start_time=0)
    for i in range(5):
        lat, lon = ramal_39_0_points[i]
        near_trip.points.append(TripPoint(
            ts=i*30, lat=lat, lon=lon, speed=7.0, odo=i*150
        ))

    far_result = project_trip(far_trip, ramal_39_0_points)
    near_result = project_trip(near_trip, ramal_39_0_points)

    assert len(far_result.points) == 0
    assert len(near_result.points) == 5


def test_project_trip_preserves_valid_points(sample_trips_projected):
    for trip in sample_trips_projected:
        assert len(trip.points) > 0
        for pt in trip.points:
            assert pt.perp_error_m <= 150.0
            assert pt.dist_along_shape_m >= 0
