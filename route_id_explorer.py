#!/usr/bin/env python
"""
route_id_explorer.py — Análisis empírico de route_ids por línea

Preguntas que responde:
  1. ¿Cuántos route_ids únicos por línea en el período?
  2. ¿Qué direction_id(s) usa cada route_id?
  3. ¿Cuándo aparece por primera vez cada route_id?
  4. ¿Cuándo se detectan rotaciones (muchos route_ids nuevos el mismo día)?
  5. ¿Los route_ids viejos persisten después de una rotación?
  6. ¿Algún route_id reaparece después de desaparecer?

Uso:
  python route_id_explorer.py --data-dir Z:\\grabaciones --lines 26 39 42 92 124 151 168
  python route_id_explorer.py --data-dir Z:\\grabaciones --lines 39 --skip-first 0
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from prediccion.pipeline.reader import iter_daily_files, reconstruct_snapshots
from prediccion.pipeline.shapes_io import load_label_line_map

INTERVAL_S = 300          # muestra cada 5 min — suficiente para trackear route_ids
ROTATION_MIN_NEW = 3      # mínimo de route_ids nuevos en un día para llamarlo rotación
GAP_REAPPEAR_DAYS = 5    # días de ausencia para considerar que un route_id "desapareció"


def main() -> None:
    parser = argparse.ArgumentParser(description="Análisis de route_ids por línea")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--lines", nargs="+", required=True, metavar="LINE")
    parser.add_argument(
        "--label-map",
        type=Path,
        default=Path(__file__).parent / "LABEL_LINE_MAP.json",
    )
    parser.add_argument("--skip-first", type=int, default=1)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("route_id_explorer_results.json"))
    args = parser.parse_args()

    label_line_map = load_label_line_map(str(args.label_map))
    target_lines = set(args.lines)

    daily_files = list(iter_daily_files(args.data_dir))
    today_str = date.today().isoformat()
    daily_files = [f for f in daily_files if f.name[:10] != today_str]
    if args.skip_first:
        daily_files = daily_files[args.skip_first:]
    if args.max_days:
        daily_files = daily_files[: args.max_days]
    if not daily_files:
        print("ERROR: sin archivos en", args.data_dir, file=sys.stderr)
        sys.exit(1)

    print(f"Líneas: {sorted(target_lines)}")
    print(f"Período: {daily_files[0].name[:10]} → {daily_files[-1].name[:10]}  ({len(daily_files)} días)")

    # ── Estructuras de tracking ───────────────────────────────────────────────

    # route_id → metadatos
    rid_info: dict[str, dict] = {}

    # line → date → set[route_id] activos ese día
    line_day_rids: dict[str, dict[str, set]] = {l: {} for l in target_lines}

    all_dates: list[str] = []

    # ── Loop por día ──────────────────────────────────────────────────────────

    t0_total = time.time()

    for i, fp in enumerate(daily_files):
        day_str = fp.name[:10]
        all_dates.append(day_str)
        t0 = time.time()

        # route_ids activos hoy por línea
        day_active: dict[str, set] = {l: set() for l in target_lines}

        for _ts, state in reconstruct_snapshots(fp, interval_s=INTERVAL_S):
            for _vid, fields in state.items():
                label = fields.get("label", "")
                suffix = label.split("-")[-1] if label else ""
                line = label_line_map.get(suffix)
                if line not in target_lines:
                    continue

                rid = str(fields.get("route_id") or "").strip()
                if not rid:
                    continue
                dir_id = fields.get("direction_id")

                day_active[line].add(rid)

                if rid not in rid_info:
                    rid_info[rid] = {
                        "line": line,
                        "direction_ids": set(),
                        "first_seen": day_str,
                        "last_seen": day_str,
                        "days_active": set(),
                        "obs_count": 0,
                    }

                rd = rid_info[rid]
                rd["last_seen"] = day_str
                rd["days_active"].add(day_str)
                rd["obs_count"] += 1
                if dir_id is not None:
                    rd["direction_ids"].add(int(dir_id))

        for line in target_lines:
            line_day_rids[line][day_str] = day_active[line]

        new_today = [r for r in (
            rid for line_set in day_active.values() for rid in line_set
        ) if rid_info[r]["first_seen"] == day_str]

        elapsed = time.time() - t0
        print(
            f"  [{i+1:2d}/{len(daily_files)}] {day_str}  "
            f"active: {sum(len(s) for s in day_active.values())}  "
            f"nuevos: {len(new_today)}  [{elapsed:.0f}s]"
        )

    total_elapsed = time.time() - t0_total
    print(f"\nTiempo total: {total_elapsed/60:.1f} min")

    # ── Análisis por línea ────────────────────────────────────────────────────

    results_by_line: dict[str, dict] = {}

    for line in sorted(target_lines):
        rids_of_line = {r: rd for r, rd in rid_info.items() if rd["line"] == line}

        # Rotaciones: días donde aparecen ≥ ROTATION_MIN_NEW route_ids nuevos
        rotation_events = []
        first_day = all_dates[0] if all_dates else ""
        new_by_date: dict[str, list] = defaultdict(list)
        for rid, rd in rids_of_line.items():
            new_by_date[rd["first_seen"]].append(rid)

        for rot_date in sorted(new_by_date):
            if rot_date == first_day:
                continue
            new_rids = new_by_date[rot_date]
            if len(new_rids) < ROTATION_MIN_NEW:
                continue

            rot_dt = datetime.strptime(rot_date, "%Y-%m-%d")

            # ¿Los route_ids anteriores a esta fecha siguen activos?
            old_rids = [r for r, rd in rids_of_line.items() if rd["first_seen"] < rot_date]
            still_active_after = []
            gone_after = []
            for old_rid in old_rids:
                old_rd = rids_of_line[old_rid]
                old_last = datetime.strptime(old_rd["last_seen"], "%Y-%m-%d")
                if (old_last - rot_dt).days >= 0:
                    still_active_after.append(old_rid)
                else:
                    gone_after.append(old_rid)

            # ¿Cuántos días después de la rotación persisten los viejos?
            if still_active_after:
                max_overlap_days = max(
                    (datetime.strptime(rids_of_line[r]["last_seen"], "%Y-%m-%d") - rot_dt).days
                    for r in still_active_after
                )
            else:
                max_overlap_days = 0

            rotation_events.append({
                "date": rot_date,
                "new_route_ids": sorted(new_rids),
                "n_new": len(new_rids),
                "old_rids_gone": sorted(gone_after),
                "old_rids_still_active": sorted(still_active_after),
                "max_overlap_days": max_overlap_days,
            })

        # Reapariciones: route_ids que tuvieron gap > GAP_REAPPEAR_DAYS y volvieron
        reappearances = []
        for rid, rd in rids_of_line.items():
            days = sorted(rd["days_active"])
            for j in range(1, len(days)):
                dt_prev = datetime.strptime(days[j - 1], "%Y-%m-%d")
                dt_curr = datetime.strptime(days[j], "%Y-%m-%d")
                gap = (dt_curr - dt_prev).days
                if gap > GAP_REAPPEAR_DAYS:
                    reappearances.append({
                        "route_id": rid,
                        "disappeared_after": days[j - 1],
                        "reappeared_on": days[j],
                        "gap_days": gap,
                        "direction_ids": sorted(rd["direction_ids"]),
                    })

        # Resumen de direction_ids: ¿algún route_id usa ambas direcciones?
        dual_direction = [r for r, rd in rids_of_line.items() if len(rd["direction_ids"]) > 1]

        results_by_line[line] = {
            "unique_route_ids": len(rids_of_line),
            "rotation_events": rotation_events,
            "reappearances": reappearances,
            "dual_direction_rids": dual_direction,
            "route_ids": [
                {
                    "route_id": r,
                    "direction_ids": sorted(rd["direction_ids"]),
                    "first_seen": rd["first_seen"],
                    "last_seen": rd["last_seen"],
                    "days_active": len(rd["days_active"]),
                    "obs_count": rd["obs_count"],
                }
                for r, rd in sorted(rids_of_line.items(), key=lambda x: x[1]["first_seen"])
            ],
        }

    # ── Imprimir resumen ──────────────────────────────────────────────────────

    sep = "=" * 64
    print(f"\n{sep}")
    print("RESUMEN — route_id explorer")
    print(sep)

    for line in sorted(target_lines):
        res = results_by_line[line]
        print(f"\nLínea {line}:")
        print(f"  route_ids únicos: {res['unique_route_ids']}")

        if res["dual_direction_rids"]:
            print(f"  ⚠ route_ids con ambas direcciones: {res['dual_direction_rids']}")

        if res["rotation_events"]:
            print(f"  Rotaciones detectadas: {len(res['rotation_events'])}")
            for ev in res["rotation_events"]:
                overlap = f"overlap {ev['max_overlap_days']}d" if ev["old_rids_still_active"] else "corte limpio"
                print(
                    f"    {ev['date']}: {ev['n_new']} nuevos  |  "
                    f"viejos que persisten: {len(ev['old_rids_still_active'])}  ({overlap})"
                )
                print(f"      nuevos: {ev['new_route_ids']}")
                if ev["old_rids_still_active"]:
                    print(f"      siguen activos: {ev['old_rids_still_active']}")
        else:
            print("  Sin rotaciones detectadas en el período")

        if res["reappearances"]:
            print(f"  Reapariciones (gap >{GAP_REAPPEAR_DAYS}d): {len(res['reappearances'])}")
            for r in res["reappearances"][:5]:
                print(f"    {r['route_id']}: desapareció {r['disappeared_after']} → volvió {r['reappeared_on']} ({r['gap_days']}d)")
        else:
            print("  Sin reapariciones")

        print("  route_ids por dirección:")
        for rd in res["route_ids"]:
            dirs = rd["direction_ids"] or ["?"]
            print(
                f"    {rd['route_id']}  dir={dirs}  "
                f"{rd['first_seen']} → {rd['last_seen']}  "
                f"({rd['days_active']} días activo)"
            )

    print(f"\n{sep}")

    # ── Escribir JSON ─────────────────────────────────────────────────────────

    output = {
        "generated_at": datetime.now().isoformat(),
        "period": {
            "from": daily_files[0].name[:10],
            "to": daily_files[-1].name[:10],
            "days_analyzed": len(daily_files),
        },
        "lines": results_by_line,
    }

    # Convertir sets a listas para serialización
    def make_serializable(obj):
        if isinstance(obj, set):
            return sorted(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=make_serializable)

    print(f"\nEscrito: {args.out}")


if __name__ == "__main__":
    main()
