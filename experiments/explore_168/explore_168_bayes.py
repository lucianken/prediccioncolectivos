"""
Combinación Bayesiana:
  P(ramal=A | vehiculo, viaje_previo) ∝ P(A|vehiculo) × P(A|viaje_previo)

Método leave-one-out: para predecir el viaje i del vehículo,
el prior del vehículo se calcula sobre TODOS sus otros viajes (no el i).
"""
import gzip, json, sys, datetime, collections, glob, os, math
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = 'Z:/grabaciones'
all_files = sorted(glob.glob(os.path.join(DATA_DIR, '*.ndjson.gz')))

veh_history = collections.defaultdict(list)
veh_meta    = {}
state       = {}

def merge(base, upd):
    r = base.copy()
    for k, v in upd.items():
        if k != 'id': r[k] = v
    return r

print("Leyendo...", end='', flush=True)
for fpath in all_files:
    with gzip.open(fpath, 'rt', encoding='utf-8') as f:
        for line in f:
            obj = json.loads(line)
            ts  = obj.get('t', 0)
            for veh in obj.get('new', []):
                vid = veh.get('id','')
                lbl = veh.get('label','')
                if not lbl.endswith('-133'): continue
                entry = {k: veh.get(k,'') for k in ['route_id','lat','lon','license_plate']}
                entry['ts'] = ts
                state[vid]  = entry
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
print(" listo")

DARWIN_RIDS  = {'1780','1260','1774','1256'}
A_RIDS       = {'1773','1781','1254','1255'}
C_RIDS       = {'1775','1783','1258','1259'}
RESOLVE_RIDS = A_RIDS | C_RIDS
MAX_GAP      = 7200

# Construir todos los viajes Darwin resueltos
trips = []
for vid, history in veh_history.items():
    plate = veh_meta[vid]['plate']
    for i, ev in enumerate(history):
        if ev['route_id'] not in DARWIN_RIDS: continue
        for j in range(i+1, min(i+15, len(history))):
            fut = history[j]
            if fut['route_id'] in RESOLVE_RIDS:
                if fut['ts'] - ev['ts'] <= MAX_GAP:
                    dt = datetime.datetime.fromtimestamp(ev['ts'])
                    trips.append({
                        'vid':   vid,
                        'plate': plate,
                        'ts':    ev['ts'],
                        'date':  dt.strftime('%Y-%m-%d'),
                        'ramal': 'A' if fut['route_id'] in A_RIDS else 'C',
                    })
                break
            if fut['route_id'] not in ('',) and fut['route_id'] not in DARWIN_RIDS:
                break

trips.sort(key=lambda x: x['ts'])
total = len(trips)
print(f"Total viajes: {total}")

# ─── Baseline: solo prior global ──────────────────────────────────────────
global_rate_a = sum(1 for t in trips if t['ramal']=='A') / total
print(f"\nBaseline global (siempre predecir mayoritario): "
      f"{max(global_rate_a, 1-global_rate_a):.0%}")

# ─── Signal 1: prior del vehículo (leave-one-out) ─────────────────────────
# Para cada viaje i, prior = (n_A_veh - I(ramal_i==A)) / (n_total_veh - 1)
veh_total = collections.Counter(t['vid'] for t in trips)
veh_a     = collections.Counter(t['vid'] for t in trips if t['ramal']=='A')

def veh_prior_loo(vid, is_a, smoothing=2):
    """P(A | vehiculo) sin contar el viaje actual. Laplace smoothing."""
    n   = veh_total[vid] - 1
    n_a = veh_a[vid] - (1 if is_a else 0)
    return (n_a + smoothing/2) / (n + smoothing)

# Accuracy con solo prior de vehículo
correct_veh = sum(
    1 for t in trips
    if (veh_prior_loo(t['vid'], t['ramal']=='A') >= 0.5) == (t['ramal']=='A')
)
print(f"Prior vehículo solo (LOO):                     {correct_veh/total:.0%}")

# Distribución de priors de vehículo — ¿hay vehículos realmente sesgados?
print(f"\nDistribución de priors por vehículo (sin LOO):")
veh_rates = {}
for vid in veh_total:
    if veh_total[vid] < 10: continue
    rate_a = veh_a[vid] / veh_total[vid]
    veh_rates[vid] = rate_a

bins = [(0,.35,'fuerte C'), (.35,.45,'leve C'), (.45,.55,'neutro'),
        (.55,.65,'leve A'), (.65,1.01,'fuerte A')]
for lo, hi, label in bins:
    n = sum(1 for r in veh_rates.values() if lo <= r < hi)
    print(f"  {label:<12} ({lo:.0%}-{hi:.0%}): {n} vehículos")

# ─── Signal 2: viaje previo del mismo vehículo ese día ────────────────────
# Para cada viaje, buscar el último viaje Darwin resuelto del mismo vehículo ese día
by_veh_day = collections.defaultdict(list)
for t in trips:
    by_veh_day[(t['vid'], t['date'])].append(t)

# P(A | prev=A) y P(A | prev=C) globales
prev_signal = collections.Counter()  # (prev_ramal, cur_ramal)
for day_trips in by_veh_day.values():
    day_trips.sort(key=lambda x: x['ts'])
    for i in range(1, len(day_trips)):
        prev_signal[(day_trips[i-1]['ramal'], day_trips[i]['ramal'])] += 1

pa_given_a = prev_signal[('A','A')] / (prev_signal[('A','A')] + prev_signal[('A','C')])
pa_given_c = prev_signal[('C','A')] / (prev_signal[('C','A')] + prev_signal[('C','C')])
print(f"\nLikelihoods del viaje previo:")
print(f"  P(A | prev=A) = {pa_given_a:.3f}")
print(f"  P(A | prev=C) = {pa_given_c:.3f}")

# ─── Combinación Bayesiana ─────────────────────────────────────────────────
# P(A | veh, prev) ∝ P(A|veh) * P(prev|A) / P(prev)
# Equivalente naive Bayes: log-odds = log-odds_veh + log-odds_prev

def logit(p): return math.log(p / (1 - p)) if 0 < p < 1 else (10 if p >= 1 else -10)
def sigmoid(x): return 1 / (1 + math.exp(-x))

# Construir lookup: para cada viaje, cuál es el viaje previo del día
trip_idx = {(t['vid'], t['ts']): i for i, t in enumerate(trips)}

results = []
for day_trips in by_veh_day.values():
    day_trips.sort(key=lambda x: x['ts'])
    for k, t in enumerate(day_trips):
        is_a    = t['ramal'] == 'A'
        prior_a = veh_prior_loo(t['vid'], is_a)

        if k == 0:
            prev_ramal = None  # primer viaje del día
        else:
            prev_ramal = day_trips[k-1]['ramal']

        # Log-odds combinados
        lo_veh = logit(prior_a)
        if prev_ramal == 'A':
            lo_prev = logit(pa_given_a)
        elif prev_ramal == 'C':
            lo_prev = logit(pa_given_c)
        else:
            lo_prev = 0.0  # sin información

        # Naive Bayes: suma de log-odds (descontando el prior global)
        lo_global = logit(global_rate_a)
        lo_combined = lo_veh + (lo_prev - lo_global)  # evitar doble-contar prior global

        p_a_combined = sigmoid(lo_combined)

        results.append({
            **t,
            'prior_a':     prior_a,
            'prev_ramal':  prev_ramal,
            'p_a_combined': p_a_combined,
            'has_prev':    prev_ramal is not None,
        })

# ─── Métricas ─────────────────────────────────────────────────────────────
def accuracy_at_threshold(rlist, key, thr=0.5):
    correct = sum(1 for r in rlist if (r[key] >= thr) == (r['ramal'] == 'A'))
    return correct / len(rlist)

def accuracy_high_conf(rlist, key, conf=0.65):
    subset = [r for r in rlist if r[key] >= conf or r[key] <= 1-conf]
    if not subset: return 0, 0
    correct = sum(1 for r in subset if (r[key] >= 0.5) == (r['ramal'] == 'A'))
    return correct/len(subset), len(subset)

print(f"\n{'─'*60}")
print(f"Comparativa de predictores:")
print(f"{'─'*60}")
print(f"  {'modelo':<35} {'acc@50%':>8} {'acc@65%':>8} {'cob@65%':>8}")

# 1. Baseline
base_acc = max(global_rate_a, 1-global_rate_a)
print(f"  {'Baseline global':<35} {base_acc:>7.0%}")

# 2. Solo prior vehículo
acc_veh = accuracy_at_threshold(results, 'prior_a')
acc65_veh, cov65_veh = accuracy_high_conf(results, 'prior_a')
print(f"  {'Prior vehículo (LOO)':<35} {acc_veh:>7.0%}  {acc65_veh:>7.0%}  {cov65_veh/total:>7.0%}")

# 3. Solo viaje previo (solo cuando hay)
with_prev = [r for r in results if r['has_prev']]
# P(A|prev) como predictor
def p_a_from_prev(r):
    return pa_given_a if r['prev_ramal']=='A' else pa_given_c
if with_prev:
    acc_prev = sum(1 for r in with_prev if (p_a_from_prev(r) >= 0.5) == (r['ramal']=='A')) / len(with_prev)
    print(f"  {'Viaje previo (cuando hay)':<35} {acc_prev:>7.0%}  {'—':>7}  {len(with_prev)/total:>7.0%}")

# 4. Combinación Bayesiana
acc_comb = accuracy_at_threshold(results, 'p_a_combined')
acc65_comb, cov65_comb = accuracy_high_conf(results, 'p_a_combined')
print(f"  {'Bayes (veh + prev)':<35} {acc_comb:>7.0%}  {acc65_comb:>7.0%}  {cov65_comb/total:>7.0%}")

# 5. Combinación solo cuando hay viaje previo
with_prev_r = [r for r in results if r['has_prev']]
if with_prev_r:
    acc_comb_prev = accuracy_at_threshold(with_prev_r, 'p_a_combined')
    acc65_cp, cov65_cp = accuracy_high_conf(with_prev_r, 'p_a_combined')
    print(f"  {'Bayes (veh+prev), solo con prev':<35} {acc_comb_prev:>7.0%}  {acc65_cp:>7.0%}  {cov65_cp/len(with_prev_r):>7.0%}")

# ─── Curva de confianza ────────────────────────────────────────────────────
print(f"\nCurva de precisión por confianza (modelo combinado):")
print(f"  {'umbral_conf':>12} {'cobertura':>10} {'accuracy':>10}")
for conf in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]:
    subset = [r for r in results if r['p_a_combined'] >= conf or r['p_a_combined'] <= 1-conf]
    if not subset: continue
    correct = sum(1 for r in subset if (r['p_a_combined'] >= 0.5) == (r['ramal'] == 'A'))
    print(f"  {conf:>12.0%} {len(subset)/total:>10.0%} {correct/len(subset):>10.0%}")

# ─── Dónde gana el modelo combinado ───────────────────────────────────────
print(f"\nAnálisis: ¿cuándo aporta el viaje previo vs solo el prior?")
# Casos donde el prior vehículo es fuerte (>65%) — el previo no debería ayudar mucho
strong_prior = [r for r in results if r['prior_a'] >= 0.65 or r['prior_a'] <= 0.35]
neutral_prior = [r for r in results if 0.40 <= r['prior_a'] <= 0.60]

if strong_prior:
    a1 = accuracy_at_threshold(strong_prior, 'prior_a')
    a2 = accuracy_at_threshold(strong_prior, 'p_a_combined')
    print(f"  Prior fuerte (>65% o <35%): n={len(strong_prior)}  solo_prior={a1:.0%}  combinado={a2:.0%}")
if neutral_prior:
    a1 = accuracy_at_threshold(neutral_prior, 'prior_a')
    a2 = accuracy_at_threshold(neutral_prior, 'p_a_combined')
    print(f"  Prior neutro (40-60%):      n={len(neutral_prior)}  solo_prior={a1:.0%}  combinado={a2:.0%}")

# ─── Distribución de p_a_combined ─────────────────────────────────────────
print(f"\nDistribución de p_a_combined (¿el modelo es confiado?):")
buckets = collections.Counter(int(r['p_a_combined']*10)/10 for r in results)
for b in sorted(buckets):
    subset = [r for r in results if int(r['p_a_combined']*10)/10 == b]
    correct = sum(1 for r in subset if (r['p_a_combined'] >= 0.5) == (r['ramal']=='A'))
    bar = '█' * (buckets[b]//20)
    print(f"  p={b:.1f}: {buckets[b]:>5} viajes  acc={correct/len(subset):.0%}  {bar}")
