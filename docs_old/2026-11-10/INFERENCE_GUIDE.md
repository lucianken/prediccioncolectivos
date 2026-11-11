# Guía de inferencia — eta_a3_final.onnx

## Qué hace el modelo

Dado un bus específico en movimiento sobre un ramal conocido, predice cuántos
segundos tarda en llegar a la posición del usuario proyectada sobre ese shape.

**Output:** `eta_seconds` — float, segundos hasta que el bus llega al punto del usuario.

---

## Inputs requeridos

Todos los tensores tienen batch dimension. Para inferencia en tiempo real, batch=1.

### trajectory `(1, 10, 3)` float32
Historial de posiciones del bus consultado — últimos 10 puntos GPS del viaje actual,
del más viejo al más reciente. Cada punto tiene 3 features:

| Columna | Descripción | Rango |
|---------|-------------|-------|
| `[i, 0]` | Posición sobre el shape normalizada: `dist_along_shape_m / shape_length_m` | 0.0–1.0 |
| `[i, 1]` | Velocidad: `speed_mps / 30.0` | 0.0–1.0 |
| `[i, 2]` | Tiempo desde el punto anterior: `dt_seconds / 30.0`, clampeado a 5.0 | 0.0–5.0 |

Si hay menos de 10 puntos históricos, rellenar con ceros desde el inicio
(los puntos reales van al final del tensor). Ejemplo con 3 puntos:
```
[[0,0,0], [0,0,0], [0,0,0], [0,0,0], [0,0,0], [0,0,0], [0,0,0],
 [pt_old], [pt_mid], [pt_now]]
```

### trajectory_mask `(1, 10)` bool
`True` = posición de padding (ignorar), `False` = punto real.
```
[True, True, True, True, True, True, True, False, False, False]  ← 3 puntos reales
```

### fleet `(1, N, 5)` float32
Estado de todos los vehículos activos de la agencia en este momento.
N = cantidad real de vehículos (variable). Cada fila:

| Columna | Descripción | Rango |
|---------|-------------|-------|
| `[i, 0]` | Latitud normalizada: `(lat - (-34.6)) * 10.0` | ~-0.5 a 0.25 |
| `[i, 1]` | Longitud normalizada: `(lon - (-58.4)) * 10.0` | ~-0.5 a 0.35 |
| `[i, 2]` | Velocidad en m/s | 0.0–18.0 |
| `[i, 3]` | direction_id del vehículo (0 o 1) | 0.0 o 1.0 |
| `[i, 4]` | ¿Va en la misma dirección que el bus consultado? | 0.0 o 1.0 |

Excluir el bus consultado de la lista. Si no hay flota activa, pasar tensor vacío `(1, 0, 5)`.

### fleet_mask `(1, N)` bool
Todo `False` (ningún bus es padding — son todos reales).
Si fleet es vacío, pasar `(1, 0)`.

### hour_sin `(1, 1)` float32
`sin(2π × hora_decimal / 24)` donde `hora_decimal = hora + minuto/60`.

### hour_cos `(1, 1)` float32
`cos(2π × hora_decimal / 24)`.

### dow `(1, 1)` int64
Día de la semana: 0=Lunes, 1=Martes, ..., 6=Domingo.

### dist_remaining_norm `(1, 1)` float32
Distancia del bus al punto del usuario, normalizada por el largo del shape:
`(dist_target_m - dist_bus_m) / shape_length_m`.
Siempre positivo (el usuario está adelante del bus).

### time_since_start `(1, 1)` float32
Segundos desde que el bus arrancó el viaje, dividido por 3600:
`(now_unix - trip_start_unix) / 3600.0`.

### has_active_bus `(1, 1)` float32
`1.0` siempre que haya un bus real con posición conocida (que es el caso cuando
se usa este modelo). `0.0` solo si se predice sin bus visible — no implementado aún.

---

## Implementación en producción (Node.js / proyectoconsola)

```javascript
const ort = require('onnxruntime-node');

async function predictETA(bus, userPosition, fleet, shapes) {
    const session = await ort.InferenceSession.create('eta_a3_final.onnx');

    // 1. Resolver ramal del bus (ya resuelto por ramal_lookup)
    const ramalId = bus.shape_id;  // ej: "382202"
    const shape   = shapes[ramalId];
    const shapeLen = shape.length_m;

    // 2. Proyectar posiciones sobre el shape
    const distBus    = projectOnShape(bus.lat, bus.lon, shape.points);
    const distTarget = projectOnShape(userPosition.lat, userPosition.lon, shape.points);
    const distRem    = distTarget - distBus;
    if (distRem <= 0) return null;  // bus ya pasó

    // 3. Construir traj (últimos 10 puntos del bus)
    const trajData = buildTraj(bus.history, shapeLen);  // ver abajo

    // 4. Flota de la agencia (excluir el bus consultado)
    const fleetData = fleet
        .filter(v => v.vehicle_id !== bus.vehicle_id)
        .map(v => [
            (v.lat - (-34.6)) * 10.0,
            (v.lon - (-58.4)) * 10.0,
            v.speed,
            v.direction_id,
            v.direction_id === bus.direction_id ? 1.0 : 0.0,
        ]);
    const N = fleetData.length;

    // 5. Tiempo
    const now = new Date();
    const hourDecimal = now.getHours() + now.getMinutes() / 60;
    const angle = 2 * Math.PI * hourDecimal / 24;
    const dow = (now.getDay() + 6) % 7;  // JS: 0=domingo → convertir a 0=lunes

    // 6. Armar tensores ONNX
    const feeds = {
        trajectory:         new ort.Tensor('float32', trajData.values, [1, 10, 3]),
        trajectory_mask:    new ort.Tensor('bool',    trajData.mask,   [1, 10]),
        fleet:              new ort.Tensor('float32', fleetData.flat(), [1, N, 5]),
        fleet_mask:         new ort.Tensor('bool',    new Array(N).fill(false), [1, N]),
        hour_sin:           new ort.Tensor('float32', [Math.sin(angle)], [1, 1]),
        hour_cos:           new ort.Tensor('float32', [Math.cos(angle)], [1, 1]),
        dow:                new ort.Tensor('int64',   [BigInt(dow)],     [1, 1]),
        dist_remaining_norm: new ort.Tensor('float32', [distRem / shapeLen], [1, 1]),
        time_since_start:   new ort.Tensor('float32', [(Date.now()/1000 - bus.trip_start_unix) / 3600], [1, 1]),
        has_active_bus:     new ort.Tensor('float32', [1.0], [1, 1]),
    };

    const result = await session.run(feeds);
    return result.eta_seconds.data[0];  // segundos
}

function buildTraj(history, shapeLen) {
    // history: array de puntos [{dist_along_m, speed, ts}, ...], ordenado del más viejo al más nuevo
    const K = Math.min(history.length, 10);
    const values = new Float32Array(10 * 3).fill(0);
    const mask   = new Array(10).fill(true);
    const offset = 10 - K;  // puntos reales van al final
    for (let i = 0; i < K; i++) {
        const pt = history[history.length - K + i];
        const prev = i > 0 ? history[history.length - K + i - 1] : null;
        const j = offset + i;
        values[j * 3 + 0] = Math.min(pt.dist_along_m / shapeLen, 1.0);
        values[j * 3 + 1] = Math.min(pt.speed / 30.0, 1.0);
        values[j * 3 + 2] = prev ? Math.min((pt.ts - prev.ts) / 30.0, 5.0) : 0.0;
        mask[j] = false;
    }
    return { values, mask };
}
```

---

## Notas de integración

- **Frecuencia:** llamar al modelo cada vez que llega un nuevo snapshot de GPS (~30s).
  El output anterior queda stale después de 30s.
- **Latencia:** < 1ms en CPU con onnxruntime. No necesita GPU en producción.
- **Fleet vacío:** si la API de agencia no responde, pasar `fleet=(1,0,5)` y
  `fleet_mask=(1,0)`. El FleetEncoder devuelve ceros y el modelo predice solo
  desde trayectoria + contexto temporal (comportamiento degradado aceptable).
- **Bus ya pasó** (`distRem <= 0`): no llamar al modelo, mostrar "pasó hace X metros".
- **ONNX runtime:** `npm install onnxruntime-node` para Node.js.
  Versión recomendada: 1.17+.

---

## UX: los últimos 500 metros

**No usar posición directa para el countdown final.** La API reporta con hasta 30s
de delay — a 30 km/h el bus ya se movió 250m desde el último reporte. A 500m de
distancia eso es 50% de error solo por el lag, antes de sumar tiempo de red.

El modelo es mejor acá porque fue entrenado con ese mismo lag: aprendió a compensar
el delay de la API implícitamente. Usar el modelo hasta el final.

La única lógica especial es detectar "ya pasó":

```javascript
function getETA(bus, distRem, shapeLen, ...) {
    // Con el lag de la API, -100m significa que probablemente está llegando justo ahora
    if (distRem < -100) return { passed: true };

    // distRem entre -100 y 0: mostrar "llegando" — no llamar al modelo
    if (distRem <= 0) return { arriving: true };

    // Para todo lo demás, el modelo sabe mejor — incluyendo los últimos 500m
    const eta = runModel(...);
    const confidence = bus.historyPoints >= 5 ? 'HIGH' : 'LOW';
    return { eta, confidence };
}
```

**Tier de confianza** (no hay output explícito del modelo — calcularlo en el cliente):

| `historyPoints` | Confianza | Label en UI |
|----------------|-----------|-------------|
| ≥ 5 (~2.5 min) | HIGH | "8 min" |
| 2–4 | MEDIUM | "~8 min" |
| 1 | LOW | "~8 min (estimado)" |

Para cold start (1 punto), A3 sigue siendo mejor que un baseline estadístico porque
usa la velocidad actual y el estado de la flota en tiempo real — no usar A1 como
fallback. Solo cambiar el label en la UI.

---

## UX: prefetch al abrir la app

El modelo corre en < 1ms por bus. Con 60 buses activos en la agencia son 60ms
totales — imperceptible. Usar esto para prefetch:

```javascript
class ETACache {
    constructor(ttlMs = 10 * 60 * 1000) {  // 10 minutos
        this.cache = new Map();
        this.ttl = ttlMs;
    }

    async prefetchAll(agencyFleet, shapes) {
        // Llamar una sola vez a la API → predecir para TODOS los buses activos
        // Esto corre al abrir la app, antes de que el usuario elija una línea
        for (const bus of agencyFleet) {
            if (!shapes[bus.shape_id]) continue;
            const eta = await predictETA(bus, /* userPos aproximado */ null, agencyFleet, shapes);
            this.cache.set(bus.vehicle_id, { eta, ts: Date.now(), traj_len: bus.history.length });
        }
    }

    get(vehicleId) {
        const entry = this.cache.get(vehicleId);
        if (!entry) return null;
        if (Date.now() - entry.ts > this.ttl) {
            this.cache.delete(vehicleId);
            return null;
        }
        return entry;
    }

    invalidate(vehicleId) { this.cache.delete(vehicleId); }
}
```

**Flujo recomendado:**

```
App abre / usuario abre el mapa
    → GET /api/agency-fleet  (una llamada, todos los buses activos)
    → prefetchAll() en background — 60ms para 60 buses
    → cache listo antes de que el usuario elija una línea

Usuario navega, no eligió línea todavía
    → UI puede mostrar "39 ~8 min | 151 ~12 min" desde el caché
    → comparación entre líneas disponible inmediatamente

Usuario elige el 39
    → suscribir a updates del 39 únicamente
    → el resto del caché expira solo a los 10 min (o se purga explícitamente)
    → cada nuevo snapshot del 39 → invalidate(bus_id) → predecir → guardar

Caché entry expira si:
    → age > 10 min (trayectoria demasiado vieja para el modelo)
    → bus desaparece de la API en el siguiente snapshot
```

El cuello de botella siempre es la llamada a la API de agencia, no la inferencia.
El prefetch resuelve el "cold start de UX" (usuario eligió pero no hay predicción
todavía) sin cambiar nada en el modelo.
