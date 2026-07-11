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


def load_label_line_data(path: str | Path) -> dict:
    """Carga LABEL_LINE_MAP.json (schema v2, keyed por línea) sin resolver vigencias."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "lines" not in data:
        raise ValueError(
            f"{path}: schema v1 detectado; migrar con scripts/migrate_label_line_map_v2.py"
        )
    return data


def resolve_label_line_index(
    data: dict, on_date: str | None = None
) -> dict[str, dict]:
    """
    Invierte el schema v2 a {sufijo → {line, agencyId, agencyName}}.

    on_date: fecha "YYYY-MM-DD" para resolver vigencias (from/to inclusive).
      - None: incluye todo sufijo alguna vez vigente (unión de períodos);
        si un sufijo tuvo varias asignaciones gana la de `from` más reciente.
      - Con fecha: solo sufijos vigentes ese día (to=null cuenta como vigente).
        Usar la fecha del archivo NDJSON al procesar grabaciones históricas.
    """
    result: dict[str, dict] = {}
    latest_from: dict[str, str] = {}
    for line, entry in data["lines"].items():
        agency_by_id = {a["agencyId"]: a for a in entry.get("agencies", [])}
        for s in entry["suffixes"]:
            if on_date is not None:
                if s["from"] > on_date:
                    continue
                if s["to"] is not None and s["to"] < on_date:
                    continue
            suffix = s["suffix"]
            if suffix not in result or s["from"] >= latest_from[suffix]:
                agency = agency_by_id.get(s.get("agencyId"), {})
                result[suffix] = {
                    "line": line,
                    "agencyId": agency.get("agencyId"),
                    "agencyName": agency.get("agencyName"),
                }
                latest_from[suffix] = s["from"]
    return result


def resolve_label_line_map(data: dict, on_date: str | None = None) -> dict[str, str]:
    """Como resolve_label_line_index pero retorna solo {sufijo → line_number}."""
    return {sfx: info["line"] for sfx, info in resolve_label_line_index(data, on_date).items()}


def load_label_line_map(path: str | Path, on_date: str | None = None) -> dict[str, str]:
    """
    Carga LABEL_LINE_MAP.json (schema v2) y retorna {sufijo_label → line_number}.

    El sufijo es la parte numérica al final del VP_label (ej: "5-1350" → "1350").
    Los sufijos ambiguos viven en CANDIDATES.json y no entran acá.
    Ver resolve_label_line_index para la semántica de on_date; en loops
    multi-día conviene load_label_line_data una vez y resolver por fecha.
    """
    return resolve_label_line_map(load_label_line_data(path), on_date)


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
