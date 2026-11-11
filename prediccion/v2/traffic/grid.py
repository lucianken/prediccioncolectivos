"""Grilla de ciudad: misma definición que `CityGridEncoder` (prediccion/models/a3_eta.py), sin torch en los workers."""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

_M_PER_DEG = 111_320.0


@dataclass(frozen=True)
class GridSpec:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    n_lat: int
    n_lon: int
    cell_m: float

    @property
    def stride(self) -> int:
        """Ancho de fila del indexado del encoder (vértices = celdas + 1 por eje)."""
        return self.n_lon + 1

    @property
    def n_ids(self) -> int:
        return (self.n_lat + 1) * (self.n_lon + 1)

    def to_dict(self) -> dict:
        return asdict(self)


def grid_from_encoder(cell_m: float = 500.0) -> GridSpec:
    """Lee bbox y tamaño de la instancia real de CityGridEncoder (importa torch: llamar solo en el proceso principal)."""
    from prediccion.models import a3_eta
    enc = a3_eta.CityGridEncoder(cell_m=cell_m, dim=1)
    return GridSpec(a3_eta.GRID_LAT_MIN, a3_eta.GRID_LAT_MAX, a3_eta.GRID_LON_MIN, a3_eta.GRID_LON_MAX,
                    enc.n_lat, enc.n_lon, float(cell_m))


def cell_index(grid: GridSpec, lat, lon) -> np.ndarray:
    """
    Id de celda = índice del vértice inferior de la celda en el embedding del encoder (i0 * (n_lon + 1) + j0),
    con la misma saturación al borde que `CityGridEncoder.encode`. Devuelve int32.
    """
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    u = (lat - grid.lat_min) / (grid.lat_max - grid.lat_min) * grid.n_lat
    v = (lon - grid.lon_min) / (grid.lon_max - grid.lon_min) * grid.n_lon
    u = np.clip(u, 0.0, grid.n_lat - 1e-4)
    v = np.clip(v, 0.0, grid.n_lon - 1e-4)
    return (np.floor(u).astype(np.int64) * grid.stride + np.floor(v).astype(np.int64)).astype(np.int32)
