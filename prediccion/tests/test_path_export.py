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
    from red.path_reference import eta_on_shapes, load_bundle
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
    from red.path_reference import load_bundle, predict_from_raw
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
        if abs(sh.project(*p)[0] - d0) > 1 or abs(sh.project(*t)[0] - d0 - rem) > 1 or d0 < 700:
            continue
        out = predict_from_raw(bundle, r.line, {"lat": p[0], "lon": p[1], "speed_mps": float(r.speed_mps), "ts": float(r.ts_p)},
                               t, float(r.ts_p) + float(r.ts_age_s), history=_hist(sh, float(r.ts_p), [d0 - 600, d0 - 300]),
                               only_shapes=[r.shape_id])
        assert out["status"] == "ok"
        cand = out["candidates"][0]
        assert abs(cand["eta_model_s"] - pred[i]) < 0.5
        assert out["eta_s"] == pytest.approx(max(0.0, cand["eta_model_s"] - r.ts_age_s))
        n += 1
    assert n >= 10


# ── comportamiento de la selección de candidatos (sin checkpoint: usa el export si existe) ─────────────────────

def _hist(sh, ts, ds, dt=60.0):
    """Pings previos del coche sobre el shape, en las distancias `ds` (ascendentes en el tiempo), el último `dt` antes de ts."""
    return [{"ts": ts - dt * (len(ds) - i), "lat": sh.latlon_at(d)[0], "lon": sh.latlon_at(d)[1]} for i, d in enumerate(ds)]


def _scenario(bundle, line="39"):
    shapes = bundle.lines[line]
    sh = next(iter(shapes.values()))
    at = lambda d: sh.latlon_at(d)  # noqa: E731
    return sh, at


@needs_data
def test_linea_fuera_del_modelo_no_predice():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    out = predict_from_raw(b, "12", {"lat": -34.6, "lon": -58.4, "speed_mps": 5.0, "ts": 1.79e9}, (-34.61, -58.41), 1.79e9)
    assert out["status"] == "linea_fuera_del_modelo" and out["eta_s"] is None


@needs_data
def test_usuario_atras_del_coche_es_pasado_y_cerca_es_llegando():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    veh = lambda d: {"lat": at(d)[0], "lon": at(d)[1], "speed_mps": 6.0, "ts": ts}  # noqa: E731
    only = [sh.id]
    hist = _hist(sh, ts, [4400, 4700])
    assert predict_from_raw(b, "39", veh(5000), at(3000), ts, history=hist, only_shapes=only)["status"] == "pasado"
    out = predict_from_raw(b, "39", veh(5000), at(5060), ts, history=hist, only_shapes=only)
    assert out["status"] == "llegando" and out["eta_s"] == 0.0
    out = predict_from_raw(b, "39", veh(5000), at(8000), ts, history=hist, only_shapes=only)
    assert out["status"] == "ok" and out["eta_s"] > 0


@needs_data
def test_historial_en_sentido_contrario_descarta_el_shape_y_en_sentido_correcto_lo_acepta():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    hist = lambda ds: _hist(sh, ts, ds)  # noqa: E731
    veh = {"lat": at(5000)[0], "lon": at(5000)[1], "speed_mps": 6.0, "ts": ts}
    fw = predict_from_raw(b, "39", veh, at(8000), ts, history=hist([4000, 4400, 4800]), only_shapes=[sh.id])
    bw = predict_from_raw(b, "39", veh, at(8000), ts, history=hist([6000, 5600, 5300]), only_shapes=[sh.id])
    assert fw["status"] == "ok"
    assert bw["status"] == "sin_sentido" and bw["eta_s"] is None
    assert {"shape_id": sh.id, "reason": "sentido_incoherente"} in bw["discarded"]


@needs_data
def test_con_varios_candidatos_el_eta_anunciado_es_el_minimo():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    ts = 1.79e9
    found = False
    for line, shapes in b.lines.items():
        ids = list(shapes)
        for a in ids:
            sa = shapes[a]
            veh = sa.latlon_at(min(2500.0, sa.length_m * 0.2))
            usr = sa.latlon_at(min(7000.0, sa.length_m * 0.6))
            hist = _hist(sa, ts, [max(sa.length_m * 0.2 - 600, 0.0), max(sa.length_m * 0.2 - 300, 0.0)] if sa.length_m * 0.2 < 2500 else [1900.0, 2200.0])
            out = predict_from_raw(b, line, {"lat": veh[0], "lon": veh[1], "speed_mps": 5.0, "ts": ts}, usr, ts, history=hist)
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
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    p = at(250.0)
    out = predict_from_raw(b, "39", {"lat": p[0], "lon": p[1], "speed_mps": 0.0, "ts": ts}, at(4000), ts,
                           history=_hist(sh, ts, [0.0, 120.0]), only_shapes=[sh.id])
    assert out["status"] == "ok" and out["en_cabecera"] is True


@needs_data
def test_ping_viejo_se_descuenta_del_eta():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    veh = {"lat": at(3000)[0], "lon": at(3000)[1], "speed_mps": 6.0, "ts": ts}
    hist = _hist(sh, ts, [2400, 2700])
    a = predict_from_raw(b, "39", veh, at(6000), ts, history=hist, only_shapes=[sh.id])
    c = predict_from_raw(b, "39", veh, at(6000), ts + 40, history=hist, only_shapes=[sh.id])
    assert a["candidates"][0]["eta_model_s"] > 0
    assert c["eta_s"] < a["eta_s"] + 1e-6 and c["eta_s"] == pytest.approx(max(0.0, c["candidates"][0]["eta_model_s"] - 40))


@needs_data
def test_coche_de_adelante_pasado_por_T_se_detecta_y_sin_pasar_no_se_encuentra():
    from red.path_reference import last_bus, load_bundle
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


# ── regla de candidatos 1.2: sentido obligatorio, shapes del usuario, grupos ────────────────────────────────────

def _veh_at(sh, d, ts, speed=6.0):
    return {"lat": sh.latlon_at(d)[0], "lon": sh.latlon_at(d)[1], "speed_mps": speed, "ts": ts}


@needs_data
def test_sin_historial_el_eta_es_provisional_y_el_minimo_entre_los_shapes_posibles():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    out = predict_from_raw(b, "39", _veh_at(sh, 5000, ts), at(8000), ts)
    assert out["status"] == "provisional" and out["group"] == "provisional" and out["eta_s"] > 0
    assert out["compatible"] == [] and any(k["passes"] for k in out["provisional"])
    assert out["eta_s"] == min(k["eta_s"] for k in out["candidates"])
    # coche quieto sin avance (en cabecera): mismo criterio, con la marca de cabecera
    out = predict_from_raw(b, "39", _veh_at(sh, 60, ts, 0.0), at(8000), ts, history=_hist(sh, ts, [58, 59]))
    assert out["status"] == "provisional" and out["en_cabecera"] is True


@needs_data
def test_provisional_no_lista_al_coche_si_el_usuario_queda_atras_en_todos_los_shapes_posibles():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    out = predict_from_raw(b, "39", _veh_at(sh, 7000, ts), at(6000), ts, only_shapes=[sh.id])
    assert out["status"] == "pasado" and out["eta_s"] is None and out["group"] is None


@needs_data
def test_con_historial_suficiente_la_clasificacion_provisional_pasa_a_normal():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    veh = _veh_at(sh, 5000, ts)
    assert predict_from_raw(b, "39", veh, at(8000), ts)["group"] == "provisional"
    out = predict_from_raw(b, "39", veh, at(8000), ts, history=_hist(sh, ts, [4400, 4700]))
    assert out["status"] == "ok" and out["group"] in ("seguro", "puede_venir") and out["provisional"] == []
    # con historial que muestra que el coche se alejó del punto, deja de listarse
    out = predict_from_raw(b, "39", _veh_at(sh, 7000, ts), at(6000), ts, history=_hist(sh, ts, [6400, 6700]))
    assert out["status"] == "pasado"


@needs_data
def test_coche_que_ya_paso_con_historial_no_recibe_eta_y_el_opuesto_no_lo_acepta():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    sh, at = _scenario(b)
    ts = 1.79e9
    out = predict_from_raw(b, "39", _veh_at(sh, 7000, ts), at(6000), ts, history=_hist(sh, ts, [6400, 6700]))
    assert out["status"] == "pasado" and out["eta_s"] is None and out["group"] is None


@needs_data
def test_parada_que_sirve_un_solo_ramal_con_coche_en_el_tronco_es_puede_venir():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    shapes = list(b.lines["39"].values())
    a = shapes[0]   # Ramal 1 ida; comparte el tronco con el Ramal 2 ida hasta ~14 km
    ts = 1.79e9
    stop = a.latlon_at(14870.0)
    hist = _hist(a, ts, [7400, 7700])
    out = predict_from_raw(b, "39", _veh_at(a, 8000, ts), stop, ts, history=hist, user_kind="parada", stop_recorridos=[a.name])
    assert out["status"] == "ok" and out["group"] == "puede_venir"
    assert a.id in out["depends_on"] and shapes[2].id not in out["depends_on"]
    assert any(k["shape_id"] == shapes[2].id and not k["passes"] and k["reason"] == "no_sirve_parada" for k in out["compatible"])
    # si la parada la sirven todos los recorridos del tronco, el coche pasa seguro
    out = predict_from_raw(b, "39", _veh_at(a, 8000, ts), a.latlon_at(9500.0), ts, history=hist, user_kind="parada",
                           stop_recorridos=[s.name for s in shapes])
    assert out["group"] == "seguro" and out["eta_s"] > 0


@needs_data
def test_coche_en_ramal_unico_pasa_seguro():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    a = list(b.lines["39"].values())[4]   # Ramal 3 ida: entre ~11 y ~13,5 km ningún otro recorrido queda a < 150 m
    ts = 1.79e9
    out = predict_from_raw(b, "39", _veh_at(a, 12000, ts), a.latlon_at(13500.0), ts, history=_hist(a, ts, [11400, 11700]))
    assert [k["shape_id"] for k in out["compatible"]] == [a.id] and out["group"] == "seguro"


@needs_data
def test_punto_cerca_de_un_shape_paralelo_descarta_la_paralela():
    from red.path_reference import load_bundle, user_shapes
    b = load_bundle(EXPORT)
    found = False
    for line, shapes in b.lines.items():
        items = list(shapes.items())
        for sid, sh in items:
            for oid, other in items:
                if oid == sid:
                    continue
                for d in range(500, int(sh.length_m) - 500, 100):
                    pt = sh.latlon_at(float(d))
                    perp = other.project(*pt)[1]
                    if 20 <= perp <= 38 and sh.project(*pt)[1] < 5:
                        us = user_shapes(b, line, pt)
                        assert us[sid] == (True, None)
                        assert us[oid] == (False, "paralela")
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found:
            break
    assert found


# ── sentido por geometría (contrato 2.1) ────────────────────────────────────────────────────────────────────────

@needs_data
def test_coche_sin_historial_en_tramo_de_un_solo_sentido_viene_desde_la_primera_consulta():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    shapes = b.lines["168"]
    stop = (-34.6033362, -58.4241505)   # Gascón y Corrientes: la sirven los dos recorridos que suben por Gascón
    names = [sh.name for sh in shapes.values() if sh.project(*stop)[1] <= 20]
    assert len(names) == 2
    a = next(sh for sh in shapes.values() if sh.name == names[0])
    d_s = a.project(*stop)[0]
    ts = 1.79e9
    for back in (300, 1000, 2500):
        out = predict_from_raw(b, "168", _veh_at(a, d_s - back, ts), stop, ts, user_kind="parada", stop_recorridos=names)
        assert out["status"] == "ok" and out["group"] == "seguro" and out["sense"] == "geometria", back
        assert out["provisional"] == [] and out["eta_s"] > 0


@needs_data
def test_coche_sin_historial_donde_ida_y_vuelta_comparten_la_calle_sigue_provisional():
    from red.path_reference import load_bundle, predict_from_raw
    from red import geo_assign as G
    b = load_bundle(EXPORT)
    a = next(iter(b.lines["39"].values()))
    ts = 1.79e9
    veh = _veh_at(a, 4000, ts)
    assert not G.direction_from_geometry(veh["lat"], veh["lon"], b.lines["39"])
    out = predict_from_raw(b, "39", veh, a.latlon_at(6000), ts)
    assert out["group"] == "provisional" and out["sense"] is None
    # con historial que avanza, el sentido sale del historial
    out = predict_from_raw(b, "39", veh, a.latlon_at(6000), ts, history=_hist(a, ts, [3400, 3700]))
    assert out["group"] in ("seguro", "puede_venir") and out["sense"] == "historial"


@needs_data
def test_historial_que_contradice_la_geometria_descarta_el_shape():
    from red.path_reference import load_bundle, predict_from_raw
    b = load_bundle(EXPORT)
    shapes = b.lines["168"]
    stop = (-34.6033362, -58.4241505)
    a = next(sh for sh in shapes.values() if sh.project(*stop)[1] <= 20)
    d_s = a.project(*stop)[0]
    ts = 1.79e9
    # el coche retrocede sobre el tramo de mano única (desvío o ruido): el historial lo descarta, no se lista
    out = predict_from_raw(b, "168", _veh_at(a, d_s - 1000, ts), stop, ts, history=_hist(a, ts, [d_s - 400, d_s - 700]),
                           user_kind="parada")
    assert out["group"] is None and any(k["reason"] == "sentido_incoherente" for k in out["discarded"])


# ── v3: modelo con paradas por tramo (contrato 2.2) ─────────────────────────────────────────────────────────────

EXPORT_V3 = ROOT / "data" / "ml" / "export" / "path_v3_l1_s1"
CKPT_V3 = ROOT / "data" / "ml" / "v3_sub" / "runs" / "path_lr2e-3_s1" / "path_eta_best.pt"


@pytest.mark.skipif(not (EXPORT_V3 / "manifest.json").exists() or not CKPT_V3.exists(),
                    reason="falta el export o el checkpoint v3")
def test_la_referencia_con_paradas_da_el_mismo_eta_que_el_modelo_entrenado():
    import torch
    from red.path_reference import encode_time, eta_on_shape, load_bundle
    from prediccion.models.path_eta import PathETAModel, state_features
    model = PathETAModel.from_checkpoint(torch.load(str(CKPT_V3), map_location="cpu", weights_only=False)).eval()
    b = load_bundle(EXPORT_V3)
    assert b.manifest["contract_version"] == "2.3" and b.manifest["stops_feature"]
    rng = np.random.default_rng(1)
    items = [(ln, sid, sh) for ln, d in b.lines.items() for sid, sh in d.items() if sh.length_m > 400]
    worst = 0.0
    for _ in range(200):
        ln, sid, sh = items[rng.integers(len(items))]
        d0 = rng.random() * sh.length_m * 0.6
        rem = 100 + rng.random() * (sh.length_m - d0 - 100)
        ts = 1784214000 + int(rng.integers(0, 6 * 86400))
        sp, age = float(rng.choice([0, 3, 8])), float(rng.choice([0, 30, 120]))
        got = eta_on_shape(b, ln, sh, d0, rem, ts, sp, age)
        hs, hc, dow = encode_time(ts)
        st = state_features([sp], [age], [0.0], [d0], [3600.0], [0.0], [rem], start_unknown=[1.0])
        t = lambda x, dt=torch.float32: torch.tensor(x, dtype=dt)  # noqa: E731
        with torch.no_grad():
            ref = model(torch.tensor([model.shape_ids.index(sid)]), torch.tensor([model.line_ids.index(ln) + 1]),
                        t([d0]), t([rem]), t([[hs]]), t([[hc]]), torch.tensor([[dow]]), torch.tensor(st))[0].item()
        worst = max(worst, abs(max(ref, 0.0) - got))
    assert worst < 0.5
