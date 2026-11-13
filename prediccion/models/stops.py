"""
Paradas por recorrido (ARQUITECTURA.md §6.2, "Paradas por tramo").

Fuente: `ramales[].stops` de proyectoconsola/data/line_shapes/{N}.json, el mismo archivo y la misma entrada de ramal
de la que salen los puntos del shape (la asociación parada-shape es la del ramal; no hay emparejamiento por nombre ni
por distancia). Cada parada se proyecta sobre su shape con la fórmula de ángulo pequeño de ShapeIndex y queda como
metros desde el inicio del shape, ordenados y redondeados a 2 decimales (`STOP_DECIMALS`). Esos metros son lo que viaja
en el export (`lines/<línea>.json`, clave `stops_m` de cada shape) y lo único que usa la app.

Features por tramo [lo, hi) (metros desde el inicio del shape, ya recortado a P->T):
  conteo   cantidad de paradas con lo <= parada < hi
  próxima  metros desde `lo` hasta la primera parada >= lo, topeados en STOP_NEXT_CAP_M (sin parada: el tope)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

STOP_DECIMALS = 2
STOP_NEXT_CAP_M = 1000.0
_M_PER_DEG_LAT = 111_320.0


def project_stops(points, stops) -> list[float]:
    """Metros desde el inicio del shape de cada parada ({lat, lng}), ordenados y redondeados."""
    from prediccion.pipeline.projector import ShapeIndex
    if not stops:
        return []
    si = ShapeIndex([tuple(p) for p in points])
    d = [si.project(float(s["lat"]), float(s["lng"]))[0] for s in stops]
    return [round(float(x), STOP_DECIMALS) for x in sorted(d)]


def load_shape_stops(lines, shapes_dir=None) -> dict[str, list[float]]:
    """{shape_id: metros de las paradas} de las líneas dadas (mismos shapes que load_shape_points)."""
    from prediccion.v2.shapes import DEFAULT_LINE_SHAPES_DIR
    d = Path(shapes_dir or DEFAULT_LINE_SHAPES_DIR)
    out: dict[str, list[float]] = {}
    for ln in lines:
        p = d / f"{ln}.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for r in data.get("ramales", []):
            sid, pts = r.get("shapeId"), r.get("points", [])
            if sid is None or len(pts) < 2:
                continue
            out[str(sid)] = project_stops(pts, r.get("stops", []))
    return out


def stop_features_np(stops_m, lo, hi) -> tuple[np.ndarray, np.ndarray]:
    """(conteo, próxima) por tramo para un shape; `stops_m` ordenado, `lo`/`hi` arrays (N,). Referencia del cliente."""
    s = np.asarray(stops_m, dtype=np.float64)
    lo = np.asarray(lo, dtype=np.float64)
    hi = np.asarray(hi, dtype=np.float64)
    i0 = np.searchsorted(s, lo, side="left")
    i1 = np.searchsorted(s, hi, side="left")
    count = (i1 - i0).astype(np.float64)
    if len(s) == 0:
        return count, np.full(lo.shape, STOP_NEXT_CAP_M)
    nxt = np.where(i0 < len(s), s[np.minimum(i0, len(s) - 1)] - lo, STOP_NEXT_CAP_M)
    return count, np.minimum(nxt, STOP_NEXT_CAP_M)
