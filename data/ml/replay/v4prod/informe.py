import json
import pandas as pd
from pathlib import Path
t = Path('data/ml/replay/v4prod/tablas.md').read_text(encoding='utf-8')
sec = {s.split('\n', 1)[0]: s.split('\n', 1)[1].strip() for s in t.split('## ')[1:]}
grp = sec[[k for k in sec if k.startswith('Grupos')][0]]
par = sec['Pareada']; nue = sec['72 nuevas']; act = sec['8 actuales']; ext = sec['Extra']
nue_tab, prop = nue.split('\n\nPropuesta: ')
r = pd.read_csv('data/ml/v4_eval_ext/resultados.csv')
meta = json.load(open('data/ml/v4_eval_ext/ext_meta.json'))
rows = ["| línea | n filas (3–7 min) | clusters | MAE (s) | IC 95 % (bootstrap por cluster) | IC 95 % (iid) | MAE solo filas del eval congelado (n) | MAE solo filas adicionales | llega antes % | llega después % | start_unknown % | pasa (n ≥ 100, MAE ≤ 71,1) |",
        "|---|---:|---:|---:|---|---|---|---|---|---|---|---|"]
for _, x in r.sort_values('mae').iterrows():
    rows.append(f"| {x.line} | {x.n} | {x.n_cl} | {x.mae:.1f} | {x.ci_lo:.1f}–{x.ci_hi:.1f} | {x.iid_lo:.1f}–{x.iid_hi:.1f} | {x.mae_frozen:.1f} ({x.n_frozen}) | {x.mae_add:.1f} | {x.antes:.1f} | {x.desp:.1f} | {x.su:.0f} | {'sí' if x.pasa else 'no'} |")
exp2 = "\n".join(rows)
tpl = Path('data/ml/replay/v4prod/informe_tpl.md').read_text(encoding='utf-8')
doc = (tpl.replace('@@GRP@@', grp).replace('@@PAR@@', par).replace('@@NUE@@', nue_tab).replace('@@PROP@@', prop)
          .replace('@@ACT@@', act).replace('@@EXT@@', ext).replace('@@EXP2@@', exp2)
          .replace('@@CKPT@@', meta['ckpt']).replace('@@N@@', str(meta['n'])).replace('@@NFZ@@', str(meta['n_in_frozen'])))
Path('data/ml/replay/V4_PRODUCCION.md').write_text(doc, encoding='utf-8')
print(len(doc))
