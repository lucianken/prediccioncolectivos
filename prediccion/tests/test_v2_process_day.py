"""process_day (idempotencia, agregar línea) y assemble_dataset (split) con NDJSON sintético."""

import json
import os
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from prediccion.v2.assemble import assemble_dataset, split_days
from prediccion.v2.day import process_day, read_meta, update_manifest
from prediccion.v2.shapes import LineShapes
from prediccion.tests.v2_synth import label_data, line_pts, write_day, write_line_shapes

LABELS = label_data({"9001": "900", "9002": "901", "9003": "902"})
BASE = 1_789_560_000   # 2026-09-16 ~ 08:00 BA


@pytest.fixture
def world(tmp_path):
    shapes_dir = tmp_path / "line_shapes"
    # tres líneas en barrios distintos; cada una con un recorrido
    write_line_shapes(shapes_dir, "900", {"S900": line_pts(-34.70)})
    write_line_shapes(shapes_dir, "901", {"S901": line_pts(-34.50)})
    write_line_shapes(shapes_dir, "902", {"S902": line_pts(-34.30)})
    data_dir = tmp_path / "rec"
    data_dir.mkdir()

    def day(name, base, lines):
        vs = []
        for k, ln in enumerate(lines):
            sfx = {"900": "9001", "901": "9002", "902": "9003"}[ln]
            start = {"900": -34.70, "901": -34.50, "902": -34.30}[ln]
            for v in range(3):
                vs.append({"id": f"{ln}-{v}", "suffix": sfx, "points": line_pts(start), "offset_s": v * 600,
                           "start_time": f"0{8 + v}:00:00"})
        write_day(data_dir / f"{name}.ndjson.gz", base, vs)

    return {"shapes": LineShapes(shapes_dir), "shapes_dir": shapes_dir, "data": data_dir, "day": day,
            "out": tmp_path / "v2", "tmp": tmp_path}


def _run(w, d, lines, **kw):
    return process_day(d, lines, data_dir=w["data"], out_dir=w["out"], shapes=w["shapes"], label_data=LABELS,
                       k_pairs=kw.pop("k_pairs", 16), **kw)


def test_process_day_genera_filas_con_linea_y_shape_id(world):
    world["day"]("2026-09-16", BASE, ["900"])
    m = _run(world, "2026-09-16", ["900"])
    assert m["status"] == "processed" and m["n_rows"] > 0
    t = pq.read_table(world["out"] / "daily" / "2026-09-16.parquet").to_pandas()
    assert set(t["line"]) == {"900"} and set(t["shape_id"]) == {"S900"}
    assert (t["ramal_id"] == t["shape_id"]).all()
    assert t["dist_remaining_m"].min() >= 100.0 and (t["observed_eta_s"] > 0).all()
    assert t.groupby("ts_p").size().max() <= 16 * 3        # K por viaje respetado (3 vehículos, mismo ts_p posible)
    assert "fleet_flat" not in t.columns                     # flota apagada por defecto


def test_process_day_es_idempotente(world):
    world["day"]("2026-09-16", BASE, ["900"])
    first = _run(world, "2026-09-16", ["900"])
    p = world["out"] / "daily" / "2026-09-16.parquet"
    stamp = (p.stat().st_mtime_ns, p.stat().st_size)
    again = _run(world, "2026-09-16", ["900"])
    assert first["status"] == "processed" and again["status"] == "skipped"
    assert (p.stat().st_mtime_ns, p.stat().st_size) == stamp
    # y con --force da el mismo contenido (determinista)
    before = pq.read_table(p).to_pandas().drop(columns=["traj_flat"])
    _run(world, "2026-09-16", ["900"], force=True)
    after = pq.read_table(p).to_pandas().drop(columns=["traj_flat"])
    assert before.equals(after)


def test_agregar_una_linea_reprocesa_solo_los_dias_que_no_la_tienen(world):
    world["day"]("2026-09-16", BASE, ["900", "901"])
    world["day"]("2026-09-17", BASE + 86400, ["900", "901"])
    _run(world, "2026-09-16", ["900", "901"])
    _run(world, "2026-09-17", ["900"])               # este día se construyó solo con la 900
    assert read_meta(world["out"], "2026-09-17")["lines"] == ["900"]

    st = {d: _run(world, d, ["900", "901"])["status"] for d in ("2026-09-16", "2026-09-17")}
    assert st == {"2026-09-16": "skipped", "2026-09-17": "processed"}
    t = pq.read_table(world["out"] / "daily" / "2026-09-17.parquet", columns=["line"]).to_pandas()
    assert set(t["line"]) == {"900", "901"}
    man = update_manifest(world["out"])
    assert man["days"]["2026-09-17"]["lines"] == ["900", "901"]


def test_cambiar_k_reprocesa(world):
    world["day"]("2026-09-16", BASE, ["900"])
    _run(world, "2026-09-16", ["900"], k_pairs=8)
    assert _run(world, "2026-09-16", ["900"], k_pairs=8)["status"] == "skipped"
    assert _run(world, "2026-09-16", ["900"], k_pairs=16)["status"] == "processed"


def test_carry_une_un_viaje_que_cruza_la_medianoche(world):
    # viaje de 60 puntos: 30 pings al final del día 1 y 30 al comienzo del día 2 (mismo start_time)
    pts = line_pts(-34.70, n=60)
    end_d1 = 1_789_603_200 - 30 * 60            # 30 min antes del cambio de día (UTC-3 irrelevante: solo hace falta continuidad)
    write_day(world["data"] / "2026-09-16.ndjson.gz", end_d1,
              [{"id": "x", "suffix": "9001", "points": pts[:30], "start_time": "23:00:00"}])
    write_day(world["data"] / "2026-09-17.ndjson.gz", end_d1 + 30 * 60,
              [{"id": "x", "suffix": "9001", "points": pts[30:], "start_time": "23:00:00"}])
    _run(world, "2026-09-16", ["900"])
    m2 = _run(world, "2026-09-17", ["900"])
    assert m2["carry_in"] is True
    tr = pq.read_table(world["out"] / "daily" / "2026-09-17.trips.parquet").to_pandas()
    # con carry el viaje del día 2 incluye los últimos pings del día 1
    assert tr["n_points"].max() > 30


def test_split_sin_solapes_y_con_exclusiones():
    days = ["2026-09-14", "2026-09-15", "2026-10-14", "2026-10-15", "2026-07-26", "2026-03-28"]
    train, val = split_days(days, "2026-09-15", "2026-10-14", excluded={"2026-07-26"})
    assert val == ["2026-09-15", "2026-10-14"]
    assert train == ["2026-03-28", "2026-09-14"]
    assert not set(train) & set(val)
    assert "2026-10-15" not in train + val


def test_assemble_heldout_nunca_en_train_y_dias_de_validacion_fuera_de_train(world):
    from datetime import datetime, timedelta, timezone
    ba = timezone(timedelta(hours=-3))
    world["day"]("2026-09-14", BASE - 2 * 86400, ["900", "901", "902"])
    world["day"]("2026-09-15", BASE - 86400, ["900", "901", "902"])
    for d in ("2026-09-14", "2026-09-15"):
        _run(world, d, ["900", "901", "902"])
    lines_file = world["tmp"] / "lines.json"
    lines_file.write_text(json.dumps({"train": ["900", "901"], "heldout": ["902"]}))
    summary = assemble_dataset(world["out"], lines_file, shapes_dir=world["shapes_dir"])

    tr = pq.read_table(world["out"] / "training" / "eta_train.parquet", columns=["line", "ts_p"]).to_pandas()
    va = pq.read_table(world["out"] / "training" / "eta_val.parquet", columns=["line", "ts_p"]).to_pandas()
    assert len(tr) > 0 and len(va) > 0
    assert "902" not in set(tr["line"]) | set(va["line"])           # heldout jamás en train ni en val
    dates = lambda df: {datetime.fromtimestamp(int(t), ba).date().isoformat() for t in df["ts_p"]}  # noqa: E731
    assert all(d < "2026-09-15" for d in dates(tr))                  # ningún día de validación en train
    assert dates(va) == {"2026-09-15"}
    assert summary["n_train_days"] == 1 and summary["n_val_days"] == 1
    lengths = json.loads((world["out"] / "shape_lengths.json").read_text())
    assert set(lengths) == {"S900", "S901", "S902"}                  # el eval heldout necesita su largo
    assert (world["out"] / "schedule_dev_medians.json").exists()


def test_assemble_rechaza_lineas_en_train_y_heldout(world):
    lines_file = world["tmp"] / "lines.json"
    lines_file.write_text(json.dumps({"train": ["900"], "heldout": ["900"]}))
    (world["out"] / "daily").mkdir(parents=True)
    with pytest.raises(ValueError):
        assemble_dataset(world["out"], lines_file, shapes_dir=world["shapes_dir"])


def test_make_eval_congelado_estratificado_y_sin_heldout_en_seen(world):
    from prediccion.v2.make_eval import eta_bucket, make_eval
    world["day"]("2026-09-15", BASE - 86400, ["900", "901", "902"])
    _run(world, "2026-09-15", ["900", "901", "902"], k_pairs=64)
    lines_file = world["tmp"] / "lines.json"
    lines_file.write_text(json.dumps({"train": ["900", "901"], "heldout": ["902"]}))

    meta = make_eval(world["out"], lines_file, n_per_bucket=40, seed=1)
    seen = pq.read_table(world["out"] / "eval" / "eval_seen.parquet").to_pandas()
    held = pq.read_table(world["out"] / "eval" / "eval_heldout.parquet").to_pandas()
    assert set(seen["line"]) <= {"900", "901"} and set(held["line"]) == {"902"}
    for df in (seen, held):
        counts = np.bincount(eta_bucket(df["observed_eta_s"].to_numpy()), minlength=4)
        assert counts.max() <= 40                       # tope por bucket
        assert (counts > 0).sum() >= 2                  # estratificado: varios buckets de ETA presentes
    p = world["out"] / "eval" / "eval_seen.parquet"
    stamp = p.stat().st_mtime_ns
    make_eval(world["out"], lines_file, n_per_bucket=40, seed=1)          # ya existe: no se regenera
    assert p.stat().st_mtime_ns == stamp
    make_eval(world["out"], lines_file, n_per_bucket=40, seed=1, force=True)   # --force: mismo contenido
    again = pq.read_table(p).to_pandas()
    assert again[["ts_p", "dist_remaining_m", "observed_eta_s"]].equals(seen[["ts_p", "dist_remaining_m", "observed_eta_s"]])
    assert meta["counts"]["seen/total"] == len(seen)


def test_assemble_only_lines_y_dest_no_pisan_el_dataset_principal(world):
    world["day"]("2026-09-14", BASE - 2 * 86400, ["900", "901", "902"])
    _run(world, "2026-09-14", ["900", "901", "902"])
    lines_file = world["tmp"] / "lines.json"
    lines_file.write_text(json.dumps({"train": ["900", "901"], "heldout": ["902"]}))
    assemble_dataset(world["out"], lines_file, shapes_dir=world["shapes_dir"])
    dest = world["out"] / "e1"
    assemble_dataset(world["out"], lines_file, shapes_dir=world["shapes_dir"], dest_dir=dest, only_lines=["900"])
    only = pq.read_table(dest / "training" / "eta_train.parquet", columns=["line"]).to_pandas()
    full = pq.read_table(world["out"] / "training" / "eta_train.parquet", columns=["line"]).to_pandas()
    assert set(only["line"]) == {"900"} and set(full["line"]) == {"900", "901"}
    with pytest.raises(ValueError):
        assemble_dataset(world["out"], lines_file, shapes_dir=world["shapes_dir"], dest_dir=dest, only_lines=["902"])
