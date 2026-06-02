"""
collect.py — Extrae vehículos de NDJSON y actualiza fleet_db.json.

Guarda TODOS los vehículos (con o sin línea asignada).
Trackea first_seen / last_seen por vehículo.
Registra run_dates en __meta__.

Modos:
  python collect.py                        -> horas pico, dias 2026-05-23 al 30
  python collect.py --all DATE             -> todos los frames de un dia
  python collect.py --all DATE1 DATE2      -> todos los frames de un rango
"""

import gzip
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

GRABACIONES_DIR = Path(r"Z:\grabaciones")
SCRIPT_DIR = Path(__file__).parent
FLEET_DB_PATH = SCRIPT_DIR / "fleet_db.json"
LABEL_LINE_MAP_PATH = SCRIPT_DIR.parent / "LABEL_LINE_MAP.json"

DEFAULT_DATES = [f"2026-05-{d:02d}" for d in range(23, 31)]
PEAK_HOURS_UTC = {13, 14, 15, 16, 18, 19, 21, 22, 23}

NEW_PLATE_RE = re.compile(r'^[A-Z]{2}\d{3}[A-Z]{2}$')
OLD_PLATE_RE = re.compile(r'^[A-Z]{3}\d{3}$')

NEW_PLATE_BREAKPOINTS = [
    (0,    2016), (1000, 2017), (2000, 2017), (2200, 2018),
    (3000, 2018), (3400, 2019), (4000, 2019), (4100, 2020),
    (4600, 2021), (5000, 2021), (5150, 2022), (5600, 2022),
    (5800, 2023), (6000, 2023), (6450, 2024), (7000, 2024),
    (7236, 2025), (8000, 2025),
]

OLD_PLATE_BREAKPOINTS = [
    ("JN", 2011), ("KU", 2012), ("MB", 2013),
    ("NM", 2014), ("ON", 2015), ("PM", 2016),
]

MAX_LINE = 200
META_KEY = "__meta__"


def is_peak(t: int) -> bool:
    return datetime.fromtimestamp(t, tz=timezone.utc).hour in PEAK_HOURS_UTC


def estimate_year(raw_plate: str) -> int | None:
    p = raw_plate.replace("-", "").upper()
    if NEW_PLATE_RE.match(p):
        score = (ord(p[0]) - 65) * 26 * 1000 + (ord(p[1]) - 65) * 1000 + int(p[2:5])
        year = NEW_PLATE_BREAKPOINTS[0][1]
        for bp_score, bp_year in NEW_PLATE_BREAKPOINTS:
            if score >= bp_score:
                year = bp_year
            else:
                break
        return year
    if OLD_PLATE_RE.match(p):
        prefix2 = p[:2]
        year = 2010
        for bp, bp_year in OLD_PLATE_BREAKPOINTS:
            if prefix2 >= bp:
                year = bp_year
            else:
                break
        return year
    return None


def load_label_map() -> dict:
    with open(LABEL_LINE_MAP_PATH, encoding="utf-8") as f:
        return json.load(f)["map"]


def resolve_line(label: str, label_map: dict) -> tuple[str | None, str | None]:
    suffix = label.split("-")[-1]
    entry = label_map.get(suffix)
    if not entry:
        return None, None
    line = entry.get("line")
    if not line:
        return None, None
    try:
        if int(line) > MAX_LINE:
            return None, None
    except ValueError:
        return None, None
    return line, entry.get("agencyName", "")


def load_fleet_db() -> dict:
    if FLEET_DB_PATH.exists():
        with open(FLEET_DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {META_KEY: {"run_dates": []}}


def save_fleet_db(db: dict):
    with open(FLEET_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def date_range(start: str, end: str) -> list[str]:
    d1 = date.fromisoformat(start)
    d2 = date.fromisoformat(end)
    out = []
    cur = d1
    while cur <= d2:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def process_day(date_str: str, label_map: dict, db: dict, all_frames: bool) -> tuple[int, int]:
    """Returns (new_vehicles, updated_last_seen)."""
    path = GRABACIONES_DIR / f"{date_str}.ndjson.gz"
    if not path.exists():
        print(f"  [skip] {date_str} no encontrado")
        return 0, 0

    added = 0
    updated = 0
    frames_read = 0
    frames_used = 0

    # Vehicles seen today (to update last_seen once per day)
    seen_today: set[str] = set()

    with gzip.open(path, "rt", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            frames_read += 1
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue

            t = rec.get("t", 0)
            if not all_frames and not is_peak(t):
                continue
            frames_used += 1

            for v in rec.get("new", []):
                plate = v.get("license_plate", "").strip()
                label = v.get("label", "").strip()
                if not plate or not label:
                    continue

                # Update last_seen for any vehicle we see
                if plate in db and plate not in seen_today:
                    if db[plate].get("last_seen", "") < date_str:
                        db[plate]["last_seen"] = date_str
                        updated += 1
                    seen_today.add(plate)
                    continue

                if plate in seen_today:
                    continue

                seen_today.add(plate)

                # New vehicle
                line, agency = resolve_line(label, label_map)
                year = estimate_year(plate)

                db[plate] = {
                    "line": line,
                    "label": label,
                    "agency": agency,
                    "est_year": year,
                    "first_seen": date_str,
                    "last_seen": date_str,
                }
                added += 1

    mode = "todos" if all_frames else "pico"
    print(f"  {date_str} [{mode}]: {frames_used}/{frames_read} frames | +{added} nuevos | {updated} last_seen actualizados")
    return added, updated


def print_summary(db: dict):
    counts: dict[str, int] = defaultdict(int)
    no_line = 0
    for k, v in db.items():
        if k == META_KEY:
            continue
        if v.get("line"):
            counts[v["line"]] += 1
        else:
            no_line += 1
    total = sum(counts.values()) + no_line
    print(f"\n  Total vehiculos: {total}")
    print(f"  Con linea asignada: {sum(counts.values())} en {len(counts)} lineas")
    print(f"  Sin linea asignada: {no_line}")


def main():
    all_frames = False
    dates = DEFAULT_DATES

    args = sys.argv[1:]
    if args and args[0] == "--all":
        all_frames = True
        if len(args) == 2:
            dates = [args[1]]
        elif len(args) >= 3:
            dates = date_range(args[1], args[2])
        else:
            print("Uso: collect.py --all FECHA [FECHA_FIN]")
            sys.exit(1)

    print(f"=== collect.py === modo: {'todos los frames' if all_frames else 'horas pico'}")
    print(f"Fechas: {dates[0]} al {dates[-1]} ({len(dates)} dias)\n")

    if not GRABACIONES_DIR.exists():
        print(f"ERROR: {GRABACIONES_DIR} no encontrado. Verificar SMB.")
        sys.exit(1)

    label_map = load_label_map()
    print(f"LABEL_LINE_MAP: {len(label_map)} entradas")

    db = load_fleet_db()
    if META_KEY not in db:
        db[META_KEY] = {"run_dates": []}

    before = sum(1 for k in db if k != META_KEY)
    print(f"fleet_db.json previo: {before} vehiculos\n")

    total_added = total_updated = 0
    for d in dates:
        added, upd = process_day(d, label_map, db, all_frames)
        total_added += added
        total_updated += upd

    # Registrar run en meta
    run_entry = {
        "date": date.today().isoformat(),
        "mode": "all_frames" if all_frames else "peak",
        "range": [dates[0], dates[-1]],
        "added": total_added,
    }
    db[META_KEY]["run_dates"].append(run_entry)

    save_fleet_db(db)

    print(f"\n--- Resumen ---")
    print(f"Vehiculos nuevos: {total_added}")
    print(f"last_seen actualizados: {total_updated}")
    print(f"Total en fleet_db.json: {sum(1 for k in db if k != META_KEY)}")
    print_summary(db)
    print(f"\nfleet_db.json: {FLEET_DB_PATH}")


if __name__ == "__main__":
    main()
