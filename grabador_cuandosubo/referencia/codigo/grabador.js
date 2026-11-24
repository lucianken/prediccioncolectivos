import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { baDate } from './identity.js';

/**
 * Grabador continuo — continuación del grabador del NUC (prediccion colectivos/grabador), que
 * leía la API CABA (muerta desde 2026-10-15). Mismo formato y misma carpeta, así el pipeline de ML,
 * stats.py y los scripts de análisis siguen funcionando:
 *
 *   {dir}/YYYY-MM-DD.ndjson.gz   (fecha Buenos Aires; miembros gzip concatenados, como gzip.open 'at')
 *   keyframe: {"t", "keyframe": true, "src": "oba", "new": [vehículo completo...], "del": [], "upd": []}
 *   delta:    {"t", "new": [...], "del": [ids], "upd": [{id, ts, ...solo campos que cambiaron}]}
 *   gap:      {"t", "gap": true, "gap_seconds", "reason": "restart"}   (antes del keyframe de reinicio)
 *
 * Vehículo (campos del formato original; los que OBA no tiene van null):
 *   id, label, license_plate, route_id, trip_id, direction_id, start_date, start_time,
 *   lat, lon, speed, odo, stop_id, seq, status, ts
 * + campos nuevos (OBA): agency, label_src ('oba'|'registry'|'learned'|null), ts_src ('oba' = lastUpdateTime de OBA, hora
 *   del último reporte real; 'obs' = sin lastUpdateTime, hora de la respuesta), sched_dev, dist_along, next_stop, predicted
 *
 * id / route_id / trip_id sin prefijo de agencia = mismos valores que usaba la API CABA.
 *
 * Presupuesto del WAF (limitador compartido con los usuarios, que tienen prioridad 0):
 *   tier A (líneas de RECORD_LINES): todas sus agencias en cada ciclo (prioridad 1)
 *   tier B (resto de agencias AMBA): rotación continua en los huecos libres (prioridad 3)
 */

// Bounding box CABA + GBA (igual que el grabador original)
const LAT_MIN = -35.1, LAT_MAX = -34.3, LON_MIN = -59.1, LON_MAX = -57.9;

// Campos que pueden aparecer en un delta de actualización (además de id y ts) — delta.py + campos OBA
const DYNAMIC = ['lat', 'lon', 'speed', 'odo', 'stop_id', 'seq', 'status', 'trip_id', 'route_id', 'direction_id', 'start_time',
  'label', 'label_src', 'ts_src', 'sched_dev', 'dist_along', 'next_stop', 'predicted'];

/** Port de delta.py:compute_delta. Devuelve [frame, nuevoEstado]. */
export function computeDelta(prev, vehicles) {
  const curr = new Map(vehicles.map((v) => [v.id, v]));
  const t = vehicles.reduce((m, v) => Math.max(m, v.ts), 0);
  const added = [], upd = [], del = [];
  for (const [id, v] of curr) {
    const p = prev[id];
    if (!p) { added.push(v); continue; }
    const changed = {};
    for (const k of DYNAMIC) if (v[k] !== p[k]) changed[k] = v[k] ?? null;
    if (Object.keys(changed).length) upd.push({ id, ts: v.ts, ...changed });
  }
  for (const id of Object.keys(prev)) if (!curr.has(id)) del.push(id);
  return [{ t, new: added, del, upd }, Object.fromEntries(curr)];
}

/** Port de delta.py:make_keyframe. */
export function makeKeyframe(vehicles) {
  return { t: vehicles.reduce((m, v) => Math.max(m, v.ts), 0), keyframe: true, src: 'oba', new: vehicles, del: [], upd: [] };
}

const stripAgency = (x) => (x ? x.slice(x.indexOf('_') + 1) : null);
const round6 = (x) => Math.round(x * 1e6) / 1e6;

export class Grabador {
  constructor({ client, identity, plates = {}, config, dir, cycleMs = 30000, keyframeEvery = 100, gapThresholdS = 600, now = () => Date.now() }) {
    this.client = client;
    this.identity = identity;
    this.plates = plates;
    this.config = config;
    this.dir = dir;
    this.cycleMs = cycleMs;
    this.keyframeEvery = keyframeEvery;
    this.gapThresholdS = gapThresholdS;
    this.now = now;
    this.stateFile = path.join(dir, 'bondiradar_state.json'); // nombre propio: no pisar el state.json del grabador viejo
    this.healthFile = path.join(dir, 'bondiradar_health');
    this.cycle = 0;
    this.running = false;
    this.stats = { cycles: 0, frames: 0, keyframes: 0, lastVehicles: 0, lastError: null, sweepRequests: 0 };
    const st = this.#loadState();
    this.prev = st.vehicles;
    this.savedAt = st.ts;
    this.forceKeyframe = true;
  }

  /** Agencias de las líneas a grabar en cada ciclo (tier A) y el resto de AMBA (tier B). */
  agencies() {
    const date = baDate(this.now());
    const all = new Set();
    for (const e of Object.values(this.identity.lines)) {
      for (const a of e.agencies || []) if (a.from <= date && (a.to == null || a.to >= date)) all.add(a.agencyId);
    }
    const tierA = new Set((this.config.recordLines || []).flatMap((l) => this.identity.agenciesFor(l, date).map((a) => a.id)));
    return { tierA: [...tierA].sort(), tierB: [...all].filter((a) => !tierA.has(a)).sort((x, y) => Number(x) - Number(y)) };
  }

  start() {
    if (this.running) return;
    this.running = true;
    fs.mkdirSync(this.dir, { recursive: true });
    const loop = async () => {
      while (this.running) {
        const t0 = this.now();
        try { await this.runCycle(); } catch (e) { this.stats.lastError = e.message; console.error(`grabador: ${e.message}`); }
        const wait = this.cycleMs - (this.now() - t0);
        if (wait > 0 && this.running) await new Promise((r) => { this.sleepTimer = setTimeout(r, wait); });
      }
    };
    this.loopPromise = loop();
    if (this.config.recordSweep) this.sweepPromise = this.#sweep();
  }

  async stop() {
    this.running = false;
    clearTimeout(this.sleepTimer);
    await this.loopPromise;
  }

  /** Tier B: recorre las demás agencias de a una, en prioridad baja (solo usa huecos libres del limitador). */
  async #sweep() {
    let i = 0;
    while (this.running) {
      const { tierB } = this.agencies();
      if (!tierB.length) { await new Promise((r) => setTimeout(r, this.cycleMs)); continue; }
      const a = tierB[i++ % tierB.length];
      try {
        await this.client.get(`vehicles-for-agency/${a}`, { ttlMs: this.cycleMs, priority: 3 });
        this.stats.sweepRequests++;
      } catch { /* agencia caída o WAF: el limitador ya pausa */ }
    }
  }

  /** Un ciclo: refresca tier A, arma el snapshot con lo último de cada agencia y escribe keyframe o delta. */
  async runCycle() {
    const { tierA, tierB } = this.agencies();
    await Promise.all(tierA.map((a) => this.client.get(`vehicles-for-agency/${a}`, { ttlMs: this.cycleMs - 5000, priority: 1 }).catch(() => null)));
    const vehicles = this.snapshot([...tierA, ...tierB]);

    const nowS = Math.floor(this.now() / 1000);
    const gap = this.savedAt ? nowS - this.savedAt : Infinity;
    const isKeyframe = this.forceKeyframe || this.cycle % this.keyframeEvery === 0 || gap > this.gapThresholdS;
    let frame;
    if (isKeyframe) {
      if (this.savedAt && gap > this.gapThresholdS) this.#append({ t: nowS, gap: true, gap_seconds: gap, reason: 'restart' });
      frame = makeKeyframe(vehicles);
      this.prev = Object.fromEntries(vehicles.map((v) => [v.id, v]));
      this.forceKeyframe = false;
      this.stats.keyframes++;
    } else {
      [frame, this.prev] = computeDelta(this.prev, vehicles);
    }
    if (vehicles.length || isKeyframe) { this.#append(frame); this.stats.frames++; }
    this.savedAt = nowS;
    this.#saveState();
    this.cycle++;
    this.stats.cycles++;
    this.stats.lastVehicles = vehicles.length;
    this.stats.lastCycleAt = new Date(this.now()).toISOString();
    return frame;
  }

  /** Todos los vehículos con posición de las agencias dadas (andando o en el depósito), desde la cache del cliente OBA. */
  snapshot(agencies) {
    const byId = new Map();
    for (const a of agencies) {
      const entry = this.client.cache.get(`vehicles-for-agency/${a}`);
      if (!entry) continue;
      const { currentTime, data } = entry.body;
      const trips = new Map((data.references?.trips || []).map((t) => [t.id, t]));
      for (const v of data.list || []) {
        const loc = v.location;
        if (!loc) continue;
        if (!(loc.lat >= LAT_MIN && loc.lat <= LAT_MAX && loc.lon >= LON_MIN && loc.lon <= LON_MAX)) continue;
        const id = stripAgency(v.vehicleId);
        const lat = round6(loc.lat), lon = round6(loc.lon);
        // lastUpdateTime = hora del último reporte real (con o sin trip)
        const ts = Math.floor((v.lastUpdateTime || currentTime) / 1000);
        const tsSrc = v.lastUpdateTime ? 'oba' : 'obs';
        if (byId.has(id) && byId.get(id).ts >= ts) continue; // id fantasma en otra agencia: gana el más reciente
        const st = v.tripStatus || null;
        const trip = v.tripId ? trips.get(v.tripId) : null;
        const { label, source } = this.identity.resolve(id, st?.vehicleLabel);
        byId.set(id, {
          id,
          label: label || '',
          license_plate: this.plates[id] || '',
          route_id: stripAgency(trip?.routeId) || '',
          trip_id: stripAgency(v.tripId) || '',
          direction_id: trip?.directionId != null ? Number(trip.directionId) : 0,
          start_date: st?.serviceDate ? baDate(st.serviceDate + 12 * 3600 * 1000).replaceAll('-', '') : '',
          start_time: '',
          lat,
          lon,
          speed: null,
          odo: null,
          stop_id: '',
          seq: 0,
          status: null,
          ts,
          agency: v.vehicleId.slice(0, v.vehicleId.indexOf('_')),
          label_src: source,
          ts_src: tsSrc,
          sched_dev: st?.scheduleDeviation ?? null,
          dist_along: st?.distanceAlongTrip != null ? Math.round(st.distanceAlongTrip) : null,
          next_stop: stripAgency(st?.nextStop) || null,
          predicted: st ? !!st.predicted : null,
        });
      }
    }
    return [...byId.values()].sort((x, y) => x.id.localeCompare(y.id, 'en', { numeric: true }));
  }

  #append(frame) {
    const date = baDate((frame.t || Math.floor(this.now() / 1000)) * 1000);
    fs.appendFileSync(path.join(this.dir, `${date}.ndjson.gz`), zlib.gzipSync(JSON.stringify(frame) + '\n'));
  }

  #loadState() {
    try {
      const j = JSON.parse(fs.readFileSync(this.stateFile, 'utf8'));
      return { vehicles: j.vehicles || {}, ts: j.ts || 0 };
    } catch { return { vehicles: {}, ts: 0 }; }
  }

  #saveState() {
    try {
      const tmp = `${this.stateFile}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify({ ts: this.savedAt, vehicles: this.prev }));
      fs.renameSync(tmp, this.stateFile);
      const t = new Date();
      try { fs.utimesSync(this.healthFile, t, t); } catch { fs.writeFileSync(this.healthFile, ''); }
    } catch (e) {
      this.stats.lastError = `state: ${e.message}`;
    }
  }
}
