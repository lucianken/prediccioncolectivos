"""
`export_path_onnx --reshape`: exportar un checkpoint con shapes distintos de los del entrenamiento.
Comportamiento observable: sin la opción aborta; con ella, el bundle describe los shapes nuevos, el ONNX da las mismas
predicciones que PyTorch sobre las tablas nuevas, los pesos no cambian y el manifest declara el origen.
"""
import json

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("onnxruntime")
import numpy as np  # noqa: E402

from prediccion.models.path_eta import PathETAModel, build_shape_table, build_stop_key  # noqa: E402
from prediccion.models.stops import project_stops  # noqa: E402
from prediccion.scripts.export_path_onnx import export  # noqa: E402


def _pts(offset_lon=0.0, n=220):
    return [(-34.60 + 0.00009 * i, -58.40 + offset_lon * min(i, n) / n if offset_lon else -58.40) for i in range(n)]


def _stops(pts, idx):
    return [{"lat": pts[i][0], "lng": pts[i][1]} for i in idx]


def _write_shapes(d, pts, stops):
    d.mkdir(parents=True, exist_ok=True)
    (d / "9.json").write_text(json.dumps({"color": "#000", "ramales": [
        {"shapeId": "S1", "name": "ida", "shortName": "A", "points": [list(p) for p in pts], "stops": stops}]}), encoding="utf-8")


@pytest.fixture()
def setup(tmp_path):
    old_pts = _pts()
    old_stops = _stops(old_pts, [10, 80, 150])
    ids, lat, lon, off = build_shape_table({"S1": old_pts})
    sk = build_stop_key(ids, {"S1": project_stops(old_pts, old_stops)})
    torch.manual_seed(0)
    m = PathETAModel(ids, lat, lon, off, ["9", "8"], hidden=16, stops_feature=True, stop_key=sk)
    ck = tmp_path / "ck.pt"
    torch.save(m.checkpoint_dict(), ck)
    new_pts = _pts(offset_lon=0.003)          # el recorrido ahora se desvía hacia el este
    new_stops = _stops(new_pts, [10, 60, 120, 200])
    return tmp_path, ck, new_pts, new_stops


def test_sin_reshape_un_shape_distinto_aborta_y_con_reshape_se_exporta(setup):
    tmp, ck, new_pts, new_stops = setup
    shapes = tmp / "shapes"
    _write_shapes(shapes, new_pts, new_stops)
    with pytest.raises(SystemExit):
        export(ck, tmp / "out_strict", shapes, verify=False)
    man = export(ck, tmp / "out", shapes, verify=True, reshape=True)
    assert man["reshaped_from"]["weights"] == "sin reentrenar"
    assert man["reshaped_from"]["checkpoint"].endswith("ck.pt")
    assert man["reshaped_from"]["date"] and man["reshaped_from"]["lines_without_shapes"] == ["8"]   # línea 8: sin archivo
    sh = json.loads((tmp / "out" / "lines" / "9.json").read_text(encoding="utf-8"))["shapes"][0]
    assert sh["stops_m"] == project_stops(new_pts, new_stops)           # paradas nuevas (4), no las del checkpoint (3)
    assert len(sh["stops_m"]) == 4
    assert man["n_cells"] == sh["n_cells"]


def test_reshape_deja_los_pesos_y_el_onnx_coherente_con_las_tablas_nuevas(setup):
    tmp, ck, new_pts, new_stops = setup
    shapes = tmp / "shapes"
    _write_shapes(shapes, new_pts, new_stops)
    man = export(ck, tmp / "out", shapes, verify=True, reshape=True)   # _verify compara ONNX contra PyTorch (tol 0,05 s)
    import onnxruntime as ort
    from prediccion.inference.path_onnx import run_onnx, segment_inputs_from_rows
    from prediccion.scripts.export_path_onnx import reshape_checkpoint
    old = torch.load(str(ck), weights_only=False)
    new, _ = reshape_checkpoint(old, shapes)
    for k, v in old["model_state_dict"].items():
        if k not in ("seg_lat", "seg_lon", "shape_off", "stop_key"):
            assert torch.equal(v, new["model_state_dict"][k])
    model = PathETAModel.from_checkpoint(new).eval()
    n = 5
    d0 = torch.tensor([0.0, 300.0, 800.0, 1200.0, 100.0])
    rem = torch.tensor([900.0, 1000.0, 600.0, 500.0, 1700.0])
    seg = segment_inputs_from_rows(model, torch.zeros(n, dtype=torch.long), d0, rem)
    ex = dict(line_idx=np.ones(n, np.int32), dow=np.zeros(n, np.int32), h_sin=np.zeros(n, np.float32),
              h_cos=np.ones(n, np.float32), state=np.zeros((n, model.n_state - 1), np.float32))
    sess = ort.InferenceSession(str(tmp / "out" / "path_eta.onnx"), providers=["CPUExecutionProvider"])
    got = run_onnx(sess, {**seg, **ex})[0]
    st = torch.zeros(n, model.n_state)
    with torch.no_grad():
        ref = model(torch.zeros(n, dtype=torch.long), torch.ones(n, dtype=torch.long), d0, rem, torch.zeros(n, 1),
                    torch.ones(n, 1), torch.zeros(n, 1, dtype=torch.long), st)[0].numpy()
    assert np.abs(got - ref).max() < 0.05 and np.isfinite(got).all() and (got > 0).all()
    assert man["checkpoint"]["path"].endswith("ck.pt")


def test_reshape_reporta_linea_sin_shapes_y_sigue(setup):
    tmp, ck, _, _ = setup
    shapes = tmp / "vacio"
    shapes.mkdir()
    man = export(ck, tmp / "out", shapes, verify=False, reshape=True)
    assert man["reshaped_from"]["lines_without_shapes"] == ["9", "8"] and man["n_shapes"] == 0
