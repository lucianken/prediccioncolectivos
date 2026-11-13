"""v2b: inicio de viaje desconocido (time_since_start NaN + start_unknown) en A3, modelo por tramos y eval.
Comportamiento observable: NaN no llega a la predicción, los datos v2 (sin la columna) siguen andando y los
checkpoints viejos (sin la entrada) se siguen evaluando."""
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import torch

from prediccion.eval import compute_start_unknown_breakdown, predict_a3
from prediccion.models.a3_eta import A3ETAModel
from prediccion.models.eta_dataset import ETADataset
from prediccion.models.path_eta import PathETAModel, build_shape_table, predict_path

N = 12
SHAPE_LEN = 2000.0


def _table(with_col: bool, tss_nan_idx=(1, 4, 7), with_tss: bool = True) -> pa.Table:
    rng = np.random.default_rng(0)
    tss = rng.uniform(100, 3000, N).astype(np.float32)
    tss[list(tss_nan_idx)] = np.nan
    cols = {
        "line": ["9"] * N, "shape_id": ["S1"] * N, "ramal_id": ["S1"] * N,
        "dist_along_m": rng.uniform(0, 800, N).astype(np.float32),
        "dist_remaining_m": rng.uniform(300, 1200, N).astype(np.float32),
        "dist_along_norm": rng.uniform(0, 0.4, N).astype(np.float32),
        "speed_mps": rng.uniform(0, 12, N).astype(np.float32),
        "hour_sin": rng.uniform(-1, 1, N).astype(np.float32), "hour_cos": rng.uniform(-1, 1, N).astype(np.float32),
        "dow": rng.integers(0, 7, N).astype(np.int8), "has_active_bus": np.ones(N, bool),
        "observed_eta_s": rng.uniform(60, 900, N).astype(np.float32),
        "ts_age_s": np.zeros(N, np.float32),
        "time_since_last_bus_s": rng.uniform(0, 600, N).astype(np.float32), "last_bus_found": np.ones(N, np.float32),
    }
    if with_tss:
        cols["time_since_start"] = tss
    if with_col:
        su = np.zeros(N, bool)
        su[list(tss_nan_idx)] = True
        cols["start_unknown"] = su
    return pa.table(cols)


def _write(tmp_path, name, **kw) -> str:
    p = str(tmp_path / name)
    pq.write_table(_table(**kw), p)
    return p


def _batch(path):
    ds = ETADataset(path, shape_lengths={"S1": SHAPE_LEN}, shuffle=False, yield_batch_size=64, use_fleet=False)
    return next(iter(ds))


def test_dataset_imputa_cero_y_marca_start_unknown_cuando_tss_es_nan(tmp_path):
    b = _batch(_write(tmp_path, "v2b.parquet", with_col=True))
    tss, su = b["time_since_start"].squeeze(-1), b["start_unknown"].squeeze(-1)
    assert torch.isfinite(tss).all() and torch.isfinite(b["schedule_dev_norm"]).all()
    assert su.sum().item() == 3 and (tss[su == 1] == 0).all() and (tss[su == 0] > 0).all()


def test_dataset_sin_columna_start_unknown_usa_el_nan_o_cero(tmp_path):
    # v2 sin NaN ni columna: start_unknown = 0 para todas las filas
    b = _batch(_write(tmp_path, "v2.parquet", with_col=False, tss_nan_idx=()))
    assert (b["start_unknown"] == 0).all() and torch.isfinite(b["time_since_start"]).all()
    # sin columna pero con NaN en time_since_start: igual se detecta
    b = _batch(_write(tmp_path, "nan_only.parquet", with_col=False))
    assert b["start_unknown"].sum().item() == 3 and torch.isfinite(b["time_since_start"]).all()
    # sin time_since_start en absoluto (datos viejos)
    b = _batch(_write(tmp_path, "old.parquet", with_col=False, tss_nan_idx=(), with_tss=False))
    assert (b["start_unknown"] == 0).all()


def _a3_inputs(B=4):
    g = torch.Generator().manual_seed(5)
    return dict(
        trajectory=torch.randn(B, 10, 3, generator=g), trajectory_mask=torch.zeros(B, 10, dtype=torch.bool),
        fleet=torch.zeros(B, 0, 5), fleet_mask=torch.zeros(B, 0, dtype=torch.bool),
        hour_sin=torch.randn(B, 1, generator=g), hour_cos=torch.randn(B, 1, generator=g),
        dow=torch.randint(0, 7, (B, 1), generator=g), dist_remaining_norm=torch.rand(B, 1, generator=g),
        time_since_start=torch.rand(B, 1, generator=g), ts_age_s=torch.zeros(B, 1),
        has_active_bus=torch.ones(B, 1), schedule_dev_norm=torch.zeros(B, 1),
        time_since_last_bus_s=torch.zeros(B, 1), last_bus_found=torch.zeros(B, 1))


def test_a3_con_start_unknown_no_produce_nan_ni_ignora_la_senal():
    torch.manual_seed(0)
    m = A3ETAModel(d_model=16, start_unknown=True).eval()
    inp = _a3_inputs()
    inp["time_since_start"][1, 0] = float("nan")          # dato crudo con NaN
    su0, su1 = torch.zeros(4, 1), torch.ones(4, 1)
    with torch.no_grad():
        a, b = m(**inp, start_unknown=su0), m(**inp, start_unknown=su1)
        sin_senal = m(**inp)                               # sin el tensor = start_unknown 0
    assert torch.isfinite(a).all() and torch.isfinite(b).all()
    assert not torch.allclose(a, b)
    torch.testing.assert_close(a, sin_senal)


def test_a3_sin_start_unknown_conserva_su_arquitectura():
    torch.manual_seed(0)
    base, nuevo = A3ETAModel(d_model=16), A3ETAModel(d_model=16, start_unknown=True)
    assert nuevo.mlp[0].in_features == base.mlp[0].in_features + 1
    with pytest.raises(RuntimeError):                      # un checkpoint viejo no carga en el modelo con la entrada...
        nuevo.load_state_dict(base.state_dict())
    base.load_state_dict(base.state_dict())                # ...y el modelo sin la entrada sigue cargándolo


@pytest.mark.parametrize("start_unknown", [False, True])
def test_predict_a3_evalua_checkpoints_con_y_sin_la_entrada(tmp_path, start_unknown):
    torch.manual_seed(0)
    model = A3ETAModel(d_model=16, start_unknown=start_unknown)
    ck = tmp_path / "m.pt"
    torch.save({"model_state_dict": model.state_dict()}, ck)
    p = _write(tmp_path, "eval.parquet", with_col=True)
    pred = predict_a3(p, ck, {"S1": SHAPE_LEN}, None, N, device="cpu")
    assert pred.shape == (N,) and np.isfinite(pred).all()


def _path_model(start_unknown):
    pts = [(-34.60 + 0.0001 * i, -58.40) for i in range(0, 2000, 10)]
    ids, lat, lon, off = build_shape_table({"S1": pts})
    return PathETAModel(ids, lat, lon, off, ["9"], hidden=16, start_unknown=start_unknown)


@pytest.mark.parametrize("start_unknown", [False, True])
@pytest.mark.parametrize("with_col", [False, True])
def test_predict_path_no_produce_nan_con_tss_nan(tmp_path, start_unknown, with_col):
    torch.manual_seed(0)
    m = _path_model(start_unknown).eval()
    ck = tmp_path / "p.pt"
    torch.save(m.checkpoint_dict(), ck)
    pred = predict_path(_write(tmp_path, "e.parquet", with_col=with_col), ck, N, device="cpu")
    assert pred.shape == (N,) and np.isfinite(pred).all()


def test_modelo_por_tramos_usa_start_unknown_como_senal():
    torch.manual_seed(0)
    m = _path_model(True).eval()
    with torch.no_grad():
        m.adj[-1].bias.fill_(0.0)
        m.adj[-1].weight.normal_()
    B = 3
    base = dict(shape_idx=torch.zeros(B, dtype=torch.long), line_idx=torch.ones(B, dtype=torch.long),
                d0=torch.full((B,), 100.0), rem=torch.full((B,), 800.0), h_sin=torch.zeros(B, 1),
                h_cos=torch.ones(B, 1), dow=torch.zeros(B, 1, dtype=torch.long))
    s0 = torch.zeros(B, m.n_state)
    s1 = s0.clone()
    s1[:, m.n_state - 2] = 1.0                              # start_unknown: columna anterior a la reservada
    with torch.no_grad():
        e0, e1 = m(**base, state=s0)[0], m(**base, state=s1)[0]
    assert torch.isfinite(e1).all() and not torch.allclose(e0, e1)


def test_desglose_por_inicio_conocido_y_desconocido():
    pred = np.array([100.0, 200.0, 300.0, 400.0])
    true = np.array([110.0, 260.0, 300.0, 450.0])
    r = compute_start_unknown_breakdown(pred, true, [False, True, False, True])
    assert r["inicio desconocido"]["n"] == 2 and r["inicio conocido"]["n"] == 2
    assert r["inicio desconocido"]["mae"] == pytest.approx(55.0) and r["inicio conocido"]["mae"] == pytest.approx(5.0)
