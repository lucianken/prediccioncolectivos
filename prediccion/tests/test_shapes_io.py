"""Tests del loader v2 de LABEL_LINE_MAP (vigencias from/to)."""

import json

import pytest

from prediccion.pipeline.shapes_io import (
    load_label_line_data,
    load_label_line_map,
    resolve_label_line_index,
    resolve_label_line_map,
)

V2_SAMPLE = {
    "version": 2,
    "lines": {
        "151": {
            "agencies": [
                {"agencyId": "9", "agencyName": "LA NUEVA METROPOL S.A.",
                 "from": "2026-03-28", "to": None},
            ],
            "suffixes": [
                {"suffix": "4045", "agencyId": "9", "from": "2026-03-28", "to": "2026-05-29"},
                {"suffix": "4852", "agencyId": "9", "from": "2026-06-11", "to": None},
            ],
        },
        "39": {
            "agencies": [
                {"agencyId": "1", "agencyName": "AGENCIA 39", "from": "2026-03-28", "to": None},
            ],
            "suffixes": [
                {"suffix": "146", "agencyId": "1", "from": "2026-03-28", "to": None},
            ],
        },
    },
}


@pytest.fixture
def v2_path(tmp_path):
    p = tmp_path / "LABEL_LINE_MAP.json"
    p.write_text(json.dumps(V2_SAMPLE), encoding="utf-8")
    return p


def test_load_v2_union(v2_path):
    m = load_label_line_map(v2_path)
    # sin fecha: union de periodos, ambos sufijos del 151 presentes
    assert m == {"4045": "151", "4852": "151", "146": "39"}


def test_on_date_resolves_vigencia(v2_path):
    # antes del cambio de flota: 4045 vigente, 4852 todavia no existe
    m_may = load_label_line_map(v2_path, on_date="2026-05-15")
    assert m_may.get("4045") == "151"
    assert "4852" not in m_may

    # despues del cambio: 4045 vencido (to=2026-05-29), 4852 vigente
    m_jun = load_label_line_map(v2_path, on_date="2026-06-20")
    assert "4045" not in m_jun
    assert m_jun.get("4852") == "151"

    # bordes inclusive
    assert "4045" in load_label_line_map(v2_path, on_date="2026-05-29")
    assert "4852" in load_label_line_map(v2_path, on_date="2026-06-11")


def test_index_carries_agency(v2_path):
    idx = resolve_label_line_index(load_label_line_data(v2_path), on_date="2026-06-20")
    assert idx["4852"] == {
        "line": "151", "agencyId": "9", "agencyName": "LA NUEVA METROPOL S.A.",
    }


def test_reassigned_suffix_latest_wins_in_union():
    data = {
        "lines": {
            "10": {"agencies": [{"agencyId": "a", "agencyName": "A", "from": "2026-03-28", "to": None}],
                   "suffixes": [{"suffix": "77", "agencyId": "a", "from": "2026-03-28", "to": "2026-05-29"}]},
            "20": {"agencies": [{"agencyId": "b", "agencyName": "B", "from": "2026-03-28", "to": None}],
                   "suffixes": [{"suffix": "77", "agencyId": "b", "from": "2026-06-11", "to": None}]},
        }
    }
    assert resolve_label_line_map(data) == {"77": "20"}
    assert resolve_label_line_map(data, on_date="2026-05-01") == {"77": "10"}
    assert resolve_label_line_map(data, on_date="2026-06-15") == {"77": "20"}


def test_v3_other_lines_excluded_by_default(tmp_path):
    """v3: `lines` = AMBA, `other_lines` = homónimos del interior."""
    v3 = {
        "version": 3,
        "lines": {
            "12": {"agencies": [{"agencyId": "6", "agencyName": "T.A. CALLAO",
                                 "from": "2026-03-28", "to": None}],
                   "suffixes": [{"suffix": "621", "agencyId": "6",
                                 "from": "2026-03-28", "to": None}]},
        },
        "other_lines": {
            "12": {"agencies": [{"agencyId": "402", "agencyName": "EMPRESA TUCUMAN",
                                 "from": "2026-03-28", "to": None}],
                   "suffixes": [{"suffix": "3771", "agencyId": "402",
                                 "from": "2026-03-28", "to": None}]},
        },
    }
    p = tmp_path / "LABEL_LINE_MAP.json"
    p.write_text(json.dumps(v3), encoding="utf-8")

    # default: solo AMBA
    assert load_label_line_map(p) == {"621": "12"}
    # include_other: entra también el homónimo del interior
    data = load_label_line_data(p)
    full = resolve_label_line_map(data, include_other=True)
    assert full == {"621": "12", "3771": "12"}
    idx = resolve_label_line_index(data, include_other=True)
    assert idx["3771"]["agencyName"] == "EMPRESA TUCUMAN"


def test_v1_schema_rejected(tmp_path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"map": {"45": {"line": "150"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="v1"):
        load_label_line_map(p)
