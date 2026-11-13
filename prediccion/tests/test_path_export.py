"""
Exportación ONNX del modelo por tramos y referencia de inferencia desde datos crudos (inference/path_reference.py).
Usa data/ml/export/path_v2b_s0 (script scripts/export_path_onnx.py) y data/ml/v2b/eval; se saltea si faltan.
"""

import math
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "data" / "ml" / "export" / "path_v2b_s0"
CKPT = ROOT / "data" / "ml" / "v2b_sub" / "runs" / "path_lr2e-3_s0" / "path_eta_best.pt"
EVAL = ROOT / "data" / "ml" / "v2b" / "eval"

needs_data = pytest.mark.skipif(not (EXPORT / "manifest.json").exists() or not CKPT.exists()
                                or not (EVAL / "eval_seen.parquet").exists(),
                                reason="falta la exportación, el checkpoint o el eval v2b")


def _sample(which: str, n: int, seed: int = 0):
    import pyarrow.parquet as pq
    t = pq.read_table(EVAL / f"eval_{which}.parquet",
                      columns=["line", "shape_id", "dist_along_m", "dist_remaining_m", "dist_along_norm", "speed_mps",
                               "hour_sin", "hour_cos", "dow", "observed_eta_s", "time_since_start", "ts_age_s",
                               "time_since_last_bus_s", "last_bus_found", "start_unknown", "ts_p"])
    idx = np.random.default_rng(seed).choice(t.num_rows, size=min(n, t.num_rows), replace=False)
    return t.take(np.sort(idx)).to_pandas()


@pytest.fixture(scope="module")
def torch_model():
    import torch
    from prediccion.models.path_eta import PathETAModel
    return PathETAModel.from_checkpoint(torch.load(str(CKPT), map_location="cpu", weights_only=False)).eval()


def _torch_pred(model, df):
    import torch
    from prediccion.models.path_eta import run_model, table_to_batch
    d = {c: (df[c].tolist() if c in ("line", "shape_id") else df[c].to_numpy()) for c in df.columns}
    batch, v = table_to_batch(d, model)
    with torch.no_grad():
        pred = run_model(model, batch, "cpu").clamp(min=0.0).numpy().astype(np.float64)
    return pred, v, batch


@needs_data
@pytest.mark.parametrize("which", ["seen", "heldout"])
def test_onnx_coincide_con_pytorch_en_eval(torch_model, which):
    import onnxruntime as ort
    from prediccion.inference.path_onnx import run_onnx, segment_inputs_from_rows
    df = _sample(which, 1000)
    pred, v, b = _torch_pred(torch_model, df)
    assert len(v) > 900
    seg = segment_inputs_from_rows(torch_model, b["shape_idx"], b["d0"], b["rem"])
    sess = ort.InferenceSession(str(EXPORT / "path_eta.onnx"), providers=["CPUExecutionProvider"])
    eta = run_onnx(sess, {**seg, "line_idx": b["line_idx"].numpy(), "dow": b["dow"][:, 0].numpy(),
                          "h_sin": b["h_sin"][:, 0].numpy(), "h_cos": b["h_cos"][:, 0].numpy(),
                          "state": b["state"][:, :-1].numpy()})[0]
    assert np.abs(np.maximum(eta, 0.0) - pred).max() < 0.5


@needs_data
def test_referencia_desde_lat_lon_crudos_coincide_con_el_pipeline_de_eval(torch_model):
    """Reconstruye lat/lon de P y T sobre el shape, la hora desde ts_p y el estado desde las columnas; compara contra eval."""
    from prediccion.inference.path_reference import eta_on_shapes, load_bundle
    bundle = load_bundle(EXPORT)
    df = _sample("seen", 1500, seed=1)
    pred, v, _ = _torch_pred(torch_model, df)
    df = df.iloc[v].reset_index(drop=True)
    used, diffs = 0, []
    for i, r in df.iterrows():
        sh = bundle.lines.get(r.line, {}).get(r.shape_id)
        if sh is None or r.ts_age_s >= 600:
            continue
        d0, rem = float(r.dist_along_m), float(r.dist_remaining_m)
        pla, plo = sh.latlon_at(d0)
        tla, tlo = sh.latlon_at(d0 + rem)
        d_p, perp_p = sh.project(pla, plo)
        d_t, _ = sh.project(tla, tlo)
        if abs(d_p - d0) > 1.0 or abs(d_t - d0 - rem) > 1.0:      # shape con solapamiento: proyección ambigua, no reconstruible
            continue
        su = bool(r.start_unknown) or math.isnan(r.time_since_start)
        e = eta_on_shapes(bundle, r.line, [dict(shape=sh, d0=d_p, rem=d_t - d_p, tlb=float(r.time_since_last_bus_s),
                                                 lbf=bool(r.last_bus_found))],
                          float(r.ts_p), float(r.speed_mps), float(r.ts_age_s),
                          None if su else float(r.time_since_start), su)[0]
        diffs.append(abs(e - pred[i]))
        used += 1
    assert used > 0.8 * len(df)
    assert max(diffs) < 0.5


@needs_data
def test_predict_from_raw_de_punta_a_punta_sin_historial_ni_coche_de_adelante(torch_model):
    from prediccion.inference.path_reference import load_bundle, predict_from_raw
    bundle = load_bundle(EXPORT)
    df = _sample("seen", 600, seed=2)
    pred, v, _ = _torch_pred(torch_model, df)
    df = df.iloc[v].reset_index(drop=True)
    df = df[(~df.last_bus_found) & (df.ts_age_s < 600) & (df.start_unknown | df.time_since_start.isna())]
    n = 0
    for i, r in df.head(80).iterrows():
        sh = bundle.lines[r.line][r.shape_id]
        d0, rem = float(r.dist_along_m), float(r.dist_remaining_m)
        p, t = sh.latlon_at(d0), sh.latlon_at(d0 + rem)
        if abs(sh.project(*p)[0] - d0) > 1 or abs(sh.project(*t)[0] - d0 - rem) > 1:
            continue
        out = predict_from_raw(bundle, r.line, {"lat": p[0], "lon": p[1], "speed_mps": float(r.speed_mps), "ts": float(r.ts_p)},
                               t, float(r.ts_p) + float(r.ts_age_s), only_shapes=[r.shape_id])
        assert out["status"] == "ok"
        cand = out["candidates"][0]
        assert abs(cand["eta_model_s"] - pred[i]) < 0.5
        assert out["eta_s"] == pytest.approx(max(0.0, cand["eta_model_s"] - r.ts_age_s))
        n += 1
    assert n >= 20


# ── comportamiento de la selección de candidatos (sin checkpoint: usa el export si existe) ─────────────────────

def _scenario(bundle, line="39"):
    shapes = bundle.lines[line]
    sh = next(iter(shapes.values()))
    at = lambda d: sh.latlon_at(d)  # noqa: E731
    return sh, at


@needs_data
def test_linea_fuera_del_modelo_no_predice():
    from prediccion.inference.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    out = predict_from_raw(b, "12", {"lat": -34.6, "lon": -58.4, "speed_mps": 5.0, "ts": 1.79e9}, (-34.61, -58.41), 1.79e9)
    assert out["status"] == "linea_fuera_del_modelo" and out["eta_s"] is None


@needs_data
def test_usuario_atras_del_coche_es_pasado_y_cerca_es_llegando():
    from prediccion.inference.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    veh = lambda d: {"lat": at(d)[0], "lon": at(d)[1], "speed_mps": 6.0, "ts": ts}  # noqa: E731
    only = [sh.id]
    assert predict_from_raw(b, "39", veh(5000), at(3000), ts, only_shapes=only)["status"] == "pasado"
    out = predict_from_raw(b, "39", veh(5000), at(5060), ts, only_shapes=only)
    assert out["status"] == "llegando" and out["eta_s"] == 0.0
    out = predict_from_raw(b, "39", veh(5000), at(8000), ts, only_shapes=only)
    assert out["status"] == "ok" and out["eta_s"] > 0


@needs_data
def test_historial_en_sentido_contrario_descarta_el_shape_y_en_sentido_correcto_lo_acepta():
    from prediccion.inference.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    hist = lambda ds: [{"ts": ts - 60 * (len(ds) - i), "lat": at(d)[0], "lon": at(d)[1]} for i, d in enumerate(ds)]  # noqa: E731
    veh = {"lat": at(5000)[0], "lon": at(5000)[1], "speed_mps": 6.0, "ts": ts}
    fw = predict_from_raw(b, "39", veh, at(8000), ts, history=hist([4000, 4400, 4800]), only_shapes=[sh.id])
    bw = predict_from_raw(b, "39", veh, at(8000), ts, history=hist([6000, 5600, 5300]), only_shapes=[sh.id])
    assert fw["status"] == "ok"
    assert bw["status"] == "sin_candidatos"


@needs_data
def test_con_varios_candidatos_el_eta_anunciado_es_el_minimo():
    from prediccion.inference.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    ts = 1.79e9
    found = False
    for line, shapes in b.lines.items():
        ids = list(shapes)
        for a in ids:
            sa = shapes[a]
            veh = sa.latlon_at(min(2500.0, sa.length_m * 0.2))
            usr = sa.latlon_at(min(7000.0, sa.length_m * 0.6))
            out = predict_from_raw(b, line, {"lat": veh[0], "lon": veh[1], "speed_mps": 5.0, "ts": ts}, usr, ts)
            if len(out["candidates"]) >= 2:
                found = True
                assert out["eta_s"] == pytest.approx(min(c["eta_s"] for c in out["candidates"]))
                assert out["shape_id"] == min(out["candidates"], key=lambda c: c["eta_s"])["shape_id"]
                break
        if found:
            break
    assert found


@needs_data
def test_coche_quieto_en_cabecera_se_marca():
    from prediccion.inference.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    p = at(20.0)
    out = predict_from_raw(b, "39", {"lat": p[0], "lon": p[1], "speed_mps": 0.0, "ts": ts}, at(4000), ts, only_shapes=[sh.id])
    assert out["status"] == "ok" and out["en_cabecera"] is True


@needs_data
def test_ping_viejo_se_descuenta_del_eta():
    from prediccion.inference.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    veh = {"lat": at(3000)[0], "lon": at(3000)[1], "speed_mps": 6.0, "ts": ts}
    a = predict_from_raw(b, "39", veh, at(6000), ts, only_shapes=[sh.id])
    c = predict_from_raw(b, "39", veh, at(6000), ts + 40, only_shapes=[sh.id])
    assert a["candidates"][0]["eta_model_s"] > 0
    assert c["eta_s"] < a["eta_s"] + 1e-6 and c["eta_s"] == pytest.approx(max(0.0, c["candidates"][0]["eta_model_s"] - 40))


@needs_data
def test_coche_de_adelante_pasado_por_T_se_detecta_y_sin_pasar_no_se_encuentra():
    from prediccion.inference.path_reference import last_bus, load_bundle
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1_790_000_000.0
    pings = lambda ds, t0: [(t0 + 60 * i, *at(d)) for i, d in enumerate(ds)]  # noqa: E731
    ahead = {"pings": pings([5000, 5600, 6200, 6800, 7400], ts - 600)}        # pasó por d=6000 hace ~ 500 s
    behind = {"pings": pings([1000, 1500, 2000], ts - 300)}                   # no llegó a T
    t, found = last_bus(b.const, sh, [ahead, behind], 6000.0, ts)
    assert found and 450 < t < 550
    t2, found2 = last_bus(b.const, sh, [behind], 6000.0, ts)
    assert not found2 and t2 == 3600.0
