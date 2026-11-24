import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const int = (v, d) => (v === undefined || v === '' ? d : Number.parseInt(v, 10));

/** Configuración desde env. Todo tiene default razonable para correr local. */
export function loadConfig(env = process.env) {
  return {
    root: ROOT,
    port: int(env.PORT, 8080),
    host: env.HOST || '0.0.0.0',
    publicDir: env.PUBLIC_DIR || path.join(ROOT, 'public'),
    dataDir: env.DATA_DIR || path.join(ROOT, 'data'),
    // Estado mutable (labels aprendidos, grabaciones). Separado de data/ (que es generado y versionado).
    stateDir: env.STATE_DIR || path.join(ROOT, 'state'),
    oba: {
      baseUrl: env.OBA_BASE_URL || 'https://cuandosubo.sube.gob.ar/onebusaway-api-webapp/api/where',
      // Key de la API OBA de CuandoSubo. Solo por env (no versionar): ver .env.example
      key: env.OBA_KEY || '',
      // WAF de SUBE: medido seguro 1 request / 3 s secuencial. Nunca paralelizar.
      minIntervalMs: int(env.OBA_MIN_INTERVAL_MS, 3000),
      timeoutMs: int(env.OBA_TIMEOUT_MS, 30000),
      wafBackoffMs: int(env.OBA_WAF_BACKOFF_MS, 120000),
    },
    ttl: {
      vehiclesMs: int(env.TTL_VEHICLES_MS, 25000),
      arrivalsMs: int(env.TTL_ARRIVALS_MS, 30000),
      routesMs: int(env.TTL_ROUTES_MS, 7 * 24 * 3600 * 1000),
      stopsMs: int(env.TTL_STOPS_MS, 30 * 24 * 3600 * 1000),
    },
    // Coche reportando <=> currentTime - lastUpdateTime <= esto (calidad de la línea; no se oculta nada)
    maxVehicleAgeS: int(env.MAX_VEHICLE_AGE_S, 300),
    // Parada OBA a más de esto de todo ramal OSM = fuera del recorrido real (gana OSM)
    routeMatchM: int(env.ROUTE_MATCH_M, 75),
    // Grabador continuo (continuación del grabador del NUC; mismo formato NDJSON delta/keyframe)
    record: env.RECORD !== '0',
    recordDir: env.RECORD_DIR || path.join(env.STATE_DIR || path.join(ROOT, 'state'), 'grabaciones'),
    // Líneas cuyas empresas se graban en CADA ciclo (30 s). El resto de AMBA rota en los huecos libres.
    recordLines: (env.RECORD_LINES || '39 26 42 92 124 151 168').split(/[\s,]+/).filter(Boolean),
    recordSweep: env.RECORD_SWEEP !== '0',
    recordCycleMs: int(env.RECORD_CYCLE_MS, 30000),
  };
}
