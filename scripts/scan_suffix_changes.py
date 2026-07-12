"""Scan de sufijos VP_label en grabaciones NDJSON: nuevos y desaparecidos.

Recorre Z:\\grabaciones\\YYYY-MM-DD.ndjson.gz desde 2026-05-24 y por dia junta
el set de sufijos vistos (de los arrays `new` de deltas y keyframes; los `upd`
no traen label). Cachea un JSON por dia para no re-scanear.

Corte: 5 dias consecutivos sin ningun sufijo nunca-antes-visto que no este en
el map v1, o 2026-07-01, lo que ocurra primero. Dias faltantes se saltean sin
contar para la racha.

Salida: scan_suffix_changes_report.json con
  - new_suffixes: no estan en v1 -> first_seen / last_seen / route_ids / labels
  - disappeared_suffixes: estan en v1 y no vuelven a aparecer -> last_seen = `to`
  - cross_check contra desapariciones_api_mayo2026.json (por linea)

Uso:
    python scripts/scan_suffix_changes.py [--start 2026-05-24] [--end 2026-07-01]
"""

import argparse
import gzip
import json
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
GRABACIONES = Path(r"Z:\grabaciones")
CACHE_DIR = PROJECT_DIR / "experiments" / "suffix_scan_cache"
V1_MAP = PROJECT_DIR / "LABEL_LINE_MAP.json"
DESAPARICIONES = PROJECT_DIR / "desapariciones_api_mayo2026.json"
REPORT = PROJECT_DIR / "experiments" / "scan_suffix_changes_report.json"

MAX_SAMPLE_LABELS = 5
STOP_STREAK = 5


def scan_day(day_str: str) -> dict | None:
    """Devuelve {suffix: {route_ids, labels, vehicles}} para un dia, con cache."""
    cache_file = CACHE_DIR / f"{day_str}.json"
    if cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    src = GRABACIONES / f"{day_str}.ndjson.gz"
    if not src.exists():
        return None

    suffixes: dict[str, dict] = {}
    with gzip.open(src, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                continue
            for v in frame.get("new", []):
                label = v.get("label") or ""
                if "-" not in label:
                    continue
                suffix = label.rsplit("-", 1)[-1]
                if not suffix:
                    continue
                entry = suffixes.setdefault(
                    suffix, {"route_ids": {}, "labels": [], "vehicle_ids": []}
                )
                rid = v.get("route_id")
                if rid:
                    entry["route_ids"][rid] = entry["route_ids"].get(rid, 0) + 1
                if label not in entry["labels"] and len(entry["labels"]) < MAX_SAMPLE_LABELS:
                    entry["labels"].append(label)
                vid = v.get("id")
                if vid and vid not in entry["vehicle_ids"]:
                    entry["vehicle_ids"].append(vid)

    # compactar: vehicle_ids -> conteo
    for entry in suffixes.values():
        entry["vehicles"] = len(entry.pop("vehicle_ids"))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(suffixes, f, ensure_ascii=False)
    print(f"  {day_str}: {len(suffixes)} sufijos", flush=True)
    return suffixes


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-05-24")
    ap.add_argument("--end", default="2026-07-01")
    ap.add_argument("--no-early-stop", action="store_true",
                    help="ignorar la regla de 5 dias sin sufijos nuevos")
    args = ap.parse_args()

    with open(V1_MAP, encoding="utf-8") as f:
        map_data = json.load(f)
    # soporta schema v1 (map[sufijo]) y v2 (lines[linea].suffixes)
    v1: dict[str, dict] = {}
    if "map" in map_data:
        for sfx, info in map_data["map"].items():
            v1[sfx] = {"line": info.get("line"), "lines": info.get("lines", []),
                       "agencyName": info.get("agencyName")}
    else:
        # v3: sufijos conocidos = lines (AMBA) + other_lines (interior),
        # para no reportar homonimos del interior como "nuevos"
        agency_names = {}
        sections = [map_data["lines"]] + ([map_data["other_lines"]]
                                          if "other_lines" in map_data else [])
        for section in sections:
            for line, e in section.items():
                for a in e["agencies"]:
                    agency_names[a["agencyId"]] = a["agencyName"]
                for s in e["suffixes"]:
                    v1[s["suffix"]] = {"line": line, "lines": [line],
                                       "agencyName": agency_names.get(s.get("agencyId"))}
        pending_path = V1_MAP.parent.parent / "proyectoconsola" / "pending_label_work.json"
        if pending_path.exists():
            with open(pending_path, encoding="utf-8") as f:
                for sfx, c in json.load(f).get("pending", {}).items():
                    v1.setdefault(sfx, {"line": None, "lines": c.get("candidates", []),
                                        "agencyName": c.get("agencyName")})
    v1_suffixes = set(v1.keys())
    # linea -> sufijos v1 (solo resueltas) para el cross-check
    line_to_suffixes: dict[str, list[str]] = {}
    for sfx, info in v1.items():
        if info.get("line"):
            line_to_suffixes.setdefault(info["line"], []).append(sfx)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    per_day: dict[str, dict] = {}
    seen_ever: set[str] = set()
    first_seen: dict[str, str] = {}
    last_seen: dict[str, str] = {}
    streak = 0
    stopped_at = None

    for d in daterange(start, end):
        ds = d.isoformat()
        day_data = scan_day(ds)
        if day_data is None:
            print(f"  {ds}: sin archivo, salteado", flush=True)
            continue
        per_day[ds] = day_data

        new_unknown_today = [
            s for s in day_data if s not in seen_ever and s not in v1_suffixes
        ]
        for s in day_data:
            if s not in first_seen:
                first_seen[s] = ds
            last_seen[s] = ds
        seen_ever.update(day_data)

        if new_unknown_today:
            streak = 0
        else:
            streak += 1
            if streak >= STOP_STREAK and not args.no_early_stop:
                stopped_at = ds
                print(f"Corte: {STOP_STREAK} dias sin sufijos nuevos (hasta {ds})", flush=True)
                break

    scanned_days = sorted(per_day.keys())
    last_day = scanned_days[-1]

    # --- sufijos nuevos (no en v1) ---
    new_suffixes = {}
    for s in sorted(seen_ever - v1_suffixes, key=lambda x: (first_seen[x], x)):
        route_ids: dict[str, int] = {}
        labels: list[str] = []
        max_vehicles = 0
        days_present = 0
        for ds in scanned_days:
            e = per_day[ds].get(s)
            if not e:
                continue
            days_present += 1
            max_vehicles = max(max_vehicles, e["vehicles"])
            for rid, n in e["route_ids"].items():
                route_ids[rid] = route_ids.get(rid, 0) + n
            for lb in e["labels"]:
                if lb not in labels and len(labels) < MAX_SAMPLE_LABELS:
                    labels.append(lb)
        new_suffixes[s] = {
            "first_seen": first_seen[s],
            "last_seen": last_seen[s],
            "days_present": days_present,
            "max_vehicles_dia": max_vehicles,
            "route_ids": dict(sorted(route_ids.items(), key=lambda kv: -kv[1])),
            "sample_labels": labels,
        }

    # --- sufijos v1 desaparecidos (no vistos el ultimo dia y con last_seen < last_day) ---
    disappeared = {}
    still_active = []
    never_seen = []
    for s in sorted(v1_suffixes):
        if s not in seen_ever:
            never_seen.append(s)
        elif last_seen[s] < last_day:
            disappeared[s] = {
                "line": v1[s].get("line"),
                "lines": v1[s].get("lines", []),
                "agencyName": v1[s].get("agencyName"),
                "last_seen": last_seen[s],
            }
        else:
            still_active.append(s)

    # --- cross-check contra desapariciones (por linea) ---
    with open(DESAPARICIONES, encoding="utf-8") as f:
        desap = json.load(f)
    reported_lines = set()
    for lines in desap["disappearance_order"].values():
        reported_lines.update(lines)

    cross_check = {"consistent": [], "line_reported_but_suffix_alive": [],
                   "suffix_gone_line_not_reported": []}
    for line, sfxs in sorted(line_to_suffixes.items()):
        gone = [s for s in sfxs if s in disappeared]
        alive = [s for s in sfxs if s in still_active]
        if line in reported_lines:
            if gone and not alive:
                cross_check["consistent"].append(
                    {"line": line, "suffixes_gone": {s: disappeared[s]["last_seen"] for s in gone}})
            elif alive:
                cross_check["line_reported_but_suffix_alive"].append(
                    {"line": line, "suffixes_alive": alive,
                     "suffixes_gone": {s: disappeared[s]["last_seen"] for s in gone}})
        elif gone:
            cross_check["suffix_gone_line_not_reported"].append(
                {"line": line, "suffixes_gone": {s: disappeared[s]["last_seen"] for s in gone}})

    report = {
        "scan_range": {"start": args.start, "end_requested": args.end,
                       "last_day_scanned": last_day, "stopped_early_at": stopped_at,
                       "days_scanned": len(scanned_days)},
        "totals": {"suffixes_seen": len(seen_ever),
                   "new_suffixes": len(new_suffixes),
                   "v1_disappeared": len(disappeared),
                   "v1_still_active": len(still_active),
                   "v1_never_seen_in_range": len(never_seen)},
        "new_suffixes": new_suffixes,
        "disappeared_suffixes": disappeared,
        "v1_never_seen_in_range": never_seen,
        "cross_check_vs_desapariciones": cross_check,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nReporte: {REPORT}")
    print(json.dumps(report["totals"], indent=2))


if __name__ == "__main__":
    main()
