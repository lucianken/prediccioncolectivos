"""One-off: LABEL_LINE_MAP v2 -> v3 (lines = AMBA / other_lines = resto del pais)
+ campo `scope` en pending_label_work.json.

Consume lines_no_amba.json (veredictos del agente clasificador, generados
leyendo semanticamente `informacion de wikipedia.txt` contra el map):
  { "map_verdicts": [{line, agencyId, agencyName, verdict: amba|no_amba,
                      confidence: alta|dudosa, reason}],
    "pending_agencies": [{agencyName, verdict: amba|no_amba|unknown, ...}] }

Reglas:
- Cada sufijo va a la seccion de su (linea, agencyId). Nada se borra.
- Veredicto "dudosa": se aplica el verdict pero se imprime para revision.
- Pending: scope por agencyName (disambiguate) o por las agencias de las
  pistas (identify): todas no_amba => other; alguna amba => amba; sino unknown.

Uso:
    python scripts/split_amba_lines.py <ruta lines_no_amba.json> [--dry-run]
"""

import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONSOLA_DIR = PROJECT_DIR.parent / "proyectoconsola"
MAP_PATHS = [CONSOLA_DIR / "LABEL_LINE_MAP.json", PROJECT_DIR / "LABEL_LINE_MAP.json"]
PENDING_JSON = CONSOLA_DIR / "pending_label_work.json"

HINT_AGENCY_RE = re.compile(r"= .* \((.+)\) \[\d+ obs\]$")


def load_json(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p: Path, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if not args:
        sys.exit("uso: split_amba_lines.py <lines_no_amba.json> [--dry-run]")
    verdicts_data = load_json(Path(args[0]))

    v_map: dict[tuple[str, str], dict] = {}
    for v in verdicts_data["map_verdicts"]:
        v_map[(v["line"], v["agencyId"])] = v
    v_agency: dict[str, str] = {
        a["agencyName"]: a["verdict"] for a in verdicts_data.get("pending_agencies", [])
    }

    map_data = load_json(MAP_PATHS[0])
    assert map_data.get("version") == 2 and "lines" in map_data, "el map no es v2"

    # cobertura 100%
    missing = []
    for line, entry in map_data["lines"].items():
        for a in entry["agencies"]:
            if (line, a["agencyId"]) not in v_map:
                missing.append((line, a["agencyId"], a["agencyName"]))
    assert not missing, f"duplas sin veredicto ({len(missing)}): {missing[:10]}"

    n_suffixes_v2 = sum(len(e["suffixes"]) for e in map_data["lines"].values())

    amba_lines: dict[str, dict] = {}
    other_lines: dict[str, dict] = {}
    split_report: list[str] = []
    dudosas: list[str] = []

    for line, entry in map_data["lines"].items():
        buckets = {"amba": {"agencies": [], "suffixes": []},
                   "no_amba": {"agencies": [], "suffixes": []}}
        for a in entry["agencies"]:
            v = v_map[(line, a["agencyId"])]
            buckets[v["verdict"]]["agencies"].append(a)
            if v["confidence"] == "dudosa":
                dudosas.append(f"linea {line} / {a['agencyName']} -> {v['verdict']} ({v['reason']})")
        agency_bucket = {a["agencyId"]: v_map[(line, a["agencyId"])]["verdict"]
                         for a in entry["agencies"]}
        for s in entry["suffixes"]:
            buckets[agency_bucket[s["agencyId"]]]["suffixes"].append(s)

        if buckets["amba"]["suffixes"] or buckets["amba"]["agencies"]:
            amba_lines[line] = buckets["amba"]
        if buckets["no_amba"]["suffixes"] or buckets["no_amba"]["agencies"]:
            other_lines[line] = buckets["no_amba"]
        if line in amba_lines and line in other_lines:
            split_report.append(
                f"linea {line}: {len(buckets['amba']['suffixes'])} sufijos amba / "
                f"{len(buckets['no_amba']['suffixes'])} sufijos interior")

    n_suffixes_v3 = (sum(len(e["suffixes"]) for e in amba_lines.values())
                     + sum(len(e["suffixes"]) for e in other_lines.values()))
    assert n_suffixes_v3 == n_suffixes_v2, f"sufijos perdidos: {n_suffixes_v3} != {n_suffixes_v2}"

    v3 = {
        "version": 3,
        "description": ("Mapa sufijo VP_label -> linea, con vigencias (from/to inclusive; "
                        "to=null: vigente). `lines` = SOLO AMBA; `other_lines` = homonimos "
                        "del resto del pais (colapsados por numero, no interesa la ciudad). "
                        "Sufijos sin resolver: proyectoconsola/pending_label_work.json "
                        "(resolver con scripts/resolve_pending.js)."),
        "lines": amba_lines,
        "other_lines": other_lines,
    }

    # ---- scope en pending ----
    pending_data = load_json(PENDING_JSON)
    pending = pending_data["pending"]
    scope_counts = {"amba": 0, "other": 0, "unknown": 0}
    for sfx, e in pending.items():
        verdicts = []
        if e.get("agencyName"):
            verdicts.append(v_agency.get(e["agencyName"], "unknown"))
        for hint in e.get("evidence", {}).get("route_hints", []):
            m = HINT_AGENCY_RE.search(hint)
            if m:
                verdicts.append(v_agency.get(m.group(1), "unknown"))
        if "amba" in verdicts:
            e["scope"] = "amba"
        elif verdicts and all(v == "no_amba" for v in verdicts):
            e["scope"] = "other"
        else:
            e["scope"] = "unknown"
        scope_counts[e["scope"]] += 1

    # ---- reporte ----
    print(f"v2: {len(map_data['lines'])} lineas, {n_suffixes_v2} sufijos")
    print(f"v3: {len(amba_lines)} lineas AMBA + {len(other_lines)} numeros interior "
          f"({sum(len(e['suffixes']) for e in other_lines.values())} sufijos interior)")
    print(f"\nLineas partidas ({len(split_report)}):")
    for r in split_report:
        print("  " + r)
    if dudosas:
        print(f"\nVeredictos DUDOSOS aplicados ({len(dudosas)}) — revisar:")
        for d in dudosas:
            print("  " + d)
    print(f"\nPending scope: {scope_counts}")

    if dry_run:
        print("\n(dry-run: no se escribio nada)")
        return
    for p in MAP_PATHS:
        save_json(p, v3)
        print(f"Escrito: {p}")
    save_json(PENDING_JSON, pending_data)
    print(f"Escrito: {PENDING_JSON}")
    print("Regenerar MD: cd ../proyectoconsola && node scripts/promote_pending.js --render-only")


if __name__ == "__main__":
    main()
