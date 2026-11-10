"""
Analiza la secuencia temporal de viajes 1260 dentro de cada día.
Pregunta: ¿el start_time separa 168A vs 168C intra-día?
¿Se alternan? ¿Hay expectativa estadística sobre el próximo?
"""
import gzip, json, sys, datetime, collections
sys.stdout.reconfigure(encoding='utf-8')

files = [
    'Z:/grabaciones/2026-05-26.ndjson.gz',
    'Z:/grabaciones/2026-05-27.ndjson.gz',
    'Z:/grabaciones/2026-05-28.ndjson.gz',
    'Z:/grabaciones/2026-05-29.ndjson.gz',
    'Z:/grabaciones/2026-05-30.ndjson.gz',
    'Z:/grabaciones/2026-05-31.ndjson.gz',
    'Z:/grabaciones/2026-06-01.ndjson.gz',
]

# Mismo historial que antes — reusar logica
veh_history = collections.defaultdict(list)
veh_meta = {}
state = {}

def merge(base, upd):
    r = base.copy()
    for k, v in upd.items():
        if k != 'id': r[k] = v
    return r

for fpath in files:
    with gzip.open(fpath, 'rt', encoding='utf-8') as f:
        for line in f:
            obj = json.loads(line)
            ts = obj.get('t', 0)
            for veh in obj.get('new', []):
                vid = veh.get('id','')
                lbl = veh.get('label','')
                if not lbl.endswith('-133'): continue
                entry = {k: veh.get(k, '') for k in ['route_id','lat','lon','start_time','trip_id','license_plate','start_date','speed','direction_id']}
                entry['ts'] = ts
                entry['odo'] = veh.get('odo', 0)
                state[vid] = entry
                veh_meta[vid] = {'label': lbl, 'license_plate': entry['license_plate'].strip()}
                history = veh_history[vid]
                if not history or history[-1]['route_id'] != entry['route_id']:
                    veh_history[vid].append(entry.copy())
            for upd in obj.get('upd', []):
                vid = upd.get('id','')
                if vid not in state: continue
                if not veh_meta.get(vid,{}).get('label','').endswith('-133'): continue
                new_state = merge(state[vid], upd)
                new_state['ts'] = ts
                prev_rid = state[vid]['route_id']
                state[vid] = new_state
                if prev_rid != new_state.get('route_id', prev_rid):
                    veh_history[vid].append(new_state.copy())
            for did in obj.get('del', []):
                state.pop(did, None)

# Extraer viajes 1260 con destino
MAX_GAP = 7200
trips = []
for vid, history in veh_history.items():
    for i, ev in enumerate(history):
        if ev['route_id'] != '1260': continue
        start_ev = ev
        # Buscar proximo rid no-vacio
        for j in range(i+1, min(i+15, len(history))):
            fut = history[j]
            if fut['route_id'] not in ('','1260','1261'):
                if fut['ts'] - start_ev['ts'] <= MAX_GAP:
                    trips.append({
                        'vid': vid,
                        'label': veh_meta[vid]['label'],
                        'plate': veh_meta[vid]['license_plate'],
                        'ts': start_ev['ts'],
                        'start_time': start_ev['start_time'],
                        'date': datetime.datetime.fromtimestamp(start_ev['ts']).strftime('%Y-%m-%d'),
                        'hour': datetime.datetime.fromtimestamp(start_ev['ts']).hour,
                        'end_rid': fut['route_id'],
                        'end_start_time': fut.get('start_time',''),
                    })
                break

resolved = [t for t in trips if t['end_rid'] in ('1254','1258')]
print(f"Viajes 1260 resueltos (1254 o 1258): {len(resolved)}")
print(f"  168A (1254): {sum(1 for t in resolved if t['end_rid']=='1254')}")
print(f"  168C (1258): {sum(1 for t in resolved if t['end_rid']=='1258')}")

# === ANALISIS 1: start_time intra-dia ===
# Para cada (date, start_time), ¿cuantos viajes van a 1254 vs 1258?
print("\n=== A: start_time intra-dia: ¿un slot = un ramal? ===")
slot_dest = collections.defaultdict(lambda: collections.Counter())
for t in resolved:
    slot_dest[(t['date'], t['start_time'])][t['end_rid']] += 1

pure_a = sum(1 for v in slot_dest.values() if set(v)=={'1254'})
pure_c = sum(1 for v in slot_dest.values() if set(v)=={'1258'})
mixed  = sum(1 for v in slot_dest.values() if len(set(v))>1)
print(f"  Slots (date, start_time) puros 168A:  {pure_a}")
print(f"  Slots (date, start_time) puros 168C:  {pure_c}")
print(f"  Slots mixtos (ambos ramales): {mixed}")
print(f"  Total slots: {len(slot_dest)}")

# Mostrar los mixtos
print("\n  Slots MIXTOS detalle:")
for (d, st), ctr in sorted(slot_dest.items()):
    if len(set(ctr)) > 1:
        print(f"    {d} {st}: {dict(ctr)}")

# === ANALISIS 2: secuencia temporal dentro de cada dia ===
print("\n=== B: Secuencia de partidas por dia (orden por ts) ===")
by_day = collections.defaultdict(list)
for t in resolved:
    by_day[t['date']].append(t)

for day in sorted(by_day.keys()):
    day_trips = sorted(by_day[day], key=lambda x: x['ts'])
    seq = [('A' if t['end_rid']=='1254' else 'C') for t in day_trips]
    seq_str = ''.join(seq)
    print(f"\n  {day} ({len(day_trips)} viajes): {seq_str}")
    # Contar transiciones
    transitions = collections.Counter()
    for i in range(len(seq)-1):
        transitions[(seq[i], seq[i+1])] += 1
    print(f"    A->A: {transitions[('A','A')]}  A->C: {transitions[('A','C')]}  C->A: {transitions[('C','A')]}  C->C: {transitions[('C','C')]}")

# === ANALISIS 3: matriz de transicion global ===
print("\n=== C: Matriz de transicion global (siguiente en secuencia temporal) ===")
all_trips_sorted = sorted(resolved, key=lambda x: x['ts'])
trans_global = collections.Counter()
for i in range(len(all_trips_sorted)-1):
    cur = all_trips_sorted[i]
    nxt = all_trips_sorted[i+1]
    # Solo si mismo dia
    if cur['date'] == nxt['date']:
        k = ('A' if cur['end_rid']=='1254' else 'C', 'A' if nxt['end_rid']=='1254' else 'C')
        trans_global[k] += 1

total_from_a = trans_global[('A','A')] + trans_global[('A','C')]
total_from_c = trans_global[('C','A')] + trans_global[('C','C')]
print(f"  Dado A, siguiente: A={trans_global[('A','A')]} ({trans_global[('A','A')]/total_from_a:.0%}), C={trans_global[('A','C')]} ({trans_global[('A','C')]/total_from_a:.0%})")
print(f"  Dado C, siguiente: A={trans_global[('C','A')]} ({trans_global[('C','A')]/total_from_c:.0%}), C={trans_global[('C','C')]} ({trans_global[('C','C')]/total_from_c:.0%})")

# === ANALISIS 4: gap temporal entre partidas consecutivas segun tipo ===
print("\n=== D: Gap entre partidas consecutivas de la misma linea ===")
gaps_a = []
gaps_c = []
last_a = {}  # date -> ts
last_c = {}

for t in all_trips_sorted:
    d = t['date']
    if t['end_rid'] == '1254':
        if d in last_a:
            gaps_a.append(t['ts'] - last_a[d])
        last_a[d] = t['ts']
    else:
        if d in last_c:
            gaps_c.append(t['ts'] - last_c[d])
        last_c[d] = t['ts']

if gaps_a:
    ga = sorted(gaps_a)
    print(f"  168A headway: n={len(ga)} median={ga[len(ga)//2]//60}min avg={sum(ga)//len(ga)//60}min p25={ga[len(ga)//4]//60}min p75={ga[3*len(ga)//4]//60}min")
if gaps_c:
    gc = sorted(gaps_c)
    print(f"  168C headway: n={len(gc)} median={gc[len(gc)//2]//60}min avg={sum(gc)//len(gc)//60}min p25={gc[len(gc)//4]//60}min p75={gc[3*len(gc)//4]//60}min")

# === ANALISIS 5: dado que el ultimo fue X hace T minutos, proximo es? ===
print("\n=== E: Prediccion por tiempo desde ultimo conocido ===")
# Para cada viaje, cuanto tiempo paso desde el ultimo 168A y desde el ultimo 168C?
records = []
last_a_ts = {}
last_c_ts = {}
for t in all_trips_sorted:
    d = t['date']
    dt_since_a = (t['ts'] - last_a_ts[d]) // 60 if d in last_a_ts else None
    dt_since_c = (t['ts'] - last_c_ts[d]) // 60 if d in last_c_ts else None
    records.append({'end': t['end_rid'], 'since_a': dt_since_a, 'since_c': dt_since_c})
    if t['end_rid'] == '1254': last_a_ts[d] = t['ts']
    else: last_c_ts[d] = t['ts']

# Distribucion de since_c cuando es 168C (cuanto tiempo paso desde el ultimo 168C)
since_c_when_c = [r['since_c'] for r in records if r['end']=='1258' and r['since_c'] is not None]
since_c_when_a = [r['since_c'] for r in records if r['end']=='1254' and r['since_c'] is not None]
if since_c_when_c:
    print(f"  Cuando es 168C, mins desde ultimo 168C: avg={sum(since_c_when_c)/len(since_c_when_c):.1f} median={sorted(since_c_when_c)[len(since_c_when_c)//2]}")
    # Distribucion en buckets
    buckets = collections.Counter(min(x//5, 8)*5 for x in since_c_when_c)
    print(f"    Distribucion (bucket 5min): {dict(sorted(buckets.items()))}")
if since_c_when_a:
    print(f"  Cuando es 168A, mins desde ultimo 168C: avg={sum(since_c_when_a)/len(since_c_when_a):.1f} median={sorted(since_c_when_a)[len(since_c_when_a)//2]}")
    buckets2 = collections.Counter(min(x//5, 8)*5 for x in since_c_when_a)
    print(f"    Distribucion (bucket 5min): {dict(sorted(buckets2.items()))}")

# === ANALISIS 6: Dado start_time 1260, ese mismo start_time siempre es A o C? ===
print("\n=== F: start_time 1260 consistente entre dias? ===")
st_by_time = collections.defaultdict(lambda: collections.Counter())
for t in resolved:
    st_by_time[t['start_time']][t['end_rid']] += 1

pure_a = [(st, c) for st, c in st_by_time.items() if set(c)=={'1254'} and sum(c.values())>=3]
pure_c = [(st, c) for st, c in st_by_time.items() if set(c)=={'1258'} and sum(c.values())>=3]
mixed_st = [(st, c) for st, c in st_by_time.items() if len(set(c))>1 and sum(c.values())>=3]

print(f"  start_times SIEMPRE 168A (>=3 obs): {len(pure_a)}")
for st, c in sorted(pure_a)[:10]: print(f"    {st}: {dict(c)}")
print(f"  start_times SIEMPRE 168C (>=3 obs): {len(pure_c)}")
for st, c in sorted(pure_c)[:10]: print(f"    {st}: {dict(c)}")
print(f"  start_times MIXTOS (>=3 obs, ambos ramales): {len(mixed_st)}")
for st, c in sorted(mixed_st)[:15]: print(f"    {st}: {dict(c)}")
