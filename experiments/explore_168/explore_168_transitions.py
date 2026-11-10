import gzip, json, sys, datetime, collections
sys.stdout.reconfigure(encoding='utf-8')

state = {}
transitions = []

files = [
    'Z:/grabaciones/2026-05-30.ndjson.gz',
    'Z:/grabaciones/2026-05-31.ndjson.gz',
    'Z:/grabaciones/2026-06-01.ndjson.gz',
]

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
                prev = state.get(vid, {})
                prev_rid = prev.get('route_id','')
                new_rid = veh.get('route_id','')
                if prev_rid != new_rid:
                    transitions.append({'ts':ts,'vid':vid,'lbl':lbl,'from':prev_rid,'to':new_rid,
                        'lat':veh.get('lat',0),'lon':veh.get('lon',0),'st':veh.get('start_time','')})
                state[vid] = {'route_id':new_rid,'label':lbl,'lat':veh.get('lat',0),'lon':veh.get('lon',0),'ts':ts,'st':veh.get('start_time','')}
            for upd in obj.get('upd', []):
                vid = upd.get('id','')
                if vid not in state:
                    continue
                if not state[vid].get('label','').endswith('-133'):
                    continue
                if 'route_id' in upd:
                    prev_rid = state[vid]['route_id']
                    new_rid = upd['route_id']
                    if prev_rid != new_rid:
                        lat = upd.get('lat', state[vid].get('lat',0))
                        lon = upd.get('lon', state[vid].get('lon',0))
                        transitions.append({'ts':ts,'vid':vid,'lbl':state[vid]['label'],'from':prev_rid,'to':new_rid,
                            'lat':lat,'lon':lon,'st':upd.get('start_time',state[vid].get('st',''))})
                    state[vid]['route_id'] = new_rid
                for k in ['lat','lon']:
                    if k in upd:
                        state[vid][k] = upd[k]
                if 'start_time' in upd:
                    state[vid]['st'] = upd['start_time']
            for did in obj.get('del', []):
                state.pop(did, None)

# Show all unique transition pairs and counts
print("=== Transition pair counts (suffix 133) ===")
pair_counts = collections.Counter()
for tr in transitions:
    pair_counts[(tr['from'], tr['to'])] += 1
for (fr, to), cnt in sorted(pair_counts.items(), key=lambda x: -x[1]):
    print(f"  '{fr}' -> '{to}': {cnt}")

# Focus: transitions involving 1260/1261
target = {'1260','1261'}
print("\n=== Transitions involving 1260/1261 ===")
for tr in transitions:
    if tr['from'] in target or tr['to'] in target:
        t = datetime.datetime.fromtimestamp(tr['ts']).strftime('%m-%d %H:%M')
        print(f"  {t} {tr['lbl']} {tr['vid']} '{tr['from']}' -> '{tr['to']}' ({tr['lat']:.4f},{tr['lon']:.4f}) st={tr['st']}")

# Check for triple transitions: vehicles that go X->''->Y (the Darwin gap)
print("\n=== Triple transitions: rid -> '' -> different_rid (per vehicle) ===")
# Group by vehicle
from itertools import groupby
veh_trans = collections.defaultdict(list)
for tr in transitions:
    veh_trans[tr['vid']].append(tr)

triple_patterns = collections.Counter()
for vid, vtrans in veh_trans.items():
    for i in range(len(vtrans)-1):
        a, b = vtrans[i], vtrans[i+1]
        if a['to'] == '' and b['from'] == '' and a['from'] != '' and b['to'] != '':
            triple_patterns[(a['from'], b['to'])] += 1

for (fr, to), cnt in sorted(triple_patterns.items(), key=lambda x: -x[1]):
    print(f"  '{fr}' -> '' -> '{to}': {cnt} times")

# Detailed: vehicles that had 1260 at any point
print("\n=== Vehicle histories that touched 1260 ===")
vids_1260 = {tr['vid'] for tr in transitions if tr['from']=='1260' or tr['to']=='1260'}
for vid in sorted(vids_1260)[:5]:
    vtrans = veh_trans[vid]
    print(f"\n  Vehicle {vid}:")
    for tr in vtrans:
        if tr['from'] in {'1254','1255','1258','1259','1260','1261',''} or tr['to'] in {'1254','1255','1258','1259','1260','1261',''}:
            t = datetime.datetime.fromtimestamp(tr['ts']).strftime('%m-%d %H:%M')
            print(f"    {t} '{tr['from']}' -> '{tr['to']}' ({tr['lat']:.4f},{tr['lon']:.4f}) st={tr['st']}")
