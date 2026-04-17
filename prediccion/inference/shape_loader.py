import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from prediccion.pipeline.projector import haversine_m, polyline_length_m, project_to_shape

if TYPE_CHECKING:
    from prediccion.inference.fleet_cache import LiveVehicle

logger = logging.getLogger(__name__)


@dataclass
class Ramal:
    line: str
    ramal_id: str           # "39-0"
    name: str
    short_name: str
    direction: int
    shape_id: str
    points: list[tuple[float, float]]
    length_m: float = field(default=0.0)


class ShapeLoader:
    """Carga line_shapes.json y provee proyección de puntos GPS sobre polilíneas."""

    def __init__(self, source: str):
        """source: URL (http://...) o path absoluto."""
        self._source = source
        self._ramales: dict[str, list[Ramal]] = {}
        self._loaded = False

    async def load(self) -> None:
        """Carga el JSON desde URL o archivo."""
        if self._source.startswith("http"):
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(self._source)
                resp.raise_for_status()
                shapes = resp.json()
        else:
            with open(self._source) as f:
                shapes = json.load(f)

        self._ramales = {}
        for line, data in shapes.items():
            ramales = []
            for r in data.get("ramales", []):
                pts = [tuple(p) for p in r["points"]]
                length_m = polyline_length_m(pts)
                ramal_id = f"{line}-{r['direction']}"
                ramales.append(Ramal(
                    line=line,
                    ramal_id=ramal_id,
                    name=r.get("name", ""),
                    short_name=r.get("shortName", line),
                    direction=r["direction"],
                    shape_id=r.get("shapeId", ""),
                    points=pts,
                    length_m=length_m,
                ))
            self._ramales[line] = ramales
        self._loaded = True

    def get_ramales(self, line: str) -> list[Ramal]:
        return self._ramales.get(line, [])

    def find_best_ramal(
        self,
        lat: float,
        lon: float,
        line: str,
    ) -> tuple[Ramal, float, float] | None:
        """
        Proyecta sobre todos los ramales de la línea.
        Returns (ramal, dist_along_m, perp_error_m) del mejor (menor perp_error).
        None si perp_error > 150m para TODOS.
        """
        ramales = self.get_ramales(line)
        if not ramales:
            return None

        best = None
        best_perp = float("inf")
        best_dist = 0.0

        for ramal in ramales:
            dist, perp = project_to_shape(lat, lon, ramal.points)
            if perp < best_perp:
                best_perp = perp
                best_dist = dist
                best = ramal

        if best is None or best_perp > 150.0:
            return None

        return best, best_dist, best_perp

    def project_vehicles_to_ramal(
        self,
        vehicles: list["LiveVehicle"],
        ramal: Ramal,
        max_perp_error_m: float = 150.0,
    ) -> list[tuple["LiveVehicle", float]]:
        """Proyecta lista de vehículos al ramal. Filtra los que están muy lejos."""
        result = []
        for v in vehicles:
            dist, perp = project_to_shape(v.lat, v.lon, ramal.points)
            if perp <= max_perp_error_m:
                result.append((v, dist))
        return result

    @property
    def available_lines(self) -> list[str]:
        return list(self._ramales.keys())

    @property
    def is_loaded(self) -> bool:
        return self._loaded
