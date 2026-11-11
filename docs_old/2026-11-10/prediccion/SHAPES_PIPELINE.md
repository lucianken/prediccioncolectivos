# Shapes y Paradas — Pipeline de Datos Geográficos

## Qué es `data/line_shapes.json`

Archivo estático con las trayectorias y paradas de las líneas objetivo:
**26, 39, 42, 92, 124, 151, 168**

Es la única dependencia geográfica del sistema. No requiere internet en runtime.

## Estructura del archivo

```json
{
  "39": {
    "color": "brown",
    "ramales": [
      {
        "name": "Línea 39 - Ramal 1: Barracas → x Córdoba → Chacarita",
        "shortName": "39A",
        "shapeId": "382202",
        "points": [[-34.5873, -58.3682], ...],
        "stops": [
          { "id": "n454516942", "name": "Terminal Barracas", "lat": -34.649, "lng": -58.367 }
        ]
      }
    ]
  }
}
```

- `points`: `[lat, lon]` — trayectoria completa del ramal en orden
- `stops`: paradas en secuencia, con nombre y coordenadas (nodos OSM `stop_position`)
- `shapeId`: OSM relation ID (o `frac_XXXX` para fraccionados derivados)
- `shortName`: `official_ref` de OSM si existe, sino `ref`

## Fuente de datos

Todo viene directamente de **OpenStreetMap vía Overpass API**. Sin GTFS, sin BabusNova.

El archivo maestro `osm_lines/osm_lines.json` mapea cada línea a sus OSM relation IDs
con todos los tags relevantes (ref, official_ref, name, from, to, operator, etc.).

## Scripts — en `osm_lines/`

### 1. Actualizar el maestro de relaciones OSM

```bash
cd "prediccion colectivos"
python osm_lines/fetch_osm_lines.py             # genera desde cero
python osm_lines/fetch_osm_lines.py --update    # refresca OSM, preserva campos manuales
```

Consulta Overpass por todas las `route=bus` en bbox AMBA y guarda en `osm_lines/osm_lines.json`.

### 2. Regenerar line_shapes.json

```bash
python osm_lines/build_shapes_from_osm.py --lines 26 39 42 92 124 151 168
```

Para líneas específicas:
```bash
python osm_lines/build_shapes_from_osm.py --lines 39
python osm_lines/build_shapes_from_osm.py --lines all   # todas las del maestro
```

Output por defecto: `prediccion/data/line_shapes.json`

### 3. Agregar fraccionados de la línea 39

```bash
python osm_lines/add_fraccionados_39.py
```

Deriva los ramales D/E/F (Chacarita ↔ Plaza Constitución) a partir de A/B/C
truncando geometría y paradas en la parada `Plaza Constitución`.
Es idempotente: limpia fraccionados previos antes de agregar.

## Pipeline completo desde cero

```bash
# 1. Actualizar maestro OSM (solo si cambiaron los recorridos)
python osm_lines/fetch_osm_lines.py

# 2. Regenerar shapes para las 7 líneas
python osm_lines/build_shapes_from_osm.py --lines 26 39 42 92 124 151 168

# 3. Agregar fraccionados del 39
python osm_lines/add_fraccionados_39.py
```

## Cuándo regenerar

- Cuando OSM actualice los recorridos de alguna línea (infrecuente)
- Si se agregan nuevas líneas al sistema (editar `TARGET_LINES` en `build_shapes_from_osm.py`)
- Si se agregan nuevos fraccionados

## Agregar una nueva línea

1. Verificar que la línea esté en `osm_lines/osm_lines.json` (si no, correr `fetch_osm_lines.py`)
2. `python osm_lines/build_shapes_from_osm.py --lines NUEVA`
3. Correr validación: `python prediccion/scripts/validate_projection.py --line NUEVA ...`
