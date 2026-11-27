"""One-off: consolida CANDIDATES.json dentro de pending_label_work.json (schema v2).

Deja UN solo archivo de trabajo en proyectoconsola:
  pending_label_work.json v2: { pending: { sufijo -> entrada } }
  - status: "identify" (sufijo nuevo sin linea) | "disambiguate" (ex-CANDIDATES)
  - line: null  <- la resolucion se anota aca; luego `node scripts/promote_pending.js`
  - candidates: pistas de linea (ex-CANDIDATES: las candidatas; identify: derivadas
    de los route_ids del scan resueltos contra ROUTE_AGENCY_MAP FRESCO)
  - evidence.route_hints regenerados desde cero con el ROUTE_AGENCY_MAP post-cambio
    de flota (las pistas del build 31/05 se descartan por obsoletas)

Borra CANDIDATES.json de ambos proyectos. El MD se regenera con
`node scripts/promote_pending.js --render-only` (proyectoconsola).
"""

import json
import re
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONSOLA_DIR = PROJECT_DIR.parent / "proyectoconsola"

REPORT = PROJECT_DIR / "experiments" / "scan_suffix_changes_report.json"
ROUTE_AGENCY_MAP = CONSOLA_DIR / "ROUTE_AGENCY_MAP.json"
PENDING_JSON = CONSOLA_DIR / "pending_label_work.json"
CAND_PATHS = [CONSOLA_DIR / "CANDIDATES.json", PROJECT_DIR / "CANDIDATES.json"]
MAP_PATH = CONSOLA_DIR / "LABEL_LINE_MAP.json"

TOP_HINTS = 4


def load_json(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fresh_hints(route_ids: dict, ram: dict) -> tuple[list[str], list[str]]:
    """(route_hints legibles, candidatas de linea) desde ROUTE_AGENCY_MAP fresco."""
    routes, agencies = ram["routes"], ram["agencies"]
    hints, cand_counts = [], {}
    for rid, n in list(route_ids.items()):
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
    candidates = [ln for ln, _ in sorted(cand_counts.items(), key=lambda kv: -kv[1])]
    return hints, candidates


def main() -> None:
    report = load_json(REPORT)
    ram = load_json(ROUTE_AGENCY_MAP)
    old_pending = load_json(PENDING_JSON)
    cand_data = load_json(CAND_PATHS[0])
    known_suffixes = {
        s["suffix"]
        for e in load_json(MAP_PATH)["lines"].values()
        for s in e["suffixes"]
    }

    ram_build = ram.get("buildTime", "")
    print(f"ROUTE_AGENCY_MAP build: {ram_build} ({len(ram['routes'])} rutas)")
    assert ram_build >= "2026-07", "ROUTE_AGENCY_MAP no parece fresco — correr build_route_map.js"

    pending: dict[str, dict] = {}

    def scan_evidence(sfx: str, v: dict) -> dict:
        rids = report["new_suffixes"].get(sfx, {}).get("route_ids", {})
        hints, candidates = fresh_hints(rids, ram) if rids else ([], [])
        return {
            "route_hints": hints,
            "candidates": candidates,
            "sample_labels": v.get("sample_labels", []),
            "max_vehicles_dia": v.get("max_vehicles_dia"),
            "still_active": v.get("still_active"),
        }

    # 1) sufijos nuevos del scan (identify) — pistas regeneradas con map fresco
    for section in ("new_suffixes_post_fleet_change", "new_suffixes_pre_existing_unmapped"):
        pre_existing = section.endswith("unmapped")
        for sfx, v in old_pending.get(section, {}).items():
            ev = scan_evidence(sfx, v)
            notes = [h["context"] + ": " + h["hint"] if h.get("hint") else h.get("context", "")
                     for h in v.get("previous_notes", [])]
            if pre_existing:
                notes.append("Ya existia antes del cambio de flota: from real anterior "
                             "y desconocido (usar 2026-03-28 como el resto del map inicial)")
            pending[sfx] = {
                "status": "identify",
                "line": None,
                "candidates": ev.pop("candidates"),
                "agencyId": None,
                "agencyName": None,
                "from": v["from"],
                "to": None if v.get("still_active") else v.get("last_seen"),
                "evidence": ev,
                "notes": notes,
            }

    # 2) ex-CANDIDATES (disambiguate) — from/to/agency autoritativos de CANDIDATES,
    #    notas y scan_status del pending viejo
    old_disamb = old_pending.get("to_disambiguate", {})
    for sfx, c in cand_data["candidates"].items():
        d = old_disamb.get(sfx, {})
        notes = [h["context"] + ": " + h["hint"] if h.get("hint") else h.get("context", "")
                 for h in d.get("previous_notes", [])]
        pending[sfx] = {
            "status": "disambiguate",
            "line": None,
            "candidates": c.get("lines", []),
            "agencyId": c.get("agencyId"),
            "agencyName": c.get("agencyName"),
            "from": c["from"],
            "to": c["to"],
            "evidence": {"scan_status": d.get("scan_status")},
            "notes": notes,
        }

    # 3) heredados de snapshots viejos, no vistos en el scan (identify, sin evidencia)
    n_before_legacy = len(pending)
    n_legacy_skipped = 0
    for sfx, v in old_pending.get("legacy_snapshot_pending_not_seen_in_scan", {}).items():
        if sfx in pending or sfx in known_suffixes:
            n_legacy_skipped += 1
            continue
        notes = [f"({h.get('context', '')}) {h.get('hint') or 'sin hint'}"
                 for h in v.get("hints", [])]
        notes.append("No visto en la ventana del scan 2026-05-24 → 2026-07-01; "
                     "probablemente obsoleto tras el cambio de flota")
        pending[sfx] = {
            "status": "identify",
            "line": None,
            "candidates": [],
            "agencyId": None,
            "agencyName": None,
            "from": None,
            "to": None,
            "evidence": {},
            "notes": notes,
        }

    def sort_key(s: str):
        return (0, int(s)) if s.isdigit() else (1, s)

    unified = {
        "version": 2,
        "updated": date.today().isoformat(),
        "description": ("Unico archivo de trabajo sobre LABEL_LINE_MAP (absorbe CANDIDATES). "
                        "Para resolver un sufijo: completar 'line' (y agencyId/agencyName si "
                        "se conocen) y correr `node scripts/promote_pending.js` — mueve la "
                        "entrada al map, sincroniza el espejo y regenera el MD. "
                        "Pistas (candidates/route_hints) generadas con ROUTE_AGENCY_MAP "
                        f"build {ram_build[:10]}."),
        "scan_window": old_pending.get("scan_window"),
        "pending": {s: pending[s] for s in sorted(pending, key=sort_key)},
        "v1_suffixes_never_seen_in_scan_window":
            old_pending.get("v1_suffixes_never_seen_in_scan_window", []),
    }

    n_scan_new = (len(old_pending.get("new_suffixes_post_fleet_change", {}))
                  + len(old_pending.get("new_suffixes_pre_existing_unmapped", {})))
    n_cand = len(cand_data["candidates"])
    n_legacy_total = len(old_pending.get("legacy_snapshot_pending_not_seen_in_scan", {}))
    n_legacy_added = len(pending) - n_before_legacy
    # scan-new y candidates no se pisan entre sí (nuevos = no estaban en v1; candidates sí)
    assert n_before_legacy == n_scan_new + n_cand, (
        f"conteo scan+candidates no cierra: {n_before_legacy} != {n_scan_new} + {n_cand}")
    assert n_legacy_added + n_legacy_skipped == n_legacy_total, (
        f"conteo legacy no cierra: {n_legacy_added} + {n_legacy_skipped} != {n_legacy_total}")
    print(f"Conteos: {n_scan_new} scan-new + {n_cand} ex-candidates + "
          f"{n_legacy_added} legacy (de {n_legacy_total}, {n_legacy_skipped} ya cubiertos/mapeados)")

    with open(PENDING_JSON, "w", encoding="utf-8") as f:
        json.dump(unified, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Escrito: {PENDING_JSON} ({len(pending)} pendientes: "
          f"{sum(1 for p in pending.values() if p['status'] == 'identify')} identify, "
          f"{sum(1 for p in pending.values() if p['status'] == 'disambiguate')} disambiguate)")

    for p in CAND_PATHS:
        if p.exists():
            p.unlink()
            print(f"Eliminado: {p}")

    spot = pending.get("4852", {})
    print("\nSpot check 4852:", json.dumps(
        {"candidates": spot.get("candidates"), "route_hints": spot.get("evidence", {}).get("route_hints")},
        ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
