"""
Análisis completo de línea 168 sobre todos los datos disponibles.

Paso 1: mapear todos los route_ids históricos a 168A/168C/DARWIN via transiciones
Paso 2: identificar Darwin por período
Paso 3: plate × weekday sobre 65 días
"""
import gzip, json, sys, datetime, collections, glob, os
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = 'Z:/grabaciones'
all_files = sorted(glob.glob(os.path.join(DATA_DIR, '*.ndjson.gz')))
print(f"Archivos disponibles: {len(all_files)}  ({os.path.basename(all_files[0])} → {os.path.basename(all_files[-1])})")

# ── Reconstruir historial de vehículos suffix 133 ──────────────────────────
veh_history = collections.defaultdict(list)
veh_meta    = {}
state       = {}

def merge(base, upd):
    r = base.copy()
    for k, v in upd.items():
        if k != 'id': r[k] = v
    return r

print("Leyendo archivos...", end='', flush=True)
for fpath in all_files:
    with gzip.open(fpath, 'rt', encoding='utf-8') as f:
        for line in f:
            obj = json.loads(line)
            ts  = obj.get('t', 0)
            for veh in obj.get('new', []):
                vid = veh.get('id','')
                lbl = veh.get('label','')
                if not lbl.endswith('-133'): continue
                entry = {k: veh.get(k,'') for k in
                    ['route_id','lat','lon','start_time','license_plate','start_date']}
                entry['ts']  = ts
                entry['odo'] = veh.get('odo', 0)
                state[vid]   = entry
                veh_meta[vid] = {'label': lbl, 'plate': entry['license_plate'].strip()}
                h = veh_history[vid]
                if not h or h[-1]['route_id'] != entry['route_id']:
                    veh_history[vid].append(entry.copy())
            for upd in obj.get('upd', []):
                vid = upd.get('id','')
                if vid not in state: continue
                if not veh_meta.get(vid,{}).get('label','').endswith('-133'): continue
                ns = merge(state[vid], upd); ns['ts'] = ts
                prev = state[vid]['route_id']; state[vid] = ns
                if prev != ns.get('route_id', prev):
                    veh_history[vid].append(ns.copy())
            for did in obj.get('del', []):
                state.pop(did, None)

print(f" listo. Vehiculos: {len(veh_history)}")

# ── Paso 1 & 2: triple-transiciones X → '' → Y para identificar Darwin ──────
# Collecto todas las triples X → (gap) → Y para route_ids de 168

MAX_GAP = 7200
SVC_RIDS = {'1773','1775','1780','1781','1782','1783','1784',
            '1254','1255','1256','1257','1258','1259','1260','1261','1310'}

# Para cada route_id que dropea a '', ¿qué viene después?
drop_to_next = collections.defaultdict(collections.Counter)  # from_rid → {next_rid: count}

for vid, history in veh_history.items():
    for i, ev in enumerate(history):
        rid = ev['route_id']
        if rid not in SVC_RIDS: continue
        # buscar si dropea a '' y luego qué viene
        if i+1 < len(history) and history[i+1]['route_id'] == '':
            # buscar próximo no-vacío
            for j in range(i+2, min(i+10, len(history))):
                nxt = history[j]['route_id']
                if nxt != '':
                    if history[j]['ts'] - ev['ts'] <= MAX_GAP:
                        drop_to_next[rid][nxt] += 1
                    break
        # también transiciones directas (sin gap)
        elif i+1 < len(history) and history[i+1]['route_id'] != '' and history[i+1]['route_id'] != rid:
            nxt = history[i+1]['route_id']
            if nxt in SVC_RIDS:
                drop_to_next[rid][nxt] += 1

print("\n" + "="*65)
print("PASO 1+2: Transiciones por route_id (quién va adónde)")
print("="*65)

# Los destinos conocidos post-gap para clasificar
# En P2: 1254=168A-d0, 1255=168A-d1, 1258=168C-d0, 1259=168C-d1
CLEAN_168A = {'1254','1255','1773','1781'}
CLEAN_168C = {'1258','1259','1775','1783'}
CLEAN_ALL  = CLEAN_168A | CLEAN_168C

# Calcular volumen y first/last seen
rid_stats = collections.defaultdict(lambda: {'obs':0, 'days':set(), 'dirs':set()})
for vid, history in veh_history.items():
    for ev in history:
        rid = ev['route_id']
        if rid in SVC_RIDS:
            rid_stats[rid]['obs'] += 1
            rid_stats[rid]['days'].add(datetime.datetime.fromtimestamp(ev['ts']).strftime('%Y-%m-%d'))

print(f"\n{'route_id':<10} {'d':>3} {'obs':>8} {'days':>5} {'first':<12} {'last':<12}  destinos_tras_drop")
for rid in sorted(SVC_RIDS, key=lambda r: min(rid_stats[r]['days']) if rid_stats[r]['days'] else '9'):
    st = rid_stats[rid]
    if not st['days']: continue
    days_sorted = sorted(st['days'])
    dest = drop_to_next.get(rid, {})
    dest_str = '  '.join(f"{k}×{v}" for k,v in sorted(dest.items(), key=lambda x:-x[1])[:6])
    print(f"  {rid:<10} {'?':>3} {st['obs']:>8} {len(st['days']):>5} {days_sorted[0]:<12} {days_sorted[-1]:<12}  {dest_str}")

# ── Clasificación manual guiada por transiciones ───────────────────────────
# Período 1 (mar-may7): 1773,1775,1780,1781,1782,1783,1784
# Período 1.5 (may8-22): 1310
# Período 2 (may23+): 1254,1255,1256,1257,1258,1259,1260,1261

# Regla: si X → (gap) → {1254/1255/1773/1781} → X es Darwin hacia 168A
#         si X → (gap) → {1258/1259/1775/1783} → X es Darwin hacia 168C
#         si X → (gap) → ambos        → X es Darwin compartido (el bug)
def classify_darwin(rid):
    dest = drop_to_next.get(rid, {})
    to_a = sum(v for k,v in dest.items() if k in CLEAN_168A)
    to_c = sum(v for k,v in dest.items() if k in CLEAN_168C)
    total = to_a + to_c
    if total < 5: return None
    if to_a >= 5 and to_c >= 5: return 'DARWIN'
    if to_a > to_c * 3:         return '168A-ONLY?'
    if to_c > to_a * 3:         return '168C-ONLY?'
    return 'MIXED'

print("\n" + "="*65)
print("PASO 2: Clasificación de route_ids")
print("="*65)

# Route_ids con destinos claros → son clean (no Darwin)
# Route_ids con destinos a AMBOS 168A y 168C → son Darwin

RAMAL_MAP = {
    # Período 2 (confirmado por CuandoSubo)
    '1254': '168A-d0', '1255': '168A-d1',
    '1258': '168C-d0', '1259': '168C-d1',
    '1260': 'DARWIN',  '1261': 'DARWIN-terminal',
    '1256': 'DARWIN-trans', '1257': 'skip',
    # Período 1 (por volumen/tasa y confirmación de transiciones)
    '1773': '168A-d0', '1781': '168A-d1',
    '1775': '168C-d0', '1783': '168C-d1',
    '1780': 'DARWIN',  '1784': 'DARWIN-terminal',
    '1774': 'DARWIN-trans', '1782': 'skip',
    # Período 1.5
    '1310': 'DARWIN?',
}

# Verificar con transiciones
print(f"\n{'route_id':<10} {'asignado':<18} {'→168A':>6} {'→168C':>6} {'verifica':<12}")
for rid in sorted(RAMAL_MAP.keys()):
    dest   = drop_to_next.get(rid, {})
    to_a   = sum(v for k,v in dest.items() if k in CLEAN_168A)
    to_c   = sum(v for k,v in dest.items() if k in CLEAN_168C)
    cls    = classify_darwin(rid)
    asig   = RAMAL_MAP[rid]
    # Verificación
    if asig == 'DARWIN' and cls == 'DARWIN':         verif = 'OK ✓'
    elif asig in ('168A-d0','168A-d1') and to_a > 0: verif = f'OK (→A×{to_a})'
    elif asig in ('168C-d0','168C-d1') and to_c > 0: verif = f'OK (→C×{to_c})'
    elif cls is None:                                  verif = 'sin datos drop'
    else:                                              verif = cls or '?'
    print(f"  {rid:<10} {asig:<18} {to_a:>6} {to_c:>6}  {verif}")

print("\nResumen:")
for ramal in ['168A-d0','168A-d1','168C-d0','168C-d1','DARWIN']:
    rids = [r for r,v in RAMAL_MAP.items() if v == ramal]
    print(f"  {ramal:<18}: {rids}")

# ── Paso 3: plate × weekday sobre los 65 días ─────────────────────────────
print("\n" + "="*65)
print("PASO 3: plate × weekday  (todos los datos, 65 días)")
print("="*65)

# Construir viajes DARWIN → resolución
DARWIN_RIDS  = {r for r,v in RAMAL_MAP.items() if 'DARWIN' in v}
A_RIDS       = {r for r,v in RAMAL_MAP.items() if v in ('168A-d0','168A-d1')}
C_RIDS       = {r for r,v in RAMAL_MAP.items() if v in ('168C-d0','168C-d1')}
RESOLVE_RIDS = A_RIDS | C_RIDS

trips = []
for vid, history in veh_history.items():
    plate = veh_meta[vid]['plate']
    for i, ev in enumerate(history):
        if ev['route_id'] not in DARWIN_RIDS: continue
        # buscar resolución
        for j in range(i+1, min(i+15, len(history))):
            fut = history[j]
            if fut['route_id'] in RESOLVE_RIDS:
                if fut['ts'] - ev['ts'] <= MAX_GAP:
                    is_a = fut['route_id'] in A_RIDS
                    dt   = datetime.datetime.fromtimestamp(ev['ts'])
                    trips.append({
                        'plate':   plate,
                        'weekday': dt.weekday(),
                        'wname':   dt.strftime('%A'),
                        'date':    dt.strftime('%Y-%m-%d'),
                        'ramal':   'A' if is_a else 'C',
                    })
                break
            if fut['route_id'] == '' or fut['route_id'] in DARWIN_RIDS:
                continue
            break

total = len(trips)
na = sum(1 for t in trips if t['ramal']=='A')
nc = sum(1 for t in trips if t['ramal']=='C')
print(f"\nViajes DARWIN resueltos: {total}  A={na} ({na/total:.0%})  C={nc} ({nc/total:.0%})")

# Tabla plate × weekday
pdw = collections.defaultdict(collections.Counter)
for t in trips:
    pdw[(t['plate'], t['weekday'])][t['ramal']] += 1

# Métricas
def combo_accuracy(min_obs=3):
    combos = [(k,v) for k,v in pdw.items() if sum(v.values()) >= min_obs]
    covered = sum(sum(v.values()) for _,v in combos)
    correct  = sum(max(v.values()) for _,v in combos)
    pure_a   = sum(1 for _,v in combos if set(v)=={'A'})
    pure_c   = sum(1 for _,v in combos if set(v)=={'C'})
    mixed    = sum(1 for _,v in combos if len(v)>1)
    return covered, correct, pure_a, pure_c, mixed, len(combos)

WNAMES = ['Lun','Mar','Mie','Jue','Vie','Sab','Dom']

print(f"\n  Análisis por threshold de observaciones mínimas por combo:")
print(f"  {'min_obs':<8} {'combos':>7} {'puro_A':>7} {'puro_C':>7} {'mixto':>7} {'cobertura':>11} {'accuracy':>10}")
for mo in [1, 2, 3, 4, 5, 7, 10]:
    cov, cor, pa, pc, mx, nc_ = combo_accuracy(mo)
    if nc_ == 0: continue
    print(f"  {mo:<8} {nc_:>7} {pa:>7} {pc:>7} {mx:>7} {cov:>8}/{total:<6} {cor/cov:>9.0%}")

# Combos puros con >=3 obs
print(f"\n  Combos PUROS 168A (>=3 obs):")
pure_a = sorted([(k,v) for k,v in pdw.items() if set(v)=={'A'} and sum(v.values())>=3])
for (pl,wd), v in pure_a:
    print(f"    {pl:<12} {WNAMES[wd]}: {sum(v.values())}×")

print(f"\n  Combos PUROS 168C (>=3 obs):")
pure_c = sorted([(k,v) for k,v in pdw.items() if set(v)=={'C'} and sum(v.values())>=3])
for (pl,wd), v in pure_c:
    print(f"    {pl:<12} {WNAMES[wd]}: {sum(v.values())}×")

# Matriz resumida: para cada patente, sus días
print(f"\n  Patentes con dias CONSISTENTES (puro en >=2 dias distintos):")
plate_days = collections.defaultdict(dict)  # plate → {wd: ramal_puro}
for (pl, wd), v in pdw.items():
    if sum(v.values()) >= 3 and len(v) == 1:
        plate_days[pl][wd] = list(v.keys())[0]

for pl in sorted(plate_days.keys()):
    days = plate_days[pl]
    if len(days) >= 2:
        day_str = '  '.join(f"{WNAMES[wd]}={r}" for wd, r in sorted(days.items()))
        print(f"    {pl:<12}: {day_str}")

# Cuántos viajes cubre el lookup completo con >=1 obs
print(f"\n  Cobertura del lookup completo (cualquier combo con >=1 obs):")
all_combos = {k: 'A' if v.get('A',0)>=v.get('C',0) else 'C' for k,v in pdw.items()}
covered_trips = [t for t in trips if (t['plate'], t['weekday']) in all_combos]
correct_trips  = [t for t in covered_trips if all_combos[(t['plate'],t['weekday'])] == t['ramal']]
print(f"    {len(covered_trips)}/{total} viajes ({len(covered_trips)/total:.0%}) cubiertos")
print(f"    Accuracy: {len(correct_trips)}/{len(covered_trips)} = {len(correct_trips)/len(covered_trips):.0%}")

# Distribución de accuracy por número de semanas de historia
print(f"\n  Plate × weekday: consistency por patente (cuantos dias son puros)")
plate_summary = collections.defaultdict(lambda: {'pure':0,'mixed':0,'total_obs':0})
for (pl, wd), v in pdw.items():
    obs = sum(v.values())
    plate_summary[pl]['total_obs'] += obs
    if len(v)==1: plate_summary[pl]['pure'] += 1
    else:         plate_summary[pl]['mixed'] += 1

fully_pure  = sum(1 for p in plate_summary.values() if p['mixed']==0 and p['pure']>=2)
has_mixed   = sum(1 for p in plate_summary.values() if p['mixed']>0)
print(f"    Patentes 100% puras (>=2 dias): {fully_pure}")
print(f"    Patentes con al menos 1 combo mixto: {has_mixed}")
print(f"    Total patentes: {len(plate_summary)}")
