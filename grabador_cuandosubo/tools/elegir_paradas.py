"""Arma el panel de paradas para arribos (arrival_stops.json).

Para cada línea:
  1. routes-for-agency/{agencias de la línea en el map} → rutas OBA cuyo shortName empieza con la línea
     (ej. 39 → 39A..39F; 168 → "168 Saavedra x Coleg", ...). Cada ruta OBA es un sentido de un ramal.
  2. stops-for-route/{ruta} → paradas ordenadas.
  3. Agrupa las rutas por sentido (vector primera → última parada contra el de la ruta más larga).
  4. Tronco de cada sentido: paradas que están en TODOS los ramales de ese sentido (si no hay,
     las que están en la mayoría). Así la parada sirve a todos los coches de la línea en ese sentido.
  5. Elige por distancia acumulada sobre la ruta más larga del sentido:
       sentido 0: ~20 % (inicio) y ~80 % (final);  sentido 1: ~50 % (medio).
  6. Valida contra prediccion/data/line_shapes.json (distancia al recorrido real de la línea).

Requests secuenciales con el mismo limitador del grabador (>= 3,5 s, pausa 120 s ante WAF).
Las respuestas quedan en --cache para no volver a pedirlas.

Uso:
  OBA_KEY=... python tools/elegir_paradas.py --lines 39 26 42 92 168 --cache /tmp/oba_cache --out arrival_stops.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402
from identity import LabelLineMap  # noqa: E402
from limiter import RateLimiter, SystemClock  # noqa: E402
from oba_client import ObaClient, requests_transport  # noqa: E402

FRACTIONS = [(0, 0.2, "inicio"), (1, 0.5, "medio"), (0, 0.8, "final")]


def hav(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def dist_to_polyline(p, pts):
    """Distancia aproximada (m) de p a una polilínea (proyección equirectangular local)."""
    k = math.cos(math.radians(p[0]))
    best = float("inf")
    for (a, b) in zip(pts, pts[1:]):
        ax, ay = (a[1] - p[1]) * k, a[0] - p[0]
        bx, by = (b[1] - p[1]) * k, b[0] - p[0]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
        x, y = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(x, y) * 111320)
    return best


class CachedOba:
    def __init__(self, client: ObaClient, cache: Path):
        self.client, self.cache = client, cache
        cache.mkdir(parents=True, exist_ok=True)

    def get(self, resource: str) -> dict:
        f = self.cache / (re.sub(r"[^\w-]", "__", resource) + ".json")
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        body = self.client.fetch(resource)
        f.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        print(f"  GET {resource} ok", file=sys.stderr)
        return body


def routes_for_line(oba: CachedOba, llmap: LabelLineMap, line: str) -> list[str]:
    agencies = set()
    for e in llmap.lines.get(line, {}).get("agencies", []):
        agencies.add(str(e["agencyId"]))
    pat = re.compile(rf"^{re.escape(line)}(?![0-9])")
    out = []
    for ag in sorted(agencies):
        body = oba.get(f"routes-for-agency/{ag}")
        out += [r["id"] for r in body["data"]["list"] if pat.match(r.get("shortName") or "")]
    return sorted(out)


def choose(oba: CachedOba, line: str, route_ids: list[str], shapes: dict | None) -> list[dict]:
    routes = {}
    stops = {}
    for rid in route_ids:
        body = oba.get(f"stops-for-route/{rid}")
        for s in body["data"]["references"]["stops"]:
            stops[s["id"]] = s
        g = body["data"]["entry"]["stopGroupings"][0]["stopGroups"][0]
        routes[rid] = {"ids": g["stopIds"], "name": g["name"]["name"]}
    ll = lambda sid: (stops[sid]["lat"], stops[sid]["lon"])  # noqa: E731
    ref = max(routes, key=lambda r: len(routes[r]["ids"]))
    rv = (ll(routes[ref]["ids"][-1])[0] - ll(routes[ref]["ids"][0])[0], ll(routes[ref]["ids"][-1])[1] - ll(routes[ref]["ids"][0])[1])
    groups: dict[int, list[str]] = {0: [], 1: []}
    for rid, r in routes.items():
        v = (ll(r["ids"][-1])[0] - ll(r["ids"][0])[0], ll(r["ids"][-1])[1] - ll(r["ids"][0])[1])
        groups[0 if v[0] * rv[0] + v[1] * rv[1] >= 0 else 1].append(rid)

    shape_lines = []
    if shapes and line in shapes:
        shape_lines = [[tuple(p) for p in r["points"]] for r in shapes[line]["ramales"]]

    picked = []
    for direction, frac, where in FRACTIONS:
        rids = groups[direction]
        if not rids:
            continue
        cnt = Counter(sid for rid in rids for sid in set(routes[rid]["ids"]))
        need = len(rids) if max(cnt.values()) == len(rids) else max(cnt.values())
        trunk = {sid for sid, n in cnt.items() if n >= need}
        base = max(rids, key=lambda r: sum(1 for s in routes[r]["ids"] if s in trunk))
        seq = routes[base]["ids"]
        cum = [0.0]
        for a, b in zip(seq, seq[1:]):
            cum.append(cum[-1] + hav(ll(a), ll(b)))
        total = cum[-1]
        cands = [(abs(cum[i] / total - frac), i, sid) for i, sid in enumerate(seq) if sid in trunk]
        cands.sort()
        for _, i, sid in cands:
            d = min((dist_to_polyline(ll(sid), sl) for sl in shape_lines), default=None)
            if d is not None and d > 60:
                continue  # parada OBA fuera del recorrido real (line_shapes.json)
            s = stops[sid]
            picked.append({
                "id": sid, "line": line, "name": s["name"], "lat": s["lat"], "lon": s["lon"],
                "direction": direction, "headsign": routes[base]["name"], "position": where,
                "frac_along": round(cum[i] / total, 3), "routes": sorted(rids),
                "routes_serving": cnt[sid], "dist_to_shape_m": None if d is None else round(d, 1),
            })
            break
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", nargs="+", default=["39", "26", "42", "92", "168"])
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "arrival_stops.json")
    ap.add_argument("--shapes", type=Path, default=ROOT.parent / "prediccion" / "data" / "line_shapes.json")
    ap.add_argument("--merge", action="store_true",
                    help="si --out existe, conserva las paradas de las líneas que no están en --lines y reemplaza las de --lines")
    args = ap.parse_args()
    cfg = Config.from_env()
    if not cfg.oba_key:
        sys.exit("OBA_KEY no definida")
    clock = SystemClock()
    client = ObaClient(cfg.base_url, cfg.oba_key, RateLimiter(max(cfg.min_interval_s, 3.5), clock),
                       requests_transport(), clock, waf_backoff_s=cfg.waf_backoff_s)
    oba = CachedOba(client, args.cache)
    llmap = LabelLineMap(cfg.label_line_map_path, cfg.overrides_path)
    shapes = json.loads(args.shapes.read_text(encoding="utf-8")) if args.shapes.exists() else None
    out = []
    for line in args.lines:
        rids = routes_for_line(oba, llmap, line)
        print(f"{line}: rutas {rids}", file=sys.stderr)
        out += choose(oba, line, rids, shapes)
    prev_doc = None
    if args.merge and args.out.exists():
        prev_doc = json.loads(args.out.read_text(encoding="utf-8"))
        kept = [x for x in prev_doc["stops"] if x["line"] not in args.lines]
        out = kept + out
    doc = {
        "_doc": "Panel de paradas para arribos (arrivals-and-departures-for-stop). Generado por "
                "tools/elegir_paradas.py: por línea, tronco común a todos los ramales de cada sentido; "
                "sentido 0 al ~20% (inicio) y ~80% (final), sentido 1 al ~50% (medio); validado a <=60 m "
                "de prediccion/data/line_shapes.json. 151 excluido (casi no reporta y CuandoSubo le asigna viajes del 65); "
                "124 no está en CuandoSubo.",
        "generated": date.today().isoformat(),
        "stops": out,
    }
    if prev_doc is not None:
        doc["_doc"] = prev_doc["_doc"].replace("151 excluido (CuandoSubo le asigna viajes del 65)", "151 excluido (casi no reporta y CuandoSubo le asigna viajes del 65)")
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    for s in out:
        print(f"{s['line']:>4} d{s['direction']} {s['position']:<6} {s['id']:<14} {s['name'][:30]:<30} "
              f"frac={s['frac_along']} ramales={s['routes_serving']}/{len(s['routes'])} shape={s['dist_to_shape_m']}m",
              file=sys.stderr)
    print(f"{len(out)} paradas → {args.out}  (requests: {client.counters})", file=sys.stderr)


if __name__ == "__main__":
    main()
