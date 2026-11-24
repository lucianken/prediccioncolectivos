/**
 * Limitador global de requests a OBA: una a la vez, espaciadas >= minIntervalMs,
 * con cola por prioridad (0 = lo que un usuario está mirando, mayor = background).
 * El WAF de SUBE corta con 302 "Security Redirect" si se paraleliza.
 */
export class RateLimiter {
  constructor({ minIntervalMs, now = () => Date.now(), sleep = defaultSleep } = {}) {
    this.minIntervalMs = minIntervalMs;
    this.now = now;
    this.sleep = sleep;
    this.queue = [];          // { fn, priority, seq, resolve, reject }
    this.seq = 0;
    this.running = false;
    this.lastStart = -Infinity;
    this.pausedUntil = 0;
    this.stats = { executed: 0, failed: 0 };
  }

  /** Encola fn; resuelve con su resultado. */
  schedule(fn, { priority = 1 } = {}) {
    return new Promise((resolve, reject) => {
      this.queue.push({ fn, priority, seq: this.seq++, resolve, reject });
      this.queue.sort((a, b) => a.priority - b.priority || a.seq - b.seq);
      this.#pump();
    });
  }

  /** Pausa todo hasta now+ms (backoff de WAF). */
  pause(ms) {
    this.pausedUntil = Math.max(this.pausedUntil, this.now() + ms);
  }

  get pending() { return this.queue.length; }
  get paused() { return this.now() < this.pausedUntil; }

  async #pump() {
    if (this.running) return;
    this.running = true;
    try {
      while (this.queue.length) {
        const wait = Math.max(this.pausedUntil - this.now(), this.lastStart + this.minIntervalMs - this.now(), 0);
        if (wait > 0) await this.sleep(wait);
        // Puede haber llegado algo más prioritario mientras dormíamos
        const job = this.queue.shift();
        this.lastStart = this.now();
        try {
          job.resolve(await job.fn());
          this.stats.executed++;
        } catch (e) {
          this.stats.failed++;
          job.reject(e);
        }
      }
    } finally {
      this.running = false;
    }
  }
}

function defaultSleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
