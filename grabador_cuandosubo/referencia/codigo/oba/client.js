import fs from 'node:fs';
import path from 'node:path';

/**
 * Cliente OBA (CuandoSubo) con cache por recurso, coalescencia de requests en vuelo,
 * detección de WAF y "stale on error": si OBA falla y hay una copia vieja, se devuelve marcada stale.
 */
export class WafError extends Error {
  constructor(msg) { super(msg); this.name = 'WafError'; }
}
export class ObaError extends Error {
  constructor(msg, status) { super(msg); this.name = 'ObaError'; this.status = status; }
}

export class ObaClient {
  /**
   * @param {string|null} persistDir  si se indica, los recursos con ttl >= persistMinTtlMs (rutas, paradas)
   *   se guardan en disco: sobreviven reinicios y no se vuelven a pedir a CuandoSubo hasta vencer.
   */
  constructor({ baseUrl, key, limiter, timeoutMs = 30000, wafBackoffMs = 120000, fetchImpl = fetch, now = () => Date.now(), onResponse = null, persistDir = null, persistMinTtlMs = 3600000 }) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.key = key;
    this.limiter = limiter;
    this.timeoutMs = timeoutMs;
    this.wafBackoffMs = wafBackoffMs;
    this.fetch = fetchImpl;
    this.now = now;
    this.onResponse = onResponse;   // hook (path, body) — usado por el grabador
    this.cache = new Map();         // path -> { body, fetchedAt }
    this.inflight = new Map();      // path -> Promise
    this.persistDir = persistDir;
    this.persistMinTtlMs = persistMinTtlMs;
    this.lastError = null;
    this.stats = { hits: 0, misses: 0, stale: 0, errors: 0, waf: 0 };
  }

  /**
   * GET de un recurso OBA (ej. 'vehicles-for-agency/708').
   * @returns {Promise<{body: object, fetchedAt: number, stale: boolean, error?: string}>}
   */
  async get(resource, { ttlMs, priority = 1 } = {}) {
    const persist = this.persistDir && ttlMs >= this.persistMinTtlMs;
    if (persist && !this.cache.has(resource)) this.#loadPersisted(resource);
    const cached = this.cache.get(resource);
    if (cached && this.now() - cached.fetchedAt < ttlMs) {
      this.stats.hits++;
      return { body: cached.body, fetchedAt: cached.fetchedAt, stale: false };
    }
    if (this.inflight.has(resource)) return this.inflight.get(resource);

    this.stats.misses++;
    const p = this.limiter.schedule(() => this.#fetchJson(resource), { priority })
      .then((body) => {
        const entry = { body, fetchedAt: this.now() };
        this.cache.set(resource, entry);
        if (persist) this.#savePersisted(resource, entry);
        this.onResponse?.(resource, body);
        return { body, fetchedAt: entry.fetchedAt, stale: false };
      })
      .catch((err) => {
        this.stats.errors++;
        this.lastError = { at: this.now(), resource, message: err.message, type: err.name };
        if (err instanceof WafError) {
          this.stats.waf++;
          this.limiter.pause(this.wafBackoffMs);
        }
        if (cached) {
          this.stats.stale++;
          return { body: cached.body, fetchedAt: cached.fetchedAt, stale: true, error: err.message };
        }
        throw err;
      })
      .finally(() => this.inflight.delete(resource));
    this.inflight.set(resource, p);
    return p;
  }

  #file(resource) {
    return path.join(this.persistDir, `${resource.replace(/[^\w-]/g, '__')}.json`);
  }

  #loadPersisted(resource) {
    try {
      const entry = JSON.parse(fs.readFileSync(this.#file(resource), 'utf8'));
      if (entry?.body && Number.isFinite(entry.fetchedAt)) this.cache.set(resource, entry);
    } catch { /* no hay copia en disco */ }
  }

  #savePersisted(resource, entry) {
    try {
      fs.mkdirSync(this.persistDir, { recursive: true });
      const f = this.#file(resource);
      fs.writeFileSync(`${f}.tmp`, JSON.stringify(entry));
      fs.renameSync(`${f}.tmp`, f);
    } catch (e) {
      console.error(`no se pudo persistir ${resource}: ${e.message}`);
    }
  }

  async #fetchJson(resource) {
    const url = `${this.baseUrl}/${resource}.json?key=${encodeURIComponent(this.key)}`;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    let res;
    try {
      res = await this.fetch(url, {
        redirect: 'manual',
        signal: ctrl.signal,
        headers: { 'User-Agent': 'bondiradar/0.1', Accept: 'application/json' },
      });
    } catch (e) {
      throw new ObaError(`network: ${e.name === 'AbortError' ? 'timeout' : e.message}`);
    } finally {
      clearTimeout(timer);
    }
    // El WAF responde 302 a una página "Security Redirect" (loop). También tratamos 403/429 igual.
    if ([301, 302, 303, 307, 403, 429].includes(res.status) || res.type === 'opaqueredirect') {
      throw new WafError(`WAF/rate limit (HTTP ${res.status})`);
    }
    if (!res.ok) throw new ObaError(`HTTP ${res.status}`, res.status);
    const text = await res.text();
    let body;
    try { body = JSON.parse(text); } catch { throw new WafError('respuesta no JSON (probable WAF)'); }
    if (body.code !== 200) throw new ObaError(`OBA code ${body.code}: ${body.text || ''}`, body.code);
    return body;
  }

  snapshot() {
    return {
      cacheEntries: this.cache.size,
      inflight: this.inflight.size,
      queue: this.limiter.pending,
      paused: this.limiter.paused,
      stats: { ...this.stats, limiter: this.limiter.stats },
      lastError: this.lastError,
    };
  }
}
