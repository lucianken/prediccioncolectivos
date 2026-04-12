"""
Grabador de posiciones de colectivos CABA.

Descarga vehiclePositions en protobuf cada 30s, filtra vehículos en el
área de CABA/GBA, computa el delta respecto al ciclo anterior y lo escribe
en un archivo NDJSON + gzip por día (timezone Buenos Aires).

Persistencia en /data/:
  YYYY-MM-DD.ndjson.gz  — datos del día
  state.json            — prev_state para recuperar tras reinicio
  health                — tocado cada ciclo para el HEALTHCHECK de Docker

Uso:
  python grabador.py              # loop infinito
  python grabador.py --test N     # corre N ciclos y sale
"""

import argparse
import gzip
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from google.transit import gtfs_realtime_pb2

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

API_URL = "https://apitransporte.buenosaires.gob.ar/colectivos/vehiclePositions"
FETCH_TIMEOUT = 20          # segundos
CYCLE_INTERVAL = 30         # segundos entre ciclos
KEYFRAME_EVERY = 100        # ciclos entre keyframes completos
GAP_THRESHOLD = 600         # segundos: gap > 10 min → forzar keyframe
DISK_MIN_GB = 2.0           # parar escritura si hay menos de esto en /data
DISK_CHECK_EVERY = 100      # ciclos entre chequeos de disco
MAX_CONSEC_ERRORS = 10      # a partir de aquí loguear CRITICAL

# Bounding box CABA + GBA (lat sur, lat norte, lon oeste, lon este)
LAT_MIN, LAT_MAX = -35.1, -34.3
LON_MIN, LON_MAX = -59.1, -57.9

# Timezone Buenos Aires (UTC-3, sin DST)
TZ_BA = timezone(timedelta(hours=-3))

DATA_DIR = Path("/data")
STATE_FILE = DATA_DIR / "state.json"
HEALTH_FILE = DATA_DIR / "health"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("grabador")

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def get_credentials() -> tuple[str, str]:
    client_id = os.environ.get("BA_API_CLIENT_ID", "")
    client_secret = os.environ.get("BA_API_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        log.critical("BA_API_CLIENT_ID o BA_API_CLIENT_SECRET no definidos")
        sys.exit(1)
    return client_id, client_secret


def fetch_protobuf(client_id: str, client_secret: str) -> bytes:
    """Descarga vehiclePositions en protobuf. Lanza excepción si falla."""
    url = f"{API_URL}?client_id={client_id}&client_secret={client_secret}"
    resp = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": "grabador-posiciones/1.0"})
    resp.raise_for_status()
    return resp.content


def parse_vehicles(data: bytes) -> list[dict]:
    """
    Parsea el protobuf GTFS-RT y devuelve lista de dicts con los campos relevantes.
    Filtra por bounds geográficos CABA/GBA.
    Omite bearing, occupancy_status y congestion_level (siempre 0 en la API BA).
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)

    vehicles = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        lat = v.position.latitude
        lon = v.position.longitude
        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            continue
        vehicles.append({
            "id": v.vehicle.id,
            "label": v.vehicle.label,
            "license_plate": v.vehicle.license_plate,
            "route_id": v.trip.route_id,
            "trip_id": v.trip.trip_id,
            "direction_id": v.trip.direction_id,
            "start_date": v.trip.start_date,
            "start_time": v.trip.start_time,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "speed": round(v.position.speed, 2),
            "odo": v.position.odometer,
            "stop_id": v.stop_id,
            "seq": v.current_stop_sequence,
            "status": v.current_status,
            "ts": v.timestamp,
        })
    return vehicles


def ndjson_path() -> Path:
    """Devuelve el path del archivo del día actual (timezone Buenos Aires)."""
    date_str = datetime.now(TZ_BA).strftime("%Y-%m-%d")
    return DATA_DIR / f"{date_str}.ndjson.gz"


def append_frame(frame: dict) -> None:
    """Escribe una línea JSON al archivo gzip del día."""
    path = ndjson_path()
    with gzip.open(path, "at", encoding="utf-8") as f:
        f.write(json.dumps(frame, ensure_ascii=False) + "\n")


def save_state(curr_map: dict) -> None:
    """Persiste prev_state en disco para recuperar tras reinicio."""
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "vehicles": curr_map}, f)
    tmp.replace(STATE_FILE)  # reemplazo atómico


def load_state() -> tuple[dict, float]:
    """
    Carga prev_state desde disco.
    Devuelve (vehicles_dict, saved_at_unix_ts).
    Si no existe o está corrupto, devuelve ({}, 0).
    """
    if not STATE_FILE.exists():
        return {}, 0.0
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("vehicles", {}), data.get("ts", 0.0)
    except Exception as e:
        log.warning(f"No se pudo leer state.json: {e}")
        return {}, 0.0


def check_disk_space() -> float:
    """Retorna GB libres en /data."""
    usage = shutil.disk_usage(DATA_DIR)
    return usage.free / (1024 ** 3)


def touch_health() -> None:
    HEALTH_FILE.touch()


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def run(max_cycles: int | None = None) -> None:
    from delta import compute_delta, make_keyframe

    client_id, client_secret = get_credentials()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Recuperar estado previo
    prev_state, saved_at = load_state()
    now = time.time()
    gap = now - saved_at if saved_at > 0 else float("inf")
    force_keyframe = gap > GAP_THRESHOLD or not prev_state

    if saved_at > 0 and gap > GAP_THRESHOLD:
        log.warning(f"Gap detectado: {gap:.0f}s desde último ciclo guardado")
    elif not saved_at:
        log.info("Sin state.json previo, arrancando desde cero")

    cycle_count = 0
    consecutive_errors = 0
    disk_ok = True

    log.info("Grabador iniciado. Presionar Ctrl+C para detener.")

    while True:
        t0 = time.time()

        # --- 1. Fetch ---
        try:
            raw = fetch_protobuf(client_id, client_secret)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            level = logging.CRITICAL if consecutive_errors >= MAX_CONSEC_ERRORS else logging.WARNING
            log.log(level, f"Error fetch (consec={consecutive_errors}): {e}")
            _sleep_remainder(t0)
            if max_cycles is not None and cycle_count >= max_cycles:
                break
            continue

        # --- 2. Parsear ---
        try:
            vehicles = parse_vehicles(raw)
        except Exception as e:
            log.error(f"Error parse protobuf: {e} | primeros 100 bytes: {raw[:100]!r}")
            _sleep_remainder(t0)
            if max_cycles is not None and cycle_count >= max_cycles:
                break
            continue

        # --- 3. Chequeo de disco (cada DISK_CHECK_EVERY ciclos) ---
        if cycle_count % DISK_CHECK_EVERY == 0:
            free_gb = check_disk_space()
            disk_ok = free_gb >= DISK_MIN_GB
            if not disk_ok:
                log.critical(f"Disco lleno: solo {free_gb:.2f} GB libres en /data. Pausa de escritura.")

        # --- 4. Calcular frame ---
        is_keyframe = force_keyframe or (cycle_count % KEYFRAME_EVERY == 0)

        if is_keyframe:
            frame = make_keyframe(vehicles)
            if force_keyframe and saved_at > 0:
                # Insertar registro de gap antes del keyframe
                gap_record = {
                    "t": int(now),
                    "gap": True,
                    "gap_seconds": int(gap),
                    "reason": "restart",
                }
                if disk_ok:
                    try:
                        append_frame(gap_record)
                    except Exception as e:
                        log.error(f"Error escribiendo gap record: {e}")
            force_keyframe = False
            prev_state = {v["id"]: v for v in vehicles}
        else:
            frame, prev_state = compute_delta(prev_state, vehicles)

        # --- 5. Escribir al archivo del día ---
        if disk_ok:
            try:
                append_frame(frame)
            except Exception as e:
                log.error(f"Error escribiendo frame: {e}")
                # Reintentar una vez
                try:
                    append_frame(frame)
                except Exception as e2:
                    log.critical(f"Segundo intento fallido al escribir frame: {e2}")

        # --- 6. Persistir state ---
        try:
            save_state(prev_state)
        except Exception as e:
            log.error(f"Error guardando state.json: {e}")

        # --- 7. Health ---
        try:
            touch_health()
        except Exception as e:
            log.warning(f"Error tocando health file: {e}")

        # --- 8. Log del ciclo ---
        n_new = len(frame.get("new", []))
        n_del = len(frame.get("del", []))
        n_upd = len(frame.get("upd", []))
        kf_tag = " [KF]" if is_keyframe else ""
        log.info(
            f"ciclo={cycle_count} veh={len(vehicles)} "
            f"new={n_new} del={n_del} upd={n_upd}{kf_tag} "
            f"errs={consecutive_errors}"
        )

        cycle_count += 1
        if max_cycles is not None and cycle_count >= max_cycles:
            log.info(f"--test: {max_cycles} ciclos completados, saliendo.")
            break

        _sleep_remainder(t0)


def _sleep_remainder(t0: float) -> None:
    elapsed = time.time() - t0
    sleep_time = max(0.0, CYCLE_INTERVAL - elapsed)
    if sleep_time > 0:
        time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grabador de posiciones VP")
    parser.add_argument("--test", type=int, metavar="N", help="Correr solo N ciclos y salir")
    args = parser.parse_args()
    run(max_cycles=args.test)
