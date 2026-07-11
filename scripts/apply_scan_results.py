"""Aplica el resultado de scan_suffix_changes al LABEL_LINE_MAP v2 y genera
el archivo unificado de trabajo pendiente.

1. Setea `to` (ultimo dia visto) en los sufijos desaparecidos:
   - resueltos -> LABEL_LINE_MAP.json (ambas copias)
   - ambiguos  -> CANDIDATES.json (ambas copias)
2. Genera proyectoconsola/PENDING_LABEL_WORK.md + pending_label_work.json
   (unico archivo de trabajo pendiente; reemplaza PENDING_DISAMBIGUATION.md).

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
MAP_PATHS = [PROJECT_DIR / "LABEL_LINE_MAP.json", CONSOLA_DIR / "LABEL_LINE_MAP.json"]
CAND_PATHS = [PROJECT_DIR / "CANDIDATES.json", CONSOLA_DIR / "CANDIDATES.json"]
ROUTE_AGENCY_MAP = CONSOLA_DIR / "ROUTE_AGENCY_MAP.json"
OLD_PENDING = CONSOLA_DIR / "PENDING_DISAMBIGUATION.md"
NEW_PENDING_MD = CONSOLA_DIR / "PENDING_LABEL_WORK.md"
NEW_PENDING_JSON = CONSOLA_DIR / "pending_label_work.json"

FLEET_CHANGE_CUTOFF = "2026-06-10"  # first_seen >= esto -> sufijo del cambio de flota
SCAN_START = "2026-05-24"


def load_json(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p: Path, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def apply_to_dates(report: dict) -> tuple[int, int]:
    """Setea `to` en map y candidates (ambas copias). Retorna (n_map, n_cand)."""
    disappeared = report["disappeared_suffixes"]
    n_map = n_cand = 0

    map_data = load_json(MAP_PATHS[0])
    for entry in map_data["lines"].values():
        for s in entry["suffixes"]:
            d = disappeared.get(s["suffix"])
            if d and s["to"] is None:
                s["to"] = d["last_seen"]
                n_map += 1

    cand_data = load_json(CAND_PATHS[0])
    for sfx, c in cand_data["candidates"].items():
        d = disappeared.get(sfx)
        if d and c["to"] is None:
            c["to"] = d["last_seen"]
            n_cand += 1

    for p in MAP_PATHS:
        save_json(p, map_data)
    for p in CAND_PATHS:
        save_json(p, cand_data)
    return n_map, n_cand


def parse_old_pending(md_text: str) -> dict[str, dict]:
    """Extrae items abiertos `- [ ] sufijo \\`X\\` -> hint` con su seccion."""
    items: dict[str, dict] = {}
    section = subsection = ""
    for line in md_text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            subsection = ""
        elif line.startswith("### "):
            subsection = line[4:].strip()
        else:
            m = re.match(r"- \[ \] sufijo `(\w+)`(?:\s*→\s*(.*))?", line)
            if m:
                sfx, hint = m.group(1), (m.group(2) or "").strip()
                prev = items.get(sfx)
                context = f"{section} / {subsection}".strip(" /")
                if prev:  # snapshot mas nuevo pisa al viejo
                    prev["hints"].append({"context": context, "hint": hint})
                else:
                    items[sfx] = {"hints": [{"context": context, "hint": hint}]}
    return items


def route_hints(route_ids: dict[str, int], ram: dict, top: int = 4) -> list[str]:
    """['shortName (AGENCIA) [n obs]', ...] para los top route_ids."""
    routes, agencies = ram["routes"], ram["agencies"]
    out = []
    for rid, n in list(route_ids.items())[:top]:
        r = routes.get(rid)
        if r:
            ag = agencies.get(r["agencyId"], {}).get("name", f"agencyId {r['agencyId']}")
            out.append(f"rid {rid} = {r['shortName']} ({ag}) [{n} obs]")
        else:
            out.append(f"rid {rid} sin match en ROUTE_AGENCY_MAP [{n} obs]")
    return out


def main() -> None:
    report = load_json(REPORT)
    ram = load_json(ROUTE_AGENCY_MAP)
    old_items = parse_old_pending(OLD_PENDING.read_text(encoding="utf-8")) if OLD_PENDING.exists() else {}

    n_map, n_cand = apply_to_dates(report)
    print(f"Fechas `to` aplicadas: {n_map} en LABEL_LINE_MAP, {n_cand} en CANDIDATES")

    cand_data = load_json(CAND_PATHS[0])
    new_sfx = report["new_suffixes"]
    disappeared = report["disappeared_suffixes"]
    last_day = report["scan_range"]["last_day_scanned"]

    post_change = {s: v for s, v in new_sfx.items() if v["first_seen"] >= FLEET_CHANGE_CUTOFF}
    baseline = {s: v for s, v in new_sfx.items() if v["first_seen"] < FLEET_CHANGE_CUTOFF}

    def scan_status(sfx: str) -> str:
        if sfx in new_sfx:
            v = new_sfx[sfx]
            alive = v["last_seen"] == last_day
            return f"visto {v['first_seen']}→{v['last_seen']}" + ("" if alive else " (ya no aparece)")
        if sfx in disappeared:
            return f"desaparecido, ultimo dia {disappeared[sfx]['last_seen']}"
        return "no visto en la ventana del scan"

    # ---------- JSON ----------
    def pack_new(d: dict) -> dict:
        out = {}
        for sfx, v in sorted(d.items(), key=lambda kv: (kv[1]["first_seen"], int(kv[0]) if kv[0].isdigit() else 0)):
            out[sfx] = {
                "line": None,  # <- completar manualmente
                "from": v["first_seen"],
                "last_seen": v["last_seen"],
                "still_active": v["last_seen"] == last_day,
                "max_vehicles_dia": v["max_vehicles_dia"],
                "route_hints": route_hints(v["route_ids"], ram),
                "sample_labels": v["sample_labels"],
                "previous_notes": [h for h in old_items.pop(sfx, {}).get("hints", [])],
            }
        return out

    to_disambiguate = {}
    for sfx, c in cand_data["candidates"].items():
        to_disambiguate[sfx] = {
            "lines": c["lines"],
            "agencyName": c["agencyName"],
            "from": c["from"],
            "to": c["to"],
            "scan_status": scan_status(sfx),
            "previous_notes": [h for h in old_items.pop(sfx, {}).get("hints", [])],
        }

    legacy = {sfx: v for sfx, v in old_items.items()}

    pending = {
        "generated": date.today().isoformat(),
        "description": ("Unico archivo de trabajo pendiente sobre LABEL_LINE_MAP. "
                        "Al resolver un sufijo: agregarlo a LABEL_LINE_MAP.json (con from/to) "
                        "o completar su linea; si estaba en CANDIDATES.json, sacarlo de ahi."),
        "scan_window": {"start": SCAN_START, "end": last_day},
        "new_suffixes_post_fleet_change": pack_new(post_change),
        "new_suffixes_pre_existing_unmapped": pack_new(baseline),
        "to_disambiguate": to_disambiguate,
        "legacy_snapshot_pending_not_seen_in_scan": legacy,
        "v1_suffixes_never_seen_in_scan_window": report["v1_never_seen_in_range"],
    }
    save_json(NEW_PENDING_JSON, pending)

    # ---------- MD ----------
    lines_md: list[str] = []
    a = lines_md.append
    a("# LABEL_LINE_MAP — Trabajo pendiente (unificado)")
    a("")
    a(f"Generado {pending['generated']} a partir del scan de grabaciones {SCAN_START} → {last_day} "
      "(cambio de flota AMBA: salto masivo de sufijos el 2026-06-11).")
    a("")
    a("Al resolver un sufijo: agregarlo/completarlo en `LABEL_LINE_MAP.json` con su `from` "
      "(ya anotado aca) y, si estaba en `CANDIDATES.json`, sacarlo de ahi.")
    a("Fuente de datos: `prediccion colectivos/experiments/scan_suffix_changes_report.json`. "
      "Version JSON de este archivo: `pending_label_work.json`.")
    a("")

    def emit_new(title: str, d: dict, note: str):
        a("---")
        a("")
        a(f"## {title}")
        a("")
        a(note)
        a("")
        for sfx, v in d.items():
            status = "" if v["still_active"] else f" · **ya no aparece** (ultimo dia {v['last_seen']})"
            a(f"- [ ] sufijo `{sfx}` → linea **???** · from `{v['from']}` · "
              f"{v['max_vehicles_dia']} vehiculos max/dia{status}")
            a(f"  - rutas: {'; '.join(v['route_hints']) if v['route_hints'] else 'sin route_id'}")
            a(f"  - labels: {', '.join(v['sample_labels'])}")
            for h in v["previous_notes"]:
                a(f"  - nota previa ({h['context']}): {h['hint'] or '(sin hint)'}")
        a("")

    emit_new(
        f"Sufijos nuevos a identificar — cambio de flota (first_seen ≥ {FLEET_CHANGE_CUTOFF})",
        pending["new_suffixes_post_fleet_change"],
        "**El trabajo manual principal.** `from` es la fecha real de inicio del sufijo "
        "(primer dia visto en las grabaciones). Las rutas vienen de los route_id observados, "
        "resueltos contra ROUTE_AGENCY_MAP.\n\n"
        "> ⚠️ ROUTE_AGENCY_MAP es un build del **2026-05-31 (pre cambio de flota)** y los "
        "route_id rotan cada ~3 semanas: la resolucion shortName/agencia puede estar "
        "**desactualizada o directamente mal** para estos sufijos (ej. `4852` es el 151 pero "
        "sus rid resuelven a 113/111). Usar los rid crudos contra un ROUTE_AGENCY_MAP "
        "rebuildeado post-junio, o verificar en el mapa en vivo.",
    )
    emit_new(
        "Sufijos sin mapear que ya existian antes del cambio",
        pending["new_suffixes_pre_existing_unmapped"],
        f"Presentes desde el inicio de la ventana ({SCAN_START}): su fecha real de inicio es "
        "anterior y desconocida (usar `from: 2026-03-28` como el resto del map inicial).",
    )

    a("---")
    a("")
    a("## Sufijos a desambiguar (CANDIDATES.json)")
    a("")
    a("Sufijos con multiples lineas candidatas (`line` sin resolver). El estado del scan "
      "indica si siguen operando — los desaparecidos ya tienen `to` en CANDIDATES.json y "
      "son de baja prioridad.")
    a("")
    by_agency: dict[str, list[str]] = {}
    for sfx, v in to_disambiguate.items():
        by_agency.setdefault(v["agencyName"] or "Agencia desconocida", []).append(sfx)
    for agency in sorted(by_agency):
        a(f"### {agency}")
        for sfx in by_agency[agency]:
            v = to_disambiguate[sfx]
            cand = " / ".join(v["lines"]) if v["lines"] else "sin candidatas"
            a(f"- [ ] sufijo `{sfx}` → {cand} · {v['scan_status']}")
            for h in v["previous_notes"]:
                a(f"  - nota previa ({h['context']}): {h['hint'] or '(sin hint)'}")
        a("")

    a("---")
    a("")
    a("## Pendientes heredados de snapshots (no vistos en el scan)")
    a("")
    a("Items abiertos del viejo PENDING_DISAMBIGUATION.md cuyos sufijos NO aparecieron en la "
      f"ventana {SCAN_START} → {last_day}. Probablemente obsoletos tras el cambio de flota; "
      "revisar solo si reaparecen.")
    a("")
    for sfx, v in sorted(legacy.items(), key=lambda kv: (int(kv[0]) if kv[0].isdigit() else 10**9)):
        hints = "; ".join(f"({h['context']}) {h['hint'] or 'sin hint'}" for h in v["hints"])
        a(f"- [ ] sufijo `{sfx}` → {hints}")
    a("")

    a("---")
    a("")
    a("## Sufijos del map v1 sin observaciones en la ventana del scan")
    a("")
    a(f"{len(report['v1_never_seen_in_range'])} sufijos mapeados que no aparecieron ningun dia "
      f"entre {SCAN_START} y {last_day} (lineas que dejaron el feed antes del 24/05 o inactivas). "
      "Quedaron con `to: null` en el map porque no hay evidencia en esta ventana para fecharlos:")
    a("")
    a(", ".join(f"`{s}`" for s in report["v1_never_seen_in_range"]))
    a("")

    NEW_PENDING_MD.write_text("\n".join(lines_md), encoding="utf-8")
    print(f"Escrito: {NEW_PENDING_MD}")
    print(f"Escrito: {NEW_PENDING_JSON}")
    print(f"  nuevos post-cambio: {len(post_change)} | pre-existentes sin mapear: {len(baseline)}")
    print(f"  a desambiguar: {len(to_disambiguate)} | heredados no vistos: {len(legacy)}")

    if OLD_PENDING.exists():
        OLD_PENDING.unlink()
        print(f"Eliminado: {OLD_PENDING} (contenido migrado; historia en git)")


if __name__ == "__main__":
    main()
