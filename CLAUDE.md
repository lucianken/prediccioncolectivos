# grabador-posiciones

## Qué hace

Graba posiciones de colectivos CABA cada 30s de forma indefinida.
Consume la API de Transporte CABA en protobuf, filtra vehículos dentro
del bounding box CABA/GBA, y persiste el delta en archivos NDJSON + gzip.

Diseñado para correr en la VM Ubuntu del NUC (192.168.0.18) como contenedor Docker.

## Decisiones de diseño

Ver `analisis_grabacion_mensual.md` para la justificación completa. Resumen:
- **Protobuf** para la descarga: 617 KB vs 3.7 MB JSON (6x más chico, 4x más rápido)
- **NDJSON delta + gzip**: ~4.3 GB/mes vs 22.5 GB/mes si se guarda protobuf completo
- **1 call/ciclo** sin filtro de agencia → filtrar localmente por bounds geográficos
- **Omitidos**: bearing, occupancy_status, congestion_level (siempre 0 en la API BA)
- **Keyframe cada 20 ciclos** (10 min) para poder reconstruir estado sin replay largo

## Archivos

```
grabador-posiciones/
├── docker-compose.yml          # Deploy en NUC: restart:always, volume /mnt/buffer/grabaciones
├── .env.example                # Variables necesarias (copiar a .env con credenciales reales)
├── .gitignore                  # Ignora .env y data/
├── analisis_grabacion_mensual.md  # Fuente de todas las decisiones de diseño
├── grabador/
│   ├── Dockerfile              # python:3.11-slim + HEALTHCHECK
│   ├── requirements.txt        # gtfs-realtime-bindings, requests
│   ├── grabador.py             # Loop principal: fetch → parse → delta → write
│   └── delta.py                # compute_delta() y make_keyframe() — testeable por separado
└── data/                       # Ignorado por git, montado desde /mnt/buffer/grabaciones
    ├── YYYY-MM-DD.ndjson.gz    # Un archivo por día (timezone Buenos Aires)
    ├── state.json              # prev_state persistido cada ciclo (para recuperar tras crash)
    └── health                  # Tocado cada ciclo (Docker HEALTHCHECK lo monitorea)
```

## Variables de entorno

El archivo `.env` ya está creado con las credenciales de `proyectoconsola/.env.local`.
Solo incluye las dos variables necesarias (no `CUANDOSUBO_API_KEY` que no se usa acá).

```env
BA_API_CLIENT_ID=...
BA_API_CLIENT_SECRET=...
```

## Cómo ejecutar

### Deploy en NUC (producción)

```bash
# Desde Windows (el .env ya tiene credenciales)
scp -r grabador-posiciones laek@192.168.0.18:~/grabador-posiciones

# En el NUC (192.168.0.18)
mkdir -p /mnt/buffer/grabaciones
cd ~/grabador-posiciones
docker compose up -d --build

# Ver logs
docker compose logs -f
```

### Reinicio tras corte de luz / reinicio del NUC

- `docker-compose.yml` tiene `restart: always`, por lo que el container arranca solo cuando vuelve la energía.
- Si el NUC queda vivo y el volumen `/mnt/buffer/grabaciones` está intacto, el estado persiste en `state.json` y se actualiza normalmente.
- En el arranque, el grabador puede escribir:
  - `gap` event (p.ej. `{"gap":true,"gap_seconds":...,"reason":"restart"}`)
  - keyframe forzado
- Solo necesitarás intervenir manualmente si hay un problema de container:
  - `docker compose ps` (ver estado)
  - `docker compose logs -f` (ver errores)
  - `docker compose up -d --build` (reiniciar manual)

### Monitoreo con stats.py

`stats.py` es el script central de monitoreo. Vive en el NUC en `~/grabador-posiciones/stats.py`
y lee directamente desde `/mnt/buffer/grabaciones`.

**Copiar al NUC** (desde Windows, cuando haya cambios):
```powershell
scp C:\Users\LK\Documents\Dondeestaelbondi\grabador-posiciones\stats.py laek@192.168.0.18:~/grabador-posiciones/stats.py
```

**Correrlo en el NUC:**
```bash
ssh laek@192.168.0.18
cd ~/grabador-posiciones
python3 stats.py             # resumen general
python3 stats.py --detail    # + desglose por día
```

Output incluye: estado del container (health), espacio en disco, días grabados,
promedio/proyección de almacenamiento, y análisis del día actual (ciclos, KF, deltas, gaps).

### Validación diaria rápida

1. Conéctate al NUC (`ssh laek@192.168.0.18`).
2. `cd ~/grabador-posiciones && python3 stats.py`
3. Si hay problema, revisar logs: `docker compose logs --since 5m`

### Test local (Windows, sin Docker)

```bash
cd grabador-posiciones/grabador
pip install -r requirements.txt
# Poner las credenciales como variables de entorno o cargar el .env manualmente
python grabador.py --test 3    # 3 ciclos y sale
```

Los archivos se crean en `/data/` dentro del container. Para tests locales en Windows conviene cambiar `DATA_DIR` en `grabador.py` a un path local temporalmente.

## Formato de salida

### Ciclo normal (delta)
```json
{"t": 1773583230, "new": [], "del": ["5521"], "upd": [{"id": "1839", "ts": 1773583230, "lat": -34.6404, "lon": -58.5522}]}
```

### Keyframe (cada 20 ciclos o tras reinicio)
```json
{"t": 1773583200, "keyframe": true, "new": [{...vehículo completo...}, ...], "del": [], "upd": []}
```

### Registro de gap (escrito antes del keyframe de reinicio)
```json
{"t": 1773590000, "gap": true, "gap_seconds": 3600, "reason": "restart"}
```

### Campos por vehículo
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | str | Vehicle ID numérico |
| label | str | Interno-sufijo (ej: "3124-923") |
| license_plate | str | Patente |
| route_id | str | VP route_id |
| trip_id | str | Trip ID |
| direction_id | int | 0 o 1 |
| start_date | str | "YYYYMMDD" |
| start_time | str | "HH:MM:SS" |
| lat | float | 6 decimales |
| lon | float | 6 decimales |
| speed | float | m/s (de la API) |
| odo | int | Odómetro del viaje (metros) |
| stop_id | str | Parada actual |
| seq | int | Número de secuencia de parada |
| status | int | 0=INCOMING_AT, 1=STOPPED_AT, 2=IN_TRANSIT |
| ts | int | Unix timestamp de la posición |

## Guardrails implementados

| Escenario | Comportamiento |
|-----------|---------------|
| API timeout / error de red | Skip ciclo, no modifica prev_state, reintenta en 30s |
| Error de parseo protobuf | Skip ciclo, loguea primeros 100 bytes para diagnóstico |
| 10+ errores consecutivos | Log CRITICAL pero no crashea (sigue reintentando) |
| Container crash → reinicio | Lee state.json, detecta gap, escribe registro gap + keyframe forzado |
| Disco < 2 GB libre | Para de escribir, loguea CRITICAL, container sigue vivo |
| HEALTHCHECK | Si health no se toca en 2 min → Docker reinicia el container |

## Reconstrucción de estado

Para reconstruir el estado de los vehículos en un momento T dado un archivo `.ndjson.gz`:

```python
import gzip, json

def reconstruct_at(filepath, target_ts):
    state = {}
    with gzip.open(filepath, 'rt') as f:
        for line in f:
            frame = json.loads(line)
            if frame.get('gap') or frame['t'] > target_ts:
                break
            for v in frame.get('new', []):
                state[v['id']] = v.copy()
            for vid in frame.get('del', []):
                state.pop(vid, None)
            for upd in frame.get('upd', []):
                if upd['id'] in state:
                    state[upd['id']].update(upd)
    return state
```

## Almacenamiento y persistencia

Los datos viven en `/mnt/buffer/grabaciones` en la VM Ubuntu — **no se sincronizan a Windows**.
El rsync en `/home/laek/mover_archivos.sh` solo mueve `/mnt/buffer/Peliculas` y `/mnt/buffer/Series`,
por lo que grabaciones queda aislado en el buffer del NUC.

| Período | Tamaño estimado |
|---------|----------------|
| 1 día | ~10-15 MB |
| 1 mes | ~4.3 GB |
| 1 año | ~52 GB |
| ~21 años | ~1.1 TB (límite del buffer) |

Para consumir los datos desde Windows en el futuro hay varias opciones (SMB share, API HTTP sobre
los archivos, rsync manual selectivo, etc.) — a definir cuando haga falta.
