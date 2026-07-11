"""Aplica el resultado de scan_suffix_changes al LABEL_LINE_MAP v2 y al archivo
unificado de trabajo pendiente (pending_label_work.json v2 en proyectoconsola).

1. Setea `to` (ultimo dia visto) en los sufijos del map que desaparecieron
   (ambas copias del map).
2. Mergea el scan en pending_label_work.json:
   - sufijos nuevos (no en map ni en pending) -> entrada `identify` con pistas
     frescas (route_ids del scan resueltos contra ROUTE_AGENCY_MAP actual)
   - sufijos ya pendientes -> actualiza `to`/evidencia sin pisar `line` ni notas
3. NO genera el MD: correr `node scripts/promote_pending.js --render-only`
   en proyectoconsola despues de este script.

Uso:
    python scripts/apply_scan_results.py
"""

import json
import re
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONSOLA_DIR = PROJECT_DIR.parent / "proyectoconsola"

REPORT = PROJECT_DIR / "experiments" / "scan_suffix_changes_report.json"
MAP_PATHS = [CONSOLA_DIR / "LABEL_LINE_MAP.json", PROJECT_DIR / "LABEL_LINE_MAP.json"]
PENDING_JSON = CONSOLA_DIR / "pending_label_work.json"
ROUTE_AGENCY_MAP = CONSOLA_DIR / "ROUTE_AGENCY_MAP.json"

TOP_HINTS = 4


def load_json(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p: Path, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def fresh_hints(route_ids: dict, ram: dict) -> tuple[list[str], list[str]]:
    routes, agencies = ram["routes"], ram["agencies"]
    hints, cand_counts = [], {}
    for rid, n in route_ids.items():
        r = routes.get(rid)
        if r:
            ag = agencies.get(r["agencyId"], {}).get("name", f"agencyId {r['agencyId']}")
            if len(hints) < TOP_HINTS:
                hints.append(f"rid {rid} = {r['shortName']} ({ag}) [{n} obs]")
            m = re.match(r"(\d+)", r.get("shortName") or "")
            if m:
                cand_counts[m.group(1)] = cand_counts.get(m.group(1), 0) + n
        elif len(hints) < TOP_HINTS:
            hints.append(f"rid {rid} sin match en ROUTE_AGENCY_MAP [{n} obs]")
    return hints, [ln for ln, _ in sorted(cand_counts.items(), key=lambda kv: -kv[1])]


def main() -> None:
    report = load_json(REPORT)
    ram = load_json(ROUTE_AGENCY_MAP)
    disappeared = report["disappeared_suffixes"]
    last_day = report["scan_range"]["last_day_scanned"]

    # 1) fechas `to` en el map (ambas copias, misma data)
    map_data = load_json(MAP_PATHS[0])
    n_map = 0
    for entry in map_data["lines"].values():
        for s in entry["suffixes"]:
            d = disappeared.get(s["suffix"])
            if d and s["to"] is None:
                s["to"] = d["last_seen"]
                n_map += 1
    for p in MAP_PATHS:
        save_json(p, map_data)
    known_suffixes = {s["suffix"] for e in map_data["lines"].values() for s in e["suffixes"]}
    print(f"Fechas `to` aplicadas en LABEL_LINE_MAP: {n_map} (ambas copias)")

    # 2) merge en pending unificado
    pending_data = load_json(PENDING_JSON)
    assert pending_data.get("version") == 2, "pending no es v2 — correr consolidate_pending.py"
    pending = pending_data["pending"]

    n_new = n_updated = 0
    for sfx, v in report["new_suffixes"].items():
        if sfx in known_suffixes:
            continue
        hints, candidates = fresh_hints(v.get("route_ids", {}), ram)
        to = None if v["last_seen"] == last_day else v["last_seen"]
        if sfx in pending:
            e = pending[sfx]
            e.setdefault("evidence", {})
            e["evidence"]["route_hints"] = hints
            e["evidence"]["sample_labels"] = v.get("sample_labels", [])
            e["evidence"]["max_vehicles_dia"] = v.get("max_vehicles_dia")
            e["evidence"]["still_active"] = to is None
            if e.get("to") is None and to:
                e["to"] = to
            if not e.get("candidates"):
                e["candidates"] = candidates
            n_updated += 1
        else:
            pending[sfx] = {
                "status": "identify",
                "line": None,
                "candidates": candidates,
                "agencyId": None,
                "agencyName": None,
                "from": v["first_seen"],
                "to": to,
                "evidence": {"route_hints": hints,
                             "sample_labels": v.get("sample_labels", []),
                             "max_vehicles_dia": v.get("max_vehicles_dia"),
                             "still_active": to is None},
                "notes": [],
            }
            n_new += 1

    # sufijos pendientes que desaparecieron -> fechar
    n_dated = 0
    for sfx, e in pending.items():
        d = disappeared.get(sfx)
        if d and e.get("to") is None:
            e["to"] = d["last_seen"]
            n_dated += 1

    pending_data["updated"] = date.today().isoformat()
    pending_data["scan_window"] = {"start": report["scan_range"]["start"], "end": last_day}
    save_json(PENDING_JSON, pending_data)
    print(f"Pending actualizado: +{n_new} nuevos, {n_updated} refrescados, {n_dated} fechados")
    print("Ahora correr: cd ../proyectoconsola && node scripts/promote_pending.js --render-only")


if __name__ == "__main__":
    main()
