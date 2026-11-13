"""
Genera el fixture de paridad JS vs Python del modelo por tramos.

Cada caso trae las entradas crudas de produccion (linea, ultimo ping del coche, punto del usuario, hora de la consulta,
historial propio y de otros coches) y la salida de `predict_from_raw`. El test de proyectoconsola corre la implementacion
JS sobre las mismas entradas y compara (tolerancia 0,5 s en el ETA).

Uso (desde "prediccion colectivos/"):
  python -m prediccion.scripts.gen_path_parity_fixture --export data/ml/export/path_v2b_s0 \
      --out ../proyectoconsola/test/fixtures/path_parity.json [--seed 7] [--per-shape 4]
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from prediccion.inference.path_reference import load_bundle, predict_from_raw

M_PER_DEG = 111320.0
BASE_TS = 1784214000  # 2026-07-16 ~15:00 UTC, dia habil


def _norm(r: dict) -> dict:
    return {
        "status": r["status"], "eta_s": r["eta_s"], "shape_id": r["shape_id"], "en_cabecera": r["en_cabecera"],
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

    def add(name, line, vehicle, user, now, history=None, others=None):
        r = predict_from_raw(bundle, line, vehicle, user, now, history=history, others=others)
        cases.append({"name": name, "line": line, "vehicle": vehicle, "user": list(user), "now_ts": now,
                      "history": history or [], "others": others or [], "expected": _norm(r)})

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
                if kind == 1:
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
            ula, ulo = sh.latlon_at(min(d_p + 70, L))
            add(f"{line}/{sid}/llegando", line, {"lat": la, "lon": lo, "speed_mps": 6.0, "ts": now}, (ula, ulo), now)
            ula, ulo = sh.latlon_at(max(d_p - 600, 0.0)) if d_p > 700 else sh.latlon_at(0.0)
            add(f"{line}/{sid}/pasado", line, {"lat": la, "lon": lo, "speed_mps": 6.0, "ts": now}, (ula, ulo), now)
            la0, lo0 = sh.latlon_at(60.0)
            ula, ulo = sh.latlon_at(min(L * 0.5, 6000.0))
            add(f"{line}/{sid}/cabecera", line, {"lat": la0, "lon": lo0, "speed_mps": 0.0, "ts": now - 30}, (ula, ulo), now)
            fl, fo = _offset(la, lo, 400.0, 0.0)
            ula, ulo = sh.latlon_at(min(d_p + 2000, L))
            add(f"{line}/{sid}/coche_fuera_del_recorrido", line, {"lat": fl, "lon": fo, "speed_mps": 5.0, "ts": now}, (ula, ulo), now)
            ul2, ulo2 = _offset(ula, ulo, 0.0, 600.0)
            add(f"{line}/{sid}/usuario_lejos_del_recorrido", line, {"lat": la, "lon": lo, "speed_mps": 5.0, "ts": now}, (ul2, ulo2), now)
            add(f"{line}/{sid}/ping_viejo", line, {"lat": la, "lon": lo, "speed_mps": 4.0, "ts": now - 500}, (ula, ulo), now)
            # camino de largo maximo: coche al inicio, usuario al final del shape
            la1, lo1 = sh.latlon_at(150.0)
            ula, ulo = sh.latlon_at(L - 5.0)
            add(f"{line}/{sid}/camino_completo", line, {"lat": la1, "lon": lo1, "speed_mps": 7.0, "ts": now - 10}, (ula, ulo), now)

    # linea fuera del modelo y velocidad ausente
    sh = next(iter(bundle.lines["39"].values()))
    la, lo = sh.latlon_at(1000.0)
    ula, ulo = sh.latlon_at(5000.0)
    add("linea_fuera_del_modelo", "999", {"lat": la, "lon": lo, "speed_mps": 5.0, "ts": BASE_TS}, (ula, ulo), BASE_TS)
    add("velocidad_ausente", "39", {"lat": la, "lon": lo, "speed_mps": None, "ts": BASE_TS - 20}, (ula, ulo), BASE_TS)

    out = {"model_version": bundle.manifest["model_version"], "contract_version": bundle.manifest["contract_version"],
           "tolerance_s": 0.5, "n_cases": len(cases), "cases": cases}
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    by = {}
    for c in cases:
        s = c["expected"]["status"]
        by[s] = by.get(s, 0) + 1
    print(f"{len(cases)} casos -> {p} ({p.stat().st_size / 1024:.0f} KB); estados: {by}")


if __name__ == "__main__":
    main()
