class DataInsufficientError(Exception):
    """Raised when not enough data to train a model."""

MINIMUM_DAYS_PHASE2_3 = 90

def check_data_sufficiency(data_dir) -> int:
    """
    Cuenta archivos NDJSON.gz (proxy de días grabados).
    Raises DataInsufficientError si < MINIMUM_DAYS_PHASE2_3.
    Mensaje: "Phase 2/3 requiere 90 días. Tenés {N} días grabados. Usá --phase 1."
    Returns días disponibles.
    """
    from pathlib import Path
    import re
    data_dir = Path(data_dir)
    pattern = re.compile(r'^\d{4}-\d{2}-\d{2}\.ndjson\.gz$')
    n = sum(1 for p in data_dir.iterdir() if p.is_file() and pattern.match(p.name))
    if n < MINIMUM_DAYS_PHASE2_3:
        raise DataInsufficientError(
            f"Phase 2/3 requiere 90 días. Tenés {n} días grabados. Usá --phase 1."
        )
    return n
