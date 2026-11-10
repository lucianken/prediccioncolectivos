"""
Reconstruye historial completo de route_id por vehiculo (suffix 133),
luego busca patron 1260 -> gap -> destino para analizar features predictivas.
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

# Paso 1: construir historial de eventos por vehiculo
# Para cada vehiculo suffix 133, guardar lista de (ts, route_id, lat, lon, start_time, trip_id, odo, stop_id, license_plate, start_date)
veh_history = collections.defaultdict(list)  # vid -> [(ts, fields...)]
veh_meta = {}  # vid -> {label, license_plate}

state = {}  # vid -> last known state

def merge(base, upd):
    r = base.copy()
    for k, v in upd.items():
        if k != 'id':
            r[k] = v
    return r

for fpath in files:
    with gzip.open(fpath, 'rt', encoding='utf-8') as f:
        for line in f:
            obj = json.loads(line)
            ts = obj.get('t', 0)

            for veh in obj.get('new', []):
                vid = veh.get('id','')
                lbl = veh.get('label','')
                if not lbl.endswith('-133'):
                    continue
                entry = {
                    'ts': ts, 'route_id': veh.get('route_id',''),
                    'lat': veh.get('lat',0), 'lon': veh.get('lon',0),
                    'start_time': veh.get('start_time',''),
                    'trip_id': veh.get('trip_id',''),
                    'odo': veh.get('odo',0),
                    'stop_id': veh.get('stop_id',''),
                    'license_plate': veh.get('license_plate','').strip(),
                    'start_date': veh.get('start_date',''),
                    'speed': veh.get('speed',0),
                    'direction_id': veh.get('direction_id',0),
                }
                state[vid] = entry
                veh_meta[vid] = {'label': lbl, 'license_plate': entry['license_plate']}
                # Solo guardamos si hay cambio de route_id vs ultimo evento
                history = veh_history[vid]
                if not history or history[-1]['route_id'] != entry['route_id']:
                    veh_history[vid].append(entry.copy())

            for upd in obj.get('upd', []):
                vid = upd.get('id','')
                if vid not in state:
                    continue
                if not state[vid].get('label',''):
                    continue
                lbl = veh_meta.get(vid, {}).get('label','')
                if not lbl.endswith('-133'):
                    continue
                new_state = merge(state[vid], upd)
                new_state['ts'] = ts
                prev_rid = state[vid]['route_id']
                new_rid = new_state.get('route_id', prev_rid)
                state[vid] = new_state
                if prev_rid != new_rid:
                    veh_history[vid].append(new_state.copy())

            for did in obj.get('del', []):
                state.pop(did, None)

print(f"Vehiculos suffix 133: {len(veh_history)}")

# Paso 2: encontrar secuencias 1260 -> {posible gap} -> next_rid
# Buscamos en el historial de cada vehiculo eventos 1260 seguidos por evento no-1260
TARGET = '1260'
MAX_GAP_SECS = 7200  # 2 horas max para considerar que es el mismo viaje

trips_1260 = []
for vid, history in veh_history.items():
    meta = veh_meta.get(vid, {})
    in_1260 = False
    trip_start_idx = None

    for i, ev in enumerate(history):
        rid = ev['route_id']

        if rid == TARGET and not in_1260:
            in_1260 = True
            trip_start_idx = i

        elif in_1260 and rid != TARGET:
            # Salimos de 1260 - buscar el proximo rid no-vacio
            # (podria ser '' = gap, o directamente el nuevo rid)
            start_ev = history[trip_start_idx]
            drop_ev = history[i-1] if i > trip_start_idx else start_ev  # ultimo evento en 1260

            # Buscar proximo rid no-vacio dentro del window de tiempo
            next_rid = None
            next_ev = None
            for j in range(i, min(i+20, len(history))):
                future = history[j]
                if future['route_id'] not in ('', TARGET, '1261'):
                    if future['ts'] - drop_ev['ts'] <= MAX_GAP_SECS:
                        next_rid = future['route_id']
                        next_ev = future
                    break

            if next_rid:
                trip = {
                    'vid': vid,
                    'label': meta.get('label',''),
                    'license_plate': meta.get('license_plate',''),
                    'start_ts': start_ev['ts'],
                    'start_lat': start_ev['lat'],
                    'start_lon': start_ev['lon'],
                    'start_time_1260': start_ev['start_time'],
                    'start_date_1260': start_ev['start_date'],
                    'trip_id_1260': start_ev['trip_id'],
                    'drop_ts': drop_ev['ts'],
                    'drop_lat': drop_ev['lat'],
                    'drop_lon': drop_ev['lon'],
                    'drop_odo': drop_ev['odo'],
                    'drop_stop': drop_ev.get('stop_id',''),
                    'end_rid': next_rid,
                    'end_ts': next_ev['ts'],
                    'end_lat': next_ev['lat'],
                    'end_lon': next_ev['lon'],
                    'end_start_time': next_ev['start_time'],
                    'end_trip_id': next_ev['trip_id'],
                    'duration_secs': drop_ev['ts'] - start_ev['ts'],
                    'gap_secs': next_ev['ts'] - drop_ev['ts'],
                    # Stops pasadas durante 1260
                    'stops_in_1260': [h.get('stop_id','') for h in history[trip_start_idx:i] if h.get('stop_id','')],
                }
                trips_1260.append(trip)
            in_1260 = False
            trip_start_idx = None
            if rid == TARGET:  # empezo otro 1260 inmediatamente
                in_1260 = True
                trip_start_idx = i

resolved = [t for t in trips_1260 if t['end_rid'] in ('1254','1258','1256','1255')]
dest_counts = collections.Counter(t['end_rid'] for t in resolved)
print(f"\nViajes 1260 resueltos: {len(resolved)}")
for k, v in sorted(dest_counts.items()):
    label = {'1254':'168A', '1255':'168A ret', '1258':'168C', '1256':'trans'}.get(k, k)
    print(f"  {k} ({label}): {v}")

trips_a = [t for t in resolved if t['end_rid'] == '1254']
trips_c = [t for t in resolved if t['end_rid'] == '1258']
print(f"\nUsando solo 1254 vs 1258 para comparacion: {len(trips_a)} vs {len(trips_c)}")

# === F1: Patente ===
print("\n=== F1: Patente fija por destino? ===")
plate_dest = collections.defaultdict(collections.Counter)
for t in [t for t in resolved if t['end_rid'] in ('1254','1258')]:
    plate_dest[t['license_plate']][t['end_rid']] += 1

always_a, always_c, mixed = [], [], []
for plate, ctr in sorted(plate_dest.items()):
    if set(ctr.keys()) == {'1254'}: always_a.append(plate)
    elif set(ctr.keys()) == {'1258'}: always_c.append(plate)
    else: mixed.append((plate, dict(ctr)))

print(f"  SIEMPRE 168A ({len(always_a)}): {always_a}")
print(f"  SIEMPRE 168C ({len(always_c)}): {always_c}")
print(f"  MIXTAS ({len(mixed)}):")
for pl, ctr in mixed:
    print(f"    {pl}: {ctr}")

# === F2: Vehicle ID ===
print("\n=== F2: Vehicle ID por destino? ===")
vid_dest = collections.defaultdict(collections.Counter)
for t in [t for t in resolved if t['end_rid'] in ('1254','1258')]:
    vid_dest[t['vid']][t['end_rid']] += 1
always_a_v = sum(1 for v, c in vid_dest.items() if set(c)=={'1254'})
always_c_v = sum(1 for v, c in vid_dest.items() if set(c)=={'1258'})
mixed_v = sum(1 for v, c in vid_dest.items() if len(set(c))>1)
print(f"  Siempre 168A: {always_a_v}, Siempre 168C: {always_c_v}, Mixtos: {mixed_v}")
# Mostrar los mixtos
for vid, ctr in vid_dest.items():
    if len(set(ctr)) > 1:
        print(f"    vid={vid} label={veh_meta.get(vid,{}).get('label','?')} plate={veh_meta.get(vid,{}).get('license_plate','?')}: {dict(ctr)}")

# === F3: trip_id del segmento 1260 ===
print("\n=== F3: trip_id durante 1260 ===")
tid_a = [t['trip_id_1260'] for t in trips_a if t['trip_id_1260']]
tid_c = [t['trip_id_1260'] for t in trips_c if t['trip_id_1260']]
print(f"  168A con trip_id: {len(tid_a)}/{len(trips_a)} — ejemplos: {tid_a[:5]}")
print(f"  168C con trip_id: {len(tid_c)}/{len(trips_c)} — ejemplos: {tid_c[:5]}")
# Hay patron en el trip_id?
def parse_trip(t):
    # formato "NNNNN-1"
    try: return int(t.split('-')[0])
    except: return None
nums_a = [n for t in tid_a if (n := parse_trip(t))]
nums_c = [n for t in tid_c if (n := parse_trip(t))]
if nums_a: print(f"  168A trip nums: min={min(nums_a)} max={max(nums_a)} avg={sum(nums_a)//len(nums_a)}")
if nums_c: print(f"  168C trip nums: min={min(nums_c)} max={max(nums_c)} avg={sum(nums_c)//len(nums_c)}")

# === F4: start_time de la asignacion 1260 ===
print("\n=== F4: start_time del segmento 1260 ===")
st_a = collections.Counter(t['start_time_1260'] for t in trips_a if t['start_time_1260'])
st_c = collections.Counter(t['start_time_1260'] for t in trips_c if t['start_time_1260'])
excl_a = sorted(set(st_a) - set(st_c))
excl_c = sorted(set(st_c) - set(st_a))
shared = sorted(set(st_a) & set(st_c))
print(f"  Exclusivos 168A: {excl_a[:20]}")
print(f"  Exclusivos 168C: {excl_c[:20]}")
print(f"  Compartidos: {shared[:10]} ({len(shared)} total)")

# === F5: start_time del viaje posterior (end_rid) ===
print("\n=== F5: start_time del viaje posterior (1254 o 1258) ===")
est_a = collections.Counter(t['end_start_time'] for t in trips_a if t.get('end_start_time'))
est_c = collections.Counter(t['end_start_time'] for t in trips_c if t.get('end_start_time'))
excl_a2 = sorted(set(est_a) - set(est_c))
excl_c2 = sorted(set(est_c) - set(est_a))
shared2 = set(est_a) & set(est_c)
print(f"  Exclusivos 168A: {excl_a2[:20]}")
print(f"  Exclusivos 168C: {excl_c2[:20]}")
print(f"  Compartidos: {len(shared2)} start_times")

# === F6: hora del dia ===
print("\n=== F6: Hora real del inicio del viaje 1260 ===")
hours_a = collections.Counter(datetime.datetime.fromtimestamp(t['start_ts']).hour for t in trips_a)
hours_c = collections.Counter(datetime.datetime.fromtimestamp(t['start_ts']).hour for t in trips_c)
for h in sorted(set(list(hours_a)+list(hours_c))):
    tot = hours_a.get(h,0) + hours_c.get(h,0)
    ratio = f"{hours_a.get(h,0)/tot:.0%}" if tot else "?"
    print(f"  {h:02d}h: 168A={hours_a.get(h,0):3d} 168C={hours_c.get(h,0):3d}  168A%={ratio}")

# === F7: duracion del segmento ===
print("\n=== F7: Duracion segmento 1260 ===")
dur_a = [t['duration_secs'] for t in trips_a]
dur_c = [t['duration_secs'] for t in trips_c]
if dur_a: print(f"  168A: n={len(dur_a)} avg={sum(dur_a)//len(dur_a)}s min={min(dur_a)}s max={max(dur_a)}s")
if dur_c: print(f"  168C: n={len(dur_c)} avg={sum(dur_c)//len(dur_c)}s min={min(dur_c)}s max={max(dur_c)}s")

# === F8: gap entre drop y nuevo assignment ===
print("\n=== F8: Gap entre drop de 1260 y asignacion de 1254/1258 ===")
gap_a = [t['gap_secs'] for t in trips_a]
gap_c = [t['gap_secs'] for t in trips_c]
if gap_a: print(f"  168A: n={len(gap_a)} avg={sum(gap_a)//len(gap_a)}s min={min(gap_a)}s max={max(gap_a)}s")
if gap_c: print(f"  168C: n={len(gap_c)} avg={sum(gap_c)//len(gap_c)}s min={min(gap_c)}s max={max(gap_c)}s")

# === F9: posicion al drop ===
print("\n=== F9: Posicion geografica al drop ===")
if trips_a:
    la = [t['drop_lat'] for t in trips_a if t['drop_lat']]
    lo = [t['drop_lon'] for t in trips_a if t['drop_lon']]
    print(f"  168A drop: avg ({sum(la)/len(la):.4f}, {sum(lo)/len(lo):.4f}) range lat [{min(la):.4f},{max(la):.4f}]")
if trips_c:
    la = [t['drop_lat'] for t in trips_c if t['drop_lat']]
    lo = [t['drop_lon'] for t in trips_c if t['drop_lon']]
    print(f"  168C drop: avg ({sum(la)/len(la):.4f}, {sum(lo)/len(lo):.4f}) range lat [{min(la):.4f},{max(la):.4f}]")

# === F10: stops dentro del segmento 1260 ===
print("\n=== F10: stop_ids exclusivos en el segmento 1260 ===")
stops_a = collections.Counter(s for t in trips_a for s in t['stops_in_1260'] if s)
stops_c = collections.Counter(s for t in trips_c for s in t['stops_in_1260'] if s)
only_a = {s for s, c in stops_a.items() if stops_c.get(s,0)==0 and c>=3}
only_c = {s for s, c in stops_c.items() if stops_a.get(s,0)==0 and c>=3}
print(f"  stop_ids EXCLUSIVOS 168A (>=3 obs): {len(only_a)} — {sorted(only_a)[:10]}")
print(f"  stop_ids EXCLUSIVOS 168C (>=3 obs): {len(only_c)} — {sorted(only_c)[:10]}")
both = set(stops_a) & set(stops_c)
print(f"  stops en AMBOS: {len(both)}")
