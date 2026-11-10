"""
Features #7, #10, #6

#7: patente × dia de semana
#10: patron numerico en trip_id (par/impar, mod N, rango)
#6: posicion GPS durante segmento 1261 (darsena de terminal)
"""
import gzip, json, sys, datetime, collections, math
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
                entry = {k: veh.get(k,'') for k in
                         ['route_id','lat','lon','start_time','license_plate','start_date','direction_id','trip_id']}
                entry['ts']    = ts
                entry['odo']   = veh.get('odo', 0)
                entry['speed'] = veh.get('speed', 0)
                state[vid] = entry
                veh_meta[vid] = {'label': lbl, 'plate': entry['license_plate'].strip()}
                h = veh_history[vid]
                if not h or h[-1]['route_id'] != entry['route_id']:
                    veh_history[vid].append(entry.copy())
            for upd in obj.get('upd', []):
                vid = upd.get('id','')
                if vid not in state: continue
                if not veh_meta.get(vid,{}).get('label','').endswith('-133'): continue
                ns = merge(state[vid], upd)
                ns['ts'] = ts
                prev = state[vid]['route_id']
                state[vid] = ns
                if prev != ns.get('route_id', prev):
                    veh_history[vid].append(ns.copy())
            for did in obj.get('del', []):
                state.pop(did, None)

MAX_GAP  = 7200
OUTBOUND = {'1254', '1258'}

# Construir viajes 1260 con contexto + segmento 1261 previo
trips = []
for vid, history in veh_history.items():
    plate = veh_meta[vid]['plate']
    for i, ev in enumerate(history):
        if ev['route_id'] != '1260': continue

        # destino
        end_rid = end_ev = None
        for j in range(i+1, min(i+15, len(history))):
            fut = history[j]
            if fut['route_id'] not in ('','1260','1261'):
                if fut['ts'] - ev['ts'] <= MAX_GAP:
                    end_rid, end_ev = fut['route_id'], fut
                break
        if end_rid not in OUTBOUND: continue

        tid = ev.get('trip_id','')

        # Buscar segmento 1261 inmediatamente previo (hasta 3 eventos atras)
        seg_1261 = []
        for k in range(i-1, max(i-5, -1), -1):
            if history[k]['route_id'] == '1261':
                seg_1261.append(history[k])
            elif history[k]['route_id'] == '':
                continue
            else:
                break
        # posicion promedio durante 1261
        lats_1261 = [e['lat'] for e in seg_1261 if e.get('lat')]
        lons_1261 = [e['lon'] for e in seg_1261 if e.get('lon')]
        lat_1261 = sum(lats_1261)/len(lats_1261) if lats_1261 else None
        lon_1261 = sum(lons_1261)/len(lons_1261) if lons_1261 else None

        dt = datetime.datetime.fromtimestamp(ev['ts'])
        trips.append({
            'vid': vid, 'plate': plate,
            'ts': ev['ts'],
            'date': dt.strftime('%Y-%m-%d'),
            'weekday': dt.weekday(),      # 0=lun, 6=dom
            'weekday_name': dt.strftime('%A'),
            'end_rid': end_rid,
            'trip_id': tid,
            'lat_1261': lat_1261,
            'lon_1261': lon_1261,
            'has_1261': len(seg_1261) > 0,
        })

total = len(trips)
n_a = sum(1 for t in trips if t['end_rid']=='1254')
n_c = sum(1 for t in trips if t['end_rid']=='1258')
print(f"Total: {total}  168A={n_a} ({n_a/total:.0%})  168C={n_c} ({n_c/total:.0%})")

# ================================================================
# FEATURE #7: patente × dia de semana
# ================================================================
print("\n" + "="*60)
print("FEATURE #7: patente × dia de semana")
print("="*60)

# Para cada (plate, weekday), ¿es consistente el ramal?
pdw = collections.defaultdict(collections.Counter)
for t in trips:
    pdw[(t['plate'], t['weekday'])][t['end_rid']] += 1

pure_a = [(k,v) for k,v in pdw.items() if set(v)=={'1254'} and sum(v.values())>=3]
pure_c = [(k,v) for k,v in pdw.items() if set(v)=={'1258'} and sum(v.values())>=3]
mixed  = [(k,v) for k,v in pdw.items() if len(v)>1 and sum(v.values())>=3]

print(f"\n  Combos (plate, dia) puros 168A (>=3 obs): {len(pure_a)}")
for (pl,wd), v in sorted(pure_a)[:8]:
    print(f"    {pl} {['Lun','Mar','Mie','Jue','Vie','Sab','Dom'][wd]}: {dict(v)}")
print(f"  Combos (plate, dia) puros 168C (>=3 obs): {len(pure_c)}")
for (pl,wd), v in sorted(pure_c)[:8]:
    print(f"    {pl} {['Lun','Mar','Mie','Jue','Vie','Sab','Dom'][wd]}: {dict(v)}")
print(f"  Combos mixtos (>=3 obs): {len(mixed)}")
for (pl,wd), v in sorted(mixed)[:8]:
    print(f"    {pl} {['Lun','Mar','Mie','Jue','Vie','Sab','Dom'][wd]}: {dict(v)}")

# Precision global si usamos (plate, weekday) como predictor
# Para cada combo puro, cuenta cuantos aciertos vs total
total_pdw = sum(sum(v.values()) for v in pdw.values())
correct_pdw = sum(max(v.values()) for v in pdw.values())  # siempre predice el mayoritario
print(f"\n  Precision si predicimos mayoritario por (plate, dia): {correct_pdw}/{total_pdw} = {correct_pdw/total_pdw:.0%}")

# Solo mirar los dias que tienen >=3 obs por combo
with_enough = [(k,v) for k,v in pdw.items() if sum(v.values())>=3]
te = sum(sum(v.values()) for _,v in with_enough)
ce = sum(max(v.values()) for _,v in with_enough)
print(f"  Idem solo combos con >=3 obs: {ce}/{te} = {ce/te:.0%}  (cubre {te}/{total} viajes)")

# ================================================================
# FEATURE #10: patron numerico en trip_id
# ================================================================
print("\n" + "="*60)
print("FEATURE #10: patron numerico en trip_id")
print("="*60)

def parse_tid(t):
    tid = t.get('trip_id','')
    if not tid: return None
    try: return int(tid.split('-')[0])
    except: return None

with_tid = [(t, parse_tid(t)) for t in trips if parse_tid(t) is not None]
print(f"\n  Viajes con trip_id numerico: {len(with_tid)}/{total}")

if with_tid:
    nums_a = [n for t,n in with_tid if t['end_rid']=='1254']
    nums_c = [n for t,n in with_tid if t['end_rid']=='1258']

    # Par / impar
    pa_even = sum(1 for n in nums_a if n%2==0); pa_odd  = len(nums_a) - pa_even
    pc_even = sum(1 for n in nums_c if n%2==0); pc_odd  = len(nums_c) - pc_even
    print(f"\n  Paridad trip_id:")
    print(f"    168A: par={pa_even} ({pa_even/len(nums_a):.0%})  impar={pa_odd}")
    print(f"    168C: par={pc_even} ({pc_even/len(nums_c):.0%})  impar={pc_odd}")

    # mod 3
    print(f"\n  trip_id mod 3:")
    for m in range(3):
        na = sum(1 for n in nums_a if n%3==m)
        nc = sum(1 for n in nums_c if n%3==m)
        tot = na+nc
        print(f"    mod3={m}: A={na} C={nc}  P(A)={na/tot:.0%}" if tot else f"    mod3={m}: n=0")

    # mod 4
    print(f"\n  trip_id mod 4:")
    for m in range(4):
        na = sum(1 for n in nums_a if n%4==m)
        nc = sum(1 for n in nums_c if n%4==m)
        tot = na+nc
        print(f"    mod4={m}: A={na} C={nc}  P(A)={na/tot:.0%}" if tot else f"    mod4={m}: n=0")

    # Rango: ¿los A tienen trip_ids mas altos o mas bajos?
    print(f"\n  Rango:")
    print(f"    168A: min={min(nums_a)} max={max(nums_a)} avg={sum(nums_a)//len(nums_a)}")
    print(f"    168C: min={min(nums_c)} max={max(nums_c)} avg={sum(nums_c)//len(nums_c)}")

    # Distribucion en buckets de 10
    step = 10
    mn = min(nums_a+nums_c); mx = max(nums_a+nums_c)
    print(f"\n  Distribucion por bloques de {step}:")
    print(f"  {'rango':<16} {'168A':>6} {'168C':>6}  {'P(A)':>6}")
    for b in range(mn, mx+step, step):
        na = sum(1 for n in nums_a if b <= n < b+step)
        nc = sum(1 for n in nums_c if b <= n < b+step)
        if na+nc == 0: continue
        print(f"  {b}-{b+step-1:<10} {na:>6} {nc:>6}  {na/(na+nc):>5.0%}")

# ================================================================
# FEATURE #6: posicion GPS durante segmento 1261
# ================================================================
print("\n" + "="*60)
print("FEATURE #6: posicion GPS durante segmento 1261 (terminal)")
print("="*60)

with_pos = [t for t in trips if t['lat_1261'] is not None]
print(f"\n  Viajes con posicion en 1261: {len(with_pos)}/{total}")

if with_pos:
    lats_a = [t['lat_1261'] for t in with_pos if t['end_rid']=='1254']
    lons_a = [t['lon_1261'] for t in with_pos if t['end_rid']=='1254']
    lats_c = [t['lat_1261'] for t in with_pos if t['end_rid']=='1258']
    lons_c = [t['lon_1261'] for t in with_pos if t['end_rid']=='1258']

    def s(v): return f"avg={sum(v)/len(v):.6f} min={min(v):.6f} max={max(v):.6f} spread={max(v)-min(v):.6f}"
    print(f"\n  168A lat: {s(lats_a)}")
    print(f"  168C lat: {s(lats_c)}")
    print(f"  168A lon: {s(lons_a)}")
    print(f"  168C lon: {s(lons_c)}")

    # diferencia de medias
    avg_lat_a = sum(lats_a)/len(lats_a); avg_lat_c = sum(lats_c)/len(lats_c)
    avg_lon_a = sum(lons_a)/len(lons_a); avg_lon_c = sum(lons_c)/len(lons_c)
    dlat = avg_lat_a - avg_lat_c
    dlon = avg_lon_a - avg_lon_c
    dist_m = math.sqrt((dlat*111000)**2 + (dlon*111000*math.cos(math.radians(-34.63)))**2)
    print(f"\n  Diferencia de medias A vs C: dlat={dlat:.6f} dlon={dlon:.6f}  (~{dist_m:.1f}m)")

    # Buscar threshold en lat o lon que separe
    print(f"\n  Busqueda de threshold en lat:")
    all_lats = sorted(set(lats_a + lats_c))
    best_acc_lat, best_thr_lat = 0, 0
    for thr in all_lats[::max(1,len(all_lats)//80)]:
        # lat >= thr -> predecir A (mas al norte)
        corr = sum(1 for l in lats_a if l >= thr) + sum(1 for l in lats_c if l < thr)
        acc = corr / len(with_pos)
        if acc > best_acc_lat:
            best_acc_lat, best_thr_lat = acc, thr
    print(f"    Mejor threshold lat: >= {best_thr_lat:.5f} -> 168A  acc={best_acc_lat:.0%}")

    print(f"  Busqueda de threshold en lon:")
    all_lons = sorted(set(lons_a + lons_c))
    best_acc_lon, best_thr_lon = 0, 0
    for thr in all_lons[::max(1,len(all_lons)//80)]:
        corr = sum(1 for l in lons_a if l >= thr) + sum(1 for l in lons_c if l < thr)
        acc = corr / len(with_pos)
        if acc > best_acc_lon:
            best_acc_lon, best_thr_lon = acc, thr
    print(f"    Mejor threshold lon: >= {best_thr_lon:.5f} -> 168A  acc={best_acc_lon:.0%}")

    # distribucion lat en buckets finos (terminal es area pequena)
    print(f"\n  Distribucion lat (buckets 0.0002 grados ~ 22m):")
    step = 0.0002
    all_l = lats_a + lats_c
    mn_l = min(all_l); mx_l = max(all_l)
    print(f"  {'lat_bucket':<14} {'168A':>6} {'168C':>6}  {'P(A)':>6}")
    b = mn_l
    while b <= mx_l:
        na = sum(1 for l in lats_a if b <= l < b+step)
        nc = sum(1 for l in lats_c if b <= l < b+step)
        if na+nc >= 2:
            print(f"  {b:.4f}       {na:>6} {nc:>6}  {na/(na+nc):>5.0%}")
        b += step

    print(f"\n  Distribucion lon (buckets 0.0002 grados ~ 16m):")
    step = 0.0002
    all_lo = lons_a + lons_c
    mn_lo = min(all_lo); mx_lo = max(all_lo)
    b = mn_lo
    while b <= mx_lo:
        na = sum(1 for l in lons_a if b <= l < b+step)
        nc = sum(1 for l in lons_c if b <= l < b+step)
        if na+nc >= 2:
            print(f"  {b:.4f}       {na:>6} {nc:>6}  {na/(na+nc):>5.0%}")
        b += step
