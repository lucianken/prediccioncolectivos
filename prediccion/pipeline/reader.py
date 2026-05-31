import re
from pathlib import Path
from typing import Any, Iterator

# VehicleFields: one vehicle's field dict as stored in the NDJSON state.
# Values are primitives (str, int, float) read back from JSON.
VehicleFields = dict[str, Any]

# SnapshotState: {vehicle_id: VehicleFields} — the reconstructed fleet state at a moment.
SnapshotState = dict[str, VehicleFields]

# ── JSON backend: orjson si está disponible (3–4× más rápido), fallback a json ──
try:
    import orjson as _json_backend
    _json_decode = _json_backend.loads
    _JSON_DECODE_EXC = _json_backend.JSONDecodeError
except ImportError:  # pragma: no cover
    import json as _json_backend  # type: ignore[assignment]
    _json_decode = _json_backend.loads
    _JSON_DECODE_EXC = _json_backend.JSONDecodeError

# ── Gzip backend: isal (Intel ISA-L) si está disponible (~2× más rápido), fallback ──
try:
    import isal.igzip as _igzip
    def _open_gz(path: Path):
        return _igzip.open(path, "rb")
    _GZ_BINARY = True
except ImportError:  # pragma: no cover
    import gzip as _gzip
    def _open_gz(path: Path):  # type: ignore[misc]
        return _gzip.open(path, "rt", encoding="utf-8")
    _GZ_BINARY = False


def iter_frames(filepath: Path) -> Iterator[dict[str, Any]]:
    """
    Itera frames del NDJSON.gz, uno por línea.
    Incluye todos los tipos: keyframe, delta, gap record.
    No modifica el estado — solo parsea y yield.
    Líneas JSON inválidas: skip esa línea, continúa.

    Usa orjson si está disponible (3-4× más rápido que json estándar).
    Usa isal.igzip si está disponible (~2× más rápido que gzip estándar).
    """
    with _open_gz(filepath) as f:
        for line in f:
            if _GZ_BINARY:
                line = line.strip()
                if not line:
                    continue
            else:
                line = line.strip()
                if not line:
                    continue
            try:
                yield _json_decode(line)
            except _JSON_DECODE_EXC:
                continue


def reconstruct_snapshots(
    filepath: Path,
    interval_s: int = 300,
) -> Iterator[tuple[int, SnapshotState]]:
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

    Comportamiento por defecto: itera TODA la flota (compatibilidad con callers
    existentes como analisis_ramal_39.py y segmenter.py). Para filtrar por línea
    sin copiar el dict de 4000 entradas, usar reconstruct_line_snapshots().
    """
    state: SnapshotState = {}
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


def reconstruct_lines_snapshots(
    filepath: Path,
    label_line_map: dict[str, str],
    lines: set[str],
    interval_s: int = 300,
) -> Iterator[tuple[int, SnapshotState]]:
    """
    Variante filtrada de reconstruct_snapshots: mantiene en state SOLO los
    vehículos cuyo label pertenece a alguna de las líneas indicadas en `lines`.

    Ventaja de rendimiento: evita copiar el dict de ~4000 entradas de la flota
    completa en cada snapshot; en cambio copia únicamente los vehículos de las
    líneas indicadas.
    """
    state: SnapshotState = {}
    line_vids: set[str] = set()   # vids de las líneas que están vivos en state
    last_yield_t: int = 0

    for frame in iter_frames(filepath):
        if frame.get("gap"):
            continue

        t = frame["t"]
        is_keyframe = frame.get("keyframe", False)

        if is_keyframe:
            state = {}
            line_vids = set()
            for v in frame.get("new", []):
                vid = v["id"]
                suffix = v.get("label", "").split("-")[-1]
                if label_line_map.get(suffix) in lines:
                    state[vid] = dict(v)
                    line_vids.add(vid)
            last_yield_t = t
            yield (t, dict(state))
        else:
            # Delta: new entries may or may not belong to our lines
            for v in frame.get("new", []):
                vid = v["id"]
                suffix = v.get("label", "").split("-")[-1]
                if label_line_map.get(suffix) in lines:
                    state[vid] = dict(v)
                    line_vids.add(vid)
                else:
                    # Vehicle not in our lines: ensure it's not lingering
                    if vid in line_vids:
                        state.pop(vid, None)
                        line_vids.discard(vid)

            for vid in frame.get("del", []):
                state.pop(vid, None)
                line_vids.discard(vid)

            for upd in frame.get("upd", []):
                vid = upd["id"]
                if vid in state:   # only tracked line vehicles
                    state[vid].update(upd)

            if t - last_yield_t >= interval_s:
                last_yield_t = t
                yield (t, dict(state))


def reconstruct_line_snapshots(
    filepath: Path,
    label_line_map: dict[str, str],
    line: str,
    interval_s: int = 300,
) -> Iterator[tuple[int, SnapshotState]]:
    """
    Variante filtrada de reconstruct_snapshots: mantiene en state SOLO los
    vehículos cuyo label pertenece a la línea indicada.
    """
    yield from reconstruct_lines_snapshots(
        filepath, label_line_map, {line}, interval_s=interval_s
    )


def iter_daily_files(data_dir: Path) -> Iterator[Path]:
    """Itera *.ndjson.gz en data_dir, ordenados por nombre (cronológico). Solo YYYY-MM-DD.ndjson.gz."""
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
