"""
Diagnóstico B (solo medir, no entra al pipeline): calidad de trip_id por línea, comparado con los viajes del segmentador v2b.
La línea se identifica SOLO por el sufijo del label (LABEL_LINE_MAP, vigente por fecha), como el pipeline v2.
  python -m prediccion.scripts.diag_trip_id [--workers 3]
Escribe data/ml/v2b/diag/TRIP_ID_CALIDAD.md y trip_id_calidad.json.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

DATA_DIR = Path("//192.168.0.18/buffer/grabaciones")
V2B = Path("data/ml/v2b")
OUT = V2B / "diag"
DAYS = ["2026-04-08", "2026-04-18", "2026-05-12", "2026-06-07", "2026-07-14",
        "2026-08-12", "2026-09-12", "2026-09-16", "2026-10-07", "2026-10-11"]
MATCH_S = 180.0            # coincidencia de inicio de viaje con cambio de trip_id: +-3 min
TERMINAL_M = 500.0
SHORT_S, LONG_S = 600.0, 4 * 3600.0
DUP_OVERLAP_S = 120.0

# Umbrales de clasificación (explícitos; ver informe)
USABLE = dict(empty_max=5.0, bad_dur_max=15.0, near_term_min=70.0, v2b_match_min=70.0, tid_match_min=70.0,
              dup_max=2.0, inv_max=10.0)
BROKEN = dict(empty_min=30.0, bad_dur_min=50.0, near_term_max=30.0, v2b_match_max=30.0, tid_match_max=30.0,
              dup_min=10.0, inv_min=30.0)


def _xy(lat, lon, lat0):
    return (lat * 111320.0, lon * 111320.0 * math.cos(math.radians(lat0)))


def _dist_m(la1, lo1, la2, lo2):
    dy = (la2 - la1) * 111320.0
    dx = (lo2 - lo1) * 111320.0 * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot(dx, dy)


def process_day(day: str) -> dict:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
    except Exception:
        pass
    import pyarrow.parquet as pq
    from prediccion.pipeline.reader import iter_frames
    from prediccion.pipeline.shapes_io import load_label_line_data, resolve_label_line_index
    from prediccion.v2.shapes import DEFAULT_LABEL_MAP, DEFAULT_LINE_SHAPES_DIR, LineShapes

    lines = json.load(open(V2B / "lines.json", encoding="utf-8"))
    lineset = set(map(str, lines["train"] + lines["heldout"]))
    label_index = resolve_label_line_index(load_label_line_data(DEFAULT_LABEL_MAP), on_date=day)
    label_map = {s: v["line"] for s, v in label_index.items()}
    shapes = LineShapes(DEFAULT_LINE_SHAPES_DIR)
    ends = {ln: [p for s in shapes.get(ln) for p in (tuple(s.index._pts[0]), tuple(s.index._pts[-1]))] for ln in lineset}

    state: dict[str, dict] = {}
    veh: dict[str, dict] = {}        # vid -> {"line", "pings": [(ts, lat, lon, tid)]}

    def touch(vid, f):
        sfx = (f.get("label") or "").split("-")[-1]
        ln = label_map.get(sfx)
        if ln not in lineset:
            return
        t, lat, lon = f.get("ts"), f.get("lat"), f.get("lon")
        if t is None or lat is None or lon is None:
            return
        r = veh.get(vid)
        if r is None:
            r = veh[vid] = {"line": ln, "pings": []}
        if r["pings"] and t <= r["pings"][-1][0]:
            return
        r["pings"].append((t, lat, lon, f.get("trip_id") or ""))

    for fr in iter_frames(DATA_DIR / f"{day}.ndjson.gz"):
        if fr.get("gap"):
            continue
        if fr.get("keyframe"):
            state = {}
        for v in fr.get("new", []):
            sfx = (v.get("label") or "").split("-")[-1]
            if label_map.get(sfx) in lineset:
                state[v["id"]] = dict(v)
                touch(v["id"], state[v["id"]])
            else:
                state.pop(v["id"], None)
        for vid in fr.get("del", []):
            state.pop(vid, None)
        for u in fr.get("upd", []):
            s = state.get(u["id"])
            if s is not None:
                s.update(u)
                if "ts" in u:
                    touch(u["id"], s)

    trips = pq.read_table(V2B / "daily" / f"{day}.trips.parquet",
                          columns=["line", "vehicle_id", "start_ts", "direction_id", "shape_id", "start_unknown"]).to_pandas()
    trips = trips[trips["line"].isin(lineset)]
    v2b_by_vid = defaultdict(list)
    for r in trips.itertuples(index=False):
        v2b_by_vid[str(r.vehicle_id)].append((int(r.start_ts), int(r.direction_id), bool(r.start_unknown), str(r.line)))
    for k in v2b_by_vid:
        v2b_by_vid[k].sort()

    res = {"day": day, "pings": defaultdict(lambda: [0, 0]), "runs": [], "changes": [], "vd": [], "v2b": [],
           "inv": [], "dup": []}
    runs_by_tid = defaultdict(list)
    for vid, r in veh.items():
        ln, P = r["line"], r["pings"]
        for p in P:
            res["pings"][ln][0] += 1
            res["pings"][ln][1] += (p[3] == "")
        runs = []
        cur = None
        for i, p in enumerate(P):
            if p[3] == "":
                continue
            if cur is None or p[3] != cur["tid"]:
                cur = {"tid": p[3], "t0": p[0], "t1": p[0], "len": 0.0, "n": 1, "i0": i, "last": p}
                runs.append(cur)
            else:
                cur["len"] += _dist_m(cur["last"][1], cur["last"][2], p[1], p[2])
                cur["t1"] = p[0]
                cur["n"] += 1
                cur["last"] = p
        res["vd"].append((ln, len(P), len(runs)))
        vt = v2b_by_vid.get(str(vid), [])
        vstarts = [x[0] for x in vt]
        change_ts = []
        for k, ru in enumerate(runs):
            first, last = k == 0, k == len(runs) - 1
            res["runs"].append((ln, ru["t1"] - ru["t0"], ru["len"], ru["n"], first, last))
            runs_by_tid[(ln, ru["tid"])].append((vid, ru["t0"], ru["t1"]))
            if not first:
                prev = runs[k - 1]["last"]
                cur_p = P[ru["i0"]]
                d = min(min(_dist_m(q[0], q[1], e[0], e[1]) for e in ends[ln]) for q in ((prev[1], prev[2]), (cur_p[1], cur_p[2])))
                res["changes"].append((ln, d))
                change_ts.append(ru["t0"])
            # inversión de sentido dentro del trip_id: viajes v2b que arrancan adentro con otra dirección
            if ru["t1"] - ru["t0"] > 2 * MATCH_S:
                a = bisect.bisect_right(vstarts, ru["t0"] + MATCH_S)
                b = bisect.bisect_left(vstarts, ru["t1"] - MATCH_S)
                inside = vt[a:b]
                prev_dir = vt[a - 1][1] if a > 0 else None
                inv = False
                for x in inside:
                    if prev_dir is not None and x[1] != prev_dir:
                        inv = True
                    prev_dir = x[1]
                res["inv"].append((ln, inv, len(inside) > 0))
        first_ping = P[0][0] if P else 0
        for (st, dr, su, vln) in vt:
            if st < first_ping + MATCH_S:
                continue             # arranca con el primer ping del día (viene del carry): no hay cambio observable
            j = bisect.bisect_left(change_ts, st - MATCH_S)
            ok = j < len(change_ts) and change_ts[j] <= st + MATCH_S
            res["v2b"].append((vln, su, ok))
        # cambios de trip_id vs viajes v2b
        cs = []
        for ru in runs[1:]:
            j = bisect.bisect_left(vstarts, ru["t0"] - MATCH_S)
            cs.append((ln, j < len(vstarts) and vstarts[j] <= ru["t0"] + MATCH_S))
        res["changes"] = res["changes"]  # (ln, d) ya cargado
        res.setdefault("chg_match", []).extend(cs)
    for (ln, tid), lst in runs_by_tid.items():
        dup = False
        vids = {x[0] for x in lst}
        if len(vids) > 1:
            lst2 = sorted(lst, key=lambda x: x[1])
            for i in range(len(lst2)):
                for j in range(i + 1, len(lst2)):
                    if lst2[j][1] >= lst2[i][2] - DUP_OVERLAP_S:
                        break
                    if lst2[i][0] != lst2[j][0] and min(lst2[i][2], lst2[j][2]) - lst2[j][1] > DUP_OVERLAP_S:
                        dup = True
        res["dup"].append((ln, dup))
    res["pings"] = {k: v for k, v in res["pings"].items()}
    return res


def pct(a, b):
    return 100.0 * a / b if b else float("nan")


def fm(v, nd=1):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{nd}f}"


def classify(m: dict) -> tuple[str, list[str]]:
    u, b = USABLE, BROKEN
    why = []
    broken = (m["empty"] > b["empty_min"] or m["bad_dur"] > b["bad_dur_min"] or m["near_term"] < b["near_term_max"]
              or m["v2b_match"] < b["v2b_match_max"] or m["tid_match"] < b["tid_match_max"]
              or m["dup"] > b["dup_min"] or m["inv"] > b["inv_min"])
    usable = (m["empty"] <= u["empty_max"] and m["bad_dur"] <= u["bad_dur_max"] and m["near_term"] >= u["near_term_min"]
              and m["v2b_match"] >= u["v2b_match_min"] and m["tid_match"] >= u["tid_match_min"]
              and m["dup"] <= u["dup_max"] and m["inv"] <= u["inv_max"])
    if broken:
        if m["empty"] > b["empty_min"]: why.append("vacío")
        if m["bad_dur"] > b["bad_dur_min"]: why.append("duración")
        if m["near_term"] < b["near_term_max"]: why.append("cambio lejos de cabecera")
        if m["v2b_match"] < b["v2b_match_max"] or m["tid_match"] < b["tid_match_max"]: why.append("no coincide con v2b")
        if m["dup"] > b["dup_min"]: why.append("trip_id duplicado")
        if m["inv"] > b["inv_min"]: why.append("inversión sin cambio")
        return "roto", why
    return ("usable", []) if usable else ("dudoso", [])


def aggregate(results: list[dict]) -> tuple[dict, dict]:
    per = {}
    allines = sorted({ln for r in results for ln in r["pings"]}, key=lambda x: (len(x), x))
    for ln in allines:
        n = sum(r["pings"].get(ln, [0, 0])[0] for r in results)
        ne = sum(r["pings"].get(ln, [0, 0])[1] for r in results)
        vd = [x for r in results for x in r["vd"] if x[0] == ln]
        vd_ch = np.array([max(x[2] - 1, 0) for x in vd if x[2] > 0], float)
        runs = [x for r in results for x in r["runs"] if x[0] == ln]
        inner = [x for x in runs if not x[4] and not x[5]]      # sin la primera ni la última del coche-día (truncadas)
        dur = np.array([x[1] for x in inner], float)
        ln_m = np.array([x[2] for x in inner], float)
        ch = [x for r in results for x in r["changes"] if x[0] == ln]
        cm = [x for r in results for x in r.get("chg_match", []) if x[0] == ln]
        v2 = [x for r in results for x in r["v2b"] if x[0] == ln]
        v2k = [x for x in v2 if not x[1]]
        inv = [x for r in results for x in r["inv"] if x[0] == ln]
        dup = [x for r in results for x in r["dup"] if x[0] == ln]
        q = lambda a, p: float(np.percentile(a, p)) if len(a) else float("nan")  # noqa: E731
        m = {
            "pings": n, "empty": pct(ne, n), "vehicle_days": len(vd), "runs": len(runs), "inner_runs": len(inner),
            "chg_per_vd_mean": float(vd_ch.mean()) if len(vd_ch) else float("nan"), "chg_per_vd_p50": q(vd_ch, 50),
            "dur_p10": q(dur, 10) / 60, "dur_p50": q(dur, 50) / 60, "dur_p90": q(dur, 90) / 60,
            "len_p10": q(ln_m, 10) / 1000, "len_p50": q(ln_m, 50) / 1000, "len_p90": q(ln_m, 90) / 1000,
            "short": pct(int((dur < SHORT_S).sum()), len(dur)), "long": pct(int((dur > LONG_S).sum()), len(dur)),
            "bad_dur": pct(int(((dur < SHORT_S) | (dur > LONG_S)).sum()), len(dur)),
            "n_changes": len(ch), "near_term": pct(sum(1 for x in ch if x[1] <= TERMINAL_M), len(ch)),
            "inv": pct(sum(1 for x in inv if x[1]), sum(1 for x in inv if x[2]) or len(inv)),
            "inv_n": len(inv),
            "dup": pct(sum(1 for x in dup if x[1]), len(dup)), "n_tids": len(dup),
            "v2b_trips": len(v2), "v2b_match": pct(sum(1 for x in v2 if x[2]), len(v2)),
            "v2b_match_known": pct(sum(1 for x in v2k if x[2]), len(v2k)), "v2b_known": len(v2k),
            "tid_match": pct(sum(1 for x in cm if x[1]), len(cm)), "tid_changes": len(cm),
        }
        m["class"], m["why"] = classify(m)
        per[ln] = m
    return per, {}


def write_report(per, days):
    L = ["# Calidad de trip_id por línea", "",
         "## Conclusión", "",
         "Con estos umbrales **ninguna de las 15 líneas queda como usable**; todas salen *roto* por al menos un criterio. Dos fallas son generales: "
         "(1) el mismo trip_id aparece en dos coches a la vez en el 24-50 % de los trip_ids de toda línea (el trip_id es un viaje del horario "
         "asignado a varios coches, no un identificador único por coche); (2) menos de la mitad de los viajes v2b coinciden con un cambio de trip_id "
         "en casi todas las líneas (máx. 64 % en la 39). Además la 124 y la 151 tienen 43 % y 56 % de pings sin trip_id (la 151 ya estaba confirmada rota). "
         "Las menos malas, para un subset de prueba, son la 39, 26, 132, 168 y 92 (vacío 10-12 %, cambios en cabecera 57-91 %, coincidencia con v2b "
         "40-64 %), pero ni siquiera ellas cumplen el umbral de usable; usarlas sería aceptar un trip_id parcialmente confiable. "
         "Salvedad de la métrica de inversión: cuenta viajes v2b que arrancan dentro de una corrida con otra dirección, y el v2b también parte por huecos y "
         "esperas, así que es una cota alta. Una sola muestra de 10 días; sin pesos por día.", "",
         f"Medición (sin usar trip_id en el pipeline): 15 líneas de v2b, {len(days)} días: " + ", ".join(days) + ". Línea identificada solo por el "
         "sufijo del label (LABEL_LINE_MAP vigente por fecha). Generado por `prediccion/scripts/diag_trip_id.py`. Los coches de cada "
         "línea se toman tal como salen del NDJSON (un ping por cambio de `ts`).", "",
         "Definiciones. *Corrida* = secuencia maximal de pings con el mismo trip_id no vacío de un coche en un día; *cambio* = inicio de una corrida "
         "que no es la primera del coche-día. Duración y largo de corrida excluyen la primera y la última del coche-día (truncadas por el corte del día); "
         "largo = suma de distancias entre pings consecutivos. *Cabecera*: el cambio cae a ≤500 m de un extremo de algún recorrido de la línea "
         "(se toma el mínimo entre el último ping de la corrida anterior y el primero de la nueva). *Inversión sin cambio*: % de corridas "
         "(>6 min, con algún viaje v2b adentro) que contienen un viaje v2b que arranca ≥3 min después del inicio y ≥3 min antes del fin con "
         "dirección distinta a la del viaje v2b anterior. *Duplicado*: % de (línea, trip_id)-día que aparece en dos coches con solapamiento >2 min. "
         "*v2b→cambio*: % de viajes v2b (excluidos los que arrancan en el primer ping del día) cuyo inicio está a ±3 min de un cambio de trip_id del "
         "mismo coche; *cambio→v2b*: % de cambios con un inicio de viaje v2b del mismo coche a ±3 min.", ""]
    hdr = ["línea", "pings", "vacío %", "coche-días", "cambios/coche-día p50 (media)", "dur p10/p50/p90 (min)", "largo p10/p50/p90 (km)",
           "<10 min %", ">4 h %"]
    L += ["## 1. Vacío, cambios y duración", "", "| " + " | ".join(hdr) + " |", "|" + "|".join(["---"] + ["---:"] * (len(hdr) - 1)) + "|"]
    for ln, m in per.items():
        L.append(f"| {ln} | {m['pings']} | {fm(m['empty'])} | {m['vehicle_days']} | {fm(m['chg_per_vd_p50'], 0)} ({fm(m['chg_per_vd_mean'])}) | "
                 f"{fm(m['dur_p10'], 0)}/{fm(m['dur_p50'], 0)}/{fm(m['dur_p90'], 0)} | {fm(m['len_p10'])}/{fm(m['len_p50'])}/{fm(m['len_p90'])} | "
                 f"{fm(m['short'])} | {fm(m['long'])} |")
    hdr = ["línea", "cambios", "cambio en cabecera %", "corridas con inversión %", "trip_ids", "trip_id en 2 coches %", "viajes v2b",
           "v2b→cambio %", "(v2b sin start_unknown)", "cambio→v2b %"]
    L += ["", "## 2. Coherencia con la geometría y con v2b", "", "| " + " | ".join(hdr) + " |", "|" + "|".join(["---"] + ["---:"] * (len(hdr) - 1)) + "|"]
    for ln, m in per.items():
        L.append(f"| {ln} | {m['n_changes']} | {fm(m['near_term'])} | {fm(m['inv'])} | {m['n_tids']} | {fm(m['dup'])} | {m['v2b_trips']} | "
                 f"{fm(m['v2b_match'])} | {fm(m['v2b_match_known'])} | {fm(m['tid_match'])} |")
    u, b = USABLE, BROKEN
    L += ["", "## 3. Clasificación", "",
          f"**Usable** si cumple todo: vacío ≤{u['empty_max']:.0f} %, corridas <10 min o >4 h ≤{u['bad_dur_max']:.0f} %, cambio en cabecera ≥{u['near_term_min']:.0f} %, "
          f"v2b→cambio ≥{u['v2b_match_min']:.0f} %, cambio→v2b ≥{u['tid_match_min']:.0f} %, trip_id en 2 coches ≤{u['dup_max']:.0f} %, inversión sin cambio ≤{u['inv_max']:.0f} %. "
          f"**Roto** si falla cualquiera de: vacío >{b['empty_min']:.0f} %, duración anómala >{b['bad_dur_min']:.0f} %, cabecera <{b['near_term_max']:.0f} %, "
          f"v2b→cambio <{b['v2b_match_max']:.0f} % o cambio→v2b <{b['tid_match_max']:.0f} %, duplicado >{b['dup_min']:.0f} %, inversión >{b['inv_min']:.0f} %. "
          "**Dudoso**: el resto. Los umbrales se fijaron antes de ver los números; son criterios de este informe, no de una norma.", "",
          "| línea | clase | motivo de roto | vacío | dur. anómala | cabecera | v2b→cambio | cambio→v2b | 2 coches | inversión |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for ln, m in per.items():
        L.append(f"| {ln} | **{m['class']}** | {', '.join(m['why']) or '-'} | {fm(m['empty'])} | {fm(m['bad_dur'])} | {fm(m['near_term'])} | "
                 f"{fm(m['v2b_match'])} | {fm(m['tid_match'])} | {fm(m['dup'])} | {fm(m['inv'])} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--days", default=",".join(DAYS))
    a = ap.parse_args()
    days = a.days.split(",")
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "_trip_id_days"
    cache.mkdir(exist_ok=True)
    todo = [d for d in days if not (cache / f"{d}.json").exists()]
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for d, r in zip(todo, ex.map(process_day, todo)):
            (cache / f"{d}.json").write_text(json.dumps(r), encoding="utf-8")
            print("listo", d, flush=True)
    results = [json.loads((cache / f"{d}.json").read_text(encoding="utf-8")) for d in days]
    per, _ = aggregate(results)
    (OUT / "trip_id_calidad.json").write_text(json.dumps(per, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "TRIP_ID_CALIDAD.md").write_text(write_report(per, days), encoding="utf-8")
    print((OUT / "TRIP_ID_CALIDAD.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
