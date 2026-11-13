"""Coordenadas y coche (label) de los ejemplos del informe. Lee el NDJSON crudo."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]; sys.path.insert(0, str(ROOT))
from prediccion.v2.day import read_day
from prediccion.pipeline.shapes_io import load_label_line_data, resolve_label_line_index
from datetime import datetime, timezone, timedelta
EX = [  # (tipo, dia, linea, vid, ts)
 ("A", "2026-08-06", "151", "97385", 1786033832), ("A", "2026-10-05", "39", "77665", 1791246458),
 ("A", "2026-09-25", "92", "26763", 1790331180), ("A", "2026-08-26", "108", "95302", 1787779374),
 ("B", "2026-06-15", "108", "95455", 1781558460), ("B", "2026-09-17", "168", "20020", 1789697976),
 ("C", "2026-05-11", "128", "82838", 1778522696), ("C", "2026-04-05", "42", "77694", 1775422778),
 ("C", "2026-08-24", "106", "79281", 1787602948),
 ("D", "2026-05-07", "42", "90844", 1778172466), ("D", "2026-08-03", "92", "27269", 1785802822),
 ("D", "2026-07-07", "39", "78593", 1783392696),
 ("E", "2026-07-14", "12", "97980", 1784041136), ("E", "2026-08-12", "151", "97464", 1786559146),
 ("E", "2026-09-16", "26", "78148", 1789611618), ("E", "2026-09-16", "151", "97016", 1789567778),
]
ld = load_label_line_data(ROOT / "LABEL_LINE_MAP.json")
cache = {}
for tipo, day, ln, vid, ts in EX:
    if (day, ln) not in cache:
        li = resolve_label_line_index(ld, on_date=day)
        lm = {s: v["line"] for s, v in li.items()}
        cache[(day, ln)] = read_day(Path("//192.168.0.18/buffer/grabaciones") / f"{day}.ndjson.gz", lm, {ln}, None, 30, False)[0]
    rec = cache[(day, ln)].get(vid)
    if not rec:
        print(tipo, day, ln, vid, "sin datos"); continue
    ob = min(rec["obs"], key=lambda o: abs(o[0] - ts))
    loc = datetime.fromtimestamp(ts, timezone(timedelta(hours=-3)))
    print(json.dumps({"tipo": tipo, "dia": day, "linea": ln, "vid": vid, "label": rec["label"],
                      "hora_local": loc.strftime("%H:%M:%S"), "lat": round(ob[1], 5), "lon": round(ob[2], 5), "dt_s": int(ob[0]-ts)}, ensure_ascii=False))
