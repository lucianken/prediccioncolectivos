from __future__ import annotations

import gzip
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config  # noqa: E402
from fake_oba import TEST_KEY, FakeClock, FakeOba, load_fixture  # noqa: E402
from grabador import build  # noqa: E402

# Hora de las fotos de la agencia 708 (2026-10-19): así la fecha BA del archivo es la del fixture
T0 = load_fixture("vehicles-for-agency/708")["currentTime"] / 1000


def read_ndjson(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def read_dir(d: Path) -> list[dict]:
    out = []
    for p in sorted(d.glob("*.ndjson.gz")):
        out += read_ndjson(p)
    return out


@pytest.fixture
def clock():
    return FakeClock(T0)


@pytest.fixture
def oba(clock):
    return FakeOba(clock)


@pytest.fixture
def make(tmp_path, clock, oba):
    """make(**overrides) → Recorder sobre tmp_path/data con el OBA falso."""
    def _make(**kw):
        cfg = Config(oba_key=TEST_KEY, data_dir=tmp_path / "data", base_url="http://oba.test/api/where",
                     record_lines=["39", "151"], sweep=False, arrivals_per_cycle=0,
                     arrival_stops_path=tmp_path / "no_panel.json", trips_per_cycle=0)
        cfg = replace(cfg, **kw)
        return build(cfg, clock=clock, transport=oba)
    return _make
