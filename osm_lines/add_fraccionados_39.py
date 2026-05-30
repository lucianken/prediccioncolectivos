#!/usr/bin/env python3
"""
Agrega fraccionados D/E/F a la línea 39 en line_shapes.json.

D = fraccionado de A (vía Córdoba):      Chacarita ↔ Constitución
E = fraccionado de B (vía Colegiales):   Chacarita ↔ Constitución
F = fraccionado de C (vía Palermo Viejo): Chacarita ↔ Constitución

El corte es en la parada Plaza Constitución. Se truncan tanto los puntos
de geometría como las paradas.
"""

import json
import math
import os

SHAPES_FILE = os.path.join(
    os.path.dirname(__file__), "..", "prediccion", "data", "line_shapes.json"
)

# Mapeo: (shapeId_base, shortName_fraccionado, sentido)
# sentido: "desde_const" = Constitución→Chacarita (viene de Barracas→Chacarita)
#          "hasta_const" = Chacarita→Constitución  (viene de Chacarita→Barracas)
FRACCIONADOS = [
    ("382202", "39D", "desde_const"),  # A Barracas→Chacarita  → D Constitución→Chacarita
    ("382203", "39D", "hasta_const"),  # A Chacarita→Barracas  → D Chacarita→Constitución
    ("382208", "39E", "desde_const"),  # B Barracas→Chacarita  → E Constitución→Chacarita
    ("382209", "39E", "hasta_const"),  # B Chacarita→Barracas  → E Chacarita→Constitución
    ("382210", "39F", "desde_const"),  # C Barracas→Chacarita  → F Constitución→Chacarita
    ("382211", "39F", "hasta_const"),  # C Chacarita→Barracas  → F Chacarita→Constitución
]

# Nodo OSM de Plaza Constitución (distinto según sentido porque el colectivo
# para en lados distintos de la plaza)
CONST_NODE_DESDE = "n1493476757"   # en ramales Barracas→Chacarita (stop[7])
CONST_NODE_HASTA = "n5930603147"   # en ramales Chacarita→Barracas


def _dist_m(a, b):
    dlat = a[0] - b[0]
    dlon = (a[1] - b[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.sqrt(dlat**2 + dlon**2) * 111_320


def closest_point_idx(points, lat, lng):
    """Índice del punto en la geometría más cercano a (lat, lng)."""
    best_i, best_d = 0, float("inf")
    for i, (plat, plng) in enumerate(points):
        d = _dist_m([plat, plng], [lat, lng])
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def make_fraccionado(base_ramal, short_name, sentido):
    stops  = base_ramal["stops"]
    points = base_ramal["points"]

    const_node = CONST_NODE_DESDE if sentido == "desde_const" else CONST_NODE_HASTA

    # Encontrar índice de la parada de Constitución
    stop_idx = next(
        (i for i, s in enumerate(stops) if s["id"] == const_node), None
    )
    if stop_idx is None:
        raise ValueError(
            f"No se encontró nodo {const_node} en ramal {base_ramal['shapeId']}"
        )

    const_stop = stops[stop_idx]
    pt_idx = closest_point_idx(points, const_stop["lat"], const_stop["lng"])

    if sentido == "desde_const":
        # Constitución → Chacarita: desde el corte hasta el final
        new_stops  = stops[stop_idx:]
        new_points = points[pt_idx:]
        base_name  = base_ramal["name"]
        # Reemplazar origen (Barracas) por Constitución en el nombre
        new_name = base_name.replace("Barracas →", "Constitución →").replace(
            "Barracas ", "Constitución "
        )
    else:
        # Chacarita → Constitución: desde el inicio hasta el corte (inclusive)
        new_stops  = stops[: stop_idx + 1]
        new_points = points[: pt_idx + 1]
        base_name  = base_ramal["name"]
        new_name = base_name.replace("→ Barracas", "→ Constitución").replace(
            " Barracas", " Constitución"
        )

    return {
        "name":      new_name,
        "shortName": short_name,
        "shapeId":   f"frac_{base_ramal['shapeId']}",
        "points":    new_points,
        "stops":     new_stops,
    }


def main():
    with open(SHAPES_FILE, encoding="utf-8") as f:
        shapes = json.load(f)

    line = shapes["39"]

    # Índice de ramales por shapeId
    by_shape_id = {r["shapeId"]: r for r in line["ramales"]}

    # Eliminar fraccionados previos si se vuelve a correr
    line["ramales"] = [r for r in line["ramales"] if not r["shapeId"].startswith("frac_")]

    nuevos = []
    for base_id, short_name, sentido in FRACCIONADOS:
        base = by_shape_id.get(base_id)
        if not base:
            print(f"  SKIP: shapeId {base_id} no encontrado")
            continue
        frac = make_fraccionado(base, short_name, sentido)
        nuevos.append(frac)
        print(
            f"  {frac['shapeId']}  {short_name}  {sentido}  "
            f"{len(frac['points'])} pts  {len(frac['stops'])} paradas"
        )

    line["ramales"].extend(nuevos)

    with open(SHAPES_FILE, "w", encoding="utf-8") as f:
        json.dump(shapes, f, ensure_ascii=False)

    size_kb = os.path.getsize(SHAPES_FILE) / 1024
    print(f"\nGuardado: {SHAPES_FILE}  ({size_kb:.1f} KB)")
    print(f"Línea 39 ahora tiene {len(line['ramales'])} ramales")


if __name__ == "__main__":
    main()
