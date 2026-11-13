"""
Unidad de trabajo del pipeline v2: un día -> data/ml/v2/daily/YYYY-MM-DD.parquet.

  daily/YYYY-MM-DD.parquet       filas de entrenamiento (todas las líneas pedidas, K pares por viaje)
  daily/YYYY-MM-DD.trips.parquet un registro por viaje (línea, recorrido elegido, error perp., ...)
  daily/YYYY-MM-DD.meta.json     sidecar: líneas procesadas, K, filas, carry_in (fuente de verdad del manifest)
  daily/YYYY-MM-DD.carry.json    estado para el día siguiente (últimos 15 min de observaciones + pasajes)
  manifest.json                  agregado de los meta.json (se regenera, ver update_manifest)

Idempotente: si el meta del día cubre las líneas pedidas (y mismo K / flota) no se hace nada. Si el día
existe pero le falta una línea, se reprocesa el día con la unión (líneas previas + nuevas), de modo que el
resultado es idéntico a haberlo construido desde cero con todas las líneas.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date as _date, timedelta
from pathlib import Path

import numpy as np

from prediccion.pipeline.projector import ShapeIndex, best_shape_for_trip, MAX_PERP_ERROR_M
from prediccion.pipeline.reader import reconstruct_lines_snapshots
from prediccion.pipeline.segmenter import segment_vehicle_history
from prediccion.pipeline.shapes_io import resolve_label_line_index
from prediccion.pipeline.features import N_FLEET
from prediccion.v2 import geo_assign
from prediccion.v2.pairs import trip_seed
from prediccion.v2.rows import trip_rows, add_trip_to_passage_cache
from prediccion.v2.segmenter import GAP_S, START_UNKNOWN_M, segment_geometric
from prediccion.v2.shapes import LineShapes

CARRY_WINDOW_S = 900
PASSAGE_KEEP = 3          # pasajes por recorrido que se arrastran al día siguiente
PASSAGE_MAX_AGE_S = 3600  # el cap de time_since_last_bus_s es 1 h: más viejo no sirve
ROW_GROUP_SIZE = 250_000
META_VERSION = 3

# obs = (ts, lat, lon, speed, odo, direction_id, start_date, start_time, frame_ts, has_trip_id, route_id)
# route_id solo se guarda para diagnóstico (comparar contra ramal_map); NUNCA identifica línea ni ramal.
_OBS_KEYS = ("ts", "lat", "lon", "speed", "odo", "direction_id", "start_date",
             "start_time", "frame_ts", "has_trip_id", "route_id")


def prev_day(day: str) -> str:
    return (_date.fromisoformat(day) - timedelta(days=1)).isoformat()


def _paths(out_dir: Path, day: str) -> dict[str, Path]:
    d = Path(out_dir) / "daily"
    return {
        "parquet": d / f"{day}.parquet",
        "trips": d / f"{day}.trips.parquet",
        "waiting": d / f"{day}.waiting.parquet",
        "meta": d / f"{day}.meta.json",
        "carry": d / f"{day}.carry.json",
    }


def _atomic_json(obj, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def read_meta(out_dir: Path, day: str) -> dict | None:
    p = _paths(out_dir, day)
    if not (p["meta"].exists() and p["parquet"].exists()):
        return None
    try:
        with open(p["meta"], encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        return None
    return m if m.get("version") == META_VERSION else None


def day_is_done(meta: dict | None, lines, k_pairs: int, include_fleet: bool, segmentation: str = "geo",
                assign: str = "legacy") -> bool:
    if meta is None:
        return False
    return (set(lines) <= set(meta["lines"]) and meta["k_pairs"] == k_pairs
            and meta.get("segmentation") == segmentation and meta.get("assign", "legacy") == assign
            and bool(meta.get("include_fleet")) == include_fleet)


# ── Lectura del NDJSON ───────────────────────────────────────────────────────

def read_day(
    fp: Path,
    label_map: dict[str, str],
    lines: set[str],
    carry: dict | None = None,
    interval_s: int = 30,
    include_fleet: bool = False,
):
    """
    Lee el NDJSON del día UNA vez, filtrando por línea al leer (filter-first).
    Retorna (vehicles, stats, fleet):
      vehicles: {vid: {"label": str, "obs": [obs tuples cronológicas, ts estrictamente crecientes]}}
      stats:    {line: [n_obs, n_con_trip_id, n_con_start_time]}
      fleet:    {(line, frame_ts): [dict,...]} solo si include_fleet (flota de la línea)
    Se descartan re-observaciones del mismo ping (mismo ts) y updates con ts viejo (solo cambian seq/stop).
    """
    intern = sys.intern
    vehicles: dict[str, dict] = {}
    if carry:
        for vid, rec in carry.get("vehicles", {}).items():
            sfx = rec.get("label", "").split("-")[-1]
            if label_map.get(sfx) in lines:
                obs = [tuple(o) for o in rec["obs"]]
                # carry_ts: los viajes formados solo por pings arrastrados ya salieron en el día anterior
                vehicles[vid] = {"label": rec["label"], "obs": obs, "carry_ts": obs[-1][0] if obs else 0}
    stats: dict[str, list[int]] = {}
    fleet: dict | None = {} if include_fleet else None

    for fts, state in reconstruct_lines_snapshots(fp, label_map, lines, interval_s=interval_s):
        for vid, f in state.items():
            t = f.get("ts", fts)
            rec = vehicles.get(vid)
            if rec is None:
                rec = vehicles[vid] = {"label": f.get("label", ""), "obs": []}
            elif not rec["label"]:
                rec["label"] = f.get("label", "")
            obs = rec["obs"]
            if obs and t <= obs[-1][0]:
                continue
            lat = f.get("lat")
            lon = f.get("lon")
            if lat is None or lon is None:
                continue
            has_trip = bool(f.get("trip_id"))
            obs.append((t, lat, lon, f.get("speed", 0.0) or 0.0, f.get("odo", 0) or 0,
                        f.get("direction_id", 0), intern(f.get("start_date", "") or ""),
                        intern(f.get("start_time", "") or ""), fts, has_trip,
                        intern(str(f.get("route_id", "") or ""))))
            line = label_map.get(rec["label"].split("-")[-1])
            if line:
                s = stats.setdefault(line, [0, 0, 0])
                s[0] += 1
                s[1] += has_trip
                s[2] += bool(f.get("start_time"))
                if fleet is not None:
                    fleet.setdefault((line, fts), []).append({
                        "vehicle_id": vid, "lat": lat, "lon": lon,
                        "speed": f.get("speed", 0.0) or 0.0,
                        "direction_id": f.get("direction_id", 0)})
    return vehicles, stats, fleet


def make_carry(vehicles: dict, day: str, lines, passages: dict | None) -> dict:
    cv = {}
    last_day_ts = 0
    for vid, rec in vehicles.items():
        obs = rec["obs"]
        if not obs:
            continue
        last_day_ts = max(last_day_ts, obs[-1][0])
        cutoff = obs[-1][0] - CARRY_WINDOW_S
        cv[vid] = {"label": rec["label"], "obs": [list(o) for o in obs if o[0] >= cutoff]}
    keep_pass: dict = {}
    for sid, entries in (passages or {}).items():
        sel = [[vid, dl, tl, mn] for vid, dl, tl, mn in entries[-PASSAGE_KEEP:]
               if tl and max(tl) >= last_day_ts - PASSAGE_MAX_AGE_S]
        if sel:
            keep_pass[sid] = sel
    return {"date": day, "lines": sorted(lines), "vehicles": cv, "passages": keep_pass}


def segment_vehicles(vehicles: dict, label_index: dict[str, dict], shapes: LineShapes | None = None,
                     method: str = "geo", stats: dict | None = None, assign: str = "legacy"):
    """
    Segmenta cada vehículo en viajes. Setea line_number/agency_id (por sufijo del label).
    method="geo" (default v2): segmentador geométrico, no usa trip_id ni start_time (v2/segmenter.py).
    method="geo2" (v2b): el mismo con segmenter_version=2 (une huecos, arranca al salir de cabecera, start_unknown).
    stats (solo method="geo"): acumula por línea pings / depot / moving_total / moving_valid.
    method="trip_id": segmentador viejo (start_time/start_date/direction_id); solo para validación/comparación.
    """
    trips = []
    for vid, rec in vehicles.items():
        suffix = rec["label"].split("-")[-1] if rec["label"] else ""
        info = label_index.get(suffix)
        if not info:
            continue
        carry_ts = rec.get("carry_ts", 0)
        if method in ("geo", "geo2"):
            found, vs = segment_geometric(vid, rec["obs"], shapes.indices(info["line"]) if shapes else {},
                                          return_stats=True, segmenter_version=2 if method == "geo2" else 1,
                                          assign=assign)
            if stats is not None:
                a = stats.setdefault(info["line"], {"pings": 0, "depot": 0, "moving_total": 0, "moving_valid": 0})
                for k in ("pings", "depot", "moving_total", "moving_valid"):
                    a[k] += vs[k]
                if method == "geo2":
                    a.setdefault("gaps", []).extend(vs["gaps"])
                    a.setdefault("waits", []).extend(vs["waits"])
        else:
            obs = [dict(zip(_OBS_KEYS, o)) for o in rec["obs"]]
            found = segment_vehicle_history(vid, obs)
        for trip in found:
            if trip.points[-1].ts <= carry_ts:
                continue            # fragmento del día anterior sin continuación: ya se procesó ayer
            trip.line_number = info["line"]
            trip.agency_id = info.get("agencyId")
            trips.append(trip)
    return trips


# ── Geometría ────────────────────────────────────────────────────────────────

def geometry_for_trip(trip, line_indices: dict[str, ShapeIndex], max_perp: float = MAX_PERP_ERROR_M,
                      assign: str = "legacy"):
    """
    Elige recorrido por geometría y proyecta el viaje. Retorna dict o None:
      shape_id, median_perp, dist, perp (todos los puntos del viaje), valid (máscara de pings que generan filas)
    assign="legacy": valid = perp <= max_perp (150 m).
    assign="geo3": el recorrido se elige ex post (es la etiqueta), pero solo entre los recorridos compatibles con el
      viaje según geo_assign (>= MIN_COMPAT_FRAC de sus pings compatibles; si ninguno, el de más pings compatibles);
      valid = pings compatibles con el recorrido elegido (perp <= TOL_M y <= mínimo de la línea + MARGIN_M). Lo ex post
      solo elige la etiqueta: la validez de cada ping es la regla causal, igual que en la app.
    """
    n = len(trip.points)
    lats = np.fromiter((p.lat for p in trip.points), dtype=np.float64, count=n)
    lons = np.fromiter((p.lon for p in trip.points), dtype=np.float64, count=n)
    if assign == "geo3":
        if not line_indices or n == 0:
            return None
        proj = {sid: ix.project_many(lats, lons) for sid, ix in line_indices.items()}
        masks = geo_assign.compat_masks({sid: p for sid, (_, p) in proj.items()})
        frac = {sid: float(m.mean()) for sid, m in masks.items()}
        eligible = [sid for sid, f in frac.items() if f >= geo_assign.MIN_COMPAT_FRAC] or [max(frac, key=frac.get)]
        sid, _ = best_shape_for_trip(lats, lons, {s: line_indices[s] for s in eligible},
                                     max_perp_error_m=geo_assign.TOL_M)
        dist, perp = proj[sid]
        return {"shape_id": sid, "median_perp": float(np.median(perp)), "dist": dist, "perp": perp,
                "valid": masks[sid]}
    sid, med = best_shape_for_trip(lats, lons, line_indices)
    if sid is None:
        return None
    dist, perp = line_indices[sid].project_many(lats, lons)
    return {"shape_id": sid, "median_perp": float(med), "dist": dist, "perp": perp,
            "valid": perp <= max_perp}


# ── process_day ──────────────────────────────────────────────────────────────

WAITING_SCHEMA_FIELDS = ("vehicle_id", "line", "shape_id", "wait_start_ts", "wait_end_ts", "depart_ts",
                         "n_pings", "wait_s", "trip_start_ts")


def _make_schema(include_fleet: bool, start_unknown: bool = False):
    import pyarrow as pa
    fields = [
        pa.field("line", pa.string()), pa.field("shape_id", pa.string()),
        pa.field("ramal_id", pa.string()), pa.field("seg_idx", pa.int32()),
        pa.field("dist_along_m", pa.float32()), pa.field("dist_remaining_m", pa.float32()),
        pa.field("dist_along_norm", pa.float32()), pa.field("speed_mps", pa.float32()),
        pa.field("hour_sin", pa.float32()), pa.field("hour_cos", pa.float32()),
        pa.field("dow", pa.int8()), pa.field("has_active_bus", pa.bool_()),
        pa.field("observed_eta_s", pa.float32()), pa.field("time_since_start", pa.float32()),
        pa.field("ts_age_s", pa.float32()), pa.field("traj_flat", pa.list_(pa.float32(), 30)),
        pa.field("traj_len", pa.int8()), pa.field("time_since_last_bus_s", pa.float32()),
        pa.field("last_bus_found", pa.bool_()), pa.field("ts_p", pa.int64()),
    ]
    if start_unknown:
        fields.append(pa.field("start_unknown", pa.bool_()))   # solo segmentación geo2 (time_since_start = NaN si True)
    if include_fleet:
        fields += [pa.field("fleet_flat", pa.list_(pa.float32(), N_FLEET * 5)),
                   pa.field("n_fleet", pa.int8())]
    return pa.schema(fields)


def _to_table(cols: dict, schema):
    import pyarrow as pa
    arrays = []
    for field in schema:
        a = cols[field.name]
        if pa.types.is_fixed_size_list(field.type):
            w = field.type.list_size
            flat = np.ascontiguousarray(a, dtype=np.float32).reshape(-1)
            arrays.append(pa.FixedSizeListArray.from_arrays(pa.array(flat), w))
        elif pa.types.is_string(field.type):
            arrays.append(pa.array(a.tolist(), type=pa.string()))
        else:
            arrays.append(pa.array(a, type=field.type))
    return pa.Table.from_arrays(arrays, schema=schema)


def _fleet_cols(trip_line, frame_ts_p, vehicle_id, direction_id, fleet):
    """fleet_flat/n_fleet por fila (misma codificación que features.make_training_rows_eta)."""
    m = len(frame_ts_p)
    flat = np.zeros((m, N_FLEET * 5), dtype=np.float32)
    nf = np.zeros(m, dtype=np.int8)
    for r in range(m):
        lst = [f for f in fleet.get((trip_line, int(frame_ts_p[r])), []) if f["vehicle_id"] != vehicle_id][:N_FLEET]
        nf[r] = len(lst)
        for j, f in enumerate(lst):
            flat[r, j * 5:(j + 1) * 5] = [(f["lat"] + 34.6) * 10.0, (f["lon"] + 58.4) * 10.0, f["speed"],
                                         f["direction_id"], 1.0 if f["direction_id"] == direction_id else 0.0]
    return flat, nf


def process_day(
    day: str,
    lines,
    *,
    data_dir: Path,
    out_dir: Path,
    shapes: LineShapes,
    label_data: dict,
    k_pairs: int = 64,
    include_fleet: bool = False,
    use_carry: bool = True,
    force: bool = False,
    interval_s: int = 30,
    segmentation: str = "geo",
    assign: str = "legacy",
) -> dict:
    """
    Procesa un día. Retorna el meta dict con meta["status"] en {"skipped", "processed"}
    (status no se persiste). Ver docstring del módulo para la semántica de idempotencia.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir = Path(out_dir)
    (out_dir / "daily").mkdir(parents=True, exist_ok=True)
    paths = _paths(out_dir, day)
    lines = sorted(set(map(str, lines)))
    meta_old = read_meta(out_dir, day)
    if not force and day_is_done(meta_old, lines, k_pairs, include_fleet, segmentation, assign):
        return {**meta_old, "status": "skipped"}
    if (meta_old and not force and meta_old["k_pairs"] == k_pairs
            and bool(meta_old.get("include_fleet")) == include_fleet
            and meta_old.get("segmentation") == segmentation and meta_old.get("assign", "legacy") == assign):
        lines = sorted(set(lines) | set(meta_old["lines"]))   # unión: el resultado == build desde cero

    t0 = time.time()
    fp = Path(data_dir) / f"{day}.ndjson.gz"
    if not fp.exists():
        raise FileNotFoundError(fp)

    label_index = resolve_label_line_index(label_data, on_date=day)
    label_map = {s: v["line"] for s, v in label_index.items()}
    lineset = set(lines)

    carry = None
    pcarry = paths["carry"].parent / f"{prev_day(day)}.carry.json"
    if use_carry and pcarry.exists():
        try:
            with open(pcarry, encoding="utf-8") as f:
                carry = json.load(f)
        except Exception:
            carry = None

    vehicles, stats, fleet = read_day(fp, label_map, lineset, carry, interval_s, include_fleet)
    geo2 = segmentation == "geo2"
    seg_stats: dict = {}
    trips = segment_vehicles(vehicles, label_index, shapes, segmentation, seg_stats if geo2 else None, assign)
    trips.sort(key=lambda t: t.start_time)

    passage_cache: dict = {}
    if carry:
        for sid, entries in carry.get("passages", {}).items():
            passage_cache[sid] = [(e[0], e[1], e[2], e[3]) for e in entries]

    schema = _make_schema(include_fleet, start_unknown=geo2)
    chunks: list[dict] = []
    wait_recs: list[dict] = []
    trip_recs: list[dict] = []
    per_line: dict[str, dict] = {ln: {"trips": 0, "trips_shaped": 0, "rows": 0} for ln in lines}

    for trip in trips:
        ln = trip.line_number
        if ln not in lineset:
            continue
        pl = per_line[ln]
        pl["trips"] += 1
        idx = shapes.indices(ln)
        g = geometry_for_trip(trip, idx, assign=assign) if idx else None
        rec = {"line": ln, "agency_id": trip.agency_id or "", "vehicle_id": trip.vehicle_id,
               "start_ts": int(trip.start_time), "n_points": len(trip.points),
               "route_id_diag": str(trip.route_id), "direction_id": int(trip.direction_id),
               "shape_id": g["shape_id"] if g else "",
               "median_perp_m": g["median_perp"] if g else float("nan"),
               "frac_within_150": float(g["valid"].mean()) if g else 0.0,
               "n_valid": int(g["valid"].sum()) if g else 0, "n_rows": 0}
        if g is not None and g["valid"].sum() >= 2:
            pl["trips_shaped"] += 1
            v = g["valid"]
            pts_ts = np.array([p.ts for p in trip.points], dtype=np.int64)[v]
            pts_fts = np.array([p.frame_ts for p in trip.points], dtype=np.int64)[v]
            pts_sp = np.array([p.speed for p in trip.points], dtype=np.float64)[v]
            dist = g["dist"][v]
            sid = g["shape_id"]
            length = idx[sid].total_length_m
            su, seg = False, None
            if geo2:
                su = bool(dist[0] > START_UNKNOWN_M)         # el viaje no arranca en su cabecera
                rec["start_dist_m"] = float(dist[0])
                # tramos continuos: un hueco entre puntos válidos que NO se unió separa tramos (los pares no lo cruzan)
                jg = [tuple(g) for g in getattr(trip, "joined_gaps", [])]
                brk = np.zeros(len(pts_ts) - 1, dtype=bool)
                for q in np.flatnonzero(np.diff(pts_ts) > GAP_S):
                    a_, b_ = int(pts_ts[q]), int(pts_ts[q + 1])
                    brk[q] = not any(a_ <= g1 and b_ >= g0 for g0, g1 in jg)     # el hueco no coincide con uno unido
                seg = np.concatenate([[0], np.cumsum(brk)]).astype(np.int64)
            cols = trip_rows(
                line=ln, shape_id=sid, shape_length_m=length, vehicle_id=trip.vehicle_id,
                ts=pts_ts, frame_ts=pts_fts, speed=pts_sp, dist=dist, k_pairs=k_pairs,
                seed=trip_seed(day, trip.vehicle_id, trip.start_time), passage_cache=passage_cache,
                start_unknown=su, seg=seg)
            if cols is not None:
                if include_fleet:
                    p_pos = np.searchsorted(pts_ts, cols["ts_p"])
                    cols["fleet_flat"], cols["n_fleet"] = _fleet_cols(
                        ln, pts_fts[p_pos], trip.vehicle_id, trip.direction_id, fleet)
                chunks.append(cols)
                rec["n_rows"] = len(cols["ts_p"])
                pl["rows"] += rec["n_rows"]
            add_trip_to_passage_cache(passage_cache, sid, trip.vehicle_id, dist, pts_ts)
            rec["start_unknown"] = su
        elif geo2:
            rec["start_unknown"] = False
        if geo2:
            rec["n_joined_gaps"] = len(getattr(trip, "joined_gaps", []))
            w = getattr(trip, "waiting", None)
            if w:
                wait_recs.append({
                    "vehicle_id": trip.vehicle_id, "line": ln,
                    "shape_id": rec["shape_id"] or (w["shape_candidates"][0] if w["shape_candidates"] else ""),
                    "wait_start_ts": w["start_ts"], "wait_end_ts": w["end_ts"], "depart_ts": w["depart_ts"],
                    "n_pings": w["n_pings"], "wait_s": w["end_ts"] - w["start_ts"],
                    "trip_start_ts": int(trip.start_time)})
        trip_recs.append(rec)

    # Concatenar, mezclar filas (semilla por día) y escribir en row groups
    n_rows = sum(len(c["ts_p"]) for c in chunks)
    tmp = paths["parquet"].with_name(paths["parquet"].name + ".tmp")
    writer = pq.ParquetWriter(str(tmp), schema)
    if n_rows:
        merged = {name: np.concatenate([c[name] for c in chunks]) for name in schema.names}
        perm = np.random.default_rng(trip_seed(day, "shuffle", 0)).permutation(n_rows)
        for s in range(0, n_rows, ROW_GROUP_SIZE):
            sl = perm[s:s + ROW_GROUP_SIZE]
            writer.write_table(_to_table({k: v[sl] for k, v in merged.items()}, schema))
    else:
        writer.write_table(schema.empty_table())
    writer.close()
    os.replace(tmp, paths["parquet"])

    if trip_recs:
        ttmp = paths["trips"].with_name(paths["trips"].name + ".tmp")
        pq.write_table(pa.Table.from_pylist(trip_recs), str(ttmp))
        os.replace(ttmp, paths["trips"])

    if geo2:
        # esperas en cabecera previas a la salida (no son parte del viaje; quedan para el problema "cuándo sale")
        wtmp = paths["waiting"].with_name(paths["waiting"].name + ".tmp")
        wtbl = (pa.Table.from_pylist(wait_recs) if wait_recs else pa.table({
            "vehicle_id": pa.array([], pa.string()), "line": pa.array([], pa.string()),
            "shape_id": pa.array([], pa.string()), "wait_start_ts": pa.array([], pa.int64()),
            "wait_end_ts": pa.array([], pa.int64()), "depart_ts": pa.array([], pa.int64()),
            "n_pings": pa.array([], pa.int64()), "wait_s": pa.array([], pa.int64()),
            "trip_start_ts": pa.array([], pa.int64())}))
        pq.write_table(wtbl, str(wtmp))
        os.replace(wtmp, paths["waiting"])

    _atomic_json(make_carry(vehicles, day, lines, passage_cache), paths["carry"])

    meta = {
        "version": META_VERSION, "date": day, "lines": lines, "k_pairs": k_pairs,
        "include_fleet": include_fleet, "segmentation": segmentation, "assign": assign,
        "assign_params": geo_assign.manifest_params() if assign == "geo3" else None, "n_rows": int(n_rows), "n_trips": len(trip_recs),
        "pings_in_shaped_trips": int(sum(r["n_points"] for r in trip_recs if r["shape_id"])),
        "pings_valid": int(sum(r["n_valid"] for r in trip_recs if r["shape_id"])),
        "per_line": per_line, "carry_in": carry is not None,
        "line_stats": {ln: {"pings": s[0], "with_trip_id": s[1], "with_start_time": s[2]}
                       for ln, s in stats.items()},
        "elapsed_s": round(time.time() - t0, 1),
    }
    if geo2:
        gl = [g for a in seg_stats.values() for g in a.get("gaps", [])]
        meta["geo2"] = {"gaps_joined": sum(g["joined"] and g["kind"] == "gap" for g in gl),
                        "gaps_cut": sum(not g["joined"] and g["kind"] == "gap" for g in gl),
                        "off_joined": sum(g["joined"] and g["kind"] == "off" for g in gl),
                        "off_cut": sum(not g["joined"] and g["kind"] == "off" for g in gl),
                        "n_waiting": len(wait_recs),
                        "n_start_unknown": sum(bool(r.get("start_unknown")) for r in trip_recs)}
    _atomic_json(meta, paths["meta"])
    return {**meta, "status": "processed"}


# ── Manifest ─────────────────────────────────────────────────────────────────

def update_manifest(out_dir: Path) -> dict:
    """Regenera manifest.json a partir de los meta.json (fuente de verdad)."""
    out_dir = Path(out_dir)
    days = {}
    for p in sorted((out_dir / "daily").glob("*.meta.json")):
        day = p.name[:10]
        m = read_meta(out_dir, day)
        if m:
            days[day] = {"lines": m["lines"], "k_pairs": m["k_pairs"], "include_fleet": m["include_fleet"],
                         "n_rows": m["n_rows"], "n_trips": m["n_trips"], "carry_in": m["carry_in"],
                         "elapsed_s": m["elapsed_s"], "done": True}
    manifest = {"version": META_VERSION, "days": days}
    _atomic_json(manifest, out_dir / "manifest.json")
    return manifest
