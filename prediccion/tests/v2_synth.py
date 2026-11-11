"""Fixtures sintéticos chicos para los tests de v2 (sin depender de Z:)."""

import gzip
import json
from pathlib import Path

M_PER_DEG = 111_320.0
LON0 = -58.40


def line_pts(lat0, n=60, dlat=0.0015, lon=LON0):
    """Recta N-S (~167 m por punto)."""
    return [(lat0 + i * dlat, lon) for i in range(n)]


def write_line_shapes(dir_: Path, line: str, shapes: dict[str, list]):
    """shapes: {shapeId: [(lat, lon), ...]} -> {dir}/{line}.json en el formato de proyectoconsola."""
    dir_.mkdir(parents=True, exist_ok=True)
    data = {"color": "#fff", "ramales": [
        {"name": f"{line} {sid}", "shortName": line, "shapeId": sid, "points": [list(p) for p in pts], "stops": []}
        for sid, pts in shapes.items()]}
    with open(dir_ / f"{line}.json", "w", encoding="utf-8") as f:
        json.dump(data, f)


def label_data(mapping: dict[str, str]):
    """mapping: {sufijo: línea} -> LABEL_LINE_MAP v3 mínimo."""
    lines = {}
    for sfx, ln in mapping.items():
        e = lines.setdefault(ln, {"agencies": [{"agencyId": "1", "agencyName": "AG"}], "suffixes": []})
        e["suffixes"].append({"suffix": sfx, "agencyId": "1", "from": None, "to": None})
    return {"version": 3, "lines": lines, "other_lines": {}}


def write_day(path: Path, base_ts: int, vehicles: list[dict], step_s=60):
    """
    vehicles: [{"id", "suffix", "points": [(lat, lon)...], "start_idx_ts": offset_s, "start_time": "08:00:00"}]
    Genera frames cada step_s: keyframe inicial + deltas con upd (el formato del grabador).
    """
    n_frames = max(len(v["points"]) + int(v.get("offset_s", 0) // step_s) for v in vehicles) + 1
    frames = []
    for k in range(n_frames):
        t = base_ts + k * step_s
        new, upd = [], []
        for v in vehicles:
            i = k - int(v.get("offset_s", 0) // step_s)
            if i < 0 or i >= len(v["points"]):
                continue
            lat, lon = v["points"][i]
            rec = {"id": v["id"], "label": f"5-{v['suffix']}", "route_id": "R1", "trip_id": "T1",
                   "direction_id": v.get("direction_id", 0), "start_date": "20260916",
                   "start_time": v.get("start_time", "08:00:00"), "lat": lat, "lon": lon,
                   "speed": 8.0, "odo": 0, "ts": t}
            if i == 0:
                new.append(rec)
            else:
                upd.append({"id": v["id"], "ts": t, "lat": lat, "lon": lon, "speed": 8.0})
        frames.append({"t": t, "keyframe": k == 0, "new": new, "del": [], "upd": upd} if k else
                      {"t": t, "keyframe": True, "new": new, "del": [], "upd": []})
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for fr in frames:
            f.write(json.dumps(fr) + "\n")
