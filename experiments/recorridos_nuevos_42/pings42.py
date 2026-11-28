"""Extrae los pings de la línea 42 de cada día (read_day, mismo filtro que el replay) a parquet (cache, no se commitea)."""
import sys
from pathlib import Path
import pandas as pd
from red.label_map import load_label_line_data, resolve_label_line_index
from prediccion.v2.day import read_day
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/ml/replay/recorridos_nuevos_42/cache"; OUT.mkdir(parents=True, exist_ok=True)
for day in sys.argv[1:]:
    if (OUT / f"{day}_42.parquet").exists(): continue
    li = resolve_label_line_index(load_label_line_data(str(ROOT / "LABEL_LINE_MAP.json")), on_date=day)
    lm = {s: v["line"] for s, v in li.items()}
    veh, _, _ = read_day(Path("Z:/grabaciones") / f"{day}.ndjson.gz", lm, {"42"}, None, 30, False)
    rows = [(vid, o[0], o[1], o[2], o[3]) for vid, r in veh.items() for o in r["obs"]]
    pd.DataFrame(rows, columns=["vid", "ts", "lat", "lon", "speed"]).to_parquet(OUT / f"{day}_42.parquet")
    print(day, len(veh), len(rows), flush=True)
