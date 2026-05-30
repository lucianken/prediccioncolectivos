"""Helpers de I/O para line_shapes.json y LABEL_LINE_MAP.json."""

import json
import urllib.request
from pathlib import Path

DEFAULT_SHAPES_PATH: Path = Path(__file__).parent.parent / "data" / "line_shapes.json"


def load_shapes(shapes_url: str) -> dict:
    """Carga shapes desde URL HTTP/HTTPS o path local JSON."""
    if shapes_url.startswith("http://") or shapes_url.startswith("https://"):
        with urllib.request.urlopen(shapes_url, timeout=30) as resp:
            return json.loads(resp.read())
    else:
        with open(shapes_url, encoding="utf-8") as f:
            return json.load(f)


def load_label_line_map(path: str | Path) -> dict[str, str]:
    """
    Carga LABEL_LINE_MAP.json y retorna {sufijo_label → line_number}.

    El sufijo es la parte numérica al final del VP_label (ej: "5-1350" → "1350").
    Solo incluye entradas con línea única. Las multi-línea se ignoran
    porque no se puede resolver a qué línea pertenece el vehículo.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    result: dict[str, str] = {}
    for suffix, info in data.get("map", {}).items():
        line = info.get("line")  # None para entradas multi-línea
        if line:
            result[suffix] = line
    return result


def build_label_line_map(shapes: dict) -> dict[str, str]:
    """
    Fallback: mapa {shortName → line_number} desde shapes.
    Usar load_label_line_map(LABEL_LINE_MAP.json) cuando esté disponible.
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
