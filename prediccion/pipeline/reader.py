import gzip
import json
import re
from pathlib import Path
from typing import Iterator


def iter_frames(filepath: Path) -> Iterator[dict]:
    """
    Itera frames del NDJSON.gz, uno por línea.
    Incluye todos los tipos: keyframe, delta, gap record.
    No modifica el estado — solo parsea y yield.
    Líneas JSON inválidas: skip esa línea, continúa.
    """
    with gzip.open(filepath, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def reconstruct_snapshots(
    filepath: Path,
    interval_s: int = 300,
) -> Iterator[tuple[int, dict[str, dict]]]:
    """
    Reconstruye el estado de la flota aplicando keyframes y deltas.
    Yields (timestamp, state_dict) donde state_dict = {vehicle_id: fields_dict}.

    Lógica:
    - Keyframe: resetea state completo a frame["new"] (indexado por id)
    - Delta: aplica new/del/upd sobre state acumulado
    - Gap record (frame con "gap":true): no modifica state, no yield
    - Yield cuando: es keyframe (siempre) OR t - last_yield_t >= interval_s

    Nota: en keyframe, los vehículos en frame["new"] son dicts con campo "id".
    State: {vehicle_id: {todos los campos del vehículo}}
    """
    state: dict[str, dict] = {}
    last_yield_t: int = 0

    for frame in iter_frames(filepath):
        # Gap record: skip
        if frame.get("gap"):
            continue

        t = frame["t"]
        is_keyframe = frame.get("keyframe", False)

        if is_keyframe:
            # Reset state from keyframe's "new" list
            state = {}
            for v in frame.get("new", []):
                state[v["id"]] = dict(v)
            last_yield_t = t
            yield (t, dict(state))
        else:
            # Delta frame
            for v in frame.get("new", []):
                state[v["id"]] = dict(v)
            for vid in frame.get("del", []):
                state.pop(vid, None)
            for upd in frame.get("upd", []):
                vid = upd["id"]
                if vid in state:
                    state[vid].update(upd)

            if t - last_yield_t >= interval_s:
                last_yield_t = t
                yield (t, dict(state))


def iter_daily_files(data_dir: Path) -> Iterator[Path]:
    """
    Itera *.ndjson.gz en data_dir, ordenados por nombre (cronológico).
    Solo archivos con nombre YYYY-MM-DD.ndjson.gz (ignora otros).
    Patron: re.match(YYYY-MM-DD.ndjson.gz pattern, filename)
    """
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\.ndjson\.gz$")
    files = [
        p for p in data_dir.iterdir()
        if p.is_file() and pattern.match(p.name)
    ]
    files.sort(key=lambda p: p.name)
    yield from files


def count_days(data_dir: Path) -> int:
    """Cuenta archivos YYYY-MM-DD.ndjson.gz. Usado para check de suficiencia."""
    return sum(1 for _ in iter_daily_files(data_dir))
