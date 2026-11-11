"""
Coordenadas geográficas de P (coche) y T (punto objetivo) para el CityGridEncoder (experimento E1c).

El parquet v2 no guarda lat/lon, pero sí `shape_id`, `dist_along_m` y `dist_remaining_m`. Con el recorrido
(proyectoconsola/data/line_shapes/{N}.json) se interpola lat/lon en dist_along_m (P, el coche proyectado sobre el
shape) y en dist_along_m + dist_remaining_m (T, el punto objetivo). La distancia acumulada usa la misma fórmula
(ángulo pequeño) que `ShapeIndex`, así que es consistente con la que generó dist_along_m.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_M_PER_DEG_LAT = 111_320.0


class ShapeGeo:
    """Un recorrido: puntos (lat, lon) y distancia acumulada en metros."""

    def __init__(self, points):
        pts = np.asarray(points, dtype=np.float64)
        lat_mid = (pts[:-1, 0] + pts[1:, 0]) / 2.0
        dy = (pts[1:, 0] - pts[:-1, 0]) * _M_PER_DEG_LAT
        dx = (pts[1:, 1] - pts[:-1, 1]) * _M_PER_DEG_LAT * np.cos(np.radians(lat_mid))
        self.lat = pts[:, 0]
        self.lon = pts[:, 1]
        self.cum = np.concatenate([[0.0], np.cumsum(np.sqrt(dx * dx + dy * dy))])

    @property
    def length_m(self) -> float:
        return float(self.cum[-1])

    def latlon_at(self, dist_m) -> tuple[np.ndarray, np.ndarray]:
        """Lat/lon en `dist_m` metros sobre el recorrido (se satura en los extremos)."""
        d = np.asarray(dist_m, dtype=np.float64)
        return np.interp(d, self.cum, self.lat), np.interp(d, self.cum, self.lon)


class ShapeGeoStore:
    """Carga perezosa de recorridos por (línea, shape_id). Barata de serializar (cache vacío al pickle)."""

    def __init__(self, shapes_dir: Path | str | None = None):
        if shapes_dir is None:
            from prediccion.v2.shapes import DEFAULT_LINE_SHAPES_DIR
            shapes_dir = DEFAULT_LINE_SHAPES_DIR
        self.dir = Path(shapes_dir)
        self._cache: dict[str, dict[str, ShapeGeo]] = {}

    def __getstate__(self):
        return {"dir": self.dir, "_cache": {}}

    def shapes_of(self, line: str) -> dict[str, ShapeGeo]:
        if line not in self._cache:
            out: dict[str, ShapeGeo] = {}
            p = self.dir / f"{line}.json"
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                for r in data.get("ramales", []):
                    sid, pts = r.get("shapeId"), r.get("points", [])
                    if sid is not None and len(pts) >= 2:
                        out[str(sid)] = ShapeGeo(pts)
            self._cache[line] = out
        return self._cache[line]

    def get(self, line: str, shape_id: str) -> ShapeGeo | None:
        return self.shapes_of(str(line)).get(str(shape_id))


def geo_coords(lines, shape_ids, dist_along_m, dist_remaining_m, store: ShapeGeoStore) -> np.ndarray:
    """
    (N, 4) float32 con [lat_P, lon_P, lat_T, lon_T]. Las filas cuyo shape no se encuentra quedan en NaN
    (el llamador decide qué hacer; el dataset las descarta).
    """
    n = len(shape_ids)
    out = np.full((n, 4), np.nan, dtype=np.float64)
    d0 = np.asarray(dist_along_m, dtype=np.float64)
    d1 = d0 + np.asarray(dist_remaining_m, dtype=np.float64)
    keys = np.array([f"{ln}\x00{sid}" for ln, sid in zip(lines, shape_ids)], dtype=object)
    for key in set(keys.tolist()):
        ln, sid = key.split("\x00")
        sg = store.get(ln, sid)
        if sg is None:
            continue
        m = keys == key
        out[m, 0], out[m, 1] = sg.latlon_at(d0[m])
        out[m, 2], out[m, 3] = sg.latlon_at(d1[m])
    return out.astype(np.float32)
