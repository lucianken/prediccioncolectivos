#!/usr/bin/env python
"""
visualizar_fraccionados.py — Mapa Leaflet de GPS de fraccionados d0.

Genera un HTML interactivo con Leaflet mostrando:
  - Shapes de los completos A, B, C (línea gris discontinua)
  - Shapes de los fraccionados D, E, F (línea de color)
  - Puntos GPS reales del día indicado para route_ids de D, E, F
  - Marcadores en el inicio de cada shape y en el primer GPS de cada viaje

Uso:
  python ramal_lookup/visualizar_fraccionados.py --data-dir Z:\\grabaciones --day 2026-04-02
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from prediccion.pipeline.reader import reconstruct_snapshots
from prediccion.pipeline.segmenter import segment_vehicle_history
from prediccion.pipeline.shapes_io import load_label_line_map, load_shapes
from ramal_lookup.route_lookup import build_shape_entries, load_families

LINE = "39"
INTERVAL_S = 30

FRACCIONADOS_D0 = {
    "1338": {"name": "39D", "color": "#e74c3c"},
    "1339": {"name": "39E", "color": "#f39c12"},
    "1340": {"name": "39F", "color": "#8e44ad"},
}
COMPLETOS_COLOR = "#aab7b8"
COMPLETOS_NAMES = {"39A", "39B", "39C"}


def load_gps(fp: Path, rids: set, label_line_map: dict) -> dict[str, list]:
    vehicle_obs: dict[str, list] = defaultdict(list)
    for ts, state in reconstruct_snapshots(fp, interval_s=INTERVAL_S):
        for vid, fields in state.items():
            obs = dict(fields)
            obs["ts"] = obs.get("ts", ts)
            suffix = obs.get("label", "").split("-")[-1]
            if label_line_map.get(suffix) != LINE:
                continue
            vehicle_obs[vid].append(obs)

    points: dict[str, list] = defaultdict(list)
    for vid, observations in vehicle_obs.items():
        observations.sort(key=lambda o: o["ts"])
        for trip in segment_vehicle_history(vid, observations):
            if trip.route_id not in rids:
                continue
            for pt in trip.points:
                points[trip.route_id].append((pt.lat, pt.lon, pt.ts))
    return points


def split_trips(pts: list, gap_s: int = 600) -> list[list]:
    if not pts:
        return []
    trips, cur = [], [pts[0]]
    for p in pts[1:]:
        if p[2] - cur[-1][2] > gap_s:
            trips.append(cur)
            cur = [p]
        else:
            cur.append(p)
    trips.append(cur)
    return trips


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--day", type=str, default="2026-04-02")
    parser.add_argument("--shapes", type=Path,
        default=Path(__file__).parent.parent / "prediccion" / "data" / "line_shapes.json")
    parser.add_argument("--families", type=Path,
        default=Path(__file__).parent / "families_39.json")
    parser.add_argument("--label-map", type=Path,
        default=Path(__file__).parent.parent / "LABEL_LINE_MAP.json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    shapes_data = load_shapes(str(args.shapes))
    families = load_families(args.families)
    entries = build_shape_entries(shapes_data, LINE, families)
    label_line_map = load_label_line_map(str(args.label_map))

    fp = args.data_dir / f"{args.day}.ndjson.gz"
    if not fp.exists():
        print(f"ERROR: no existe {fp}", file=sys.stderr)
        sys.exit(1)

    print(f"Leyendo {fp.name}...")
    gps = load_gps(fp, set(FRACCIONADOS_D0.keys()), label_line_map)
    for rid, info in FRACCIONADOS_D0.items():
        print(f"  {rid} ({info['name']}): {len(gps.get(rid, []))} pts")

    # ── Construir objetos JS ──────────────────────────────────────────────────

    layers_js = []

    # Shapes completos d0 (gris discontinuo, detrás)
    for e in entries:
        if e.direction != 0 or e.short_name not in COMPLETOS_NAMES:
            continue
        coords = [[float(p[0]), float(p[1])] for p in e.index._pts]
        layers_js.append(f"""
    L.polyline({json.dumps(coords)}, {{
        color: '{COMPLETOS_COLOR}', weight: 2, opacity: 0.6,
        dashArray: '6 4',
    }}).bindTooltip('{e.key} — {e.index.total_length_m/1000:.1f}km (completo)').addTo(map);
    L.circleMarker({json.dumps(coords[0])}, {{
        radius: 5, color: '{COMPLETOS_COLOR}', fillColor: '{COMPLETOS_COLOR}',
        fillOpacity: 1, weight: 2,
    }}).bindTooltip('INICIO SHAPE {e.key}').addTo(map);""")

    # Shapes fraccionados d0 (color, encima)
    frac_entries = {e.short_name: e for e in entries if e.direction == 0 and e.is_fraccionado}
    for rid, info in FRACCIONADOS_D0.items():
        sname = info["name"]
        color = info["color"]
        e = frac_entries.get(sname)
        if not e:
            continue
        coords = [[float(p[0]), float(p[1])] for p in e.index._pts]
        layers_js.append(f"""
    L.polyline({json.dumps(coords)}, {{
        color: '{color}', weight: 4, opacity: 0.8,
    }}).bindTooltip('{e.key} — {e.index.total_length_m/1000:.1f}km').addTo(map);
    L.circleMarker({json.dumps(coords[0])}, {{
        radius: 8, color: '{color}', fillColor: '{color}',
        fillOpacity: 1, weight: 2,
    }}).bindTooltip('INICIO SHAPE {e.key}').addTo(map);""")

    # GPS de fraccionados
    for rid, info in FRACCIONADOS_D0.items():
        color = info["color"]
        sname = info["name"]
        pts = gps.get(rid, [])
        if not pts:
            continue
        trips = split_trips(pts)
        for i, trip in enumerate(trips):
            coords = [[p[0], p[1]] for p in trip]
            layers_js.append(f"""
    L.polyline({json.dumps(coords)}, {{
        color: '{color}', weight: 2, opacity: 0.45,
    }}).bindTooltip('{rid} {sname} viaje {i+1} ({len(coords)} pts)').addTo(map);""")
            # Primer punto del viaje (círculo blanco con borde de color)
            first = [trip[0][0], trip[0][1]]
            layers_js.append(f"""
    L.circleMarker({json.dumps(first)}, {{
        radius: 6, color: '{color}', fillColor: 'white',
        fillOpacity: 1, weight: 2.5,
    }}).bindTooltip('PRIMER GPS {rid} {sname} viaje {i+1}').addTo(map);""")

    # Centro del mapa
    all_lats = [p[0] for pts in gps.values() for p in pts]
    all_lons = [p[1] for pts in gps.values() for p in pts]
    if all_lats:
        clat = sum(all_lats) / len(all_lats)
        clon = sum(all_lons) / len(all_lons)
    else:
        clat, clon = -34.62, -58.41

    layers_code = "\n".join(layers_js)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Fraccionados d0 — {args.day}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body {{ margin:0; padding:0; height:100%; }}
  #map {{ height:100vh; }}
  .legend {{
    background: white; padding: 12px 16px; border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,.25); font: 13px/1.6 sans-serif; line-height: 1.8;
  }}
  .swatch {{ display:inline-block; width:28px; height:4px; vertical-align:middle; margin-right:6px; border-radius:2px; }}
  .swatch-dash {{ background: repeating-linear-gradient(90deg,{COMPLETOS_COLOR} 0 6px,transparent 6px 10px); }}
</style>
</head>
<body>
<div id="map"></div>
<script>
var map = L.map('map').setView([{clat:.5f}, {clon:.5f}], 13);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: 'abcd', maxZoom: 20
}}).addTo(map);

{layers_code}

var legend = L.control({{position: 'bottomleft'}});
legend.onAdd = function() {{
    var d = L.DomUtil.create('div', 'legend');
    d.innerHTML = `
      <b>Línea 39 — dirección 0 (vuelta) — {args.day}</b><br>
      <span class="swatch swatch-dash"></span> shapes completos A / B / C<br>
      <span class="swatch" style="background:#e74c3c;height:4px"></span> shape D + GPS 1338<br>
      <span class="swatch" style="background:#f39c12;height:4px"></span> shape E + GPS 1339<br>
      <span class="swatch" style="background:#8e44ad;height:4px"></span> shape F + GPS 1340<br>
      <br>
      ● inicio del shape &nbsp;&nbsp; ◎ primer GPS de cada viaje
    `;
    return d;
}};
legend.addTo(map);
</script>
</body>
</html>"""

    out = args.output or Path(__file__).parent / f"fraccionados_d0_{args.day}.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nMapa guardado: {out}")


if __name__ == "__main__":
    main()
