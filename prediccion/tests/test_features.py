import math
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from prediccion.pipeline.features import encode_time, get_segment_index, make_training_rows_eta

TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")


def ts_for_ba_hour(hour: int, dow_offset: int = 0) -> int:
    """Crea unix timestamp para una hora específica en Buenos Aires (lunes = 0)."""
    # 2026-03-02 es lunes
    dt = datetime(2026, 3, 2 + dow_offset, hour, 0, 0, tzinfo=TZ_BA)
    return int(dt.timestamp())


def test_encode_time_noon():
    ts = ts_for_ba_hour(12)
    enc = encode_time(ts)
    assert enc["hour_sin"] == pytest.approx(0.0, abs=0.02)
    assert enc["hour_cos"] == pytest.approx(-1.0, abs=0.02)


def test_encode_time_midnight_continuity():
    ts_late = ts_for_ba_hour(23) + 59 * 60  # 23:59
    ts_early = ts_for_ba_hour(0) + 60       # 00:01 siguiente día
    enc_late = encode_time(ts_late)
    enc_early = encode_time(ts_early)
    assert abs(enc_late["hour_cos"] - enc_early["hour_cos"]) < 0.05


def test_encode_time_dow_range():
    for offset in range(7):
        ts = ts_for_ba_hour(9, dow_offset=offset)
        enc = encode_time(ts)
        assert 0 <= enc["dow"] <= 6


def test_encode_time_timezone():
    # UTC 15:00 = BsAs 12:00 (UTC-3)
    # Usar timestamp que corresponda a 15:00 UTC
    dt_utc = datetime(2026, 3, 2, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
    ts = int(dt_utc.timestamp())
    enc = encode_time(ts)
    # 12:00 BsAs → hour_sin ≈ 0, hour_cos ≈ -1
    assert enc["hour_sin"] == pytest.approx(0.0, abs=0.02)
    assert enc["hour_cos"] == pytest.approx(-1.0, abs=0.02)


def test_make_training_rows_count(sample_trips_projected):
    total = 0
    for trip in sample_trips_projected:
        n = len(trip.points)
        rows = make_training_rows_eta(trip, "39-0", 3000.0)
        # Máximo N*(N-1)/2 pares, pero algunos pueden filtrarse
        assert len(rows) <= n * (n - 1) // 2
        total += len(rows)
    assert total > 0


def test_make_training_rows_eta_nonnegative(sample_trips_projected):
    for trip in sample_trips_projected:
        rows = make_training_rows_eta(trip, "39-0", 3000.0)
        for row in rows:
            assert row["observed_eta_s"] >= 0


def test_make_training_rows_dist_positive(sample_trips_projected):
    for trip in sample_trips_projected:
        rows = make_training_rows_eta(trip, "39-0", 3000.0)
        for row in rows:
            assert row["dist_remaining_m"] > 0


def test_get_segment_index():
    assert get_segment_index(0) == 0
    assert get_segment_index(499) == 0
    assert get_segment_index(500) == 1
    assert get_segment_index(1200) == 2
