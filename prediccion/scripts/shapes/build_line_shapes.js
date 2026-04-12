#!/usr/bin/env node
/**
 * build_line_shapes.js
 * Extrae shapes + stops de BabusNova GTFS para las líneas objetivo y los guarda
 * en line_shapes.json (local a proyectoconsola, sin dependencia del repo BabusNova).
 *
 * Uso: node scripts/build_line_shapes.js
 */

const fs       = require('fs');
const path     = require('path');
const readline = require('readline');

const GTFS_DIR    = path.join(__dirname, '../../BabusNova/amba-gtfs/output/AMBA_GTFS_filtered');
const OUTPUT_FILE = path.join(__dirname, '../line_shapes.json');

const TARGET_LINES = ['39', '42', '151', '168', '124', '26', '92'];

// ── CSV helpers ──────────────────────────────────────────────────────────────

function readCsvSync(file) {
  const lines = fs.readFileSync(file, 'utf8').trim().split('\n');
  const headers = lines[0].split(',').map(h => h.trim());
  return lines.slice(1).map(l => {
    const vals = l.split(',');
    const obj = {};
    headers.forEach((h, i) => { obj[h] = (vals[i] || '').trim(); });
    return obj;
  });
}

// ── Query Overpass para ref tags de OSM relations ────────────────────────────

const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';

async function fetchOsmRefs(shapeIds) {
  const ids = [...shapeIds];
  const BATCH = 50;
  const refs  = {}; // shapeId → ref string | null

  for (let i = 0; i < ids.length; i += BATCH) {
    const batch = ids.slice(i, i + BATCH);
    const query = `[out:json][timeout:60];(${batch.map(id => `relation(${id});`).join('')});out tags;`;
    console.log(`  Overpass batch ${Math.floor(i / BATCH) + 1}/${Math.ceil(ids.length / BATCH)} (${batch.length} relations)...`);
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const resp = await fetch(OVERPASS_URL, {
          method:  'POST',
          body:    new URLSearchParams({ data: query }),
          headers: { 'User-Agent': 'BabusNova-GTFS-Enrich/1.0' },
        });
        const data = await resp.json();
        for (const elem of data.elements || []) {
          refs[String(elem.id)] = elem.tags?.ref || null;
        }
        break;
      } catch (e) {
        if (attempt < 2) { console.warn(`    reintento ${attempt + 1} (${e.message})`); await new Promise(r => setTimeout(r, 3000)); }
        else console.warn(`    falló: ${e.message}`);
      }
    }
  }
  return refs;
}

// ── Derivar shortName: OSM ref primero, luego headsign, luego Rn ─────────────

function deriveShortName(lineNum, headsign, osmRef, idx) {
  if (osmRef) return osmRef; // Authoritative: OSM ref tag ("42A", "39A", etc.)
  const m = headsign.match(new RegExp(`^${lineNum}([A-Z])\\b`));
  if (m) return `${lineNum}${m[1]}`;
  return `${lineNum}R${idx + 1}`;
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {

  // 1. Routes ─────────────────────────────────────────────────────────────────
  // BabusNova GTFS contiene líneas de todo AMBA + provincias. Hay múltiples
  // route_ids con el mismo route_short_name (ej: línea 42 en BA y en Misiones).
  // Guardamos TODOS los candidatos; luego filtramos por geografía BA.
  console.log('1. Leyendo routes.txt...');
  const routesRows = readCsvSync(path.join(GTFS_DIR, 'routes.txt'));

  // lineNum → [ { gtfsRouteId, color } ]
  const lineToRoutes = {};
  for (const r of routesRows) {
    const sn = r.route_short_name;
    if (!TARGET_LINES.includes(sn)) continue;
    if (!lineToRoutes[sn]) lineToRoutes[sn] = [];
    lineToRoutes[sn].push({ gtfsRouteId: r.route_id, color: r.route_color || '' });
    console.log(`  Línea ${sn}: ${r.route_id}  agency=${r.agency_id}  color=${r.route_color || '(vacío)'}`);
  }
  const neededGtfsRouteIds = new Set(
    Object.values(lineToRoutes).flatMap(arr => arr.map(v => v.gtfsRouteId))
  );
  console.log(`  ${Object.keys(lineToRoutes).length}/${TARGET_LINES.length} líneas encontradas (${neededGtfsRouteIds.size} route_ids total)\n`);

  // 2. Trips ──────────────────────────────────────────────────────────────────
  console.log('2. Leyendo trips.txt...');
  const tripsRows = readCsvSync(path.join(GTFS_DIR, 'trips.txt'));

  // lineNum → { headsign → { direction → { shapeId, tripId } } }
  const lineTrips    = {};
  const neededShapeIds = new Set();
  const neededTripIds  = new Set();

  // Build reverse map: gtfsRouteId → lineNum
  const routeIdToLine = {};
  for (const [ln, arr] of Object.entries(lineToRoutes)) {
    for (const { gtfsRouteId } of arr) routeIdToLine[gtfsRouteId] = ln;
  }

  for (const t of tripsRows) {
    const lineNum = routeIdToLine[t.route_id];
    if (!lineNum) continue;
    const headsign = t.trip_headsign;
    const dir      = Number(t.direction_id);
    const shapeId  = t.shape_id;
    const tripId   = t.trip_id;

    if (!lineTrips[lineNum])          lineTrips[lineNum] = {};
    if (!lineTrips[lineNum][headsign]) lineTrips[lineNum][headsign] = {};
    if (!lineTrips[lineNum][headsign][dir]) {
      lineTrips[lineNum][headsign][dir] = { shapeId, tripId };
      neededShapeIds.add(shapeId);
      neededTripIds.add(tripId);
    }
  }

  for (const [ln, hs] of Object.entries(lineTrips)) {
    const count = Object.values(hs).reduce((s, dirs) => s + Object.keys(dirs).length, 0);
    console.log(`  Línea ${ln}: ${Object.keys(hs).length} headsigns, ${count} trips`);
  }
  console.log(`  Total: ${neededShapeIds.size} shapes, ${neededTripIds.size} trips\n`);

  // 3. Shapes (stream — 700k líneas) ─────────────────────────────────────────
  console.log('3. Leyendo shapes.txt (stream)...');
  const shapeMap = {};
  for (const id of neededShapeIds) shapeMap[id] = [];

  await new Promise(resolve => {
    const rl = readline.createInterface({
      input: fs.createReadStream(path.join(GTFS_DIR, 'shapes.txt')),
      crlfDelay: Infinity,
    });
    let first = true;
    rl.on('line', line => {
      if (first) { first = false; return; } // skip header
      const c1 = line.indexOf(',');
      const id = line.substring(0, c1);
      if (!neededShapeIds.has(id)) return;
      const rest = line.substring(c1 + 1).split(',');
      shapeMap[id].push([Number(rest[0]), Number(rest[1]), Number(rest[2])]);
    });
    rl.on('close', resolve);
  });

  // Buenos Aires bounding box: lat -35.5 a -33.5, lon -59.5 a -57.5
  const BA_LAT_MIN = -35.5, BA_LAT_MAX = -33.5;
  const BA_LON_MIN = -59.5, BA_LON_MAX = -57.5;
  function isInBA(pts) {
    if (!pts.length) return false;
    const [lat, lon] = pts[0];
    return lat > BA_LAT_MIN && lat < BA_LAT_MAX && lon > BA_LON_MIN && lon < BA_LON_MAX;
  }

  const baShapeIds = new Set();
  for (const id of neededShapeIds) {
    shapeMap[id].sort((a, b) => a[2] - b[2]);
    shapeMap[id] = shapeMap[id].map(([lat, lon]) => [lat, lon]);
    const inBA = isInBA(shapeMap[id]);
    console.log(`  Shape ${id}: ${shapeMap[id].length} pts ${inBA ? '✓ BA' : '✗ fuera de BA — descartado'}`);
    if (inBA) baShapeIds.add(id);
  }
  console.log('');

  // 3b. Overpass: get ref tag per shape (= OSM relation ID) ─────────────────
  console.log('3b. Consultando Overpass para refs de OSM...');
  const osmRefs = await fetchOsmRefs(baShapeIds); // only BA shapes
  let refHits = 0;
  for (const [id, ref] of Object.entries(osmRefs)) {
    if (ref) { console.log(`  Shape ${id} → ref="${ref}"`); refHits++; }
  }
  console.log(`  ${refHits}/${baShapeIds.size} shapes con ref OSM\n`);

  // 4. Stop times ─────────────────────────────────────────────────────────────
  console.log('4. Leyendo stop_times.txt...');
  const stopTimesRows = readCsvSync(path.join(GTFS_DIR, 'stop_times.txt'));

  const tripStops = {}; // tripId → [{ stopId, seq }]
  for (const st of stopTimesRows) {
    if (!neededTripIds.has(st.trip_id)) continue;
    if (!tripStops[st.trip_id]) tripStops[st.trip_id] = [];
    tripStops[st.trip_id].push({ stopId: st.stop_id, seq: Number(st.stop_sequence) });
  }
  for (const arr of Object.values(tripStops)) arr.sort((a, b) => a.seq - b.seq);

  const neededStopIds = new Set(
    Object.values(tripStops).flatMap(arr => arr.map(s => s.stopId))
  );
  console.log(`  ${Object.keys(tripStops).length} trips con paradas, ${neededStopIds.size} stops únicos\n`);

  // 5. Stops ──────────────────────────────────────────────────────────────────
  console.log('5. Leyendo stops.txt...');
  const stopsRows = readCsvSync(path.join(GTFS_DIR, 'stops.txt'));

  const stopDetails = {};
  for (const s of stopsRows) {
    if (!neededStopIds.has(s.stop_id)) continue;
    stopDetails[s.stop_id] = {
      id:   s.stop_id,
      name: s.stop_name,
      lat:  Number(s.stop_lat),
      lng:  Number(s.stop_lon),
    };
  }
  console.log(`  ${Object.keys(stopDetails).length} stops cargados\n`);

  // 6. Armar output ───────────────────────────────────────────────────────────
  console.log('6. Armando output...');
  const output = {};

  for (const lineNum of TARGET_LINES) {
    const routeInfoList = lineToRoutes[lineNum];
    if (!routeInfoList) { console.warn(`  ⚠ Línea ${lineNum}: no en routes.txt`); continue; }

    const headsignMap = lineTrips[lineNum];
    if (!headsignMap) { console.warn(`  ⚠ Línea ${lineNum}: sin trips`); continue; }

    const sortedHeadsigns = Object.keys(headsignMap).sort();
    const ramales = [];

    sortedHeadsigns.forEach((headsign, hsIdx) => {
      for (const [dirStr, { shapeId, tripId }] of Object.entries(headsignMap[headsign])) {
        // Skip shapes outside Buenos Aires
        if (!baShapeIds.has(shapeId)) {
          console.log(`    Skip ${lineNum} "${headsign}" dir${dirStr}: shape ${shapeId} fuera de BA`);
          continue;
        }
        const osmRef   = osmRefs[shapeId] || null;
        const shortName = deriveShortName(lineNum, headsign, osmRef, hsIdx);
        const points   = shapeMap[shapeId] || [];
        const stopList = (tripStops[tripId] || []).map(s => stopDetails[s.stopId]).filter(Boolean);
        ramales.push({
          name:      headsign,
          shortName,
          direction: Number(dirStr),
          shapeId,
          points,
          stops: stopList,
        });
      }
    });

    if (!ramales.length) { console.warn(`  ⚠ Línea ${lineNum}: sin ramales BA`); continue; }

    // Color: usar el de la primera route_id cuyo shape esté en BA
    const baRouteIds = new Set(
      Object.values(headsignMap).flatMap(dirs =>
        Object.values(dirs).filter(({ shapeId }) => baShapeIds.has(shapeId)).map(({ shapeId }) => shapeId)
      )
    );
    const colorEntry = routeInfoList.find(ri => {
      // Pick the route_id that produced at least one BA shape
      return Object.values(headsignMap).some(dirs =>
        Object.values(dirs).some(({ shapeId }) => baShapeIds.has(shapeId))
      );
    });
    const color = colorEntry ? colorEntry.color : '';

    output[lineNum] = { color, ramales };

    const totalPts   = ramales.reduce((s, r) => s + r.points.length, 0);
    const totalStops = ramales.reduce((s, r) => s + r.stops.length, 0);
    console.log(`  Línea ${lineNum}: ${ramales.length} ramal-dirs, ${totalPts} pts, ${totalStops} paradas`);
  }

  // 7. Escribir ───────────────────────────────────────────────────────────────
  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output));
  const sizeMb = (fs.statSync(OUTPUT_FILE).size / 1024 / 1024).toFixed(2);
  console.log(`\n✓ Escrito ${OUTPUT_FILE}  (${sizeMb} MB)\n`);
}

main().catch(err => { console.error(err); process.exit(1); });
