"""Arnés de replay (prediccion/replay): comportamiento observable sobre un caso sintético, sin el modelo real."""
import json
import math
import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from prediccion.replay import core
from prediccion.replay import metrics as MT
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


# ── vara corregida (2026-11-16): un caso por artefacto de medición ───────────────────────────────────────────

def _cross(ts, d, ok=None, d_stop=500.0, length=None):
    ok = [True] * len(ts) if ok is None else ok
    return core.crossings_v2(ts, d, ok, d_stop, length)


def test_cruce_al_final_del_shape_se_acepta_si_el_coche_llega():
    tc, _, _, firm = _cross([0, 60, 120], [900, 970, 995], d_stop=1000.0, length=1000.0)   # parada = final del shape
    assert len(core.crossing_times([0, 60, 120], [900, 970, 995], [True] * 3, 1000.0)) == 0   # definición anterior: no existe
    assert len(tc) == 1 and firm[0] and 0 < tc[0] < 60
    assert len(_cross([0, 60, 120], [100, 200, 300], d_stop=1000.0, length=1000.0)[0]) == 0    # si no llega, no cruza


def test_hueco_de_gps_de_10_a_40_min_es_no_verificable_no_cruce_firme():
    tc, _, _, firm = _cross([0, 900], [0, 1000])                        # 15 min entre pings
    assert len(tc) == 1 and not firm[0]
    assert _cross([0, 500], [0, 1000])[3][0]                             # 8 min: cruce firme
    assert len(_cross([0, 3000], [0, 1000])[0]) == 0                     # 50 min: ni siquiera se ve
    assert len(_cross([0, 450, 900], [0, 500, 1000], [True, False, True])[0]) == 0   # transmitió fuera del shape: no hay evidencia
    assert len(_cross([0, 900], [1000, 0])[0]) == 0                      # al revés no cruza


def test_cruce_entre_pings_no_consecutivos_compatibles():
    ts, d, ok = [0, 60, 120], [0, 500, 1000], [True, False, True]       # el ping del medio está fuera del shape
    assert len(core.crossing_times(ts, d, ok, 750.0)) == 0               # definición anterior
    tc, _, _, firm = _cross(ts, d, ok, d_stop=750.0)
    assert firm[0] and tc[0] == pytest.approx(90.0)


def test_salto_de_gps_implausible_no_es_cruce_pero_un_tramo_largo_en_10_min_si():
    assert len(_cross([0, 10], [0, 6000], d_stop=3000.0)[0]) == 0        # 6 km en 10 s: teletransporte
    tc, _, _, firm = _cross([0, 500], [0, 6000], d_stop=3000.0)          # 6 km en 8 min (12 m/s): sí (antes: salto > 5 km)
    assert len(core.crossing_times([0, 500], [0, 6000], [True] * 2, 3000.0)) == 0
    assert firm[0] and tc[0] == pytest.approx(250.0)


def test_coche_de_otro_recorrido_que_pasa_por_la_calle_sin_tener_la_parada_en_su_lista_no_cuenta_como_paso(bundle):
    t0 = 1_000_000.0
    mpd = bundle.const["m_per_deg_lat"]
    branch_c = trunk() + [(3000 + e, 35.0) for e in range(100, 3001, 100)]     # recorrido C: mismo tronco, luego 35 m al costado de A
    bundle.lines["39"]["C"] = PR.Shape(shape_dict("C", "Ramal C", branch_c), mpd)
    st = stop_on(bundle, 4000, 0, ["Ramal A"])                           # la parada está en la lista de A; C no la tiene
    assert set(st.serving) == {"A"}
    c = veh_along(branch_c, t0)
    c.trips = [(c.ts[0], c.ts[-1], "C")]
    rv, ri = run(bundle, c, st, t0 + 1500 / 8.0, variants=("base",))
    r = rv[0]
    assert r["listed"]                                                   # en el tronco la app lo lista (compatible con A)
    assert np.isnan(r["tp_s"]) and np.isnan(r["tp2_s"]) and not r["past"] and not r["unv"]   # pasa a 35 m de la parada pero no para ahí: falsa alarma
    assert np.isnan(ri[0]["real_next2_s"]) and ri[0]["n_pass2_20"] == 0
    a = veh_along(branch_a(), t0, vid="v2")                              # el coche de A sí la sirve
    a.trips = [(a.ts[0], a.ts[-1], "A")]
    rv, ri = run(bundle, a, st, t0 + 1500 / 8.0, variants=("base",))
    assert rv[0]["tp2_s"] == pytest.approx(2500 / 8.0, abs=6.0) and ri[0]["n_pass2_20"] == 1


def _tronco_con_trip(bundle, sid_trip, trips=True):
    t0 = 1_000_000.0
    a = veh_along(branch_a(), t0)
    a.trips = [(a.ts[0], a.ts[-1], sid_trip)] if trips else []
    a.expost = True
    st = stop_on(bundle, 2000, 0, ["Ramal A", "Ramal B"])      # parada del tronco: en la lista de A y B, no en la de un tercer recorrido
    assert set(st.serving) == {"A", "B"}
    return a, st, t0 + 500 / 8.0


def test_coche_de_un_recorrido_sin_la_parada_en_su_lista_no_cuenta_como_paso_aunque_vaya_compatible_y_es_falsa_alarma_real(bundle):
    a, st, t = _tronco_con_trip(bundle, "R3")                  # el coche va por el tronco, pero su viaje ex post es de R3
    rv, ri = run(bundle, a, st, t, variants=("base",))
    r = rv[0]
    assert r["listed"]                                         # la app lo lista (no conoce el recorrido)
    assert np.isnan(r["tp2_s"]) and not r["unv"] and not r["past"]   # no paso: falsa alarma real
    assert np.isnan(ri[0]["real_next2_s"]) and ri[0]["n_pass2_20"] == 0
    assert r["tp_s"] == pytest.approx(1500 / 8.0, abs=6.0)     # la definición anterior sí lo contaba
    fa = MT.false_alarms(pd.DataFrame(rv), corrected=True)
    assert fa["n_evaluados"] == 1 and fa["falsa_alarma_pct"] == 100.0


def test_coche_de_un_recorrido_que_si_tiene_la_parada_cuenta_como_paso(bundle):
    a, st, t = _tronco_con_trip(bundle, "A")
    rv, ri = run(bundle, a, st, t, variants=("base",))
    assert rv[0]["tp2_s"] == pytest.approx(1500 / 8.0, abs=6.0) and not rv[0]["unv"]
    assert ri[0]["n_pass2_20"] == 1


def test_cruce_sin_viaje_ex_post_es_no_verificable_no_paso_ni_falsa_alarma(bundle):
    a, st, t = _tronco_con_trip(bundle, "", trips=False)       # segmentado pero sin viaje que cubra el cruce
    rv, ri = run(bundle, a, st, t, variants=("base",))
    r = rv[0]
    assert np.isnan(r["tp2_s"]) and r["unv"]
    assert np.isnan(ri[0]["real_next2_s"]) and ri[0]["unv_first_s"] >= 0
    fa = MT.false_alarms(pd.DataFrame(rv), corrected=True)
    assert fa["n_evaluados"] == 0 and fa["n_no_verificable"] == 1


def test_sin_segmentacion_ex_post_la_verdad_conserva_el_cruce_por_compatibilidad(bundle):
    a, st, t = _tronco_con_trip(bundle, "", trips=False)
    a.expost = False                                           # corrida sin viajes ex post: no se puede filtrar
    rv, _ = run(bundle, a, st, t, variants=("base",))
    assert rv[0]["tp2_s"] == pytest.approx(1500 / 8.0, abs=6.0)


def test_integracion_final_de_shape_y_hueco_de_gps(bundle):
    t0 = 1_000_000.0
    # parada en el final del shape A (6000 m): antes ningún cruce posible
    a = veh_along(branch_a(), t0, step=5.0)
    a.trips = [(a.ts[0], a.ts[-1], "A")]
    rv, _ = run(bundle, a, stop_on(bundle, 6000, 0, ["Ramal A"]), t0 + 1500 / 8.0, variants=("base",))
    r = rv[0]
    assert np.isnan(r["tp_s"]) and r["tp2_s"] == pytest.approx((5950 - 1500) / 8.0, abs=6.0) and not r["unv"]
    # coche que cruza la parada (4000 m) dentro de un hueco de 15 min: ni falsa alarma ni cruce firme
    b = veh_along(branch_a(), t0, vid="v2")
    d = (b.ts - t0) * 8.0
    keep = (d <= 3500) | (d >= 4500)
    ts2 = b.ts[keep] + np.where(d[keep] >= 4500, 900.0, 0.0)
    b2 = core.Veh("v2", ts2, b.lat[keep], b.lon[keep], b.speed[keep])
    b2.trips = [(ts2[0], ts2[-1], "A")]
    rv, ri = run(bundle, b2, stop_on(bundle, 4000, 0, ["Ramal A"]), t0 + 1500 / 8.0, variants=("base",))
    r = rv[0]
    assert r["listed"] and np.isnan(r["tp_s"]) and np.isnan(r["tp2_s"]) and r["unv"]
    assert ri[0]["unv_first_s"] > 0 and np.isnan(ri[0]["real_next2_s"])


def _veh_rows(**cols):
    base = {"listed": True, "group": "seguro", "eta0_s": 300.0, "tp_s": np.nan, "tp2_s": np.nan, "unv": False, "past": False,
            "visible": True}
    n = max(len(v) for v in cols.values())
    return pd.DataFrame({k: cols.get(k, [v] * n) for k, v in base.items()})


def test_falsa_alarma_corregida_solo_cuenta_dentro_del_horizonte_y_sin_artefactos():
    df = _veh_rows(
        eta0_s=[300, 3000, 300, 300, 300, 300],             # el 2º anuncia a 50 min: fuera del horizonte
        tp2_s=[100, np.nan, np.nan, np.nan, np.nan, np.nan],   # el 1º pasa
        unv=[False, False, True, False, False, False],       # el 3º cruza en un hueco: no verificable
        past=[False, False, False, True, False, False],      # el 4º pasó segundos antes de t: llega antes, no falsa alarma
    )
    old = MT.false_alarms(df.assign(tp_s=df.tp2_s))
    assert old["falsa_alarma_pct"] == pytest.approx(100 * 5 / 6)   # la definición anterior cuenta todo lo que no cruza
    new = MT.false_alarms(df, corrected=True)
    assert (new["n_fuera_horizonte"], new["n_no_verificable"], new["n_ya_paso"], new["n_evaluados"]) == (1, 1, 1, 4)
    assert new["falsa_alarma_pct"] == pytest.approx(100 * 2 / 4)   # quedan 2 reales (filas 5 y 6) de 4 evaluados


def test_proximo_coche_y_omision_corregidos_excluyen_lo_no_verificable():
    inst = pd.DataFrame({"real_next_s": [300.0, 300.0], "real_next2_s": [300.0, 600.0], "ann_any_s": [300.0, 300.0],
                         "unv_first_s": [np.nan, 100.0], "has_seguro": [True, True], "n_pass_20": [1, 1], "n_pass2_20": [1, 1],
                         "n_shown_status": [1, 1]})
    assert MT.next_bus(inst, "ann_any_s", 180, 420)["n"] == 2
    nb = MT.next_bus(inst, "ann_any_s", 180, 420, corrected=True)
    assert nb["n"] == 1 and nb["mae_s"] == 0.0                       # el 2º tenía un paso posible antes (hueco): se excluye del MAE
    v = _veh_rows(listed=[True, False], tp2_s=[100.0, 200.0])
    assert MT.omissions(v, corrected=True)["omision_pct"] == 50.0


def test_variante_cs_restringe_al_ramal_informado_y_marca_los_errores(bundle):
    t0 = 1_000_000.0
    stop_a = stop_on(bundle, 5000, 0, ["Ramal A"])      # tramo exclusivo de A
    t = t0 + 1500 / 8.0                                  # el coche va por el tronco, compatible con A y B

    def run_cs(true_shape, informed_ids, rid="9"):
        v = veh_along(branch_a() if true_shape == "A" else branch_b(), t0)
        v.trips = [(v.ts[0], v.ts[-1], true_shape)]
        v.rid = [rid] * len(v.ts)
        with core.memoized():
            rv, _ = core.evaluate_line(bundle, "39", [v], [stop_a], [t], ("base", "cs"), "d",
                                       cs_rid={"9": ("t", informed_ids), "7": ("u", None)})
        return {x["variant"]: x for x in rv}

    r = run_cs("B", ["B"])                               # CuandoSubo acierta: va por B, la parada de A no lo lista
    assert r["base"]["listed"] and "cs" not in r      # base lo lista (falsa alarma); con cs no hay fila: ni listado ni pasa
    r = run_cs("A", ["B"])                               # CuandoSubo se equivoca: el coche va por A y se lo oculta
    assert r["base"]["listed"] and not r["cs"]["listed"] and r["cs"]["cs_applied"] and r["cs"]["cs_wrong"]
    assert r["cs"]["tp2_s"] == pytest.approx((5000 - 1500) / 8.0, abs=2.0)    # pasa de verdad: omisión causada por el dato
    r = run_cs("A", None, rid="7")                       # ramal informado pero ausente de la tabla: sin restricción
    assert r["cs"]["listed"] == r["base"]["listed"] and not r["cs"]["cs_applied"]


def test_dentro_de_tolerancia_cuenta_instantes_con_primer_arribo_cerca_del_paso_real():
    inst = pd.DataFrame({
        "real_next2_s": [200.0, 300.0, 400.0, 250.0, 100.0],
        "unv_first_s": [np.nan] * 5,
        "ann0_any_s": [250.0, 450.0, np.nan, 240.0, 100.0]})   # el 5.º está fuera de la banda 3-7 min
    r = MT.within_tol(inst, tols=(60.0, 120.0))
    assert r["n"] == 4 and r["n_con"] == 3
    assert r["dentro_60_con_pct"] == pytest.approx(100 * 2 / 3) and r["dentro_60_total_pct"] == pytest.approx(50.0)
    assert r["dentro_120_con_pct"] == pytest.approx(100 * 2 / 3)
    r2 = MT.within_tol(inst, tols=(200.0,))
    assert r2["dentro_200_con_pct"] == pytest.approx(100.0)
