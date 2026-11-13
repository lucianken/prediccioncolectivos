"""Arnés de replay (prediccion/replay): comportamiento observable sobre un caso sintético, sin el modelo real."""
import json
import math
import random
from pathlib import Path

import numpy as np
import pytest

from prediccion.replay import core
from prediccion.replay.pinned import path_reference as PR

MAN = Path(__file__).resolve().parents[2] / "data" / "ml" / "export" / "path_v2c_l1_s1" / "manifest.json"
pytestmark = pytest.mark.skipif(not MAN.exists(), reason="falta el export del modelo (constantes)")

M = 111_320.0
LAT0, LON0 = -34.60, -58.50
MLON = M * math.cos(math.radians(LAT0))


def xy(e, n):
    return LAT0 + n / M, LON0 + e / MLON


def shape_dict(sid, name, pts_en):
    pts = [xy(e, n) for e, n in pts_en]
    cells = pts
    return {"id": sid, "name": name, "short_name": name[-1], "length_m": 1.0,
            "points": [c for p in pts for c in p], "cells": [c for p in cells for c in p]}


def trunk():
    return [(e, 0.0) for e in range(0, 3001, 100)]


def branch_a():
    return trunk() + [(3000 + e, 0.0) for e in range(100, 3001, 100)]


def branch_b():
    return trunk() + [(3000 + e * 0.7071, e * 0.7071) for e in range(100, 3001, 100)]


class StubSession:
    def run(self, _names, feed):   # eta = metros restantes / 8 m/s
        return [feed["seg_len"].sum(axis=1) / 8.0]


@pytest.fixture()
def bundle():
    man = json.loads(MAN.read_text(encoding="utf-8"))
    mpd = man["constants"]["m_per_deg_lat"]
    shapes = {"A": PR.Shape(shape_dict("A", "Ramal A", branch_a()), mpd), "B": PR.Shape(shape_dict("B", "Ramal B", branch_b()), mpd)}
    return PR.Bundle(Path("."), {"constants": man["constants"], "lines": {"39": 1}}, {"39": shapes}, StubSession())


def veh_along(path_en, t0, speed=8.0, step=30.0, vid="v1"):
    """Coche que recorre `path_en` (lista (e,n)) a `speed` m/s con un ping cada `step` s desde t0."""
    pts = np.array(path_en, float)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    ts = np.arange(t0, t0 + cum[-1] / speed, step)
    d = (ts - t0) * speed
    e = np.interp(d, cum, pts[:, 0]); n = np.interp(d, cum, pts[:, 1])
    ll = np.array([xy(a, b) for a, b in zip(e, n)])
    return core.Veh(vid, ts, ll[:, 0], ll[:, 1], np.full(len(ts), speed))


def stop_on(bundle, e, n, names):
    st = core.Stop("S", "parada", *xy(e, n), recorridos=names)
    us = PR.user_shapes(bundle, "39", (st.lat, st.lon), "parada", names)
    st.serving = {sid: bundle.lines["39"][sid].project(st.lat, st.lon)[0] for sid, (ok, _) in us.items() if ok}
    st.cls = "exclusivo"
    return st


def run(bundle, veh, stop, t, variants=("base", "ramal")):
    with core.memoized():
        return core.evaluate_line(bundle, "39", [veh], [stop], [t], variants, "d")


def test_coche_en_el_tronco_rumbo_a_otro_ramal_es_falsa_alarma_solo_sin_oraculo(bundle):
    t0 = 1_000_000.0
    b = veh_along(branch_b(), t0)                       # va por B y nunca pasa por la rama exclusiva de A
    b.trips = [(b.ts[0], b.ts[-1], "B")]
    stop_a = stop_on(bundle, 5000, 0, ["Ramal A"])      # parada en el tramo exclusivo de A
    t = t0 + 1500 / 8.0                                  # el coche va por el tronco (1500 m), con historial de sentido
    rv, ri = run(bundle, b, stop_a, t)
    base = [r for r in rv if r["variant"] == "base"]
    ram = [r for r in rv if r["variant"] == "ramal"]
    assert len(base) == 1 and base[0]["listed"] and base[0]["group"] == "puede_venir"
    assert np.isnan(base[0]["tp_s"])                     # falsa alarma: nunca cruza la parada de A
    assert not any(r["listed"] for r in ram)             # con el ramal conocido no se lista
    assert not any(not math.isnan(r["tp_s"]) for r in rv)


def test_coche_que_pasa_por_la_parada_se_cuenta_como_verdad_y_su_eta_es_cercana(bundle):
    t0 = 1_000_000.0
    a = veh_along(branch_a(), t0)
    a.trips = [(a.ts[0], a.ts[-1], "A")]
    stop_a = stop_on(bundle, 4000, 0, ["Ramal A"])
    t = t0 + 1500 / 8.0
    rv, ri = run(bundle, a, stop_a, t)
    for var in ("base", "ramal"):
        r = [x for x in rv if x["variant"] == var][0]
        # en el tronco el coche es compatible con A y B: sin oráculo "puede venir"; con el ramal conocido, seguro
        assert r["listed"] and r["group"] == ("puede_venir" if var == "base" else "seguro")
        assert r["tp_s"] == pytest.approx((4000 - 1500) / 8.0, abs=2.0)   # pasa por la parada en ~312 s
        assert abs(r["eta_s"] - r["tp_s"]) < 120.0
    i = [x for x in ri if x["variant"] == "base"][0]
    assert i["real_next_s"] == pytest.approx(312.5, abs=2.0) and i["n_pass_10"] == 1


def test_coche_que_ya_paso_no_es_verdad_ni_se_lista(bundle):
    t0 = 1_000_000.0
    a = veh_along(branch_a(), t0)
    a.trips = [(a.ts[0], a.ts[-1], "A")]
    stop = stop_on(bundle, 1000, 0, ["Ramal A", "Ramal B"])
    rv, _ = run(bundle, a, stop, t0 + 2000 / 8.0)
    assert rv == []


def test_build_list_aplica_el_tope_de_5_seguros_primero():
    ok = lambda g, e: {"status": "ok", "group": g, "eta_s": e}  # noqa: E731
    preds = {f"s{i}": ok("seguro", 100 + i) for i in range(4)}
    preds.update({"m1": ok("puede_venir", 10), "p1": {"status": "provisional", "group": "provisional", "eta_s": 20},
                  "x": {"status": "pasado", "group": None, "eta_s": None}})
    lst = core.build_list(preds)
    assert [v for v, _, _ in lst["shown"]] == ["s0", "s1", "s2", "s3", "m1"]   # seguros por ETA, luego el más cercano de los inciertos
    assert "x" not in {v for v, _, _ in lst["seguro"] + lst["otros"]}


def test_crossing_times_interpola_e_ignora_pings_no_compatibles():
    ts = [0, 60, 120]
    assert core.crossing_times(ts, [0, 500, 1000], [True] * 3, 750.0)[0] == pytest.approx(90.0)
    assert len(core.crossing_times(ts, [0, 500, 1000], [True, False, True], 750.0)) == 0
    assert len(core.crossing_times(ts, [1000, 500, 0], [True] * 3, 750.0)) == 0      # al revés no cruza
    assert len(core.crossing_times([0, 900], [0, 1000], [True] * 2, 500.0)) == 0      # hueco demasiado largo


def test_last_bus_memoizado_equivale_al_original(bundle):
    sh = bundle.lines["39"]["A"]
    c = bundle.const
    rng = random.Random(3)
    others = []
    for _ in range(12):
        start, spd = rng.uniform(0, 2000), rng.uniform(3, 12)
        others.append({"pings": [(1000.0 + 30 * k, *xy(start + spd * 30 * k, rng.uniform(-8, 8))) for k in range(30)]})
    with core.memoized():
        for d_t in (800.0, 2500.0, 4200.0):
            for ts in (1500.0, 1900.0):
                assert PR.last_bus(c, sh, others, d_t, ts) == core._ORIG["last_bus"](c, sh, others, d_t, ts)
