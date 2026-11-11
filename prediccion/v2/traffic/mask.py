"""Máscara de celdas por donde pasa algún recorrido + puntos densos de recorrido (para el descarte de depósito)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from prediccion.v2.traffic.grid import GridSpec, cell_index, _M_PER_DEG

DENSIFY_M = 25.0   # paso de muestreo a lo largo de cada segmento (celda = 500 m: no se saltea ninguna)


def densify(points, step_m: float = DENSIFY_M) -> np.ndarray:
    """Polilínea [(lat, lon), ...] -> array (n, 2) con puntos cada <= step_m a lo largo de cada segmento."""
    p = np.asarray(points, dtype=np.float64)
    if len(p) < 2:
        return p.reshape(-1, 2)
    cos = math.cos(math.radians(float(p[:, 0].mean())))
    out = [p[:1]]
    for a, b in zip(p[:-1], p[1:]):
        d = math.hypot((b[0] - a[0]) * _M_PER_DEG, (b[1] - a[1]) * _M_PER_DEG * cos)
        k = max(1, math.ceil(d / step_m))
        t = np.linspace(0.0, 1.0, k + 1)[1:, None]
        out.append(a + (b - a) * t)
    return np.concatenate(out)


def cells_of_polylines(grid: GridSpec, polylines) -> np.ndarray:
    """Celdas (ids únicos, ordenados) que toca alguna polilínea, incluidas las intermedias de cada segmento."""
    pts = np.concatenate([densify(pl) for pl in polylines])
    return np.unique(cell_index(grid, pts[:, 0], pts[:, 1]))


def load_polylines(shapes_dir: Path, lines) -> list[list[tuple[float, float]]]:
    out = []
    for ln in lines:
        p = Path(shapes_dir) / f"{ln}.json"
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("ramales", []):
            pts = r.get("points", [])
            if len(pts) >= 2:
                out.append([tuple(x) for x in pts])
    return out


def build_route_geometry(grid: GridSpec, shapes_dir: Path, lines) -> dict:
    """{'cells': ids de celdas de recorridos, 'points': (n,2) lat/lon densos cada DENSIFY_M, 'n_polylines': int}."""
    pls = load_polylines(shapes_dir, lines)
    pts = np.concatenate([densify(pl) for pl in pls])
    cells = np.unique(cell_index(grid, pts[:, 0], pts[:, 1]))
    return {"cells": cells, "points": pts.astype(np.float32), "n_polylines": len(pls)}


def cell_lookup(grid: GridSpec, cells: np.ndarray) -> np.ndarray:
    m = np.zeros(grid.n_ids, dtype=bool)
    m[cells] = True
    return m
