"""
Testa features #1, #2, #4 para predecir ramal de viaje 1260.

#1: ramal del viaje previo del mismo vehiculo (1255=168A, 1259=168C)
#2: consistencia intra-dia (vehiculo que hizo 168A esta manana, sigue haciendo 168A?)
#4: odo delta (cuanto recorrio el vehiculo en el viaje previo — revela el ramal anterior)
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
                entry = {k: veh.get(k,'') for k in ['route_id','lat','lon','start_time','license_plate','start_date','direction_id']}
                entry['ts'] = ts
                entry['odo'] = veh.get('odo', 0)
                entry['speed'] = veh.get('speed', 0)
                state[vid] = entry
                veh_meta[vid] = {'label': lbl, 'plate': entry['license_plate'].strip()}
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

# ---- Construir lista de viajes 1260 con contexto completo ----
MAX_GAP = 7200
INBOUND  = {'1255', '1259'}
OUTBOUND = {'1254', '1258'}
ALL_SVC  = {'1254','1255','1258','1259','1260'}

trips = []
for vid, history in veh_history.items():
    meta = veh_meta[vid]
    for i, ev in enumerate(history):
        if ev['route_id'] != '1260': continue

        # Destino (siguiente rid no-vacio post-1260)
        end_rid = None
        end_ev  = None
        for j in range(i+1, min(i+15, len(history))):
            fut = history[j]
            if fut['route_id'] not in ('','1260','1261'):
                if fut['ts'] - ev['ts'] <= MAX_GAP:
                    end_rid = fut['route_id']
                    end_ev  = fut
                break
        if end_rid not in OUTBOUND: continue

        # --- FEATURE #1: ultimo ramal de servicio real ANTES del 1260 ---
        prev_svc_rid = None
        prev_svc_odo = None
        for k in range(i-1, max(i-20, -1), -1):
            r = history[k]['route_id']
            if r in ALL_SVC:
                prev_svc_rid = r
                prev_svc_odo = history[k]['odo']
                break

        # --- FEATURE #4: odo delta (odo al iniciar 1260 - odo del ultimo evento previo con odo>0) ---
        odo_at_1260 = ev['odo']
        prev_odo_val = None
        for k in range(i-1, max(i-30, -1), -1):
            if history[k]['odo'] > 0:
                prev_odo_val = history[k]['odo']
                break
        odo_delta = (odo_at_1260 - prev_odo_val) if (odo_at_1260 > 0 and prev_odo_val and odo_at_1260 >= prev_odo_val) else None

        # --- FEATURE #2: ramal mayoritario del vehiculo ANTES de este viaje (mismo dia) ---
        day_str = datetime.datetime.fromtimestamp(ev['ts']).strftime('%Y-%m-%d')
        prior_a = sum(1 for k in range(i) if history[k]['route_id']=='1254'
                      and datetime.datetime.fromtimestamp(history[k]['ts']).strftime('%Y-%m-%d')==day_str)
        prior_c = sum(1 for k in range(i) if history[k]['route_id']=='1258'
                      and datetime.datetime.fromtimestamp(history[k]['ts']).strftime('%Y-%m-%d')==day_str)

        trips.append({
            'vid': vid, 'plate': meta['plate'], 'label': meta['label'],
            'ts': ev['ts'], 'date': day_str,
            'end_rid': end_rid,
            # #1
            'prev_svc_rid': prev_svc_rid,
            # #2
            'prior_a_today': prior_a, 'prior_c_today': prior_c,
            # #4
            'odo_delta': odo_delta,
            'odo_at_start': odo_at_1260,
        })

total = len(trips)
n_a = sum(1 for t in trips if t['end_rid']=='1254')
n_c = sum(1 for t in trips if t['end_rid']=='1258')
print(f"Viajes 1260 → 1254/1258: {total}  (168A={n_a} {n_a/total:.0%}, 168C={n_c} {n_c/total:.0%})")

# ================================================================
# FEATURE #1: ramal del viaje previo
# ================================================================
print("\n" + "="*60)
print("FEATURE #1: Ramal del viaje previo predice el siguiente?")
print("="*60)

# Matriz: prev_rid → end_rid
matrix = collections.defaultdict(collections.Counter)
for t in trips:
    matrix[t['prev_svc_rid'] or 'UNKNOWN'][t['end_rid']] += 1

print(f"\n{'prev_rid':<12} {'->1254(A)':>10} {'->1258(C)':>10} {'total':>8}  {'P(A)':>6}")
for prev in sorted(matrix.keys()):
    ctr = matrix[prev]
    tot = sum(ctr.values())
    a   = ctr.get('1254',0)
    c   = ctr.get('1258',0)
    pa  = a/tot if tot else 0
    print(f"  {prev:<12} {a:>10} {c:>10} {tot:>8}  {pa:>5.0%}")

# Detallar los casos de ramal previo 1255 y 1259
for prev_label, prev_rid in [('168A inbound (1255)', '1255'), ('168C inbound (1259)', '1259')]:
    subset = [t for t in trips if t['prev_svc_rid'] == prev_rid]
    if not subset: continue
    na = sum(1 for t in subset if t['end_rid']=='1254')
    nc = sum(1 for t in subset if t['end_rid']=='1258')
    print(f"\n  Prev={prev_label}: n={len(subset)}, A={na} ({na/len(subset):.0%}), C={nc} ({nc/len(subset):.0%})")
    # Consistencia por vehiculo: de los que vinieron de 1255, cuantos hacen 168A?
    by_veh = collections.defaultdict(lambda: collections.Counter())
    for t in subset:
        by_veh[t['plate']][t['end_rid']] += 1
    pure_a = sum(1 for v in by_veh.values() if set(v)=={'1254'})
    pure_c = sum(1 for v in by_veh.values() if set(v)=={'1258'})
    mixed  = sum(1 for v in by_veh.values() if len(v)>1)
    print(f"    Por vehiculo: siempre_A={pure_a}, siempre_C={pure_c}, mixtos={mixed}")

# ================================================================
# FEATURE #2: consistencia intra-dia
# ================================================================
print("\n" + "="*60)
print("FEATURE #2: Historial del vehiculo en el mismo dia")
print("="*60)

# Caso A: primer viaje del dia (sin historial previo)
first_of_day = [t for t in trips if t['prior_a_today']==0 and t['prior_c_today']==0]
fa = sum(1 for t in first_of_day if t['end_rid']=='1254')
fc = sum(1 for t in first_of_day if t['end_rid']=='1258')
print(f"\n  Primer viaje del dia (sin historial): n={len(first_of_day)}  A={fa} ({fa/len(first_of_day):.0%})  C={fc} ({fc/len(first_of_day):.0%})")

# Caso B: tiene historial solo de 168A hoy
only_a = [t for t in trips if t['prior_a_today']>0 and t['prior_c_today']==0]
if only_a:
    fa2 = sum(1 for t in only_a if t['end_rid']=='1254')
    fc2 = sum(1 for t in only_a if t['end_rid']=='1258')
    print(f"  Solo hizo 168A hoy (antes de este viaje): n={len(only_a)}  A={fa2} ({fa2/len(only_a):.0%})  C={fc2} ({fc2/len(only_a):.0%})")

# Caso C: tiene historial solo de 168C hoy
only_c = [t for t in trips if t['prior_c_today']>0 and t['prior_a_today']==0]
if only_c:
    fa3 = sum(1 for t in only_c if t['end_rid']=='1254')
    fc3 = sum(1 for t in only_c if t['end_rid']=='1258')
    print(f"  Solo hizo 168C hoy (antes de este viaje): n={len(only_c)}  A={fa3} ({fa3/len(only_c):.0%})  C={fc3} ({fc3/len(only_c):.0%})")

# Caso D: hizo ambos hoy
both_today = [t for t in trips if t['prior_a_today']>0 and t['prior_c_today']>0]
if both_today:
    # Cual fue el ultimo?
    last_a_wins = [t for t in both_today if t['prior_a_today'] >= t['prior_c_today']]
    last_c_wins = [t for t in both_today if t['prior_c_today'] >  t['prior_a_today']]
    print(f"\n  Hizo ambos hoy — mas A hoy ({len(last_a_wins)} viajes):")
    if last_a_wins:
        fa4 = sum(1 for t in last_a_wins if t['end_rid']=='1254')
        fc4 = sum(1 for t in last_a_wins if t['end_rid']=='1258')
        print(f"    A={fa4} ({fa4/len(last_a_wins):.0%})  C={fc4} ({fc4/len(last_a_wins):.0%})")
    print(f"  Hizo ambos hoy — mas C hoy ({len(last_c_wins)} viajes):")
    if last_c_wins:
        fa5 = sum(1 for t in last_c_wins if t['end_rid']=='1254')
        fc5 = sum(1 for t in last_c_wins if t['end_rid']=='1258')
        print(f"    A={fa5} ({fa5/len(last_c_wins):.0%})  C={fc5} ({fc5/len(last_c_wins):.0%})")

# Grafico de precision vs cantidad de viajes previos del dia
print(f"\n  Precision segun cuantos viajes previos del dia conocemos:")
print(f"  {'viajes_prev':<12} {'n':>6} {'P(repite ramal)':>16}")
for n_prev in range(0, 8):
    subset = [t for t in trips if (t['prior_a_today'] + t['prior_c_today']) == n_prev]
    if len(subset) < 5: continue
    # Ramal dominante previo
    correct = 0
    for t in subset:
        if t['prior_a_today'] == 0 and t['prior_c_today'] == 0:
            continue  # sin informacion
        dominant = '1254' if t['prior_a_today'] >= t['prior_c_today'] else '1258'
        if t['end_rid'] == dominant: correct += 1
    if n_prev > 0:
        print(f"  {n_prev:<12} {len(subset):>6} {correct/len(subset):>15.0%}")
    else:
        print(f"  {n_prev:<12} {len(subset):>6} {'(sin base)':>16}")

# ================================================================
# FEATURE #4: odo delta
# ================================================================
print("\n" + "="*60)
print("FEATURE #4: Odo delta del viaje previo")
print("="*60)

with_odo = [t for t in trips if t['odo_delta'] is not None and t['odo_delta'] > 500]
print(f"\n  Viajes con odo_delta valido (>500m): {len(with_odo)} de {total}")

odo_a = [t['odo_delta'] for t in with_odo if t['end_rid']=='1254']
odo_c = [t['odo_delta'] for t in with_odo if t['end_rid']=='1258']

if odo_a and odo_c:
    def stats(v): return f"n={len(v)} avg={sum(v)/len(v)/1000:.1f}km median={sorted(v)[len(v)//2]/1000:.1f}km min={min(v)/1000:.1f}km max={max(v)/1000:.1f}km"
    print(f"  168A: {stats(odo_a)}")
    print(f"  168C: {stats(odo_c)}")

    # Distribucion por buckets de 2km
    print(f"\n  Distribucion odo_delta:")
    print(f"  {'bucket_km':<12} {'168A':>8} {'168C':>8}  {'P(A)':>6}")
    all_buckets = sorted(set(v//2000*2 for v in odo_a+odo_c))
    for b in all_buckets:
        na = sum(1 for v in odo_a if v//2000*2 == b)
        nc = sum(1 for v in odo_c if v//2000*2 == b)
        tot = na+nc
        pa = na/tot if tot else 0
        bar = '█'*na + '░'*nc
        print(f"  {b//1000:>3}-{(b+2000)//1000}km {na:>8} {nc:>8}  {pa:>5.0%}  {bar[:40]}")

    # Threshold optimo
    print(f"\n  Busqueda de threshold optimo:")
    thresholds = sorted(set(odo_a + odo_c))
    best_acc, best_thr = 0, 0
    for thr in thresholds[::max(1,len(thresholds)//50)]:
        # debajo del threshold -> predecir 168C, arriba -> 168A
        correct = sum(1 for v in odo_a if v >= thr) + sum(1 for v in odo_c if v < thr)
        acc = correct / len(with_odo)
        if acc > best_acc:
            best_acc = acc
            best_thr = thr
    print(f"  Mejor threshold: odo_delta >= {best_thr/1000:.1f}km -> 168A  (accuracy={best_acc:.0%})")

# ================================================================
# COMBINACION: #1 + #2
# ================================================================
print("\n" + "="*60)
print("COMBINACION #1 + #2: prev_rid + historial intra-dia")
print("="*60)

combo = collections.defaultdict(collections.Counter)
for t in trips:
    prev = t['prev_svc_rid'] or 'UNK'
    if t['prior_a_today']==0 and t['prior_c_today']==0:
        hist = 'first'
    elif t['prior_a_today']>0 and t['prior_c_today']==0:
        hist = 'only_A'
    elif t['prior_c_today']>0 and t['prior_a_today']==0:
        hist = 'only_C'
    else:
        hist = 'mixed'
    combo[f"{prev}|{hist}"][t['end_rid']] += 1

print(f"\n  {'prev|hist':<22} {'->A':>6} {'->C':>6} {'tot':>6}  {'P(A)':>6}")
for key in sorted(combo.keys()):
    ctr = combo[key]
    tot = sum(ctr.values())
    a   = ctr.get('1254',0)
    c   = ctr.get('1258',0)
    pa  = a/tot if tot else 0
    flag = ' <<<' if pa >= 0.75 or pa <= 0.25 else ''
    print(f"  {key:<22} {a:>6} {c:>6} {tot:>6}  {pa:>5.0%}{flag}")
