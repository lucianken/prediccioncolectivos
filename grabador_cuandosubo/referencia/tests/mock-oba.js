import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const FIXTURES = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures', 'oba');
export const TEST_KEY = 'test-key';

/**
 * OBA falso que sirve respuestas reales grabadas de CuandoSubo (test/fixtures/oba/{recurso con / → __}.json).
 * Modos: 'ok' | 'waf' (302 Security Redirect como el WAF de SUBE) | 'down' (500).
 * Control (para E2E): POST /__mode?mode=waf  ·  GET /__log
 */
export function startMockOba({ port = 0 } = {}) {
  const state = { mode: 'ok', log: [], overrides: new Map(), sequences: new Map() };
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    if (url.pathname === '/__mode') {
      state.mode = url.searchParams.get('mode') || 'ok';
      res.writeHead(204).end();
      return;
    }
    if (url.pathname === '/__seq') {
      useSequence(state, url.searchParams.get('resource'));
      res.writeHead(204).end();
      return;
    }
    if (url.pathname === '/__log') {
      res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify(state.log));
      return;
    }
    const m = /^\/api\/where\/(.+)\.json$/.exec(url.pathname);
    const resource = m?.[1];
    state.log.push({ at: Date.now(), resource, key: url.searchParams.get('key') });
    if (state.mode === 'waf') {
      res.writeHead(302, { Location: '/security-redirect' }).end();
      return;
    }
    if (state.mode === 'down') {
      res.writeHead(500).end('down');
      return;
    }
    if (!resource) return json(res, 404, { code: 404, text: 'not found' });
    if (url.searchParams.get('key') !== TEST_KEY) return json(res, 200, { code: 401, text: 'permission denied', version: 2 });
    if (state.overrides.has(resource)) return json(res, 200, state.overrides.get(resource));
    const seq = state.sequences.get(resource);
    if (seq) {
      // Fotos reales consecutivas (test/fixtures/oba/seq/...): una por request, la última se repite
      const file = seq.files[Math.min(seq.i++, seq.files.length - 1)];
      res.writeHead(200, { 'Content-Type': 'application/json' });
      fs.createReadStream(file).pipe(res);
      return;
    }
    const file = path.join(FIXTURES, `${resource.replaceAll('/', '__')}.json`);
    if (!fs.existsSync(file)) return json(res, 200, { code: 404, text: 'resource not found', version: 2 });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      const { port: p } = server.address();
      resolve({
        url: `http://127.0.0.1:${p}/api/where`,
        port: p,
        state,
        setMode: (m) => { state.mode = m; },
        requests: (prefix = '') => state.log.filter((l) => l.resource?.startsWith(prefix)),
        override: (resource, body) => state.overrides.set(resource, body),
        useSequence: (resource) => useSequence(state, resource),
        close: () => new Promise((r) => server.close(() => r())),
      });
    });
  });
}

function useSequence(state, resource) {
  const dir = path.join(FIXTURES, 'seq', resource.replaceAll('/', '__'));
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.json')).sort().map((f) => path.join(dir, f));
  state.sequences.set(resource, { files, i: 0 });
}

export function loadSequence(resource) {
  const dir = path.join(FIXTURES, 'seq', resource.replaceAll('/', '__'));
  return fs.readdirSync(dir).filter((f) => f.endsWith('.json')).sort().map((f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')));
}

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(body));
}

export function loadFixture(resource) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, `${resource.replaceAll('/', '__')}.json`), 'utf8'));
}
