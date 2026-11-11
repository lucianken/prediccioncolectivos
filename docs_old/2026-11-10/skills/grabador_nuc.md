# Grabador de posiciones — referencia completa

## Dónde corre
- NUC 192.168.0.18 (Ubuntu VM), carpeta `~/grabador-posiciones`
- Datos en `/mnt/buffer/grabaciones` — NO se sincronizan a Windows automáticamente
- Docker con `restart: always` — arranca solo tras corte de luz

## Estado
Corriendo desde ~finales de marzo 2026.

## Deploy / actualizar

```bash
# Desde Windows
scp -r grabador-posiciones laek@192.168.0.18:~/grabador-posiciones

# En el NUC
mkdir -p /mnt/buffer/grabaciones
cd ~/grabador-posiciones
docker compose up -d --build
```

## Monitoreo

```bash
ssh laek@192.168.0.18
cd ~/grabador-posiciones
python3 stats.py            # resumen general
python3 stats.py --detail   # + desglose por día
docker compose logs --since 5m
docker compose ps
```

Si hay cambios en `stats.py` local, copiar:
```powershell
scp C:\Users\LK\Documents\Dondeestaelbondi\grabador-posiciones\stats.py laek@192.168.0.18:~/grabador-posiciones/stats.py
```

## Variables de entorno

`.env` ya tiene credenciales de `proyectoconsola/.env.local`:
```
BA_API_CLIENT_ID=...
BA_API_CLIENT_SECRET=...
```

## Formato NDJSON.gz — un archivo por día (TZ Buenos Aires)

**Delta (cada 30s):**
```json
{"t": 1773583230, "new": [], "del": ["5521"], "upd": [{"id": "1839", "ts": 1773583230, "lat": -34.6404, "lon": -58.5522}]}
```

**Keyframe (cada 20 ciclos = ~10 min, o tras reinicio):**
```json
{"t": 1773583200, "keyframe": true, "new": [{...vehículo completo...}], "del": [], "upd": []}
```

**Gap (antes del keyframe de reinicio):**
```json
{"t": 1773590000, "gap": true, "gap_seconds": 3600, "reason": "restart"}
```

## Campos por vehículo

| Campo | Tipo | Notas |
|-------|------|-------|
| id | str | Vehicle ID, permanente |
| label | str | Interno-sufijo ej "3124-923" |
| license_plate | str | Patente |
| route_id | str | Rota cada ~3 semanas |
| trip_id | str | Cambia al inicio de cada viaje |
| direction_id | int | 0 o 1 |
| start_date | str | "YYYYMMDD" |
| start_time | str | "HH:MM:SS" |
| lat, lon | float | 6 decimales |
| speed | float | m/s (promedio del último ciclo de 30s) |
| odo | int | Siempre 0 — descartar |
| stop_id, seq | str/int | Datos obsoletos en la API BA — descartar |
| status | int | 0=INCOMING_AT (nunca ocurre), 1=STOPPED_AT (~1.2%), 2=IN_TRANSIT |
| ts | int | Unix timestamp de la posición |

Omitidos (siempre 0 en la API BA): bearing, occupancy_status, congestion_level.

## Decisiones de diseño

- **Protobuf** para descarga: 617 KB vs 3.7 MB JSON (6x más chico, 4x más rápido)
- **NDJSON delta + gzip**: ~4.3 GB/mes vs 22.5 GB/mes si se guarda protobuf completo
- **1 call/ciclo** sin filtro de agencia → filtrar localmente por bounds geográficos
- **Keyframe cada 20 ciclos** (10 min) para reconstruir estado sin replay largo
- Justificación completa: `prediccion colectivos/analisis_grabacion_mensual.md`

## Guardrails

| Escenario | Comportamiento |
|-----------|---------------|
| API timeout / error de red | Skip ciclo, no modifica prev_state, reintenta en 30s |
| Error de parseo protobuf | Skip ciclo, loguea primeros 100 bytes |
| 10+ errores consecutivos | Log CRITICAL pero sigue reintentando |
| Container crash → reinicio | Lee state.json, detecta gap, escribe gap record + keyframe forzado |
| Disco < 2 GB libre | Para de escribir, loguea CRITICAL, container sigue vivo |
| 20 fetches consecutivos fallidos | `sys.exit(1)` → `restart: always` recrea el container (regenera DNS) |
| HEALTHCHECK | health no tocado en 2 min → Docker marca `unhealthy`. **NO reinicia**: `restart: always` sólo reacciona a que el proceso muera, no al healthcheck. Por eso existe la salida por errores consecutivos |

## Reconstrucción de estado en momento T

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

## Volúmenes

| Período | Tamaño |
|---------|--------|
| 1 día | ~10-15 MB |
| 1 mes | ~4.3 GB |
| 1 año | ~52 GB |
| ~21 años | ~1.1 TB (límite del buffer) |
