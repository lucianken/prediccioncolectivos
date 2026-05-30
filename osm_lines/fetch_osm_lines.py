#!/usr/bin/env python3
"""
Genera osm_lines.json — archivo maestro de relaciones OSM de colectivos AMBA.

Consulta Overpass por todas las relaciones route=bus en el bbox AMBA y guarda
todos los tags relevantes. Cada entrada es una relación (= un ramal/recorrido).

Uso:
    python fetch_osm_lines.py             # genera desde cero
    python fetch_osm_lines.py --update    # refresca tags OSM, preserva campos extra
"""

import argparse
import json
import os
import re

import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "osm_lines.json")
HEADERS = {"User-Agent": "DondeestaelbondiOSM/1.0 (lucianken@gmail.com)"}

# Bbox CABA + GBA próximo — captura todas las líneas CABA (sus recorridos pasan por acá)
BBOX = "-34.80,-58.60,-34.45,-58.25"

# Líneas de jurisdicción CABA/Nacional conocidas
CABA_LINES = {
    1, 2, 4, 7, 8, 9, 10, 12, 15, 17, 19, 20, 21, 22, 24, 25, 26, 28, 29,
    31, 32, 33, 34, 37, 39, 41, 42, 44, 45, 46, 47, 49, 50, 51, 53, 55, 56,
    57, 59, 60, 61, 62, 63, 64, 65, 67, 68, 70, 71, 74, 76, 78, 79, 80, 84,
    85, 86, 87, 88, 91, 92, 93, 95, 96, 97, 98, 100, 101, 102, 103, 105, 106,
    107, 108, 109, 110, 111, 113, 114, 115, 117, 118, 119, 123, 124, 126, 127,
    128, 129, 130, 132, 133, 134, 135, 136, 140, 143, 145, 146, 150, 151, 152,
    153, 154, 158, 159, 160, 161, 163, 164, 166, 168, 169, 172, 174, 176, 177,
    178, 179, 180, 181, 182, 184, 185, 188, 193, 194, 195, 197,
}

# Tags OSM a extraer (en orden de salida)
OSM_TAGS = [
    "ref",
    "official_ref",
    "name",
    "description",
    "from",
    "to",
    "via",
    "operator",
    "network",
    "colour",
    "trip_headsign",
    "public_transport:version",
    "roundtrip",
    "website",
]


def extract_line_number(ref: str):
    if not ref:
        return None
    m = re.match(r"^(\d+)", ref.strip())
    if m:
        n = int(m.group(1))
        return n if n in CABA_LINES else None
    return None


def fetch_relations() -> list:
    query = f"""[out:json][timeout:240];
(
  relation["route"="bus"]({BBOX});
);
out tags;"""
    print(f"Consultando Overpass (bbox {BBOX})...")
    for url in OVERPASS_URLS:
        print(f"  → {url}")
        resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=300)
        if resp.ok:
            elements = resp.json().get("elements", [])
            print(f"  Relaciones recibidas: {len(elements)}")
            return elements
        print(f"  HTTP {resp.status_code}, probando siguiente instancia...")
    raise RuntimeError(f"Todas las instancias Overpass fallaron. Último status: {resp.status_code}")


def build_entry(el: dict) -> dict | None:
    tags = el.get("tags", {})
    ref  = tags.get("ref", "")
    line_number = extract_line_number(ref)
    if line_number is None:
        return None

    entry = {
        "relation_id": str(el["id"]),
        "line_number":  line_number,
    }
    for tag in OSM_TAGS:
        # colour/color: normalizar a "colour"
        val = tags.get(tag) or (tags.get("color") if tag == "colour" else None)
        if val:
            entry[tag] = val

    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update", action="store_true",
        help="Refresca tags OSM pero preserva campos extra ya en el JSON",
    )
    args = parser.parse_args()

    existing_by_id: dict[str, dict] = {}
    if args.update and os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            for row in json.load(f):
                existing_by_id[row["relation_id"]] = row
        print(f"JSON existente cargado: {len(existing_by_id)} entradas")

    elements = fetch_relations()

    entries = []
    skipped = 0
    for el in elements:
        entry = build_entry(el)
        if entry is None:
            skipped += 1
            continue

        if args.update and entry["relation_id"] in existing_by_id:
            old = existing_by_id[entry["relation_id"]]
            # Tags frescos de OSM dominan; campos extra manuales se preservan
            merged = {**old, **entry}
            entry = merged

        entries.append(entry)

    entries.sort(key=lambda e: (e["line_number"], e.get("ref", "")))

    # Resumen por línea
    by_line: dict[int, int] = {}
    for e in entries:
        by_line[e["line_number"]] = by_line.get(e["line_number"], 0) + 1

    print(f"\nIncluidas: {len(entries)} relaciones | Descartadas (fuera de rango): {skipped}")
    print(f"Líneas únicas: {len(by_line)}")
    for ln in sorted(by_line):
        print(f"  Línea {ln:>3}: {by_line[ln]} relaciones")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\nGuardado: {OUTPUT_FILE}  ({size_kb:.1f} KB, {len(entries)} entradas)")


if __name__ == "__main__":
    main()
