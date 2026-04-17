"""Helpers de I/O para line_shapes.json: carga desde URL o path local, helpers de lookup."""

import json
import urllib.request
from pathlib import Path

# Path canónico al JSON de shapes incluido en el paquete prediccion.
# Todos los entrypoints (serve.py, train.py, build_dataset.py, validate_projection.py)
# lo usan como default; definirlo aquí evita calcularlo desde __file__ en cada uno.
DEFAULT_SHAPES_PATH: Path = Path(__file__).parent.parent / "data" / "line_shapes.json"


def load_shapes(shapes_url: str) -> dict:
    """Carga shapes desde URL HTTP/HTTPS o path local JSON."""
    if shapes_url.startswith("http://") or shapes_url.startswith("https://"):
        with urllib.request.urlopen(shapes_url, timeout=30) as resp:
            return json.loads(resp.read())
    else:
        with open(shapes_url, encoding="utf-8") as f:
            return json.load(f)


def build_label_line_map(shapes: dict) -> dict[str, str]:
    """
    Construye un mapa {label → line_number} desde el JSON de shapes.

    Para cada línea incluye:
      - la propia clave numérica: "39" → "39"
      - los shortName de cada ramal: "39R" → "39"

    Usado por build_dataset y validate_projection para resolver route_id/label
    al número de línea canónico.
    """
    label_line_map: dict[str, str] = {}
    for line_num, line_data in shapes.items():
        label_line_map[line_num] = line_num
        for ramal in line_data.get("ramales", []):
            short_name = ramal.get("shortName", line_num)
            label_line_map[short_name] = line_num
    return label_line_map


def get_shape_points(
    shapes: dict,
    line: str,
    direction: int,
) -> list[tuple[float, float]] | None:
    """
    Extrae la lista de puntos (lat, lon) del shape para una línea y dirección.
    Retorna None si no existe.
    """
    if line not in shapes:
        return None
    for ramal in shapes[line].get("ramales", []):
        if ramal.get("direction") == direction:
            return [tuple(p) for p in ramal["points"]]
    return None
