"""Segmentador v2b (segmenter_version=2): unión de huecos, start_unknown, espera en cabecera y final del recorrido.

Los tests miran el comportamiento (qué viajes salen, qué se marca, qué filas se escriben), no cómo se calcula.
"""

import gzip
import json

import numpy as np
import pyarrow.parquet as pq
import pytest

from prediccion.pipeline.projector import ShapeIndex
from prediccion.tests.v2_synth import label_data, line_pts, write_day, write_line_shapes
from prediccion.v2.day import process_day
from prediccion.v2.pairs import sample_pairs
from prediccion.v2.rows import trip_rows
from prediccion.v2.segmenter import segment_geometric
from prediccion.v2.shapes import LineShapes

LON = -58.40
STEP = 0.0015          # ~167 m
T0 = 1_790_000_000


def _shape(n):
    return [(-34.70 + i * STEP, LON) for i in range(n)]


IDX = {"ida": ShapeIndex(_shape(60)), "vuelta": ShapeIndex(list(reversed(_shape(60))))}
IDX_LARGO = {"ida": ShapeIndex(_shape(200))}      # ~33 km: permite saltos que ningún colectivo puede hacer


def _pings(path_idx, t0=T0, dt=60):
    return [(t0 + k * dt, -34.70 + p * STEP, LON, 5.0, 0, 0, "", "", t0 + k * dt, False, "")
            for k, p in enumerate(path_idx)]


def _v2(obs, idx=IDX):
    return segment_geometric("v", obs, idx, segmenter_version=2)


def test_hueco_con_avance_coherente_se_une_y_el_tiempo_sigue():
    a = _pings(np.arange(0, 20, 1.0))
    b = _pings(np.arange(25, 45, 1.0), t0=a[-1][0] + 6 * 60)       # 6 min sin datos; avanzó ~1 km (10 km/h)
    trips = _v2(a + b)
    assert len(trips) == 1
    t = trips[0]
    assert t.points[0].ts == a[0][0] and t.points[-1].ts == b[-1][0]   # un solo viaje, desde la salida real
    assert not t.start_unknown
    assert t.joined_gaps == [(a[-1][0], b[0][0])]
    # el tiempo desde la salida sigue contando a través del hueco
    ts = np.array([p.ts for p in t.points])
    assert (ts[-1] - ts[0]) == 19 * 60 + 6 * 60 + 19 * 60


def test_hueco_con_salto_imposible_no_se_une_y_queda_start_unknown():
    a = _pings(np.arange(0, 20, 1.0))
    b = _pings(np.arange(150, 170, 1.0), t0=a[-1][0] + 6 * 60)     # ~22 km en 6 min: 220 km/h
    trips = _v2(a + b, IDX_LARGO)
    assert len(trips) == 2
    assert not trips[0].start_unknown                              # arrancó en la cabecera
    assert trips[1].start_unknown                                  # arranca a ~25 km del inicio del recorrido
    assert trips[1].points[0].ts == b[0][0] and trips[1].joined_gaps == []


def test_hueco_con_retroceso_no_se_une():
    a = _pings(np.arange(0, 30, 1.0))
    b = _pings(np.arange(20, 45, 1.0), t0=a[-1][0] + 6 * 60)       # después del hueco el coche está más atrás
    trips = _v2(a + b)
    assert len(trips) == 2 and trips[1].start_unknown


def test_coche_parado_horas_en_un_punto_del_recorrido_no_se_une():
    a = _pings(np.arange(0, 20, 1.0))
    b = _pings(np.arange(19, 45, 1.0), t0=a[-1][0] + 3 * 3600)     # 3 h después, en el mismo lugar
    trips = _v2(a + b)
    assert len(trips) == 2 and trips[1].start_unknown


def test_viaje_que_arranca_en_cabecera_no_es_start_unknown():
    trips = _v2(_pings(np.arange(0, 40, 1.0)))
    assert len(trips) == 1 and not trips[0].start_unknown and trips[0].waiting is None


def test_espera_de_7_min_en_cabecera_queda_fuera_y_el_viaje_arranca_al_salir():
    path = [0.0] * 8 + list(np.arange(1, 41, 1.0))                 # 8 pings quietos = 7 min de espera
    trips = _v2(_pings(path))
    assert len(trips) == 1
    t = trips[0]
    last_parked = T0 + 7 * 60
    assert t.points[0].ts == last_parked                           # el viaje arranca en el último ping quieto
    assert not t.start_unknown
    w = t.waiting
    assert w["start_ts"] == T0 and w["end_ts"] == last_parked
    assert w["end_ts"] - w["start_ts"] == 7 * 60 and w["n_pings"] == 7
    assert w["depart_ts"] > w["end_ts"]                            # salió de la zona después
    assert all(p.ts >= last_parked for p in t.points)              # ninguna posición de la espera es de viaje


def test_espera_en_la_terminal_final_no_genera_posiciones_de_viaje():
    ida = list(np.arange(0, 58, 1.0))                              # llega a ~10 m de la terminal (D > L - 400)
    parked = [57.0] * 4                                            # 4 min quieto: menos que el corte viejo de 10 min
    vuelta = list(np.arange(56, 5, -1.0))
    trips = _v2(_pings(ida + parked + vuelta))
    arrival = T0 + 57 * 60
    assert trips[0].points[-1].ts == arrival                       # el viaje termina al llegar
    for t in trips:                                                # y ningún viaje contiene los pings quietos
        pts = [(p.lat, p.ts) for p in t.points]
        quiet = sum(abs(a - b) * 111_320 < 25 for (a, _), (b, _) in zip(pts, pts[1:]))
        assert quiet <= 1
    assert not any(arrival < p.ts <= arrival + 4 * 60 for t in trips[:1] for p in t.points)


def test_v1_por_defecto_da_lo_mismo_que_antes():
    a = _pings(np.arange(0, 20, 1.0))
    b = _pings(np.arange(25, 45, 1.0), t0=a[-1][0] + 6 * 60)
    for kw in ({}, {"segmenter_version": 1}):
        trips = segment_geometric("v", a + b, IDX, **kw)
        assert [(t.points[0].ts, t.points[-1].ts) for t in trips] == [(a[0][0], a[-1][0]), (b[0][0], b[-1][0])]
        assert not hasattr(trips[0], "start_unknown")              # el Trip de siempre, sin campos nuevos


def test_pares_de_entrenamiento_no_cruzan_un_hueco_que_no_se_unio():
    dist = np.arange(0, 3000, 150.0)                               # 20 puntos
    ts = T0 + np.arange(20) * 60
    seg = np.array([0] * 10 + [1] * 10)
    for seed in range(5):
        pi, fj = sample_pairs(dist, ts, 32, seed, seg)
        assert len(pi) > 0 and (seg[pi] == seg[fj]).all()
    pi, fj = sample_pairs(dist, ts, 32, 0)                         # sin seg: igual que siempre, cruza tramos
    assert (seg[pi] != seg[fj]).any()


def test_trip_rows_start_unknown_guarda_nan_y_la_columna():
    kw = dict(line="900", shape_id="S", shape_length_m=5000.0, vehicle_id="v", ts=T0 + np.arange(20) * 60,
              frame_ts=T0 + np.arange(20) * 60, speed=np.full(20, 5.0), dist=np.arange(20) * 150.0, k_pairs=8, seed=1)
    ok = trip_rows(**kw)
    unk = trip_rows(**kw, start_unknown=True)
    assert not ok["start_unknown"].any() and not np.isnan(ok["time_since_start"]).any()
    assert unk["start_unknown"].all() and np.isnan(unk["time_since_start"]).all()
    assert np.array_equal(ok["ts_p"], unk["ts_p"])                 # mismos pares: solo cambia el tiempo desde la salida


# ── process_day con segmentation="geo2" ──────────────────────────────────────

LABELS = label_data({"9001": "900"})
BASE = 1_789_560_000


def _drop_pings(path, vid, from_k, to_k, base):
    """Saca los pings del coche entre los frames from_k..to_k (inclusive): un hueco de datos."""
    lines = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for ln in f:
            fr = json.loads(ln)
            k = (fr["t"] - base) // 60
            if from_k <= k <= to_k:
                fr["upd"] = [u for u in fr["upd"] if u["id"] != vid]
            lines.append(fr)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for fr in lines:
            f.write(json.dumps(fr) + "\n")


@pytest.fixture
def world(tmp_path):
    shapes_dir = tmp_path / "line_shapes"
    write_line_shapes(shapes_dir, "900", {"S900": line_pts(-34.70)})
    (tmp_path / "rec").mkdir()
    return {"shapes": LineShapes(shapes_dir), "data": tmp_path / "rec", "tmp": tmp_path}


def _run(w, day, name, segmentation):
    return process_day(day, ["900"], data_dir=w["data"], out_dir=w["tmp"] / name, shapes=w["shapes"],
                       label_data=LABELS, k_pairs=16, use_carry=False, segmentation=segmentation)


def test_process_day_geo2_une_el_hueco_y_el_tiempo_desde_la_salida_sigue(world):
    pts = line_pts(-34.70)
    p = world["data"] / "2026-09-16.ndjson.gz"
    write_day(p, BASE, [{"id": "a", "suffix": "9001", "points": pts[:50]}])
    _drop_pings(p, "a", 20, 24, BASE)                               # hueco de 6 min, el coche sigue avanzando
    _run(world, "2026-09-16", "geo2", "geo2")
    _run(world, "2026-09-16", "geo", "geo")
    rows = pq.read_table(world["tmp"] / "geo2" / "daily" / "2026-09-16.parquet").to_pandas()
    trips = pq.read_table(world["tmp"] / "geo2" / "daily" / "2026-09-16.trips.parquet").to_pandas()
    assert len(trips) == 1 and trips["n_joined_gaps"].iloc[0] == 1 and not trips["start_unknown"].iloc[0]
    assert not rows["start_unknown"].any() and not rows["time_since_start"].isna().any()
    after_gap = rows[rows["ts_p"] >= BASE + 25 * 60]
    assert len(after_gap) > 0
    assert (after_gap["time_since_start"] == after_gap["ts_p"] - BASE).all()    # cuenta desde la salida real
    # el v1 (default) corta el hueco: dos viajes y sin columna nueva
    old = pq.read_table(world["tmp"] / "geo" / "daily" / "2026-09-16.parquet")
    assert "start_unknown" not in old.column_names
    assert len(pq.read_table(world["tmp"] / "geo" / "daily" / "2026-09-16.trips.parquet")) == 2
    assert not (world["tmp"] / "geo" / "daily" / "2026-09-16.waiting.parquet").exists()


def test_process_day_geo2_hueco_no_unido_marca_start_unknown_con_nan_y_no_cruza_pares(world):
    pts = line_pts(-34.70)
    p = world["data"] / "2026-09-16.ndjson.gz"
    # sube hasta el punto 29 y, tras 6 min sin datos, aparece más atrás (punto 20) y sigue
    write_day(p, BASE, [{"id": "b", "suffix": "9001", "points": pts[:30] + pts[20:50]}])
    _drop_pings(p, "b", 30, 34, BASE)
    _run(world, "2026-09-16", "geo2", "geo2")
    rows = pq.read_table(world["tmp"] / "geo2" / "daily" / "2026-09-16.parquet").to_pandas()
    trips = pq.read_table(world["tmp"] / "geo2" / "daily" / "2026-09-16.trips.parquet").to_pandas()
    assert sorted(trips["start_unknown"].tolist()) == [False, True]
    unk, ok = rows[rows["start_unknown"]], rows[~rows["start_unknown"]]
    assert len(unk) > 0 and len(ok) > 0
    assert unk["time_since_start"].isna().all() and ok["time_since_start"].notna().all()
    # cada fila de un viaje tiene su P y su F en ese viaje: ts_p + ETA no pasa del último ping del viaje
    assert (ok["ts_p"] + ok["observed_eta_s"] <= BASE + 29 * 60).all()


def test_process_day_geo2_escribe_la_espera_en_cabecera_aparte(world):
    pts = line_pts(-34.70)
    write_day(world["data"] / "2026-09-16.ndjson.gz", BASE,
              [{"id": "w", "suffix": "9001", "points": [pts[0]] * 8 + pts[1:40]}])      # 7 min quieto en la cabecera
    _run(world, "2026-09-16", "geo2", "geo2")
    w = pq.read_table(world["tmp"] / "geo2" / "daily" / "2026-09-16.waiting.parquet").to_pandas()
    assert len(w) == 1
    r = w.iloc[0]
    assert r["vehicle_id"] == "w" and r["line"] == "900" and r["shape_id"] == "S900"
    assert r["wait_s"] == 7 * 60 and r["wait_start_ts"] == BASE and r["wait_end_ts"] == BASE + 7 * 60
    assert r["depart_ts"] > r["wait_end_ts"] and r["n_pings"] == 7
    rows = pq.read_table(world["tmp"] / "geo2" / "daily" / "2026-09-16.parquet").to_pandas()
    assert rows["ts_p"].min() >= BASE + 7 * 60                      # ninguna fila de entrenamiento sale de la espera


def test_medianas_de_schedule_dev_ignoran_los_time_since_start_nan(tmp_path):
    import pyarrow as pa
    from prediccion.pipeline.build_schedule_dev_table import build_medians
    n = 10
    tss = [float(i) for i in range(n)] + [float("nan")] * 10          # 10 reales (mediana 4,5) y 10 start_unknown
    t = pa.table({"ramal_id": ["S"] * (2 * n), "dist_along_norm": [0.5 + 0.001 * i for i in range(2 * n)],
                  "time_since_start": pa.array(tss, pa.float32())})
    pq.write_table(t, tmp_path / "train.parquet")
    build_medians(tmp_path / "train.parquet", tmp_path / "med.json", force=True)
    med = json.loads((tmp_path / "med.json").read_text())
    assert med["S"]["10"] == pytest.approx(4.5)
