import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { execFileSync } from 'node:child_process';
import { startStack, FIXTURE_DATA } from '../support/harness.js';
import { loadFixture } from '../support/mock-oba.js';
import { Grabador, computeDelta, makeKeyframe } from '../../src/grabador.js';

const registry = JSON.parse(fs.readFileSync(path.join(FIXTURE_DATA, 'registry.json'), 'utf8')).vehicles;
const LEGACY_FIELDS = ['id', 'label', 'license_plate', 'route_id', 'trip_id', 'direction_id', 'start_date', 'start_time',
  'lat', 'lon', 'speed', 'odo', 'stop_id', 'seq', 'status', 'ts'];

function readFrames(dir) {
  const out = [];
  for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.ndjson.gz')).sort()) {
    const text = zlib.gunzipSync(fs.readFileSync(path.join(dir, f))).toString(); // multi-member gzip
    for (const line of text.split('\n').filter(Boolean)) out.push({ file: f, ...JSON.parse(line) });
  }
  return out;
}

function makeGrabador(stack, dir, extra = {}) {
  return new Grabador({
    client: stack.app.client,
    identity: stack.app.identity,
    plates: { 93193: 'AH846RP' },
    config: { ...stack.config, recordLines: ['151', '39'], maxVehicleAgeS: 300 },
    dir,
    cycleMs: 30000,
    ...extra,
  });
}

describe('delta (port de delta.py)', () => {
  test('new / del / upd solo con campos cambiados', () => {
    const a = { id: '1', ts: 10, lat: 1, lon: 1, label: 'x-1' };
    const b = { id: '2', ts: 10, lat: 2, lon: 2, label: 'x-2' };
    const [f1, s1] = computeDelta({}, [a, b]);
    assert.deepEqual(f1.new.map((v) => v.id), ['1', '2']);
    const [f2] = computeDelta(s1, [{ ...a, ts: 40, lat: 1.5 }, { id: '3', ts: 40, lat: 3, lon: 3 }]);
    assert.equal(f2.t, 40);
    assert.deepEqual(f2.upd, [{ id: '1', ts: 40, lat: 1.5 }]);
    assert.deepEqual(f2.del, ['2']);
    assert.deepEqual(f2.new.map((v) => v.id), ['3']);
    const kf = makeKeyframe([a, b]);
    assert.equal(kf.keyframe, true);
    assert.equal(kf.t, 10);
  });
});

describe('grabador continuo (formato del grabador del NUC)', () => {
  let s, dir;
  before(async () => { s = await startStack(); dir = fs.mkdtempSync(path.join(os.tmpdir(), 'grab-')); });
  after(async () => { await s.close(); fs.rmSync(dir, { recursive: true, force: true }); });

  test('tier A = agencias de las líneas configuradas; tier B = resto de AMBA', () => {
    const g = makeGrabador(s, dir);
    const { tierA, tierB } = g.agencies();
    assert.deepEqual(tierA, ['56', '708']);
    assert.ok(tierB.length > 100);
    assert.ok(!tierB.includes('708'));
  });

  test('keyframe inicial completo, luego delta; campos del formato original', async () => {
    const g = makeGrabador(s, dir);
    const kf = await g.runCycle();
    assert.equal(kf.keyframe, true);
    assert.equal(kf.src, 'oba');
    assert.ok(kf.new.length > 50);
    for (const v of kf.new) {
      for (const k of LEGACY_FIELDS) assert.ok(k in v, `falta ${k}`);
      assert.doesNotMatch(v.id, /_/, 'id sin prefijo de agencia (igual que la API CABA)');
      assert.ok(v.lat <= -34.3 && v.lat >= -35.1);
    }
    // toda la flota con posición (andando o en el depósito: no se descarta nada)
    const body708 = loadFixture('vehicles-for-agency/708');
    const all708 = body708.data.list.filter((v) => v.location && v.location.lat <= -34.3 && v.location.lat >= -35.1);
    assert.equal(kf.new.filter((v) => v.agency === '708').length, all708.length);
    // ts: hora GPS de OBA solo con trip fresco; sin trip, hora de observación
    for (const v of kf.new) {
      assert.equal(v.ts_src, 'oba', 'ts = lastUpdateTime, con o sin trip');
    }
    // coche del 151 sin trip: label del registro, sin route
    const noTrip = kf.new.find((v) => v.agency === '708' && !v.trip_id && registry[v.id]?.endsWith('-4852'));
    assert.ok(noTrip);
    assert.equal(noTrip.label_src, 'registry');
    assert.equal(noTrip.route_id, '');
    // con trip: route_id numérico como la API CABA
    const withTrip = kf.new.find((v) => v.trip_id);
    assert.match(withTrip.route_id, /^\d+$/);
    assert.match(withTrip.start_date, /^\d{8}$/);

    const d = await g.runCycle();
    assert.equal(d.keyframe, undefined);
    assert.deepEqual(d.new, []);
    assert.deepEqual(d.del, []);
    assert.deepEqual(d.upd, [], 'misma foto de OBA → delta vacío');
  });

  test('movimientos, altas y bajas entre ciclos', async () => {
    const t = await startStack();
    const d2 = fs.mkdtempSync(path.join(os.tmpdir(), 'grab-'));
    try {
      const g = makeGrabador(t, d2, { config: { ...t.config, recordLines: ['151'], maxVehicleAgeS: 300 } });
      await g.runCycle();
      const body = loadFixture('vehicles-for-agency/708');
      const live = body.data.list.filter((v) => v.location && v.tripId && (body.currentTime - v.lastUpdateTime) / 1000 <= 300);
      const [moved, gone] = live;
      // sin trip: uno quieto (sin cambios) y uno que reporta posición nueva (ts = su lastUpdateTime)
      const [still, walker] = body.data.list.filter((v) => v.location && !v.tripId && registry[v.vehicleId.split('_')[1]]);
      walker.location = { lat: walker.location.lat + 0.001, lon: walker.location.lon };
      walker.lastUpdateTime = body.currentTime + 25000;
      moved.location = { lat: moved.location.lat + 0.001, lon: moved.location.lon };
      moved.lastUpdateTime += 30000;
      body.data.list = body.data.list.filter((v) => v !== gone);
      body.currentTime += 30000;
      t.mock.override('vehicles-for-agency/708', body);
      t.app.client.cache.delete('vehicles-for-agency/708');
      const d = await g.runCycle();
      const movedId = moved.vehicleId.split('_')[1];
      const u = d.upd.find((x) => x.id === movedId);
      assert.ok(u, 'el coche movido aparece en upd');
      assert.equal(u.ts, Math.floor(moved.lastUpdateTime / 1000));
      assert.ok('lat' in u && !('lon' in u), 'upd trae solo lo que cambió');
      assert.ok(d.del.includes(gone.vehicleId.split('_')[1]));
      assert.ok(!d.upd.some((x) => x.id === still.vehicleId.split('_')[1]), 'sin trip y quieto → sin cambios');
      const w = d.upd.find((x) => x.id === walker.vehicleId.split('_')[1]);
      assert.equal(w.ts, Math.floor(walker.lastUpdateTime / 1000));
    } finally { await t.close(); fs.rmSync(d2, { recursive: true, force: true }); }
  });

  test('reinicio tras un gap: registro de gap + keyframe (estado propio, no pisa state.json viejo)', async () => {
    const d3 = fs.mkdtempSync(path.join(os.tmpdir(), 'grab-'));
    fs.writeFileSync(path.join(d3, 'state.json'), '{"legacy": true}');
    try {
      // Reloj anclado a la hora de las fotos del fixture: con Date.now() el gap puede caer en el archivo de otro día
      let clock = loadFixture('vehicles-for-agency/708').currentTime;
      const g1 = makeGrabador(s, d3, { now: () => clock });
      await g1.runCycle();
      clock += 3600 * 1000; // 1 h sin grabar
      const g2 = makeGrabador(s, d3, { now: () => clock });
      await g2.runCycle();
      const frames = readFrames(d3);
      const gapIdx = frames.findIndex((f) => f.gap);
      assert.ok(gapIdx > 0);
      assert.equal(frames[gapIdx].reason, 'restart');
      assert.ok(frames[gapIdx].gap_seconds >= 3600);
      assert.equal(frames[gapIdx + 1].keyframe, true);
      assert.equal(fs.readFileSync(path.join(d3, 'state.json'), 'utf8'), '{"legacy": true}');
      assert.ok(fs.existsSync(path.join(d3, 'bondiradar_state.json')));
    } finally { fs.rmSync(d3, { recursive: true, force: true }); }
  });

  test('el archivo se lee con gzip de Python, como lo lee el pipeline de ML', (t) => {
    const frames = readFrames(dir);
    assert.ok(frames.length >= 2);
    const file = path.join(dir, frames[0].file);
    let out;
    try {
      out = execFileSync('python', ['-c',
        'import gzip,json,sys\nn=0\nfor l in gzip.open(sys.argv[1],"rt",encoding="utf-8"):\n  json.loads(l); n+=1\nprint(n)', file], { encoding: 'utf8' });
    } catch {
      t.skip('python no disponible');
      return;
    }
    assert.equal(Number(out.trim()), frames.filter((f) => f.file === frames[0].file).length);
  });
});
