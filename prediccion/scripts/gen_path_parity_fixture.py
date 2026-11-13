"""
Genera el fixture de paridad JS vs Python del modelo por tramos.

Cada caso trae las entradas crudas de produccion (linea, ultimo ping del coche, punto del usuario, hora de la consulta,
historial propio y de otros coches) y la salida de `predict_from_raw`. El test de proyectoconsola corre la implementacion
JS sobre las mismas entradas y compara (tolerancia 0,5 s en el ETA).

Uso (desde "prediccion colectivos/"):
  python -m prediccion.scripts.gen_path_parity_fixture --export data/ml/export/path_v2c_l1_s1 \
      --out ../proyectoconsola/test/fixtures/path_parity.json [--seed 7] [--per-shape 4]
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from prediccion.inference.path_reference import load_bundle, predict_from_raw, snap_to_route
from prediccion.v2 import geo_assign as G

M_PER_DEG = 111320.0
BASE_TS = 1784214000  # 2026-07-16 ~15:00 UTC, dia habil


def _norm(r: dict) -> dict:
    return {
        "status": r["status"], "eta_s": r["eta_s"], "shape_id": r["shape_id"], "en_cabecera": r["en_cabecera"],
        "group": r["group"], "depends_on": r["depends_on"], "sense": r["sense"], "compatible": r["compatible"],
        "provisional": r["provisional"],
        "discarded": r["discarded"],
        "candidates": [{k: (float(v) if isinstance(v, float) else v) for k, v in c.items()} for c in r["candidates"]],
    }


def _offset(lat, lon, north_m=0.0, east_m=0.0):
    return lat + north_m / M_PER_DEG, lon + east_m / (M_PER_DEG * math.cos(math.radians(lat)))


def _trail(sh, d_p, now, n, step_m, dt_s, backward=False, jitter=None, rnd=None):
    """Pings anteriores del coche sobre el shape, ascendentes en el tiempo."""
    out = []
    for i in range(n, 0, -1):
        d = d_p - i * step_m if not backward else d_p + i * step_m
        if d < 0 or d > sh.length_m:
            continue
        la, lo = sh.latlon_at(d)
        if jitter and rnd:
            la, lo = _offset(la, lo, rnd.uniform(-jitter, jitter), rnd.uniform(-jitter, jitter))
        out.append({"ts": now - i * dt_s, "lat": la, "lon": lo})
    return out


def _others(sh, d_t, now, rnd, n_buses):
    """Otros coches de la linea que pasaron por T antes de `now`, con pings cada 30 s."""
    res = []
    for _ in range(n_buses):
        speed_mps = rnd.uniform(3, 9)
        t_pass = now - rnd.uniform(60, 1500)
        pings = []
        for k in range(-6, 4):
            d = d_t + k * speed_mps * 30 + rnd.uniform(-20, 20)
            if 0 <= d <= sh.length_m:
                la, lo = sh.latlon_at(d)
                pings.append([t_pass + k * 30, la, lo])
        res.append({"pings": pings})
    return res


def _veh(sh, d, ts, speed=6.0):
    la, lo = sh.latlon_at(d)
    return {"lat": la, "lon": lo, "speed_mps": speed, "ts": ts}


def _perp_to(other, sh, d):
    la, lo = sh.latlon_at(d)
    return other.project(la, lo)[1]


def _scenarios(bundle, add, rnd):
    """Casos de la regla de candidatos (sentido obligatorio, shapes del usuario, grupos seguro / puede venir)."""
    now = BASE_TS + 54321
    for line, shapes in bundle.lines.items():
        items = list(shapes.items())
        for sid, sh in items:
            L = sh.length_m
            if L < 6000:
                continue
            tag = f"{line}/{sid}"
            d_p = L * 0.4
            veh = _veh(sh, d_p, now - 10)
            hist = _trail(sh, d_p, now - 10, 6, 200, 60)
            ahead = sh.latlon_at(d_p + 1500)
            behind = sh.latlon_at(d_p - 800)
            # coche sin historial: ETA provisional
            add(f"{tag}/sin_historial", line, veh, ahead, now)
            # provisionales: sin historial o con un solo ping previo, punto adelante / atras, parada y punto
            add(f"{tag}/provisional_adelante_parada", line, veh, ahead, now, None, user_kind="parada", stop_recorridos=[sh.name])
            add(f"{tag}/provisional_atras", line, veh, behind, now)
            add(f"{tag}/provisional_un_ping", line, veh, ahead, now, _trail(sh, d_p, now - 10, 1, 10, 60))
            add(f"{tag}/provisional_cabecera", line, _veh(sh, 80.0, now - 10, 0.0), sh.latlon_at(3000.0), now,
                _trail(sh, 80.0, now - 10, 2, 5, 60))
            # coche quieto con historial sin avance: provisional
            add(f"{tag}/quieto_sin_avance", line, {**veh, "speed_mps": 0.0}, ahead, now, _trail(sh, d_p, now - 10, 5, 5, 60))
            # coche con historial que ya paso por el punto
            add(f"{tag}/ya_paso_con_historial", line, veh, behind, now, hist)
            # coche con historial hacia adelante: punto adelante
            add(f"{tag}/viene_con_historial", line, veh, ahead, now, hist)
            # coche con historial al reves: va en sentido contrario al shape
            add(f"{tag}/historial_al_reves", line, veh, ahead, now, _trail(sh, d_p, now - 10, 6, 200, 60, backward=True))
            # parada que sirve solo este recorrido (por nombre), coche en el tronco o no
            add(f"{tag}/parada_un_recorrido", line, veh, ahead, now, hist, user_kind="parada", stop_recorridos=[sh.name])
            # parada servida por todos los recorridos de la linea
            add(f"{tag}/parada_todos", line, veh, ahead, now, hist, user_kind="parada", stop_recorridos=[x.name for _, x in items])
            # parada sin recorridos asociados: se asocia por distancia (<= 25 m)
            add(f"{tag}/parada_por_distancia", line, veh, ahead, now, hist, user_kind="parada", stop_recorridos=None)
            # parada con nombre que no existe: cae a la distancia
            add(f"{tag}/parada_nombre_desconocido", line, veh, ahead, now, hist, user_kind="parada", stop_recorridos=["no existe"])

            # recorridos paralelos: el punto esta a 45..100 m de otro shape
            for oid, other in items:
                if oid == sid or L < 3000:
                    continue
                for d_u in range(1000, int(L) - 500, 150):
                    perp = _perp_to(other, sh, d_u)
                    if 45 <= perp <= 100:
                        user = sh.latlon_at(d_u)
                        a_d = max(d_u - 1200, 200.0)
                        add(f"{tag}/paralelo_{oid}/coche_en_este", line, _veh(sh, a_d, now - 10), user, now,
                            _trail(sh, a_d, now - 10, 6, 200, 60))
                        d_o = other.project(*user)[0]
                        b_d = max(d_o - 1200, 200.0)
                        add(f"{tag}/paralelo_{oid}/coche_en_paralelo", line, _veh(other, b_d, now - 10), user, now,
                            _trail(other, b_d, now - 10, 6, 200, 60))
                        break
                else:
                    continue
                break

            # ramal unico: coche en un tramo donde ningun otro shape queda a menos de 200 m, punto adelante sobre este shape
            for d_b in range(1000, int(L) - 3000, 200):
                if all(_perp_to(o, sh, d_b) > 200 and _perp_to(o, sh, d_b - 600) > 200 for oid, o in items if oid != sid):
                    a_d = d_b + 1500
                    add(f"{tag}/ramal_unico", line, _veh(sh, d_b, now - 10), sh.latlon_at(a_d), now,
                        _trail(sh, d_b, now - 10, 6, 100, 60))
                    break

    # linea 39: coche en el tronco compartido de los tres ramales y parada que solo sirve el Ramal 1 (Cordoba y Dorrego)
    if "39" in bundle.lines:
        shapes = bundle.lines["39"]
        a = next(iter(shapes.values()))
        names_a = [a.name]
        la, lo = a.latlon_at(14870.0)
        for d_b in (4000.0, 8000.0, 12500.0):
            add(f"39/tronco_compartido_{int(d_b)}", "39", _veh(a, d_b, now - 10), (la, lo), now,
                _trail(a, d_b, now - 10, 6, 150, 60), user_kind="parada", stop_recorridos=names_a)
        add("39/tronco_compartido_punto_gps", "39", _veh(a, 8000.0, now - 10), (la, lo), now, _trail(a, 8000.0, now - 10, 6, 150, 60))


def _assign_scenarios(bundle, add, rnd):
    """Casos de la asignacion geo_assign (compatibilidad por posicion con T/M, sentido por historial, ramal exclusivo)."""
    now = BASE_TS + 77777
    for line, shapes in bundle.lines.items():
        items = list(shapes.items())
        done = {"ruido": 0, "par100": 0, "idavuelta": 0, "excl": 0}
        for sid, sh in items:
            L = sh.length_m
            if L < 6000:
                continue
            tag = f"{line}/{sid}"
            # ruido de GPS de ~10 m en coche, historial y punto del usuario: sigue siendo compatible
            if done["ruido"] < 2:
                done["ruido"] += 1
                d_p = L * 0.35
                jit = lambda la_lo: _offset(la_lo[0], la_lo[1], rnd.uniform(-7, 7), rnd.uniform(-7, 7))  # noqa: E731
                la, lo = jit(sh.latlon_at(d_p))
                tla, tlo = jit(sh.latlon_at(d_p + 2000))
                add(f"{tag}/ruido_10m", line, {"lat": la, "lon": lo, "speed_mps": 6.0, "ts": now - 10}, (tla, tlo), now,
                    _trail(sh, d_p, now - 10, 8, 150, 45, jitter=7, rnd=rnd))
            for oid, other in items:
                if oid == sid:
                    continue
                # calle paralela a ~100 m (80..130 m del otro recorrido): el otro no es compatible con ese punto
                if done["par100"] < 2:
                    for d_u in range(1000, int(L) - 500, 100):
                        if 80 <= _perp_to(other, sh, d_u) <= 130:
                            done["par100"] += 1
                            user = sh.latlon_at(d_u)
                            a_d = max(d_u - 1200, 200.0)
                            add(f"{tag}/paralela_100m_{oid}/coche_en_este", line, _veh(sh, a_d, now - 10), user, now,
                                _trail(sh, a_d, now - 10, 6, 200, 60))
                            b_d = max(other.project(*user)[0] - 1200, 200.0)
                            add(f"{tag}/paralela_100m_{oid}/coche_en_paralelo", line, _veh(other, b_d, now - 10), user, now,
                                _trail(other, b_d, now - 10, 6, 200, 60))
                            break
                # ida y vuelta por la misma calle: dos shapes casi superpuestos recorridos en sentido contrario
                if done["idavuelta"] < 2:
                    for d_a in range(1000, int(L) - 2600, 150):
                        pa, pb = sh.latlon_at(d_a), sh.latlon_at(d_a + 1500)
                        (d0, e0), (d1, e1) = other.project(*pa), other.project(*pb)
                        if e0 < 8 and e1 < 8 and d1 < d0 - 1000:
                            done["idavuelta"] += 1
                            user = sh.latlon_at(d_a + 1000)
                            veh = _veh(sh, d_a, now - 10)
                            add(f"{tag}/ida_vuelta_{oid}/con_historial", line, veh, user, now, _trail(sh, d_a, now - 10, 6, 150, 60))
                            add(f"{tag}/ida_vuelta_{oid}/sin_historial", line, veh, user, now)
                            add(f"{tag}/ida_vuelta_{oid}/historial_inverso", line, _veh(other, d0, now - 10), user, now,
                                _trail(other, d0, now - 10, 6, 150, 60))
                            break
                # coche pasada la bifurcacion, sobre un tramo exclusivo de `sid` (a > 200 m de `other`), con el punto sobre un
                # tramo exclusivo de `other`: `sid` no sirve el punto y el coche no se lista
                if done["excl"] < 2:
                    d_b = next((d for d in range(1500, int(L) - 500, 200)
                                if _perp_to(other, sh, d) > 200 and _perp_to(other, sh, d - 600) > 200), None)
                    d_u = next((d for d in range(1000, int(other.length_m) - 500, 200)
                                if _perp_to(sh, other, d) > 200), None)
                    if d_b is not None and d_u is not None:
                        done["excl"] += 1
                        user = other.latlon_at(d_u)
                        hist = _trail(sh, d_b, now - 10, 6, 150, 60)
                        add(f"{tag}/exclusivo_de_{oid}/parada", line, _veh(sh, d_b, now - 10), user, now, hist,
                            user_kind="parada", stop_recorridos=[other.name])
                        add(f"{tag}/exclusivo_de_{oid}/punto", line, _veh(sh, d_b, now - 10), user, now, hist)


def _geo_sense_scenarios(bundle, add, rnd):
    """Sentido por geometría (contrato 2.1), todos sin historial:
      geo_un_shape        calle que recorre un solo shape (mano única)         -> viene (seguro)
      geo_tronco_todos    tronco de un solo sentido, parada de todos los ramales -> viene (seguro)
      geo_bifurcacion     tronco de un solo sentido, la parada solo la sirve un ramal (se bifurca después) -> puede venir
      ida_y_vuelta        misma calle en los dos sentidos                       -> provisional
    """
    now = BASE_TS + 33333
    for line, shapes in bundle.lines.items():
        items = list(shapes.items())
        done = {"un": 0, "todos": 0, "bif": 0, "iv": 0}
        for sid, sh in items:
            L = sh.length_m
            tag = f"{line}/{sid}"
            for d in range(500, int(L) - 2500, 250):
                la, lo = sh.latlon_at(d)
                comp = [c[0] for c in G.compatible_shapes(la, lo, shapes)]
                if sid not in comp:
                    continue
                geo = G.direction_from_geometry(la, lo, shapes)
                veh = {"lat": la, "lon": lo, "speed_mps": 6.0, "ts": now - 10}
                if geo and len(comp) == 1 and done["un"] < 1:
                    done["un"] += 1
                    add(f"{tag}/geo_un_shape_sin_historial", line, veh, sh.latlon_at(d + 1200), now)
                elif geo and len(comp) >= 2 and (done["todos"] < 1 or done["bif"] < 1):
                    # parada adelante: ¿la sirven todos los compatibles (tronco) o solo este (después de la bifurcación)?
                    for du in range(d + 400, min(int(L) - 100, d + 6000), 200):
                        ula, ulo = sh.latlon_at(du)
                        on_all = all(shapes[c].project(ula, ulo)[1] <= 20
                                     and shapes[c].project(ula, ulo)[0] > shapes[c].project(la, lo)[0] + 100 for c in comp)
                        only_me = all(shapes[c].project(ula, ulo)[1] > 200 for c in comp if c != sid)
                        if on_all and done["todos"] < 1:
                            done["todos"] += 1
                            add(f"{tag}/geo_tronco_todos_sin_historial", line, veh, (ula, ulo), now, user_kind="parada",
                                stop_recorridos=[shapes[c].name for c in comp])
                            break
                        if only_me and done["bif"] < 1:
                            done["bif"] += 1
                            add(f"{tag}/geo_bifurcacion_sin_historial", line, veh, (ula, ulo), now, user_kind="parada",
                                stop_recorridos=[sh.name])
                            break
                elif not geo and len(comp) >= 2 and done["iv"] < 1:
                    hs = [G.shape_heading(shapes[c], la, lo, G.TOL_M)[0] for c in comp]
                    if any(G.angle_diff_deg(hs[0], h) > 135 for h in hs[1:]):
                        done["iv"] += 1
                        add(f"{tag}/geo_ida_y_vuelta_sin_historial", line, veh, sh.latlon_at(d + 1200), now)

    # línea 168, parada "Gascón y Corrientes" (la sirven los dos recorridos hacia el norte por Gascón): coche sin
    # historial sobre el tramo de un solo sentido, 300 m a 2,5 km antes de la parada
    if "168" in bundle.lines:
        shapes = bundle.lines["168"]
        stop = (-34.6033362, -58.4241505)
        names = [sh.name for sh in shapes.values() if sh.project(*stop)[1] <= 20]
        a = next(sh for sh in shapes.values() if sh.project(*stop)[1] <= 20)
        d_s = a.project(*stop)[0]
        for back in (300, 1000, 2500):
            add(f"168/gascon_y_corrientes/sin_historial_{back}m", "168", _veh(a, d_s - back, now - 10), stop, now,
                user_kind="parada", stop_recorridos=names)


def _snap_cases(bundle, rnd):
    """Ajuste del punto del usuario al recorrido (snap_to_route): puntos a 0..300 m de un shape."""
    out = []
    for line, shapes in bundle.lines.items():
        for sid, sh in list(shapes.items())[:2]:
            for off in (0.0, 15.0, 40.0, 50.0, 120.0, 300.0):
                d = rnd.uniform(200, sh.length_m - 200)
                la, lo = _offset(*sh.latlon_at(d), off * rnd.choice([-1, 1]), rnd.uniform(-5, 5))
                r = snap_to_route(bundle, line, la, lo)
                out.append({"line": line, "point": [la, lo], "expected": r})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--per-shape", type=int, default=4)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    bundle = load_bundle(a.export)
    cases = []

    def add(name, line, vehicle, user, now, history=None, others=None, user_kind="punto", stop_recorridos=None):
        r = predict_from_raw(bundle, line, vehicle, user, now, history=history, others=others, user_kind=user_kind,
                             stop_recorridos=stop_recorridos)
        cases.append({"name": name, "line": line, "vehicle": vehicle, "user": list(user), "now_ts": now,
                      "history": history or [], "others": others or [], "user_kind": user_kind,
                      "stop_recorridos": stop_recorridos, "expected": _norm(r)})

    for line, shapes in bundle.lines.items():
        for sid, sh in shapes.items():
            L = sh.length_m
            for i in range(a.per_shape):
                d_p = rnd.uniform(0, L * 0.7)
                rem = rnd.uniform(100, min(L - d_p, 9000)) if L - d_p > 100 else 100
                d_t = min(d_p + rem, L)
                now = BASE_TS + rnd.randint(0, 6 * 86400)
                age = rnd.choice([0, 5, 20, 45, 120, 300])
                speed = rnd.choice([0.0, 0.0, 2.0, 5.5, 8.0, 12.0])
                vla, vlo = sh.latlon_at(d_p)
                vla, vlo = _offset(vla, vlo, rnd.uniform(-40, 40), rnd.uniform(-40, 40))
                tla, tlo = sh.latlon_at(d_t)
                tla, tlo = _offset(tla, tlo, rnd.uniform(-30, 30), rnd.uniform(-30, 30))
                veh = {"lat": vla, "lon": vlo, "speed_mps": speed, "ts": now - age}
                hist = others = None
                kind = i % 4
                if kind == 0:
                    hist = _trail(sh, d_p, now - age, 6, 250, 45)
                elif kind == 1:
                    hist = _trail(sh, d_p, now - age, 20, 250, 45, jitter=15, rnd=rnd)
                elif kind == 2:
                    hist = _trail(sh, d_p, now - age, 15, 250, 45, backward=True)
                    others = _others(sh, d_t, now - age, rnd, 3)
                elif kind == 3:
                    others = _others(sh, d_t, now - age, rnd, 4)
                    hist = _trail(sh, d_p, now - age, 10, 300, 60)
                add(f"{line}/{sid}/azar{i}", line, veh, (tla, tlo), now, hist, others)

            # casos limite por shape
            now = BASE_TS + 12345
            d_p = min(400.0, L * 0.1)
            la, lo = sh.latlon_at(d_p)
            h_p = _trail(sh, d_p, now, 4, 100, 30)
            h_p = h_p if d_p >= 400 else _trail(sh, d_p, now, 3, 130, 30)
            ula, ulo = sh.latlon_at(min(d_p + 70, L))
            add(f"{line}/{sid}/llegando", line, {"lat": la, "lon": lo, "speed_mps": 6.0, "ts": now}, (ula, ulo), now, h_p)
            ula, ulo = sh.latlon_at(max(d_p - 600, 0.0)) if d_p > 700 else sh.latlon_at(0.0)
            add(f"{line}/{sid}/pasado", line, {"lat": la, "lon": lo, "speed_mps": 6.0, "ts": now}, (ula, ulo), now, h_p)
            la0, lo0 = sh.latlon_at(60.0)
            ula, ulo = sh.latlon_at(min(L * 0.5, 6000.0))
            add(f"{line}/{sid}/cabecera", line, {"lat": la0, "lon": lo0, "speed_mps": 0.0, "ts": now - 30}, (ula, ulo), now,
                _trail(sh, 60.0, now - 30, 2, 30, 30))
            fl, fo = _offset(la, lo, 400.0, 0.0)
            ula, ulo = sh.latlon_at(min(d_p + 2000, L))
            add(f"{line}/{sid}/coche_fuera_del_recorrido", line, {"lat": fl, "lon": fo, "speed_mps": 5.0, "ts": now}, (ula, ulo), now, h_p)
            ul2, ulo2 = _offset(ula, ulo, 0.0, 600.0)
            add(f"{line}/{sid}/usuario_lejos_del_recorrido", line, {"lat": la, "lon": lo, "speed_mps": 5.0, "ts": now}, (ul2, ulo2), now, h_p)
            add(f"{line}/{sid}/ping_viejo", line, {"lat": la, "lon": lo, "speed_mps": 4.0, "ts": now - 500}, (ula, ulo), now,
                _trail(sh, d_p, now - 500, 4, 100, 30))
            # camino de largo maximo: coche al inicio, usuario al final del shape
            la1, lo1 = sh.latlon_at(150.0)
            ula, ulo = sh.latlon_at(L - 5.0)
            add(f"{line}/{sid}/camino_completo", line, {"lat": la1, "lon": lo1, "speed_mps": 7.0, "ts": now - 10}, (ula, ulo), now,
                _trail(sh, 150.0, now - 10, 3, 50, 30))

    _scenarios(bundle, add, rnd)
    _assign_scenarios(bundle, add, rnd)
    _geo_sense_scenarios(bundle, add, rnd)

    # linea fuera del modelo y velocidad ausente
    sh = next(iter(bundle.lines["39"].values()))
    la, lo = sh.latlon_at(1000.0)
    ula, ulo = sh.latlon_at(5000.0)
    add("linea_fuera_del_modelo", "999", {"lat": la, "lon": lo, "speed_mps": 5.0, "ts": BASE_TS}, (ula, ulo), BASE_TS)
    add("velocidad_ausente", "39", {"lat": la, "lon": lo, "speed_mps": None, "ts": BASE_TS - 20}, (ula, ulo), BASE_TS)

    out = {"model_version": bundle.manifest["model_version"], "contract_version": bundle.manifest["contract_version"],
           "tolerance_s": 0.5, "n_cases": len(cases), "cases": cases, "snaps": _snap_cases(bundle, rnd)}
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    by = {}
    for c in cases:
        s = c["expected"]["status"]
        by[s] = by.get(s, 0) + 1
    groups = {}
    for c in cases:
        g = c["expected"]["group"]
        groups[g] = groups.get(g, 0) + 1
    print(f"{len(cases)} casos -> {p} ({p.stat().st_size / 1024:.0f} KB); estados: {by}; grupos: {groups}")
    geo = {}
    for c in cases:
        if "/geo_" in c["name"] or "gascon" in c["name"] or "ida_vuelta" in c["name"]:
            k = c["name"].split("/")[-1] if "gascon" not in c["name"] else "gascon"
            k = k if "ida_vuelta" not in c["name"] else "ida_vuelta/" + k
            geo.setdefault(k, {}).setdefault(str(c["expected"]["group"]), 0)
            geo[k][str(c["expected"]["group"])] += 1
    print("sentido por geometría:", geo)


if __name__ == "__main__":
    main()
