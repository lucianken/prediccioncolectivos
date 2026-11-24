"""Tests del grabador de CuandoSubo (README §7). Comportamiento observable: archivos, contenido, stats, tiempos."""

from __future__ import annotations

import copy
import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from conftest import T0, read_dir, read_ndjson
from fake_oba import FIXTURES, TEST_KEY, load_fixture, load_sequence
from identity import Identity, LabelLineMap, ba_date
from limiter import RateLimiter, SystemClock
from oba_client import ObaClient, WafError, requests_transport

CABA_FIELDS = ["id", "label", "license_plate", "route_id", "trip_id", "direction_id", "start_date", "start_time",
               "lat", "lon", "speed", "odo", "stop_id", "seq", "status", "ts"]
EXTRA_FIELDS = ["agency", "label_src", "line", "pred_lat", "pred_lon", "sched_dev", "dist_along", "next_stop",
                "next_stop_eta_s", "predicted"]
REGISTRY = json.loads((FIXTURES.parent / "datos" / "registry.json").read_text(encoding="utf-8"))["vehicles"]


def in_bbox(lat, lon):
    return -35.1 <= lat <= -34.3 and -59.1 <= lon <= -57.9


def raw_by_id(*bodies):
    out = {}
    for b in bodies:
        for v in b["data"]["list"]:
            loc = v.get("location")
            if loc and in_bbox(loc["lat"], loc["lon"]):
                out[v["vehicleId"].split("_", 1)[1]] = v
    return out


def pos_frames(tmp_path):
    return read_dir(tmp_path / "data" / "posiciones")


def stats(tmp_path):
    return json.loads((tmp_path / "data" / "stats.json").read_text(encoding="utf-8"))


# 1 ---------------------------------------------------------------------------------------------
def test_primer_ciclo_keyframe_completo(make, tmp_path):
    make().run(1)
    frames = pos_frames(tmp_path)
    assert len(frames) == 1
    kf = frames[0]
    assert kf["keyframe"] is True and kf["src"] == "cuandosubo" and kf["del"] == [] and kf["upd"] == []
    raw = raw_by_id(load_fixture("vehicles-for-agency/56"), load_fixture("vehicles-for-agency/708"))
    assert {v["id"] for v in kf["new"]} == set(raw)
    for v in kf["new"]:
        for k in CABA_FIELDS + EXTRA_FIELDS:
            assert k in v, f"falta {k}"
        assert "_" not in v["id"]
        assert in_bbox(v["lat"], v["lon"])
        assert v["ts"] == raw[v["id"]]["lastUpdateTime"] // 1000
        assert (v["lat"], v["lon"]) == (round(raw[v["id"]]["location"]["lat"], 6), round(raw[v["id"]]["location"]["lon"], 6))
    # con trip: posición predicha aparte, nunca en lat/lon
    with_trip = next(v for v in kf["new"] if v["trip_id"])
    r = raw[with_trip["id"]]["tripStatus"]
    assert (with_trip["pred_lat"], with_trip["pred_lon"]) == (round(r["position"]["lat"], 6), round(r["position"]["lon"], 6))
    assert with_trip["next_stop_eta_s"] == r["nextStopTimeOffset"]
    assert kf["t"] == max(v["ts"] for v in kf["new"])
    # archivo del día por fecha de Buenos Aires de t
    assert (tmp_path / "data" / "posiciones" / f"{ba_date(kf['t'])}.ndjson.gz").exists()


# 1b --------------------------------------------------------------------------------------------
def test_frames_traen_t_poll_con_la_hora_del_servidor_por_agencia(make, oba, tmp_path):
    make().run(2)
    frames = pos_frames(tmp_path)
    assert len(frames) == 2 and frames[0].get("keyframe") and not frames[1].get("keyframe")
    for f in frames:
        assert set(f["t_poll"]) == {"56", "708"}
        for ag in ("56", "708"):
            assert f["t_poll"][ag] > 0
    # la hora de la consulta es la currentTime de la respuesta falsa, no el lastUpdateTime de los coches
    assert frames[0]["t_poll"]["708"] == load_fixture("vehicles-for-agency/708")["currentTime"] / 1000


# 2 ---------------------------------------------------------------------------------------------
def test_misma_foto_delta_vacio(make, tmp_path):
    make().run(2)
    frames = pos_frames(tmp_path)
    assert len(frames) == 2
    d = frames[1]
    assert "keyframe" not in d
    assert (d["new"], d["del"], d["upd"]) == ([], [], [])


# 3 ---------------------------------------------------------------------------------------------
def test_secuencia_real_movidos_en_upd_quietos_no(make, oba, tmp_path):
    photos = load_sequence("seq_708_cada_60s")
    oba.use_sequence("vehicles-for-agency/708", photos)
    make(record_lines=["151"]).run(4)
    frames = pos_frames(tmp_path)
    assert len(frames) == 4 and frames[0]["keyframe"]
    total_moved = 0
    for i in range(1, 4):
        prev, curr, frame = raw_by_id(photos[i - 1]), raw_by_id(photos[i]), frames[i]
        upd = {u["id"]: u for u in frame["upd"]}
        for vid, v in curr.items():
            p = prev.get(vid)
            if p is None:
                assert vid in {n["id"] for n in frame["new"]}
                continue
            if p == v:
                assert vid not in upd, f"{vid} quieto (registro idéntico) no debe ir en upd"
            elif p["lastUpdateTime"] != v["lastUpdateTime"] and p["location"] != v["location"]:
                total_moved += 1
                assert vid in upd
                assert upd[vid]["ts"] == v["lastUpdateTime"] // 1000
                assert {"lat", "lon"} & set(upd[vid])
        assert set(frame["del"]) == set(prev) - set(curr)
    assert total_moved > 0  # la secuencia real tiene movimiento


# 4 ---------------------------------------------------------------------------------------------
def test_artefacto_posicion_cambia_sin_lastupdatetime(make, oba, tmp_path):
    body = load_fixture("vehicles-for-agency/708")
    rec = make(record_lines=["151"])
    oba.overrides["vehicles-for-agency/708"] = body
    rec.run(1)
    jumped = copy.deepcopy(body)
    v = next(x for x in jumped["data"]["list"] if x.get("location") and in_bbox(x["location"]["lat"], x["location"]["lon"]))
    vid = v["vehicleId"].split("_", 1)[1]
    orig = (round(v["location"]["lat"], 6), round(v["location"]["lon"], 6))
    v["location"] = {"lat": v["location"]["lat"] + 0.03, "lon": v["location"]["lon"]}  # salto de ~3 km, misma hora
    oba.overrides["vehicles-for-agency/708"] = jumped
    rec.run(1)
    d = pos_frames(tmp_path)[1]
    assert not any(u["id"] == vid and ("lat" in u or "lon" in u) for u in d["upd"])
    assert stats(tmp_path)["artifacts"] >= 1
    state = json.loads((tmp_path / "data" / "state.json").read_text(encoding="utf-8"))
    assert (state["vehicles"][vid]["lat"], state["vehicles"][vid]["lon"]) == orig


# 5 ---------------------------------------------------------------------------------------------
def test_gap_tras_reinicio_y_nada_fuera_de_su_carpeta(make, clock, tmp_path):
    sentinel = tmp_path / "grabaciones"  # carpeta del grabador CABA: no se toca
    sentinel.mkdir()
    (sentinel / "2026-10-19.ndjson.gz").write_bytes(b"caba")
    before = {p for p in tmp_path.rglob("*")}

    make().run(1)
    clock.t += 3600
    make().run(1)  # "reinicio": proceso nuevo sobre la misma carpeta

    frames = pos_frames(tmp_path)
    gi = next(i for i, f in enumerate(frames) if f.get("gap"))
    assert gi > 0
    assert frames[gi]["reason"] == "restart" and frames[gi]["gap_seconds"] >= 3600
    assert frames[gi + 1]["keyframe"] is True
    assert (sentinel / "2026-10-19.ndjson.gz").read_bytes() == b"caba"
    created = {p for p in tmp_path.rglob("*")} - before
    data = tmp_path / "data"
    assert all(p == data or data in p.parents for p in created), created


def test_gap_en_marcha_por_caida(make, oba, clock, tmp_path):
    rec = make(fatal_fail_s=10 ** 9)
    rec.run(1)
    oba.mode = "down"
    rec.run(20)  # ~15 min sin datos: no escribe frames vacíos
    oba.mode = "ok"
    rec.run(1)
    frames = pos_frames(tmp_path)
    # los primeros ciclos caídos usan el último dato (< 2 min); después no se escribe nada hasta volver
    assert [bool(f.get("gap")) for f in frames[-2:]] == [True, False]
    assert sum(bool(f.get("gap")) for f in frames) == 1
    assert len(frames) <= 6
    assert frames[-2]["reason"] == "outage" and frames[-2]["gap_seconds"] > 600 and frames[-1]["keyframe"]


# 6 ---------------------------------------------------------------------------------------------
def test_waf_pausa_120s_y_no_pierde_frames(make, oba, tmp_path):
    oba.mode = "waf_once"
    make().run(3)
    log = oba.log
    i = next(k for k, r in enumerate(log) if r["status"] == 302)
    assert log[i + 1]["start"] - log[i]["end"] >= 120
    assert log[i + 1]["resource"] == log[i]["resource"]  # reintento del mismo recurso tras la pausa
    frames = pos_frames(tmp_path)
    assert len(frames) == 3 and frames[0]["keyframe"]
    s = stats(tmp_path)
    assert s["waf"] == 1 and s["cycles"] == 3


def test_transporte_real_no_sigue_el_302_del_waf():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "/security-redirect")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        clock = SystemClock()
        client = ObaClient(f"http://127.0.0.1:{srv.server_port}/api/where", "secreto", RateLimiter(0, clock),
                           requests_transport(), clock, waf_backoff_s=0)
        with pytest.raises(WafError) as e:
            client.fetch("vehicles-for-agency/56", retry_waf=False)
        assert "secreto" not in str(e.value)
        assert client.counters["waf"] == 1
    finally:
        srv.shutdown()


# 7 ---------------------------------------------------------------------------------------------
def test_requests_secuenciales_con_separacion_minima(make, oba, tmp_path):
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps({"stops": [{"id": "14_20444", "line": "39"}]}), encoding="utf-8")
    make(sweep=True, arrivals_per_cycle=2, arrival_stops_path=panel, trips_per_cycle=2).run(5)
    log = oba.log
    assert len(log) > 20
    assert {r["resource"].split("/")[0] for r in log} >= {"vehicles-for-agency", "arrivals-and-departures-for-stop",
                                                         "trip-details"}
    for a, b in zip(log, log[1:]):
        assert b["start"] >= a["end"], "superposición"
        assert b["start"] - a["end"] >= 3.0 - 1e-9, "separación < 3 s"
    assert stats(tmp_path)["requests_by_kind"]["C"] > 0  # la rotación C usa los huecos


# 8 ---------------------------------------------------------------------------------------------
def test_identidad_registro_vivo_conflicto(make, oba, tmp_path):
    body = load_fixture("vehicles-for-agency/708")
    no_trip = next(v for v in body["data"]["list"] if not v.get("tripId") and v["vehicleId"].split("_")[1] in REGISTRY
                   and v.get("location") and in_bbox(v["location"]["lat"], v["location"]["lon"]))
    live = next(v for v in body["data"]["list"] if v.get("tripStatus") and v["tripStatus"].get("vehicleLabel")
                and in_bbox(v["location"]["lat"], v["location"]["lon"]))
    clash = next(v for v in body["data"]["list"] if v.get("tripStatus") and v is not live
                 and v["vehicleId"].split("_")[1] in REGISTRY and in_bbox(v["location"]["lat"], v["location"]["lon"]))
    clash_id = clash["vehicleId"].split("_")[1]
    clash["tripStatus"]["vehicleLabel"] = "999-9999"  # distinto del registro
    oba.overrides["vehicles-for-agency/708"] = body
    make(record_lines=["151"]).run(1)
    kf = {v["id"]: v for v in pos_frames(tmp_path)[0]["new"]}
    nt = kf[no_trip["vehicleId"].split("_")[1]]
    assert nt["label_src"] == "registry" and nt["label"] == REGISTRY[nt["id"]]
    lv = kf[live["vehicleId"].split("_")[1]]
    assert lv["label_src"] == "oba" and lv["label"] == live["tripStatus"]["vehicleLabel"]
    assert lv["line"] == LabelLineMap(_map_path(), _overrides()).line_for_label(lv["label"], ba_date(T0))
    learned = json.loads((tmp_path / "data" / "learned_labels.json").read_text(encoding="utf-8"))
    assert [c for c in learned["conflicts"] if c["id"] == clash_id] == [
        {"id": clash_id, "known": REGISTRY[clash_id], "seen": "999-9999", "at": learned["conflicts"][0]["at"]}]


def _map_path():
    from config import Config
    return Config(oba_key="", data_dir=Path(".")).label_line_map_path


def _overrides():
    return FIXTURES.parent / "datos" / "label_line_map_overrides.json"


def test_linea_por_sufijo_a_la_fecha_26():
    m = LabelLineMap(_map_path(), _overrides())
    assert m.line_for_label("12-1336", "2026-09-17") == "26"
    assert m.line_for_label("12-1336", "2026-09-18") is None
    assert m.line_for_label("12-4820", "2026-09-18") == "26"
    assert m.line_for_label("12-4820", "2026-09-17") != "26"
    assert m.agencies_for("26", "2026-09-17") == ["13"] and m.agencies_for("26", "2026-10-20") == ["12"]
    assert set(m.agencies_for("124", "2026-10-20")) >= {"6", "704"}


def test_label_aprendido_persiste(tmp_path):
    from fake_oba import FakeClock
    c = FakeClock(T0)
    i1 = Identity({}, {}, tmp_path / "learned.json", c)
    assert i1.resolve("555", "7-1350") == ("7-1350", "oba")
    i1.flush()
    i2 = Identity({}, {}, tmp_path / "learned.json", c)
    assert i2.resolve("555", None) == ("7-1350", "learned")
    assert i2.stats()["conflicts"] == 0


# 9 ---------------------------------------------------------------------------------------------
def reconstruct_at(filepath, target_ts):
    """Copia literal de la skill grabador_nuc.md."""
    state = {}
    with gzip.open(filepath, 'rt') as f:
        for line in f:
            frame = json.loads(line)
            if frame.get('gap') or frame['t'] > target_ts:
                break
            for v in frame.get('new', []):
                state[v['id']] = v.copy()
            for vid in frame.get('del', []):
                state.pop(vid, None)
            for upd in frame.get('upd', []):
                if upd['id'] in state:
                    state[upd['id']].update(upd)
    return state


def test_gzip_python_y_reconstruccion_de_estado(make, oba, tmp_path):
    oba.use_sequence("vehicles-for-agency/708", load_sequence("seq_708_cada_60s"))
    make(record_lines=["151"]).run(4)
    files = list((tmp_path / "data" / "posiciones").glob("*.ndjson.gz"))
    assert len(files) == 1
    lines = read_ndjson(files[0])  # gzip.open(p, 'rt'), multi-member
    assert len(lines) == 4
    state = json.loads((tmp_path / "data" / "state.json").read_text(encoding="utf-8"))["vehicles"]
    assert reconstruct_at(files[0], float("inf")) == state


# 10 --------------------------------------------------------------------------------------------
def test_arribos_una_linea_por_consulta(make, tmp_path):
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps({"stops": [{"id": "14_20444", "line": "39", "name": "x"}]}), encoding="utf-8")
    make(arrivals_per_cycle=1, arrival_stops_path=panel).run(1)
    lines = read_dir(tmp_path / "data" / "arribos")
    assert len(lines) == 1
    rec = lines[0]
    raw = load_fixture("arrivals-and-departures-for-stop/14_20444")
    assert rec["t"] == raw["currentTime"] // 1000 and rec["stop"] == "14_20444" and rec["line"] == "39"
    assert len(rec["arrivals"]) == len(raw["data"]["entry"]["arrivalsAndDepartures"])
    for a in rec["arrivals"]:
        for k in ["vehicle", "label", "route", "trip", "predicted", "pred_arr", "sched_arr", "stops_away", "dist_m",
                  "frequency", "sched_dev", "veh_ts", "lat", "lon", "veh_line"]:
            assert k in a, k
        if a["predicted"]:
            assert a["pred_arr"] == a["sched_arr"] + a["sched_dev"]  # CuandoSubo = horario + desvío
            assert a["veh_line"] == "39"
        else:
            assert a["pred_arr"] is None
    assert any(a["predicted"] for a in rec["arrivals"]) and any(not a["predicted"] for a in rec["arrivals"])
    assert stats(tmp_path)["arrivals_lines"] == 1
    paradas = json.loads((tmp_path / "data" / "paradas.json").read_text(encoding="utf-8"))
    assert "14_20444" in paradas


# 11 --------------------------------------------------------------------------------------------
TRIP = "56_128107-1"


def one_trip_body(service_date_ms: int) -> dict:
    """Foto real de la agencia 56 con un solo coche del 39 con trip (TRIP) en el día de servicio dado."""
    body = load_fixture("vehicles-for-agency/56")
    v = next(x for x in body["data"]["list"] if x.get("tripStatus"))
    for x in body["data"]["list"]:
        if x is not v:
            x["tripId"] = ""
    v["tripId"] = TRIP
    v["tripStatus"]["vehicleLabel"] = "62-1350"
    v["tripStatus"]["serviceDate"] = service_date_ms
    return body


def horarios(tmp_path):
    return read_dir(tmp_path / "data" / "horarios")


def test_horario_mismo_trip_mismo_dia_no_se_repide(make, oba, tmp_path):
    sd = int(T0 // 86400 * 86400 + 3 * 3600) * 1000  # 00:00 BA del día del fixture
    oba.overrides["vehicles-for-agency/56"] = one_trip_body(sd)
    make(record_lines=["39"], trips_per_cycle=5).run(3)
    make(record_lines=["39"], trips_per_cycle=5).run(2)  # reinicio el mismo día: el índice en disco evita repetir

    assert len(oba.requests(f"trip-details/{TRIP}")) == 1
    hor = horarios(tmp_path)
    assert len(hor) == 1
    h = hor[0]
    raw = load_fixture(f"trip-details/{TRIP}")["data"]["entry"]
    assert h["oba_trip_id"] == TRIP and h["trip_id"] == "128107-1" and h["service_date"] == sd // 1000
    assert h["full"] is True and len(h["hash"]) == 16
    assert h["route_id"] == "1932" and h["direction_id"] == 0
    assert [s["stop"] for s in h["stop_times"]] == [s["stopId"] for s in raw["schedule"]["stopTimes"]]
    assert h["stop_times"][0]["arr"] == raw["schedule"]["stopTimes"][0]["arrivalTime"]
    paradas = json.loads((tmp_path / "data" / "paradas.json").read_text(encoding="utf-8"))
    assert all(s["stop"] in paradas for s in h["stop_times"])
    assert stats(tmp_path)["trips_day"]["fetched"] == 0  # stats del segundo proceso: no pidió nada


def _two_days(make, oba, clock, tmp_path, change_schedule: bool):
    sd1 = int(T0 // 86400 * 86400 + 3 * 3600) * 1000
    oba.overrides["vehicles-for-agency/56"] = one_trip_body(sd1)
    rec = make(record_lines=["39"], trips_per_cycle=5)
    rec.run(2)
    clock.t += 86400
    oba.overrides["vehicles-for-agency/56"] = one_trip_body(sd1 + 86400 * 1000)
    if change_schedule:
        td = load_fixture(f"trip-details/{TRIP}")
        td["data"]["entry"]["schedule"]["stopTimes"][5]["arrivalTime"] += 60
        oba.overrides[f"trip-details/{TRIP}"] = td
    rec.run(2)
    return sd1 // 1000


def test_horario_al_dia_siguiente_se_repide_y_si_es_igual_va_solo_el_hash(make, oba, clock, tmp_path):
    sd1 = _two_days(make, oba, clock, tmp_path, change_schedule=False)
    assert len(oba.requests(f"trip-details/{TRIP}")) == 2
    h1, h2 = horarios(tmp_path)
    assert (h1["service_date"], h2["service_date"]) == (sd1, sd1 + 86400)
    assert h1["hash"] == h2["hash"]
    assert h1["full"] is True and "stop_times" in h1
    assert h2["full"] is False and "stop_times" not in h2  # no repite el detalle
    td = stats(tmp_path)["trips_day"]
    assert td["same_as_prev_service_day"] == 1 and td["horario_cambiado"] == 0
    idx = json.loads((tmp_path / "data" / "horarios_index.json").read_text(encoding="utf-8"))
    assert idx["hashes"][h2["hash"]]["file"].startswith("horarios/")  # dónde buscar el detalle


def test_horario_distinto_al_dia_siguiente_va_completo_y_cuenta_cambio(make, oba, clock, tmp_path):
    _two_days(make, oba, clock, tmp_path, change_schedule=True)
    h1, h2 = horarios(tmp_path)
    assert h1["hash"] != h2["hash"]
    assert h2["full"] is True and h2["stop_times"][5]["arr"] == h1["stop_times"][5]["arr"] + 60
    s = stats(tmp_path)
    assert s["trips_day"]["horario_cambiado"] == 1 and s["horario_cambiado_total"] == 1


def test_trips_de_coches_en_el_panel_tienen_prioridad(make, oba, tmp_path):
    sd = int(T0 // 86400 * 86400 + 3 * 3600) * 1000
    oba.overrides["vehicles-for-agency/56"] = load_fixture("vehicles-for-agency/56")  # muchos trips del 39
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps({"stops": [{"id": "14_20444", "line": "39"}]}), encoding="utf-8")
    rec = make(record_lines=["39"], trips_per_cycle=1, arrivals_per_cycle=1, arrival_stops_path=panel)
    rec.run(1)  # cola: trips de posiciones (normal) y de arribos del panel (prioridad)
    arr = load_fixture("arrivals-and-departures-for-stop/14_20444")["data"]["entry"]["arrivalsAndDepartures"]
    panel_trips = {a["tripId"] for a in arr if a.get("vehicleId")}
    n0 = len(oba.requests("trip-details/"))
    rec.run(1)
    first = oba.requests("trip-details/")[n0]["resource"].split("/", 1)[1]
    assert first in panel_trips
    assert stats(tmp_path)["trips_queue"] > 0 and "trips_queue_priority" in stats(tmp_path)


# guardrails ------------------------------------------------------------------------------------
def test_tier_a_caido_10_min_sale_con_exit_1(make, oba, tmp_path):
    oba.mode = "down"
    with pytest.raises(SystemExit) as e:
        make().run(100)
    assert e.value.code == 1
    assert not (tmp_path / "data" / "posiciones").exists()


def test_waf_persistente_no_cuenta_como_caida(make, oba):
    oba.mode = "waf"
    make().run(10)  # no sale: el WAF es una pausa, no un fallo de red
