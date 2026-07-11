"""Migracion one-off LABEL_LINE_MAP.json v1 -> v2 + CANDIDATES.json.

v1: map[sufijo] = {agencyId, agencyName, lines[], line|null}
v2: lines[linea] = {agencies: [{agencyId, agencyName, from, to}],
                    suffixes: [{suffix, agencyId, from, to}]}

- Entradas resueltas (line truthy) -> v2, from=2026-03-28, to=null.
- Entradas ambiguas (line null, incl. lines=[]) -> CANDIDATES.json.
- agencyName se preserva byte-a-byte (mojibake incluido).

Uso:
    python scripts/migrate_label_line_map_v2.py          # escribe ambos archivos
    python scripts/migrate_label_line_map_v2.py --check  # solo sanity checks
"""

import argparse
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
V1_PATH = PROJECT_DIR / "LABEL_LINE_MAP.json"
V2_PATH = PROJECT_DIR / "LABEL_LINE_MAP.json"  # se pisa in-place
CANDIDATES_PATH = PROJECT_DIR / "CANDIDATES.json"
INITIAL_FROM = "2026-03-28"


def sort_key_numeric(s: str):
    return (0, int(s)) if s.isdigit() else (1, s)


def migrate(v1_map: dict) -> tuple[dict, dict]:
    lines: dict[str, dict] = {}
    candidates: dict[str, dict] = {}

    for suffix, info in v1_map.items():
        if info.get("line"):
            line = info["line"]
            entry = lines.setdefault(line, {"agencies": [], "suffixes": []})
            agency_ids = [a["agencyId"] for a in entry["agencies"]]
            if info["agencyId"] not in agency_ids:
                entry["agencies"].append({
                    "agencyId": info["agencyId"],
                    "agencyName": info["agencyName"],
                    "from": INITIAL_FROM,
                    "to": None,
                })
            entry["suffixes"].append({
                "suffix": suffix,
                "agencyId": info["agencyId"],
                "from": INITIAL_FROM,
                "to": None,
            })
        else:
            candidates[suffix] = {
                "agencyId": info["agencyId"],
                "agencyName": info["agencyName"],
                "lines": info.get("lines", []),
                "from": INITIAL_FROM,
                "to": None,
            }

    # orden estable: lineas y sufijos numericos
    ordered = {}
    for line in sorted(lines, key=sort_key_numeric):
        e = lines[line]
        e["agencies"].sort(key=lambda a: sort_key_numeric(a["agencyId"]))
        e["suffixes"].sort(key=lambda s: sort_key_numeric(s["suffix"]))
        ordered[line] = e
    candidates = {k: candidates[k] for k in sorted(candidates, key=sort_key_numeric)}
    return ordered, candidates


def sanity_check(v1_map: dict, lines: dict, candidates: dict) -> None:
    n_v2 = sum(len(e["suffixes"]) for e in lines.values())
    assert n_v2 + len(candidates) == len(v1_map), (
        f"conteo no cierra: {n_v2} v2 + {len(candidates)} candidatos != {len(v1_map)} v1")

    # ningun sufijo duplicado con periodos solapados (en la migracion: ninguno duplicado)
    seen = {}
    for line, e in lines.items():
        for s in e["suffixes"]:
            assert s["suffix"] not in seen, (
                f"sufijo {s['suffix']} duplicado en lineas {seen[s['suffix']]} y {line}")
            seen[s["suffix"]] = line
    assert not (set(seen) & set(candidates)), "sufijo en map y candidates a la vez"

    # cada sufijo referencia una agencia declarada en su linea
    for line, e in lines.items():
        agency_ids = {a["agencyId"] for a in e["agencies"]}
        for s in e["suffixes"]:
            assert s["agencyId"] in agency_ids, f"linea {line}: agencyId huerfano"

    # spot checks contra v1
    for sfx, expected_line in [("45", "150"), ("133", "168"), ("34", "101")]:
        assert seen.get(sfx) == expected_line, f"spot check fallo: {sfx} -> {seen.get(sfx)}"

    multi_agency = {l: [a["agencyName"] for a in e["agencies"]]
                    for l, e in lines.items() if len(e["agencies"]) > 1}
    print(f"OK: {len(v1_map)} entradas v1 -> {n_v2} sufijos en {len(lines)} lineas "
          f"+ {len(candidates)} candidatos")
    if multi_agency:
        print(f"Lineas multi-agencia ({len(multi_agency)}): {sorted(multi_agency)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="solo validar, no escribir")
    args = ap.parse_args()

    with open(V1_PATH, encoding="utf-8") as f:
        v1 = json.load(f)
    assert "map" in v1 and "version" not in v1, "el archivo no parece ser v1"

    lines, candidates = migrate(v1["map"])
    sanity_check(v1["map"], lines, candidates)
    if args.check:
        return

    v2 = {
        "version": 2,
        "description": ("Mapa sufijo VP_label -> linea, con vigencias. Fechas inclusive "
                        "(from = primer dia visto, to = ultimo dia visto; to=null: vigente). "
                        "Sufijos ambiguos sin resolver: ver CANDIDATES.json."),
        "lines": lines,
    }
    cand = {
        "version": 1,
        "description": ("Sufijos VP_label sin linea resuelta (candidatas en `lines`). "
                        "Al resolver uno, moverlo a LABEL_LINE_MAP.json."),
        "candidates": candidates,
    }
    with open(V2_PATH, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(cand, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Escrito: {V2_PATH}")
    print(f"Escrito: {CANDIDATES_PATH}")


if __name__ == "__main__":
    main()
