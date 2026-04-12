import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class RouteIdRegistry:
    """
    Registra qué route_ids están activos por línea en el período actual.
    Detecta rotaciones (>30% de route_ids cambian).
    """

    def __init__(self, registry_path: Path):
        self._path = Path(registry_path)
        self._registry: dict = {}
        self._load()

    def update(self, line: str, observed_route_ids: set[str]) -> bool:
        """
        Actualiza el registro para la línea.
        Returns True si se detectó una nueva rotación.
        """
        if line not in self._registry:
            self._registry[line] = {
                "period_start": datetime.utcnow().isoformat(),
                "route_ids": list(observed_route_ids),
                "ranks": self._assign_ranks(observed_route_ids),
            }
            self._save()
            return False

        current = set(self._registry[line]["route_ids"])
        new_ids = observed_route_ids - current
        rotation_ratio = len(new_ids) / max(len(current), 1)

        if rotation_ratio > 0.3:
            logger.info(f"Rotación de route_ids detectada para línea {line}: {len(new_ids)} nuevos IDs")
            self._registry[line] = {
                "period_start": datetime.utcnow().isoformat(),
                "route_ids": list(observed_route_ids),
                "ranks": self._assign_ranks(observed_route_ids),
            }
            self._save()
            return True

        return False

    def get_rank(self, line: str, route_id: str) -> int:
        if line not in self._registry:
            return 0
        ranks = self._registry[line].get("ranks", {})
        return ranks.get(route_id, len(ranks))

    def get_current_ranks(self, line: str) -> dict[str, int]:
        if line not in self._registry:
            return {}
        return dict(self._registry[line].get("ranks", {}))

    def _assign_ranks(self, route_ids: set[str]) -> dict[str, int]:
        """Ordena route_ids numéricamente y asigna rank 0, 1, 2..."""
        sorted_ids = sorted(
            route_ids,
            key=lambda x: int(x) if x.isdigit() else float("inf"),
        )
        return {rid: i for i, rid in enumerate(sorted_ids)}

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path) as f:
                    self._registry = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._registry = {}
        else:
            self._registry = {}

    def _save(self) -> None:
        """Escritura atómica: escribir a tmp y renombrar."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(self._registry, f, indent=2)
        tmp_path.replace(self._path)
