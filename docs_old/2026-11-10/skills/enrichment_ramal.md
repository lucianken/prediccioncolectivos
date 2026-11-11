# Enriquecimiento de vehiculos y identificacion de ramal

## Pipeline de enriquecimiento (proyectoconsola)

Cada vehiculo de la API CABA pasa por capas en orden:

**GATE — LABEL_LINE_MAP.json (schema v3, desde 2026-07)**
- Lookup por sufijo del VP_label (ej: "5-1350" → sufijo "1350"), **resuelto a una fecha**
- Schema v3: dos secciones — **`lines` = SOLO AMBA** y `other_lines` = homonimos del resto del pais (la API de Nacion Servicios reporta todo el pais: hay varios "12"; los del interior se colapsan por numero, sin distinguir ciudad, nada se borra). Formato interno: `linea → { agencies: [{agencyId, agencyName, from, to}], suffixes: [{suffix, agencyId, from, to}] }`. Fechas inclusive, `to: null` = vigente. Vigencias por el cambio de flota AMBA mayo-junio 2026 (ej. 151: sufijo 4045 hasta 2026-05-29 → 4852 desde 2026-06-11).
- Clasificacion AMBA/no-AMBA: analisis semantico contra `proyectoconsola/informacion de wikipedia.txt` (tabla de lineas AMBA con operadora por numero). La **agencia** es lo que dice la region.
- El map es estrictamente 1:1 por periodo. TODO lo no resuelto vive en **`proyectoconsola/pending_label_work.json`** — unico archivo de trabajo con `scope: amba|other|unknown` por entrada (`other` = interior, ignorar), consumido tambien en runtime (`GET /api/pending-label-work`). Vista humana generada: `PENDING_LABEL_WORK.md` (no editar a mano).
- **Ciclo de resolucion (metodo oficial)**: `node scripts/resolve_pending.js` — interactivo (sufijo → linea → confirma agencia listando las instancias existentes del numero, contra los "12" multiples) y al salir corre promote_pending.js (mueve al map segun scope, valida solapamientos en ambas secciones, sincroniza el espejo y regenera el MD).
- Inversion a indice {sufijo → linea}, AMBA-only por defecto: JS `js/labelLineMapUtil.js` (buildSuffixEntries(map, pending, fecha)), Python `prediccion/pipeline/shapes_io.py` (load_label_line_map / resolve_label_line_index con `on_date`; `include_other=True` para sumar interior). Al procesar grabaciones historicas usar la fecha del archivo.
- El map se mantiene en proyectoconsola/ con copia espejo en `prediccion colectivos/` (el pending vive SOLO en proyectoconsola).
- Es inapelable. ~321 sufijos resueltos + ~295 pendientes.
- Bug conocido API CABA: lineas 19, 133, 140, 184 comparten route_id — el label las distingue correctamente.

**ROUTE_AGENCY_MAP.json** (712KB)
- Mapeo route_id → info agencia/ruta
- Generado a partir del mapping CABA+CuandoSubo (ya completado en buenosaires-bus-pwa)

## Identificacion de ramal — RamalEngine (proyectoconsola)

Algoritmo de eliminacion iterativa sobre shapes OSM:
1. Calcula "zonas de divergencia" unicas de cada ramal (>40m de otros shapes)
2. VP hit en zona unica → route_id asignado a ese ramal
3. Al resolver un ramal, sus tramos compartidos pasan a ser unicos para los restantes (cascada)
4. route_ids consecutivos siempre son par de direccion (impar=dir0, par=dir1)

**Estado actual:** 6/11 route_ids de linea 39 identificados. Pendiente generalizar a otras lineas.

**Limitacion conocida:** Ramales 39D/E/F no tienen shapes en OSM — no son resolubles hasta que OSM los tenga.

## Route_ids cambian estacionalmente
El fingerprint aprendido debe revalidarse cuando aparecen route_ids nuevos para una linea conocida.
Linea 39 usaba 1989-1999 antes, ahora usa 1329-1340 (marzo 2026).

## Bug Darwin — línea 168 (y posiblemente otras)

Algunas líneas tienen route_ids "fantasma" que cubren un **segmento compartido** entre ramales.
El API asigna ese route_id al vehículo, luego dropea a vacío al llegar al punto de divergencia,
y reasigna el route_id correcto del ramal.

**Línea 168 documentado:**
- 1780 (P1) / 1260 (P2): segmento La Boca → Darwin, 50/50 entre 168A y 168C
- El ramal real no es predecible desde ningún campo del feed (analizado exhaustivamente)
- Única señal útil: viaje previo del mismo vehículo ese día → 62% accuracy
- Ver skill completo: `168_ramal_analysis.md`

**Cómo identificar un Darwin en otra línea:**
Route_id cuyas triple-transiciones (X → '' → Y) van a múltiples ramales distintos con ratio 0.3–3.0.
