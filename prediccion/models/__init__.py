from __future__ import annotations
from pathlib import Path


class DataInsufficientError(Exception):
    """Raised when not enough data to train a model."""

MINIMUM_DAYS_PHASE2_3 = 90

def check_data_sufficiency(data_dir: Path) -> int:
    """
    Cuenta archivos NDJSON.gz (proxy de días grabados).
    Raises DataInsufficientError si < MINIMUM_DAYS_PHASE2_3.
    Mensaje: "Phase 2/3 requiere 90 días. Tenés {N} días grabados. Usá --phase 1."
    Returns días disponibles.
    """
    from pathlib import Path
    from prediccion.pipeline.reader import count_days
    n = count_days(Path(data_dir))
    if n < MINIMUM_DAYS_PHASE2_3:
        raise DataInsufficientError(
            f"Phase 2/3 requiere 90 días. Tenés {n} días grabados. Usá --phase 1."
        )
    return n
