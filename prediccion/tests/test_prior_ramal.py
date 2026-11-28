"""Variantes prior del replay: reglas de reordenamiento de la lista según P(pasa por la parada) (comportamiento observable)."""
import numpy as np
import pandas as pd

from prediccion.replay import prior_ramal as PRI


class FakeCtx:
    def __init__(self, p):
        self.p = p

    def probs(self, preds, t, kind, mode):
        return self.p


def base_list():
    sure = [("s1", "seguro", 100.0)]
    others = [("a", "puede_venir", 120.0), ("b", "puede_venir", 150.0), ("c", "puede_venir", 200.0), ("d", "provisional", 210.0)]
    eta0 = {k: e for k, _, e in sure + others}
    return {"seguro": sure, "otros": others, "shown": (sure + others)[:5], "eta0": eta0}


def test_regla_i_baja_al_final_los_de_p_baja_y_puede_sacarlos_de_los_5_mostrados():
    lst = PRI.list_for("prior_token_i", base_list(), {}, FakeCtx({"a": 0.1, "b": 0.9}), 0.0)
    assert [x[0] for x in lst["otros"]] == ["b", "c", "d", "a"]
    assert [x[0] for x in lst["shown"]] == ["s1", "b", "c", "d", "a"]
    assert "first_any" not in lst


def test_regla_ii_ademas_pasa_a_viene_los_de_p_alta():
    lst = PRI.list_for("prior_cadena_ii", base_list(), {}, FakeCtx({"a": 0.1, "b": 0.85}), 0.0)
    assert [x[0] for x in lst["seguro"]] == ["s1", "b"] and lst["seguro"][1][1] == "seguro"
    assert [x[0] for x in lst["otros"]] == ["c", "d", "a"]


def test_regla_iii_primer_arribo_es_el_menor_eta_con_p_mayor_o_igual_a_05():
    lst = PRI.list_for("prior_token_iii", base_list(), {}, FakeCtx({"a": 0.3, "b": 0.6}), 0.0)
    assert lst["first_any"] == (100.0, 100.0)      # el seguro (P = 1) llega antes que b
    b = base_list(); b["seguro"] = []
    lst = PRI.list_for("prior_token_iii", b, {}, FakeCtx({"a": 0.3, "b": 0.6}), 0.0)
    assert lst["first_any"] == (150.0, 150.0)      # a tiene P < 0,5; b es el menor ETA con P >= 0,5
    assert [x[0] for x in lst["otros"]] == ["a", "b", "c", "d"]   # la lista no cambia


def test_sin_prior_la_lista_queda_igual_que_base():
    for v in ("prior_token_i", "prior_cadena_ii", "prior_token_iii"):
        lst = PRI.list_for(v, base_list(), {}, FakeCtx({}), 0.0)
        assert lst["shown"] == base_list()["shown"] and lst["otros"] == base_list()["otros"]


def _ctx(reveal_ts=np.nan, reveal_ramal=""):
    ev = pd.DataFrame([dict(vid="v1", det_ts=1000.0, gkey="9|X", cab="X", reveal_ts=reveal_ts, reveal_ramal=reveal_ramal,
                            **{f"P_{m}_{d}": np.array([0.7, 0.3]) for m in PRI.MODES for d in PRI.DGRID})])

    class Sh:
        def __init__(self, short, name):
            self.short_name, self.name = short, name
    shapes = {"s1": Sh("9A", "Linea 9 - Ramal 1: X → Y"), "s2": Sh("9B", "Linea 9 - Ramal 2: X → Y"), "s3": Sh("9C", "Linea 9 - Ramal 3: Z → Y")}
    return PRI.PriorCtx(ev, shapes, {"9|X": {"ramales": ["9A", "9B"]}})


def test_p_de_pasar_es_la_suma_de_los_ramales_compatibles_que_sirven_la_parada_renormalizada():
    ctx = _ctx()
    preds = {"v1": {"group": "puede_venir", "eta_s": 100.0,
                    "compatible": [{"shape_id": "s1", "passes": True}, {"shape_id": "s2", "passes": False}, {"shape_id": "s3", "passes": True}]}}
    p = ctx.probs(preds, 1000.0 + 700.0, "prior", "token")
    assert p["v1"] == 0.7           # s3 sale de otra cabecera: peso 0; 0,7 / (0,7 + 0,3)
    assert ctx.probs(preds, 500.0, "prior", "token") == {}                       # antes de la salida detectada: sin dato
    assert ctx.probs(preds, 1000.0 + 20000.0, "prior", "token") == {}            # salida vieja: no aplica


def test_ablacion_con_el_ramal_que_el_propio_coche_ya_revelo():
    preds = {"v1": {"group": "puede_venir", "eta_s": 100.0,
                    "compatible": [{"shape_id": "s1", "passes": True}, {"shape_id": "s2", "passes": False}]}}
    assert _ctx(1100.0, "9B").probs(preds, 1500.0, "memonly", "token") == {"v1": 0.0}
    assert _ctx(1100.0, "9B").probs(preds, 1050.0, "memonly", "token") == {}     # todavía no lo reveló a t
    assert _ctx().probs(preds, 1500.0, "memprior", "token") == {"v1": 0.7}       # sin revelar: cae al prior


def test_control_min_eta_sin_prior_anuncia_el_menor_eta_entre_viene_y_puede_venir_y_el_umbral_saca_los_de_p_baja():
    b = base_list(); b["seguro"] = [("s1", "seguro", 160.0)]
    lst = PRI.list_for("ctrl_min", b, {}, FakeCtx({}), 0.0)
    assert lst["first_any"] == (120.0, 120.0) and lst["shown"] == b["shown"]      # a (puede venir) llega antes que el seguro
    lst = PRI.list_for("ctrl_min_tok02", b, {}, FakeCtx({"a": 0.1}), 0.0)
    assert lst["first_any"] == (150.0, 150.0)                                      # a sale del mínimo por P < 0,2
