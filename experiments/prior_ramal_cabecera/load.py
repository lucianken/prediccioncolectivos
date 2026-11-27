"""Carga de viajes ex post (v4 trips) de las 8 lineas multi-ramal -> parquet con ramal/sentido/origen."""
import json, glob, re
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
LINES = ['39', '42', '50', '106', '107', '132', '151', '168']
def shape_table():
    rows = []
    for l in LINES:
        d = json.load(open(ROOT.parent / f'proyectoconsola/data/line_shapes/{l}.json', encoding='utf8'))
        for x in d['ramales']:
            nm = x['name']; tail = nm.split(':', 1)[1].strip()
            origin = re.split(r'\s*→', tail)[0].strip()
            rows.append(dict(line=l, shape_id=str(x['shapeId']), ramal=x['shortName'].replace(' ', ''), origin=origin))
    return pd.DataFrame(rows)
if __name__ == '__main__':
    st = shape_table(); fr = []
    for f in sorted(glob.glob(str(ROOT / 'data/ml/v4/daily/*.trips.parquet'))):
        d = Path(f).name[:10]
        x = pd.read_parquet(f); x = x[x.line.isin(LINES)].copy(); x['day'] = d; fr.append(x)
    x = pd.concat(fr); x['shape_id'] = x.shape_id.astype(str)
    x = x.merge(st, on=['line', 'shape_id'], how='inner')
    x.to_parquet(Path(__file__).parent / 'trips8.parquet')
    print(len(x), x.day.min(), x.day.max())
    print(st.to_string())
    print(x.groupby(['line', 'ramal', 'direction_id', 'origin']).size().to_string())
    print(x.groupby('line').start_unknown.mean())
