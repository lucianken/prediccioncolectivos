"""Recorridos desde proyectoconsola/data/line_shapes/{N}.json (solo lectura, fuente única de v2)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from prediccion.pipeline.projector import ShapeIndex

REPO_ROOT = Path(__file__).resolve().parents[2]          # .../prediccion colectivos
DEFAULT_LINE_SHAPES_DIR = REPO_ROOT.parent / "proyectoconsola" / "data" / "line_shapes"
DEFAULT_V2_DIR = REPO_ROOT / "data" / "ml" / "v2"
DEFAULT_LABEL_MAP = REPO_ROOT / "LABEL_LINE_MAP.json"
DEFAULT_DATA_DIR = Path("Z:/grabaciones")


@dataclass
class ShapeInfo:
    shape_id: str
    line: str
    name: str
    short_name: str
    index: ShapeIndex

    @property
    def length_m(self) -> float:
        return self.index.total_length_m


class LineShapes:
    """Carga perezosa y cacheada de los recorridos de cada línea."""

    def __init__(self, shapes_dir: Path | str = DEFAULT_LINE_SHAPES_DIR):
        self.dir = Path(shapes_dir)
        self._cache: dict[str, list[ShapeInfo]] = {}

    def available_lines(self) -> list[str]:
        out = [p.stem for p in self.dir.glob("*.json") if p.stem != "index"]
        return sorted(out, key=lambda s: (len(s), s))

    def get(self, line: str) -> list[ShapeInfo]:
        if line not in self._cache:
            p = self.dir / f"{line}.json"
            infos: list[ShapeInfo] = []
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                for r in data.get("ramales", []):
                    pts = [tuple(x) for x in r.get("points", [])]
                    sid = r.get("shapeId")
                    if sid is None or len(pts) < 2:
                        continue
                    infos.append(ShapeInfo(str(sid), line, r.get("name", ""),
                                           r.get("shortName", ""), ShapeIndex(pts, fast=True)))
            self._cache[line] = infos
        return self._cache[line]

    def indices(self, line: str) -> dict[str, ShapeIndex]:
        return {s.shape_id: s.index for s in self.get(line)}

    def lengths(self, lines) -> dict[str, float]:
        return {s.shape_id: s.length_m for ln in lines for s in self.get(ln)}
