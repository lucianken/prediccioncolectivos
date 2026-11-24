#!/usr/bin/env node
/**
 * Construye data/registry.json — id de vehículo → label (+ patente) — desde las grabaciones NDJSON de la API CABA.
 *
 *   node scripts/build-registry.js [dir_grabaciones] [--workers 6]     (default dir: Z:\grabaciones)
 *
 * Por qué alcanza con hacerlo una vez: la API CABA murió el 2026-10-15 y en 185 días ningún id
 * cambió de label (el id es "coche × registro en línea"). Lo nuevo lo aprende el servidor en vivo
 * desde tripStatus.vehicleLabel de OBA (state/learned_labels.json).
 */
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import readline from 'node:readline';
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'data', 'registry.json');

if (!isMainThread) {
  // Worker: un día → { id: { label: count } }. Solo keyframes/altas traen label (los upd son parciales).
  const vehicles = {};
  const rl = readline.createInterface({ input: fs.createReadStream(workerData.file).pipe(zlib.createGunzip()), crlfDelay: Infinity });
  rl.on('line', (line) => {
    if (!line.slice(0, 100).includes('"new": [{')) return;
    let d;
    try { d = JSON.parse(line); } catch { return; }
    for (const v of d.new || []) {
      if (!v.label) continue;
      const x = vehicles[v.id] || (vehicles[v.id] = { labels: {}, plate: null });
      x.labels[v.label] = (x.labels[v.label] || 0) + 1;
      const p = (v.license_plate || '').trim();
      // Patentes válidas (AA000AA / AAA000); ZZ… es imposible (valor de relleno del upstream)
      if (/^([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})$/.test(p) && !p.startsWith('ZZ')) x.plate = p;
    }
  });
  rl.on('close', () => parentPort.postMessage({ vehicles }));
  rl.on('error', (e) => parentPort.postMessage({ error: e.message, vehicles }));
} else {
  const args = process.argv.slice(2);
  const wi = args.indexOf('--workers');
  const nWorkers = wi >= 0 ? Number(args[wi + 1]) : 6;
  const dir = args.find((a, i) => !a.startsWith('--') && args[i - 1] !== '--workers') || 'Z:\\grabaciones';
  const files = fs.readdirSync(dir).filter((f) => /^\d{4}-\d{2}-\d{2}\.ndjson\.gz$/.test(f)).sort();
  if (!files.length) { console.error(`sin grabaciones en ${dir}`); process.exit(1); }
  console.log(`${files.length} días en ${dir} (${files[0].slice(0, 10)} → ${files.at(-1).slice(0, 10)}), ${nWorkers} workers`);

  const runDay = (file) => new Promise((resolve) => {
    const w = new Worker(fileURLToPath(import.meta.url), { workerData: { file: path.join(dir, file) } });
    w.once('message', (m) => { if (m.error) console.error(`\n  ${file}: ${m.error}`); resolve(m.vehicles); w.terminate(); });
    w.once('error', (e) => { console.error(`\n  ${file}: ${e.message}`); resolve({}); });
  });

  const results = new Array(files.length);
  let next = 0, done = 0;
  const t0 = Date.now();
  await Promise.all(Array.from({ length: Math.min(nWorkers, files.length) }, async () => {
    while (next < files.length) {
      const i = next++;
      results[i] = await runDay(files[i]);
      done++;
      process.stdout.write(`\r  ${done}/${files.length} días (${Math.round((Date.now() - t0) / 1000)} s)`);
    }
  }));

  // Merge cronológico: gana el label más reciente; cualquier cambio queda en conflicts (esperado: 0)
  const vehicles = {};
  const plates = {};   // id → última patente vista (informativa: la patente NO es clave confiable)
  const conflicts = {};
  files.forEach((f, i) => {
    const date = f.slice(0, 10);
    for (const [id, x] of Object.entries(results[i] || {})) {
      const label = Object.entries(x.labels).sort((a, b) => b[1] - a[1])[0][0];
      if (vehicles[id] && vehicles[id] !== label) (conflicts[id] ||= []).push({ from: vehicles[id], to: label, date });
      vehicles[id] = label;
      if (x.plate) plates[id] = x.plate;
    }
  });

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify({
    version: 1,
    generated: new Date().toISOString(),
    days: { from: files[0].slice(0, 10), to: files.at(-1).slice(0, 10), count: files.length },
    vehicles,
    plates,
    conflicts,
  }));
  console.log(`\n${Object.keys(vehicles).length} ids, ${Object.keys(conflicts).length} con cambio de label → ${path.relative(ROOT, OUT)}`);
}
