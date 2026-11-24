import fs from 'node:fs';
import path from 'node:path';

/**
 * Identidad vehículo → línea.
 *
 *   vehicleId OBA "708_93193" → id "93193"
 *   label = tripStatus.vehicleLabel (vivo)  ??  registro[id] (grabaciones API CABA)  ??  aprendido[id]
 *   línea = LABEL_LINE_MAP(sufijo del label, fecha)
 *
 * Invariante (ver OBA_IDENTIFICACION.md §4): un id nunca cambia de label. El id es
 * "coche × registro en línea": el mismo bondi en otra línea reporta con otro id.
 */
export class Identity {
  /**
   * @param {object} p
   * @param {object} p.labelLineMap  LABEL_LINE_MAP.json v3 ({lines: {...}})
   * @param {Record<string,string>} p.registry  id → label
   * @param {string|null} p.learnedPath  archivo JSON donde persistir labels aprendidos de OBA
   */
  constructor({ labelLineMap, registry = {}, learnedPath = null, now = () => Date.now() }) {
    this.lines = labelLineMap.lines || {};
    this.registry = registry;
    this.learnedPath = learnedPath;
    this.now = now;
    this.learned = {};      // id → {label, first_seen}
    this.conflicts = [];    // label distinto al conocido para un id (no debería pasar)
    this.indexCache = new Map(); // fecha → {suffix → line}
    this.dirty = false;
    if (learnedPath && fs.existsSync(learnedPath)) {
      try {
        const j = JSON.parse(fs.readFileSync(learnedPath, 'utf8'));
        this.learned = j.learned || {};
        this.conflicts = j.conflicts || [];
      } catch { /* archivo corrupto: arrancar vacío */ }
    }
  }

  /** Índice sufijo → línea vigente a `date` (YYYY-MM-DD). Fechas del map inclusive, to:null = vigente. */
  suffixIndex(date) {
    let idx = this.indexCache.get(date);
    if (idx) return idx;
    idx = {};
    for (const [line, e] of Object.entries(this.lines)) {
      for (const s of e.suffixes || []) {
        if (s.from <= date && (s.to == null || s.to >= date)) idx[s.suffix] = line;
      }
    }
    this.indexCache.set(date, idx);
    return idx;
  }

  /** Agencias vigentes de una línea a `date` (+ agencias extra de OBA, ver overrides/label_line_map.json). */
  agenciesFor(line, date) {
    const e = this.lines[line];
    if (!e) return [];
    const out = (e.agencies || []).filter((a) => a.from <= date && (a.to == null || a.to >= date))
      .map((a) => ({ id: a.agencyId, name: a.agencyName }));
    for (const id of e.obaAgencies || []) if (!out.some((a) => a.id === id)) out.push({ id, name: out[0]?.name || null, obaOnly: true });
    return out;
  }

  lineForLabel(label, date) {
    if (!label || !label.includes('-')) return null;
    return this.suffixIndex(date)[label.slice(label.lastIndexOf('-') + 1)] || null;
  }

  /**
   * Resuelve el label de un vehículo OBA. Si viene vivo de OBA y no lo conocíamos, lo aprende.
   * @returns {{label: string|null, source: 'oba'|'registry'|'learned'|null}}
   */
  resolve(vid, liveLabel) {
    if (liveLabel) {
      this.#learn(vid, liveLabel);
      return { label: liveLabel, source: 'oba' };
    }
    if (this.registry[vid]) return { label: this.registry[vid], source: 'registry' };
    if (this.learned[vid]) return { label: this.learned[vid].label, source: 'learned' };
    return { label: null, source: null };
  }

  #learn(vid, label) {
    const known = this.registry[vid] ?? this.learned[vid]?.label;
    if (known === label) return;
    if (known !== undefined) {
      this.conflicts.push({ id: vid, known, seen: label, at: new Date(this.now()).toISOString() });
      if (this.conflicts.length > 1000) this.conflicts.shift();
    }
    this.learned[vid] = { label, first_seen: new Date(this.now()).toISOString() };
    this.dirty = true;
  }

  /** Persiste aprendidos si cambiaron. Llamar periódicamente. */
  flush() {
    if (!this.dirty || !this.learnedPath) return false;
    fs.mkdirSync(path.dirname(this.learnedPath), { recursive: true });
    const tmp = `${this.learnedPath}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ learned: this.learned, conflicts: this.conflicts }));
    fs.renameSync(tmp, this.learnedPath);
    this.dirty = false;
    return true;
  }

  stats() {
    return {
      registry: Object.keys(this.registry).length,
      learned: Object.keys(this.learned).length,
      conflicts: this.conflicts.length,
    };
  }
}

/** Fecha local Buenos Aires (YYYY-MM-DD) de un timestamp ms. */
export function baDate(ms) {
  return new Date(ms - 3 * 3600 * 1000).toISOString().slice(0, 10);
}
