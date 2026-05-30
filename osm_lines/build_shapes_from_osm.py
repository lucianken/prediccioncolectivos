#!/usr/bin/env python3
"""
Genera line_shapes.json a partir de osm_lines.json + Overpass (sin GTFS).

Uso:
    python build_shapes_from_osm.py --lines 39
    python build_shapes_from_osm.py --lines 39 42 151
    python build_shapes_from_osm.py --lines all
    python build_shapes_from_osm.py --lines 39 --output /ruta/custom.json
"""

import argparse
import json
import math
import os
import time

import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS      = {"User-Agent": "DondeestaelbondiOSM/1.0 (lucianken@gmail.com)"}
MASTER_FILE  = os.path.join(os.path.dirname(__file__), "osm_lines.json")
DEFAULT_OUT  = os.path.join(os.path.dirname(__file__), "..", "prediccion", "data", "line_shapes.json")

SNAP_M         = 20    # metros: umbral para considerar dos nodos el mismo junction
STOP_ROLES     = {"stop", "stop_entry_only", "stop_exit_only", "platform", "stop_position", ""}
PLATFORM_ROLES = {"platform"}
DEDUP_M        = 40    # metros: plataforma a esta distancia de un stop_position → descartada
RETRY          = 3


# ── Overpass ─────────────────────────────────────────────────────────────────

def _overpass(query: str) -> list:
    for attempt in range(RETRY):
        for url in OVERPASS_URLS:
            try:
                resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=180)
                if resp.ok:
                    return resp.json().get("elements", [])
                print(f"    HTTP {resp.status_code} ({url})")
            except requests.RequestException as e:
                print(f"    Error ({url}): {e}")
        if attempt < RETRY - 1:
            wait = 5 * (attempt + 1)
            print(f"    Reintentando en {wait}s...")
            time.sleep(wait)
    raise RuntimeError("Todas las instancias Overpass fallaron")


def fetch_relation(relation_id: str) -> tuple[dict | None, dict]:
    """
    Devuelve (relation_element, nodes_by_id).
    - relation_element: objeto con members + geometría inline de ways
    - nodes_by_id: {node_id_str: element} con tags completos de todos los nodos miembro
    """
    query = f"""[out:json][timeout:120];
relation({relation_id})->.rel;
(
  .rel;
  node(r.rel);
);
out geom;"""
    elements = _overpass(query)

    relation  = None
    nodes     = {}
    for el in elements:
        if el["type"] == "relation" and str(el["id"]) == relation_id:
            relation = el
        elif el["type"] == "node":
            nodes[str(el["id"])] = el

    return relation, nodes


# ── Geometría ─────────────────────────────────────────────────────────────────

def _dist_m(a: list, b: list) -> float:
    dlat = a[0] - b[0]
    dlon = (a[1] - b[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.sqrt(dlat ** 2 + dlon ** 2) * 111_320


def stitch_ways(members: list) -> list:
    """Ensambla los way members en un polyline continuo."""
    ways = [m for m in members if m.get("type") == "way" and m.get("geometry")]
    if not ways:
        return []

    coords = [[p["lat"], p["lon"]] for p in ways[0]["geometry"]]

    for way in ways[1:]:
        pts = [[p["lat"], p["lon"]] for p in way["geometry"]]
        if not pts:
            continue

        # Elegir orientación que minimiza la brecha con el punto final actual
        if _dist_m(coords[-1], pts[-1]) < _dist_m(coords[-1], pts[0]):
            pts = pts[::-1]

        # Omitir primer punto si es el mismo junction (evitar duplicado)
        skip = 1 if _dist_m(coords[-1], pts[0]) < SNAP_M else 0
        coords.extend(pts[skip:])

    return coords


# ── Paradas ───────────────────────────────────────────────────────────────────

def build_stops(members: list, nodes_by_id: dict) -> list:
    """
    Extrae paradas en orden de aparición en la relación.
    Incluye id (OSM node ID), name, ref (código oficial si existe), lat, lng.

    Deduplicación: si un nodo platform cae a menos de DEDUP_M metros de un
    stop_position ya incluido, se descarta (son la misma parada física).
    stop_position tiene prioridad por estar sobre la calzada.
    """
    # Primer pasada: recolectar todos los candidatos con su rol
    candidates = []
    seen_ids = set()
    for m in members:
        if m.get("type") != "node":
            continue
        role = m.get("role", "")
        if role not in STOP_ROLES:
            continue
        node_id = str(m["ref"])
        if node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        lat = m.get("lat")
        lon = m.get("lon")
        if lat is None or lon is None:
            continue
        tags = nodes_by_id.get(node_id, {}).get("tags", {})
        candidates.append({
            "id":       f"n{node_id}",
            "lat":      lat,
            "lng":      lon,
            "name":     tags.get("name", ""),
            "ref":      tags.get("ref", ""),
            "is_platform": role in PLATFORM_ROLES,
        })

    # Segunda pasada: descartar platforms duplicadas de stop_positions cercanas
    stop_positions = [[c["lat"], c["lng"]] for c in candidates if not c["is_platform"]]

    stops = []
    for c in candidates:
        if c["is_platform"]:
            pt = [c["lat"], c["lng"]]
            if any(_dist_m(pt, sp) < DEDUP_M for sp in stop_positions):
                continue  # duplicado de un stop_position cercano
        stop = {"id": c["id"], "lat": c["lat"], "lng": c["lng"]}
        if c["name"]:
            stop["name"] = c["name"]
        if c["ref"]:
            stop["ref"] = c["ref"]
        stops.append(stop)

    return stops


# ── Main ──────────────────────────────────────────────────────────────────────

def normalise_colour(raw: str) -> str:
    return raw.lstrip("#").lower() if raw else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lines", nargs="+", required=True,
                        help="Números de línea (ej: 39 42) o 'all'")
    parser.add_argument("--output", default=DEFAULT_OUT,
                        help=f"Archivo de salida (default: {DEFAULT_OUT})")
    args = parser.parse_args()

    with open(MASTER_FILE, encoding="utf-8") as f:
        master = json.load(f)

    if args.lines == ["all"]:
        target_lines = None
    else:
        target_lines = {int(x) for x in args.lines}

    selected = [e for e in master
                if target_lines is None or e["line_number"] in target_lines]

    if not selected:
        print("No se encontraron relaciones para las líneas pedidas.")
        return

    line_set = sorted({e["line_number"] for e in selected})
    print(f"Procesando {len(selected)} relaciones — líneas: {line_set}\n")

    output = {}

    for i, entry in enumerate(selected, 1):
        rel_id     = entry["relation_id"]
        line_num   = str(entry["line_number"])
        name       = entry.get("name", "")
        short_name = entry.get("official_ref") or entry.get("ref", line_num)
        colour     = normalise_colour(entry.get("colour", ""))

        print(f"  [{i}/{len(selected)}] rel {rel_id}  {line_num} — {short_name}")

        try:
            relation, nodes_by_id = fetch_relation(rel_id)
        except RuntimeError as e:
            print(f"    SKIP: {e}")
            continue

        if not relation:
            print(f"    SKIP: relación {rel_id} no encontrada en respuesta Overpass")
            continue

        members = relation.get("members", [])
        points  = stitch_ways(members)
        stops   = build_stops(members, nodes_by_id)

        n_stops_with_name = sum(1 for s in stops if s.get("name"))
        n_stops_with_ref  = sum(1 for s in stops if s.get("ref"))
        print(f"    {len(points)} puntos | {len(stops)} paradas "
              f"({n_stops_with_name} con nombre, {n_stops_with_ref} con ref)")

        ramal = {
            "name":      name,
            "shortName": short_name,
            "shapeId":   rel_id,
            "points":    points,
            "stops":     stops,
        }

        if line_num not in output:
            output[line_num] = {"color": colour, "ramales": []}
        output[line_num]["ramales"].append(ramal)

        time.sleep(0.5)

    print("\nResumen final:")
    for ln, data in sorted(output.items(), key=lambda x: int(x[0])):
        total_pts   = sum(len(r["points"]) for r in data["ramales"])
        total_stops = sum(len(r["stops"])  for r in data["ramales"])
        print(f"  Línea {ln}: {len(data['ramales'])} ramales, "
              f"{total_pts} pts, {total_stops} paradas")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    size_kb = os.path.getsize(args.output) / 1024
    print(f"\nGuardado: {args.output}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
