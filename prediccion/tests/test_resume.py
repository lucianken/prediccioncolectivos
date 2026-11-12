"""Reanudación de entrenamientos (A3 y modelo por tramos): cortar y reanudar == entrenar de corrido."""

import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import torch

from prediccion.tests.v2_synth import line_pts, write_line_shapes

N_EPOCHS, K_CUT = 4, 2


def _rows(n, seed):
    rng = np.random.default_rng(seed)
    along = rng.uniform(0, 4000, n).astype(np.float32)
    rem = rng.uniform(150, 2500, n).astype(np.float32)
    hour = rng.uniform(0, 24, n)
    speed = rng.uniform(0, 12, n).astype(np.float32)
    return {
        "line": ["900"] * n, "shape_id": ["S900"] * n, "ramal_id": ["S900"] * n,
        "dist_along_m": along, "dist_remaining_m": rem, "dist_along_norm": (along / 6000.0).astype(np.float32),
        "speed_mps": speed, "hour_sin": np.sin(hour / 24 * 2 * np.pi).astype(np.float32),
        "hour_cos": np.cos(hour / 24 * 2 * np.pi).astype(np.float32),
        "dow": rng.integers(0, 7, n).astype(np.int8), "has_active_bus": np.ones(n, bool),
        "observed_eta_s": (rem / np.maximum(speed, 2.0) + rng.normal(0, 20, n)).clip(5).astype(np.float32),
        "time_since_start": rng.uniform(0, 3000, n).astype(np.float32),
        "ts_age_s": rng.uniform(0, 60, n).astype(np.float32),
        "time_since_last_bus_s": rng.uniform(0, 900, n).astype(np.float32),
        "last_bus_found": rng.random(n) < 0.7,
    }


def _write(path, n_groups, seed):
    path.parent.mkdir(parents=True, exist_ok=True)
    w = None
    for g in range(n_groups):
        t = pa.table(_rows(200, seed + g))
        w = w or pq.ParquetWriter(str(path), t.schema)
        w.write_table(t)
    w.close()


@pytest.fixture
def ml_dir(tmp_path):
    d = tmp_path / "ml"
    _write(d / "training" / "eta_train.parquet", 4, 1)
    _write(d / "training" / "eta_val.parquet", 2, 100)
    (d / "shape_lengths.json").write_text(json.dumps({"S900": 6000.0}))
    shapes = tmp_path / "shapes"
    write_line_shapes(shapes, "900", {"S900": line_pts(-34.70, n=40)})
    (tmp_path / "lines.json").write_text(json.dumps({"train": ["900"], "heldout": []}))
    return d


def _same_weights(a, b):
    sa = torch.load(a, weights_only=False)["model_state_dict"]
    sb = torch.load(b, weights_only=False)["model_state_dict"]
    assert sa.keys() == sb.keys()
    for k in sa:
        torch.testing.assert_close(sa[k].float(), sb[k].float(), rtol=1e-5, atol=1e-6, msg=k)


# ── modelo por tramos ────────────────────────────────────────────────────────

def _path(ml_dir, out, **kw):
    from prediccion.train_path import train
    torch.manual_seed(0)
    return train(ml_dir, out, kw.pop("epochs", N_EPOCHS), 64, 2e-3, None, 0.1, 0, ml_dir.parent / "lines.json",
                 "cpu", shapes_dir=ml_dir.parent / "shapes", **kw)


def test_path_cortar_y_reanudar_da_los_mismos_pesos_y_la_misma_secuencia_de_lr(ml_dir, tmp_path):
    lr_full, lr_a, lr_b = [], [], []
    _path(ml_dir, tmp_path / "full", lr_trace=lr_full)
    _path(ml_dir, tmp_path / "cut", stop_after_epoch=K_CUT, lr_trace=lr_a)
    assert not (tmp_path / "cut" / "path_eta_metrics.json").exists()            # el run se cortó
    res = _path(ml_dir, tmp_path / "cut", resume=True, lr_trace=lr_b)
    assert lr_a + lr_b == pytest.approx(lr_full, rel=1e-9)                       # mismo LR en cada paso
    assert len(lr_b) > 0 and len(lr_a) > 0
    _same_weights(tmp_path / "full" / "path_eta_last.pt", tmp_path / "cut" / "path_eta_last.pt")
    full = json.loads((tmp_path / "full" / "path_eta_metrics.json").read_text())
    assert [h["epoch"] for h in res["history"]] == [1, 2, 3, 4]
    assert res["best_epoch"] == full["best_epoch"]
    assert res["history"][-1]["val_mae_s"] == pytest.approx(full["history"][-1]["val_mae_s"], rel=1e-5)


def test_path_reanudar_con_otra_receta_falla_con_mensaje_claro(ml_dir, tmp_path):
    _path(ml_dir, tmp_path / "r", stop_after_epoch=1)
    with pytest.raises(ValueError, match="epochs"):
        _path(ml_dir, tmp_path / "r", epochs=N_EPOCHS + 2, resume=True)


def test_guardado_atomico_no_deja_tmp_y_last_sirve_para_evaluar(ml_dir, tmp_path):
    from prediccion.models.path_eta import PathETAModel
    _path(ml_dir, tmp_path / "o", stop_after_epoch=1)
    assert not list((tmp_path / "o").glob("*.tmp"))
    ck = torch.load(tmp_path / "o" / "path_eta_last.pt", weights_only=False)
    assert ck["epoch"] == 1 and ck["scheduler_state_dict"] is not None and "rng" in ck
    PathETAModel.from_checkpoint(ck)                                          # last.pt también carga como modelo


# ── A3 ───────────────────────────────────────────────────────────────────────

def _a3(ml_dir, out, **kw):
    from prediccion.models.trainer import train_phase3
    torch.manual_seed(0)
    np.random.seed(0)
    return train_phase3(ml_dir, out, epochs=kw.pop("epochs", N_EPOCHS), batch_size=64, lr=1e-3, device="cpu",
                        patience=99, d_model=8, use_fleet=False, scheduler_type="onecycle", **kw)


def test_a3_cortar_y_reanudar_da_los_mismos_pesos_y_la_misma_secuencia_de_lr(ml_dir, tmp_path):
    lr_full, lr_a, lr_b = [], [], []
    _a3(ml_dir, tmp_path / "full", lr_trace=lr_full)
    r = _a3(ml_dir, tmp_path / "cut", stop_after_epoch=K_CUT, lr_trace=lr_a)
    assert r["stopped_after_epoch"] == K_CUT
    _a3(ml_dir, tmp_path / "cut", resume=True, lr_trace=lr_b)
    assert lr_a + lr_b == pytest.approx(lr_full, rel=1e-9)
    assert len(lr_a) > 0 and len(lr_b) > 0
    _same_weights(tmp_path / "full" / "eta_a3_last.pt", tmp_path / "cut" / "eta_a3_last.pt")
    hf = torch.load(tmp_path / "full" / "eta_a3_last.pt", weights_only=False)["history"]
    hc = torch.load(tmp_path / "cut" / "eta_a3_last.pt", weights_only=False)["history"]
    assert [h["epoch"] for h in hc] == [1, 2, 3, 4]
    assert hc[-1]["val_mae_s"] == pytest.approx(hf[-1]["val_mae_s"], rel=1e-5)


def test_a3_reanudar_con_otra_receta_falla(ml_dir, tmp_path):
    _a3(ml_dir, tmp_path / "r", stop_after_epoch=1)
    with pytest.raises(ValueError, match="no se puede reanudar"):
        _a3(ml_dir, tmp_path / "r", epochs=N_EPOCHS + 1, resume=True)
