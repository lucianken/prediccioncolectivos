"""
Grabador de CuandoSubo (OneBusAway de Nación/SUBE). Paralelo al grabador de la API CABA.

Escribe SOLO en DATA_DIR (en el NUC: /mnt/buffer/grabaciones_cuandosubo):
  posiciones/YYYY-MM-DD.ndjson.gz  keyframe/delta/gap, mismo formato que el grabador CABA (+ campos extra)
  arribos/YYYY-MM-DD.ndjson.gz     una línea por consulta a una parada del panel
  horarios/YYYY-MM-DD.ndjson.gz    horario (stopTimes) de cada trip nuevo de las líneas objetivo, una vez
  horarios_index.json              (tripId, serviceDate) ya pedidos, último hash por trip, hashes con detalle
  paradas.json                     stopId → nombre, lat/lon (de las referencias de OBA)
  state.json  learned_labels.json  health  stats.json

Ver README.md (especificación) y docs/CUANDOSUBO_API.md.

Uso:
  python grabador.py            # loop infinito
  python grabador.py --test N   # N ciclos y sale
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from config import APP_DIR, Config
from identity import Identity, LabelLineMap, ba_date, load_registry, strip_prefix
from limiter import Clock, RateLimiter, SystemClock
from oba_client import KeyInvalidError, ObaClient, ObaError, WafError, requests_transport

try:  # en el contenedor, delta.py se copia junto al código (ver stage.py)
    from delta import compute_delta, make_keyframe
except ImportError:  # en el repo: el del grabador CABA, sin copiarlo ni modificarlo
    sys.path.insert(0, str(APP_DIR.parent / "grabador"))
    from delta import compute_delta, make_keyframe

log = logging.getLogger("grabador-cuandosubo")

# Bounding box CABA + GBA (igual que el grabador CABA)
LAT_MIN, LAT_MAX = -35.1, -34.3
LON_MIN, LON_MAX = -59.1, -57.9

# Campos que, además de los dinámicos de delta.py, van en `upd` si cambian.
# label/license_plate/start_date se suman para que el estado se pueda reconstruir
# exacto desde los deltas (acá sí pueden cambiar: label aprendido, cambio de día).
EXTRA_DYNAMIC = ("label", "license_plate", "start_date", "agency", "label_src", "line",
                 "pred_lat", "pred_lon", "sched_dev", "dist_along", "next_stop",
                 "next_stop_eta_s", "predicted")


def _r6(x: Any) -> float | None:
    return round(float(x), 6) if x is not None else None


def compute_delta_ext(prev: dict[str, dict], vehicles: list[dict]) -> tuple[dict, dict]:
    """delta.py:compute_delta + los campos extra de CuandoSubo, sin tocar delta.py."""
    frame, new_state = compute_delta(prev, vehicles)
    by_id = {u["id"]: u for u in frame["upd"]}
    for v in vehicles:
        p = prev.get(v["id"])
        if p is None:
            continue
        changed = {k: v.get(k) for k in EXTRA_DYNAMIC if v.get(k) != p.get(k)}
        if not changed and (v["id"] in by_id or v.get("ts") == p.get("ts")):
            continue
        # Si solo cambió ts (heartbeat de un coche quieto) igual va {id, ts}: es un reporte real (§4 regla 5).
        u = by_id.get(v["id"])
        if u is None:
            u = {"id": v["id"], "ts": v["ts"]}
            by_id[v["id"]] = u
            frame["upd"].append(u)
        u.update(changed)
    return frame, new_state


def keyframe(vehicles: list[dict]) -> dict:
    kf = make_keyframe(vehicles)
    return {"t": kf["t"], "keyframe": True, "src": "cuandosubo", "new": kf["new"], "del": kf["del"], "upd": kf["upd"]}


def append_gz(path: Path, record: dict) -> None:
    """Agrega un bloque gzip con una línea JSON (multi-member, se lee con gzip.open(p, 'rt'))."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "at", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json_atomic(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    tmp.replace(path)


def load_panel(path: Path, only: list[str] | None) -> list[dict]:
    if not path.exists():
        log.warning(f"Sin panel de paradas ({path}): no se graban arribos")
        return []
    with open(path, encoding="utf-8") as f:
        stops = json.load(f).get("stops", [])
    if only:
        known = {s["id"]: s for s in stops}
        stops = [known.get(i, {"id": i, "line": None}) for i in only]
    return stops


class Recorder:
    def __init__(self, cfg: Config, client: ObaClient, llmap: LabelLineMap, identity: Identity,
                 clock: Clock, panel: list[dict]):
        self.cfg, self.client, self.llmap, self.identity, self.clock = cfg, client, llmap, identity, clock
        self.panel = panel
        d = cfg.data_dir
        d.mkdir(parents=True, exist_ok=True)
        self.dir_pos, self.dir_arr, self.dir_hor = d / "posiciones", d / "arribos", d / "horarios"
        self.state_file, self.health_file, self.stats_file = d / "state.json", d / "health", d / "stats.json"
        self.trip_index_file, self.stops_file = d / "horarios_index.json", d / "paradas.json"

        self.prev, self.saved_at = self._load_state()
        idx = self._load_json(self.trip_index_file, {})
        if not isinstance(idx.get("trips"), dict):  # formato viejo o vacío
            idx = {}
        # trips: "tripId|serviceDate" → {hash | missing, t};  last: tripId → {sd, hash} (último día de servicio pedido)
        # hashes: hash → {file, t} (dónde está el detalle completo de ese horario)
        self.trip_index: dict[str, dict] = {"trips": idx.get("trips", {}), "last": idx.get("last", {}),
                                            "hashes": idx.get("hashes", {})}
        self.stops_known: dict[str, dict] = self._load_json(self.stops_file, {})
        self.trip_queue_hi: dict[str, None] = {}   # trips de coches vivos vistos en las paradas del panel
        self.trip_queue: dict[str, None] = {}      # el resto (coches de las líneas objetivo en posiciones)
        self.pruned_on: str | None = None
        self.first_write = True
        self.force_kf = True
        self.frames = 0
        self.cycle = 0
        self.arr_ptr = 0
        self.last_poll: dict[str, float] = {}
        self.sweep_ptr = 0
        self.fail_since: float | None = None
        self.disk_ok = True
        self.stats: dict[str, Any] = {
            "started_at": int(clock.now()), "cycles": 0, "frames": 0, "keyframes": 0, "gaps": 0,
            "empty_cycles": 0, "cycle_overrun": 0, "artifacts": 0, "shared_ts": 0,
            "requests_by_kind": {"A": 0, "arrivals": 0, "trips": 0, "C": 0},
            "fetch_errors": 0, "arrivals_lines": 0, "arrivals_entries": 0,
            "trips_fetched": 0, "trips_missing": 0, "horario_cambiado_total": 0, "last_error": None,
            "trips_day": self._new_trips_day(ba_date(clock.now())),
        }

    @staticmethod
    def _new_trips_day(date: str) -> dict[str, Any]:
        return {"date": date, "fetched": 0, "missing": 0, "new_trip_ids": 0, "same_as_prev_service_day": 0,
                "horario_cambiado": 0, "new_hashes": 0}

    # ------------------------------------------------------------------ persistencia
    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _load_state(self) -> tuple[dict, float]:
        j = self._load_json(self.state_file, {})
        return j.get("vehicles", {}) or {}, float(j.get("ts", 0.0) or 0.0)

    def _save_state(self) -> None:
        write_json_atomic(self.state_file, {"ts": self.saved_at, "vehicles": self.prev})

    def _remember_stops(self, refs: dict) -> None:
        changed = False
        for s in refs.get("stops", []) or []:
            if s.get("id") and s["id"] not in self.stops_known:
                self.stops_known[s["id"]] = {"name": s.get("name"), "code": s.get("code"),
                                             "lat": s.get("lat"), "lon": s.get("lon"),
                                             "direction": s.get("direction")}
                changed = True
        if changed:
            write_json_atomic(self.stops_file, self.stops_known)

    # ------------------------------------------------------------------ requests
    def _fetch(self, kind: str, resource: str, params: dict | None = None) -> dict | None:
        self.stats["requests_by_kind"][kind] += 1
        try:
            return self.client.fetch(resource, params)
        except KeyInvalidError:
            raise
        except WafError as e:
            self.stats["last_error"] = f"{resource}: {e}"
            log.warning(f"WAF en {resource} (pausa {self.cfg.waf_backoff_s:.0f}s ya aplicada): {e}")
            return None
        except ObaError as e:
            self.stats["fetch_errors"] += 1
            self.stats["last_error"] = f"{resource}: {e}"
            log.warning(f"Error {resource}: {e}")
            return None

    def _fits(self, deadline: float) -> bool:
        return self.client.limiter.next_start() + self.client.typical_duration() <= deadline

    def _tiers(self, date: str) -> tuple[list[str], list[str]]:
        key = lambda a: (0, int(a)) if a.isdigit() else (1, a)  # noqa: E731
        a = sorted({ag for line in self.cfg.record_lines for ag in self.llmap.agencies_for(line, date)}, key=key)
        c = sorted(self.llmap.all_agencies(date) - set(a), key=key)
        return a, c

    # ------------------------------------------------------------------ ciclo
    def run_cycle(self) -> dict | None:
        t0 = self.clock.now()
        deadline = t0 + self.cfg.cycle_s
        try:
            self.llmap.maybe_reload()
        except Exception as e:  # map roto: seguir con el anterior
            log.error(f"No se pudo recargar LABEL_LINE_MAP: {e}")
        tier_a, tier_c = self._tiers(ba_date(t0))
        waf0, req0 = self.client.counters["waf"], self.client.counters["requests"]

        # Tier A: agencias de las líneas objetivo, cada ciclo
        a_ok = a_err = 0
        for ag in tier_a:
            err0 = self.client.counters["errors"]
            if self._fetch("A", f"vehicles-for-agency/{ag}") is not None:
                a_ok += 1
            elif self.client.counters["errors"] > err0:
                a_err += 1  # error que no es WAF

        # Arribos: panel fijo en rotación
        if self.panel:
            for _ in range(min(self.cfg.arrivals_per_cycle, len(self.panel))):
                stop = self.panel[self.arr_ptr % len(self.panel)]
                self.arr_ptr += 1
                self._record_arrivals(stop)

        if self.clock.now() > deadline:
            self.stats["cycle_overrun"] += 1
            log.warning(f"cycle_overrun: tier A + arribos tardaron {self.clock.now() - t0:.0f}s (> {self.cfg.cycle_s:.0f}s)")

        # Huecos: horarios de trips nuevos, después rotación C
        n = 0
        while (self.trip_queue_hi or self.trip_queue) and n < self.cfg.trips_per_cycle and self._fits(deadline):
            q = self.trip_queue_hi if self.trip_queue_hi else self.trip_queue
            key = next(iter(q))
            del q[key]
            self._record_trip(key)
            n += 1
        n = 0
        while self.cfg.sweep and tier_c and n < len(tier_c) and self._fits(deadline):
            ag = tier_c[self.sweep_ptr % len(tier_c)]
            self.sweep_ptr += 1
            self._fetch("C", f"vehicles-for-agency/{ag}")
            n += 1

        # Guardrail: tier A fallando (no WAF) por más de fatal_fail_s → exit(1)
        if a_ok:
            self.fail_since = None
        elif a_err:
            self.fail_since = self.fail_since or t0
            if self.clock.now() - self.fail_since >= self.cfg.fatal_fail_s:
                log.critical(f"Tier A sin respuestas por {self.clock.now() - self.fail_since:.0f}s "
                             f"(no WAF). Saliendo para que Docker recree el contenedor.")
                raise SystemExit(1)

        vehicles, raw_trips = self._snapshot(tier_a, tier_c)
        self.cycle += 1
        self.stats["cycles"] += 1
        if not vehicles:
            self.stats["empty_cycles"] += 1
            log.warning(f"ciclo={self.cycle} sin vehículos: no se escribe frame")
            self._write_stats(vehicles, None)
            return None

        frame = self._write_positions(vehicles)
        self._queue_trips(vehicles, raw_trips)
        self.identity.flush()
        try:
            self.health_file.touch()
        except OSError:
            pass
        self._write_stats(vehicles, frame)
        log.info(
            f"ciclo={self.cycle} veh={len(vehicles)} new={len(frame['new'])} del={len(frame['del'])} "
            f"upd={len(frame['upd'])} artefactos={self.stats['artifacts']} "
            f"waf={self.client.counters['waf'] - waf0} reqs={self.client.counters['requests'] - req0}"
            f"{' [KF]' if frame.get('keyframe') else ''} errs={a_err} "
            f"trips_q={len(self.trip_queue_hi) + len(self.trip_queue)}"
        )
        return frame

    # ------------------------------------------------------------------ posiciones
    def _snapshot(self, tier_a: list[str], tier_c: list[str]) -> tuple[list[dict], dict[str, tuple[str, int]]]:
        by_id: dict[str, dict] = {}
        raw_ms: dict[str, int] = {}
        raw_trip: dict[str, tuple[str, int]] = {}  # id → (tripId OBA, serviceDate ms)
        self.last_poll = {}  # agencia → currentTime (s) de la respuesta usada en este frame
        for ag, max_age in [(a, self.cfg.stale_max_s) for a in tier_a] + [(c, self.cfg.sweep_max_age_s) for c in tier_c]:
            body = self.client.cached(f"vehicles-for-agency/{ag}", max_age)
            if not body:
                continue
            if body.get("currentTime"):
                self.last_poll[str(ag)] = round(body["currentTime"] / 1000, 3)
            data = body.get("data") or {}
            trips = {t["id"]: t for t in (data.get("references") or {}).get("trips", [])}
            for v in data.get("list", []) or []:
                loc = v.get("location")
                if not loc or loc.get("lat") is None or loc.get("lon") is None:
                    continue
                lat, lon = loc["lat"], loc["lon"]
                if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                    continue
                vid = strip_prefix(v.get("vehicleId"))
                lut = v.get("lastUpdateTime") or body.get("currentTime") or 0
                ts = int(lut // 1000)
                if vid in by_id and by_id[vid]["ts"] >= ts:
                    continue  # id fantasma en otra agencia: gana el más reciente
                st = v.get("tripStatus") or {}
                trip = trips.get(v.get("tripId") or "") or {}
                label, src = self.identity.resolve(vid, st.get("vehicleLabel"))
                pos = st.get("position") or {}
                sd = st.get("serviceDate")
                dir_id = trip.get("directionId")
                by_id[vid] = {
                    "id": vid,
                    "label": label or "",
                    "license_plate": self.identity.plate(vid),
                    "route_id": strip_prefix(trip.get("routeId")),
                    "trip_id": strip_prefix(v.get("tripId")),
                    "direction_id": int(dir_id) if dir_id not in (None, "") else 0,
                    "start_date": ba_date(sd / 1000 + 12 * 3600).replace("-", "") if sd else "",
                    "start_time": "",
                    "lat": _r6(lat),
                    "lon": _r6(lon),
                    "speed": None,
                    "odo": None,
                    "stop_id": "",
                    "seq": 0,
                    "status": None,
                    "ts": ts,
                    "agency": (v.get("vehicleId") or "").split("_", 1)[0],
                    "label_src": src,
                    "line": None,
                    "pred_lat": _r6(pos.get("lat")),
                    "pred_lon": _r6(pos.get("lon")),
                    "sched_dev": st.get("scheduleDeviation"),
                    "dist_along": round(st["distanceAlongTrip"]) if st.get("distanceAlongTrip") is not None else None,
                    "next_stop": strip_prefix(st.get("nextStop")) or None,
                    "next_stop_eta_s": st.get("nextStopTimeOffset") if st.get("nextStop") else None,
                    "predicted": bool(st.get("predicted")) if st else None,
                }
                raw_ms[vid] = lut
                if v.get("tripId") and sd:
                    raw_trip[vid] = (v["tripId"], int(sd))
                else:
                    raw_trip.pop(vid, None)

        vehicles = sorted(by_id.values(), key=lambda x: (len(x["id"]), x["id"]))
        if not vehicles:
            return [], {}
        date = ba_date(max(v["ts"] for v in vehicles))  # fecha del archivo donde va el frame
        shared = Counter(raw_ms.values())
        for v in vehicles:
            v["line"] = self.llmap.line_for_label(v["label"], date)
            p = self.prev.get(v["id"])
            if p is not None and p.get("ts") == v["ts"] and (p.get("lat"), p.get("lon")) != (v["lat"], v["lon"]):
                # Artefacto en lote: cambió la posición pero no lastUpdateTime → no es movimiento
                v["lat"], v["lon"] = p.get("lat"), p.get("lon")
                self.stats["artifacts"] += 1
            if shared[raw_ms[v["id"]]] > 1 and p is not None and p.get("ts") != v["ts"]:
                self.stats["shared_ts"] += 1  # reporte nuevo con hora compartida al ms (escritura en lote)
        return vehicles, raw_trip

    def _write_positions(self, vehicles: list[dict]) -> dict:
        now = self.clock.now()
        gap = now - self.saved_at if self.saved_at > 0 else float("inf")
        need_gap = self.saved_at > 0 and gap > self.cfg.gap_threshold_s
        if self.cycle % self.cfg.disk_check_every == 1 or self.cfg.disk_check_every <= 1:
            free_gb = shutil.disk_usage(self.cfg.data_dir).free / 1024 ** 3
            self.disk_ok = free_gb >= self.cfg.disk_min_gb
            if not self.disk_ok:
                log.critical(f"Disco lleno: {free_gb:.2f} GB libres en {self.cfg.data_dir}. Pausa de escritura.")

        is_kf = self.force_kf or need_gap or self.frames % self.cfg.keyframe_every == 0
        if is_kf:
            if need_gap:
                gap_rec = {"t": int(now), "gap": True, "gap_seconds": int(gap),
                           "reason": "restart" if self.first_write else "outage"}
                log.warning(f"Gap de {gap:.0f}s ({gap_rec['reason']}): registro gap + keyframe")
                if self.disk_ok:
                    append_gz(self.dir_pos / f"{ba_date(now)}.ndjson.gz", gap_rec)
                self.stats["gaps"] += 1
            frame = keyframe(vehicles)
            self.prev = {v["id"]: v for v in vehicles}
            self.force_kf = False
            self.stats["keyframes"] += 1
        else:
            frame, self.prev = compute_delta_ext(self.prev, vehicles)
        frame["t_poll"] = dict(self.last_poll)

        if self.disk_ok:
            append_gz(self.dir_pos / f"{ba_date(frame['t'])}.ndjson.gz", frame)
            self.stats["frames"] += 1
        self.frames += 1
        self.first_write = False
        self.saved_at = now
        self._save_state()
        return frame

    # ------------------------------------------------------------------ arribos
    def _record_arrivals(self, stop: dict) -> None:
        sid = stop["id"]
        body = self._fetch("arrivals", f"arrivals-and-departures-for-stop/{sid}")
        if body is None:
            return
        data = body.get("data") or {}
        t = int((body.get("currentTime") or self.clock.now() * 1000) // 1000)
        date = ba_date(t)
        out = []
        for a in (data.get("entry") or {}).get("arrivalsAndDepartures", []) or []:
            st = a.get("tripStatus") or {}
            vid = strip_prefix(a.get("vehicleId")) or None
            live = a.get("vehicleLabel") or st.get("vehicleLabel")
            label = self.identity.resolve(vid, live)[0] if vid else (live or None)
            loc = st.get("lastKnownLocation") or {}
            pos = st.get("position") or {}
            vts = a.get("lastUpdateTime") or st.get("lastUpdateTime")
            item = {
                "vehicle": vid,
                "label": label,
                "veh_line": self.llmap.line_for_label(label, date),
                "route": a.get("routeShortName"),
                "route_id": strip_prefix(a.get("routeId")),
                "trip": strip_prefix(a.get("tripId")),
                "service_date": int(a["serviceDate"] // 1000) if a.get("serviceDate") else None,
                "stop_seq": a.get("stopSequence"),
                "predicted": bool(a.get("predicted")),
                "pred_arr": int(a["predictedArrivalTime"] // 1000) if a.get("predictedArrivalTime") else None,
                "sched_arr": int(a["scheduledArrivalTime"] // 1000) if a.get("scheduledArrivalTime") else None,
                "stops_away": a.get("numberOfStopsAway"),
                "dist_m": round(a["distanceFromStop"]) if a.get("distanceFromStop") is not None else None,
                "frequency": a.get("frequency"),
                "sched_dev": st.get("scheduleDeviation") if st else None,
                "veh_ts": int(vts // 1000) if vts else None,
                "lat": _r6(loc.get("lat")),
                "lon": _r6(loc.get("lon")),
                "pred_lat": _r6(pos.get("lat")),
                "pred_lon": _r6(pos.get("lon")),
            }
            for k_src, k_dst in (("predictedArrivalInterval", "pred_interval"),
                                 ("scheduledArrivalInterval", "sched_interval")):
                if a.get(k_src) is not None:
                    item[k_dst] = a[k_src]
            out.append(item)
            if vid and item["veh_line"] in self.cfg.record_lines:
                self._want_trip(a.get("tripId"), a.get("serviceDate"), priority=True)
        rec = {"t": t, "stop": sid, "line": stop.get("line"), "arrivals": out}
        if self.disk_ok:
            append_gz(self.dir_arr / f"{date}.ndjson.gz", rec)
        self.stats["arrivals_lines"] += 1
        self.stats["arrivals_entries"] += len(out)
        self._remember_stops(data.get("references") or {})

    # ------------------------------------------------------------------ horarios
    def _want_trip(self, full: str | None, service_date_ms: Any, priority: bool) -> None:
        """Encola (tripId, serviceDate) si todavía no se pidió para ese día de servicio."""
        if not full or not service_date_ms:
            return
        key = f"{full}|{int(service_date_ms) // 1000}"
        if key in self.trip_index["trips"] or key in self.trip_queue_hi:
            return
        if priority:
            self.trip_queue.pop(key, None)
            self.trip_queue_hi[key] = None
        elif key not in self.trip_queue:
            self.trip_queue[key] = None

    def _queue_trips(self, vehicles: list[dict], raw_trip: dict[str, tuple[str, int]]) -> None:
        targets = set(self.cfg.record_lines)
        for v in vehicles:
            if v["line"] in targets and v["id"] in raw_trip:
                full, sd = raw_trip[v["id"]]
                self._want_trip(full, sd, priority=False)

    @staticmethod
    def _schedule_hash(detail: dict) -> str:
        """Hash estable del contenido relevante del horario (stopTimes, frequency, ruta, headsign, sentido)."""
        canon = json.dumps(detail, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:16]

    def _prune_trip_index(self) -> None:
        """Una vez por día BA: olvida (trip, serviceDate) de hace más de 2 días."""
        today = ba_date(self.clock.now())
        if self.pruned_on == today:
            return
        self.pruned_on = today
        limit = self.clock.now() - 3 * 86400
        trips = self.trip_index["trips"]
        for k in [k for k in trips if int(k.rsplit("|", 1)[1]) < limit]:
            del trips[k]

    def _record_trip(self, key: str) -> None:
        full, sd_s = key.rsplit("|", 1)
        sd = int(sd_s)
        now = self.clock.now()
        day = ba_date(now)
        if self.stats["trips_day"]["date"] != day:
            self.stats["trips_day"] = self._new_trips_day(day)
        tday = self.stats["trips_day"]
        self._prune_trip_index()
        self.stats["requests_by_kind"]["trips"] += 1
        try:
            body = self.client.fetch(f"trip-details/{full}", {"includeSchedule": "true", "includeStatus": "false",
                                                              "serviceDate": sd * 1000})
        except KeyInvalidError:
            raise
        except ObaError as e:
            if not isinstance(e, WafError) and e.status == 404:
                self.trip_index["trips"][key] = {"missing": True, "t": int(now)}
                self.stats["trips_missing"] += 1
                tday["missing"] += 1
                write_json_atomic(self.trip_index_file, self.trip_index)
            else:
                self.stats["fetch_errors"] += 1
                self.stats["last_error"] = f"trip-details/{full}: {e}"
                log.warning(f"Error trip-details/{full}: {e}")
            return
        data = body.get("data") or {}
        e = data.get("entry") or {}
        sch = e.get("schedule") or {}
        refs = data.get("references") or {}
        trip = next((x for x in refs.get("trips", []) if x.get("id") == full), {})
        route = next((r for r in refs.get("routes", []) if r.get("id") == trip.get("routeId")), {})
        t = int((body.get("currentTime") or now * 1000) // 1000)
        detail = {
            "route_id": strip_prefix(trip.get("routeId")),
            "headsign": trip.get("tripHeadsign"),
            "direction_id": int(trip["directionId"]) if trip.get("directionId") not in (None, "") else None,
            "frequency": e.get("frequency") or sch.get("frequency"),
            "stop_times": [
                {"stop": s.get("stopId"), "arr": s.get("arrivalTime"), "dep": s.get("departureTime"),
                 "dist": round(s["distanceAlongTrip"], 1) if s.get("distanceAlongTrip") is not None else None}
                for s in sch.get("stopTimes", []) or []
            ],
        }
        h = self._schedule_hash(detail)
        path = self.dir_hor / f"{ba_date(t)}.ndjson.gz"
        new_hash = h not in self.trip_index["hashes"]
        rec = {"t": t, "trip_id": strip_prefix(full), "oba_trip_id": full, "service_date": sd, "hash": h,
               "full": new_hash, "route": route.get("shortName"), "block_id": trip.get("blockId"),
               "shape_id": trip.get("shapeId"), "time_zone": sch.get("timeZone")}
        if new_hash:
            rec.update(detail)  # el detalle va una sola vez por hash
        if self.disk_ok:
            append_gz(path, rec)
            if new_hash:
                self.trip_index["hashes"][h] = {"file": f"horarios/{path.name}", "t": t}
                tday["new_hashes"] += 1

        prev = self.trip_index["last"].get(full)
        if prev is None:
            tday["new_trip_ids"] += 1
        elif prev["sd"] < sd:
            if prev["hash"] == h:
                tday["same_as_prev_service_day"] += 1
            else:
                tday["horario_cambiado"] += 1
                self.stats["horario_cambiado_total"] += 1
                log.info(f"horario_cambiado: {full} sd={sd} {prev['hash']} → {h}")
        if prev is None or prev["sd"] <= sd:
            self.trip_index["last"][full] = {"sd": sd, "hash": h}
        self.trip_index["trips"][key] = {"hash": h, "t": t}
        write_json_atomic(self.trip_index_file, self.trip_index)
        self.stats["trips_fetched"] += 1
        tday["fetched"] += 1
        self._remember_stops(refs)

    # ------------------------------------------------------------------ stats
    def _write_stats(self, vehicles: list[dict], frame: dict | None) -> None:
        now = self.clock.now()
        by_line = Counter(v["line"] for v in vehicles if v["line"])
        fresh = Counter(v["line"] for v in vehicles if v["line"] and now - v["ts"] <= 180)
        s = dict(self.stats)
        s.update({
            "updated_at": int(now),
            "requests": self.client.counters["requests"],
            "waf": self.client.counters["waf"],
            "errors": self.client.counters["errors"],
            "vehicles": len(vehicles),
            "vehicles_by_target_line": {l: by_line.get(l, 0) for l in self.cfg.record_lines},
            "reporting_3min_by_target_line": {l: fresh.get(l, 0) for l in self.cfg.record_lines},
            "lines_seen": len(by_line),
            "trips_queue": len(self.trip_queue_hi) + len(self.trip_queue),
            "trips_queue_priority": len(self.trip_queue_hi),
            "trips_known": len(self.trip_index["last"]),
            "schedule_hashes": len(self.trip_index["hashes"]),
            "stops_known": len(self.stops_known),
            "panel_stops": len(self.panel),
            "identity": self.identity.stats(),
            "last_cycle": None if frame is None else {
                "t": frame["t"], "keyframe": bool(frame.get("keyframe")), "new": len(frame["new"]),
                "del": len(frame["del"]), "upd": len(frame["upd"])},
        })
        try:
            write_json_atomic(self.stats_file, s)
        except OSError as e:
            log.error(f"No se pudo escribir stats.json: {e}")

    # ------------------------------------------------------------------ loop
    def run(self, max_cycles: int | None = None) -> None:
        log.info(f"Grabador CuandoSubo iniciado. DATA_DIR={self.cfg.data_dir} líneas={' '.join(self.cfg.record_lines)} "
                 f"panel={len(self.panel)} paradas ciclo={self.cfg.cycle_s:.0f}s")
        done = 0
        while max_cycles is None or done < max_cycles:
            t0 = self.clock.now()
            try:
                self.run_cycle()
            except (KeyInvalidError, SystemExit):
                raise
            except Exception as e:  # nunca morir por un bug de un ciclo; queda en el log y en stats
                log.exception(f"Error en ciclo: {e}")
                self.stats["last_error"] = f"ciclo: {e}"
            done += 1
            if max_cycles is not None and done >= max_cycles:
                break
            self.clock.sleep(self.cfg.cycle_s - (self.clock.now() - t0))


def build(cfg: Config, clock: Clock | None = None, transport=None) -> Recorder:
    clock = clock or SystemClock()
    limiter = RateLimiter(cfg.min_interval_s, clock)
    client = ObaClient(cfg.base_url, cfg.oba_key, limiter, transport or requests_transport(), clock,
                       timeout_s=cfg.timeout_s, waf_backoff_s=cfg.waf_backoff_s)
    llmap = LabelLineMap(cfg.label_line_map_path, cfg.overrides_path)
    registry, plates = load_registry(cfg.registry_path) if cfg.registry_path.exists() else ({}, {})
    if not registry:
        log.warning(f"Sin registro id→label ({cfg.registry_path}): los coches sin trip quedan sin label")
    identity = Identity(registry, plates, cfg.data_dir / "learned_labels.json", clock)
    return Recorder(cfg, client, llmap, identity, clock, load_panel(cfg.arrival_stops_path, cfg.arrival_stops_filter))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%Y-%m-%dT%H:%M:%S", stream=sys.stdout)
    ap = argparse.ArgumentParser(description="Grabador de CuandoSubo")
    ap.add_argument("--test", type=int, metavar="N", help="Correr solo N ciclos y salir")
    args = ap.parse_args(argv)
    cfg = Config.from_env()
    if not cfg.oba_key:
        log.critical("OBA_KEY no definida")
        sys.exit(1)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    rec = build(cfg)
    try:
        rec.run(args.test)
    except KeyInvalidError as e:
        log.critical(f"{e}. Revisar OBA_KEY. Espero 10 min antes de salir para no martillar la API.")
        if args.test is None:
            rec.clock.sleep(600)
        sys.exit(2)


if __name__ == "__main__":
    main()
