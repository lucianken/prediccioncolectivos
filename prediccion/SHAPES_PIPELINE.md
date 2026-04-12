# Shapes y Paradas — Pipeline de Datos Geográficos

## Qué es `data/line_shapes.json`

Archivo estático (578 KB) con las trayectorias y paradas de las 7 líneas objetivo:
**26, 39, 42, 92, 124, 151, 168**

Este archivo es la única dependencia geográfica del sistema. No requiere internet
en runtime — se incluye directamente en el repo.

## Estructura del archivo

```json
{
  "39": {
    "color": "0000ff",
    "ramales": [
      {
        "name": "Flores Sur - Retiro",
        "shortName": "39",
        "direction": 0,
        "shapeId": "23555",
        "points": [[-34.5873, -58.3682], [-34.5875, -58.3683], ...],
        "stops": [
          { "id": "n454516942", "name": "Av. Rivadavia", "lat": -34.619, "lng": -58.463 }
        ]
      },
      {
        "name": "Retiro - Flores Sur",
        "shortName": "39",
        "direction": 1,
        "shapeId": "23556",
        "points": [...],
        "stops": [...]
      }
    ]
  }
}
```

- `points`: Array de `[lat, lon]` — trayectoria completa del ramal ordenada
- `stops`: Paradas en secuencia GTFS, con nombre y coordenadas
- `direction`: 0 = ida (outbound), 1 = vuelta (return)
- `shapeId`: ID del shape en el GTFS de BabusNova (= OSM relation ID)

## Cómo se generó

### Fuente de datos

1. **GTFS de BabusNova** — derivado de OpenStreetMap vía [Jungle-Bus/Prism](https://github.com/Jungle-Bus/prism)
   - `shapes.txt` — trayectorias (~700k líneas para todo AMBA)
   - `trips.txt` — viajes con headsign y direction_id
   - `routes.txt` — líneas con nombre corto (ej: "39")
   - `stops.txt` — paradas con nombre y coordenadas
   - `stop_times.txt` — secuencia de paradas por viaje
   - Ubicación local: `../BabusNova/amba-gtfs/output/AMBA_GTFS_filtered/`

2. **Overpass API** — para obtener el tag `ref` de las OSM relations
   - Endpoint: `https://overpass-api.de/api/interpreter`
   - Query: `[out:json][timeout:60]; relation(SHAPE_ID); out tags;`
   - Propósito: el `ref` de OSM da el nombre oficial del ramal (ej: "39-1", "39A")
   - Se procesa en lotes de 50 relations para respetar rate limits

### Script de generación

`scripts/shapes/build_line_shapes.js` — copia del script original de proyectoconsola.

**Dependencias:** Node.js, `node-fetch` (o fetch nativo en Node 18+)

**Para regenerar:**
```bash
# Requiere acceso al GTFS de BabusNova
cd prediccion/scripts/shapes/

# Editar GTFS_DIR en el script para apuntar al GTFS local:
# const GTFS_DIR = '../../BabusNova/amba-gtfs/output/AMBA_GTFS_filtered'

node build_line_shapes.js

# Mueve el resultado a data/
mv line_shapes.json ../../data/line_shapes.json
```

**Cuándo regenerar:**
- Cuando OSM actualice los recorridos de las líneas (infrecuente)
- Si se agregan nuevas líneas al sistema
- Si el GTFS de BabusNova se regenera con datos corregidos

### Pipeline interno del script

```
routes.txt ──┐
trips.txt  ──┤──→ filtrar líneas objetivo (39, 42, etc.)
              │         │
              │         ↓
shapes.txt ──┼──→ cargar solo shapes necesarios (lazy load)
              │         │
              │         ↓
Overpass API ─┤──→ obtener tag ref por shape_id
              │         │
stop_times ──┤──→ secuencia de paradas por trip
stops.txt  ──┘         │
                        ↓
                   line_shapes.json
```

## Cómo usa el sistema estas shapes

### En serve.py (runtime)
```bash
# Opción A: archivo local (recomendada, sin dependencias externas)
python prediccion/serve.py \
  --model data/models/a1_v1.pkl \
  --shapes-url prediccion/data/line_shapes.json \
  --fleet-url http://localhost:3000/api/vehiclePositions

# Opción B: desde proyectoconsola (requiere proyectoconsola corriendo)
python prediccion/serve.py \
  --shapes-url http://localhost:3000/api/line-shapes \
  ...
```

### En build_dataset / train.py (entrenamiento)
```bash
python prediccion/train.py --phase 1 \
  --shapes-url prediccion/data/line_shapes.json \
  ...
```

### En ShapeLoader (código)
`prediccion/inference/shape_loader.py` detecta automáticamente si `source`
es una URL (`http://...`) o un path local.

## Agregar nuevas líneas

1. Editar `TARGET_LINES` en `scripts/shapes/build_line_shapes.js`
2. Verificar que la línea exista en el GTFS de BabusNova (`routes.txt`)
3. Regenerar `line_shapes.json`
4. Copiar a `prediccion/data/line_shapes.json`
5. Correr validación: `python prediccion/scripts/validate_projection.py --line NUEVA_LINEA ...`
6. Si pasa la validación, re-entrenar el modelo con `train.py --phase 1`

## Fuente del GTFS de BabusNova

El GTFS de BabusNova se genera a partir de OpenStreetMap con Prism:

```bash
# En BabusNova/amba-gtfs/
./scripts/01_download_osm.sh   # Descarga datos OSM para AMBA
./scripts/02_clip_amba.sh       # Recorta al bounding box de AMBA
./scripts/03_run_prism.sh       # Genera GTFS desde OSM con Prism
```

Prism: https://github.com/Jungle-Bus/prism

**Ventaja sobre GTFS oficial de CABA:** El GTFS oficial está desactualizado.
BabusNova usa OSM que está mantenido por la comunidad y refleja los recorridos reales.
