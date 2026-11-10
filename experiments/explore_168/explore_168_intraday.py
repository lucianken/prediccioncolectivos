"""
Sampling: verificar que Darwin desaparece despues de las 22h
y los vehiculos reciben 1254/1258 directamente.
Solo 5 dias aleatorios.
"""
import gzip, json, sys, datetime, collections
sys.stdout.reconfigure(encoding='utf-8')

# Sample 5 dias distribuidos en el periodo
SAMPLE_FILES = [
    'Z:/grabaciones/2026-04-05.ndjson.gz',
    'Z:/grabaciones/2026-04-20.ndjson.gz',
    'Z:/grabaciones/2026-05-10.ndjson.gz',
    'Z:/grabaciones/2026-05-28.ndjson.gz',
    'Z:/grabaciones/2026-06-01.ndjson.gz',
]

DARWIN  = {'1780','1260','1774','1256'}
CLEAN_A = {'1773','1781','1254','1255'}
CLEAN_C = {'1775','1783','1258','1259'}
CLEAN   = CLEAN_A | CLEAN_C

# Contar asignaciones NEW por hora para cada categoria
hour_darwin = collections.Counter()
hour_clean  = collections.Counter()

for fpath in SAMPLE_FILES:
    try:
        with gzip.open(fpath, 'rt', encoding='utf-8') as f:
            for line in f:
                obj = json.loads(line)
                ts  = obj.get('t', 0)
                h   = datetime.datetime.fromtimestamp(ts).hour
                for veh in obj.get('new', []):
                    if not veh.get('label','').endswith('-133'): continue
                    rid = veh.get('route_id','')
                    if rid in DARWIN:  hour_darwin[h] += 1
                    elif rid in CLEAN: hour_clean[h]  += 1
    except FileNotFoundError:
        print(f"  No encontrado: {fpath}")

print("Hora  Darwin  Limpio  %Darwin")
print("─" * 35)
for h in range(24):
    d = hour_darwin.get(h, 0)
    c = hour_clean.get(h, 0)
    tot = d + c
    if tot == 0: continue
    pct = d/tot if tot else 0
    bar = '▓'*int(pct*20) + '░'*(20-int(pct*20))
    print(f"  {h:02d}h  {d:>6}  {c:>6}  {pct:>5.0%}  {bar}")
