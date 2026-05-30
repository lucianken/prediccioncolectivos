# prediccion-colectivos

Pipeline de ML para predicción de ETA de colectivos CABA/GBA.

Graba posiciones GPS cada 30s → identifica ramal → proyecta sobre shape → predice arribo.

## Arquitectura

```
NUC (192.168.0.18)                    Windows (esta PC)
──────────────────                    ────────────────────────────────
grabador/ (Docker)                    prediccion/pipeline/build_dataset.py
  ↓ cada 30s                            ↓ lee de Z:\grabaciones (SMB)
/mnt/buffer/grabaciones/              data/ml/training/
  YYYY-MM-DD.ndjson.gz    ──SMB──→     eta_train.parquet
                                        eta_val.parquet
                                       ↓
                                     prediccion/train.py  (RTX 3080)
                                       ↓
                                     data/ml/models/
                                       model.pkl
```

## Setup inicial (una vez)

### 1. Samba en el NUC

```bash
ssh laek@192.168.0.18

sudo apt install samba

# Agregar al final de /etc/samba/smb.conf:
# [buffer]
#    path = /mnt/buffer
#    read only = yes
#    valid users = laek

sudo smbpasswd -a laek   # contraseña para el share (independiente de la del sistema)
sudo systemctl restart smbd
```

### 2. Montar el NUC como unidad en Windows

```powershell
net use Z: \\192.168.0.18\buffer /user:laek /persistent:yes
```

Verificar que los datos son accesibles:

```powershell
ls Z:\grabaciones | Select-Object -Last 5
```

### 3. Instalar dependencias Python (Windows)

```bash
cd prediccion
pip install -r requirements-train.txt
```

## Uso

### Generar dataset (leer del NUC, escribir local)

```bash
python -m prediccion.pipeline.build_dataset \
    --data-dir Z:\grabaciones \
    --ml-dir data\ml \
    --lines 26,39,42,92,124,151,168
```

Esto procesa los NDJSON día a día (streaming, bajo uso de RAM) y genera:
- `data/ml/training/eta_train.parquet` — 80% temporal (días más viejos)
- `data/ml/training/eta_val.parquet` — 20% temporal (días más recientes)
- `data/ml/trips/trips_summary.parquet` — metadata de trips

Solo necesitás acceso al NUC para este paso. Una vez generados los Parquet,
el entrenamiento corre completamente local.

### Entrenar (local, RTX 3080)

```bash
python prediccion/train.py --phase 1 --ml-dir data\ml
```

### Correr servidor de predicción

```bash
python prediccion/serve.py \
    --model data\ml\models\a1_v1.pkl \
    --fleet-url http://192.168.0.18:3000/api/vehiclePositions
```

`--shapes-url` es opcional — usa `prediccion/data/line_shapes.json` por defecto.

## Líneas disponibles en shapes

| Línea | Ramales |
|-------|---------|
| 26    | 2       |
| 39    | 2       |
| 42    | 2       |
| 92    | 2       |
| 124   | 2       |
| 151   | 2       |
| 168   | 2       |

Para agregar líneas: ver `prediccion/SHAPES_PIPELINE.md`.

## Estructura

```
grabador/                  # Docker: graba posiciones en el NUC
prediccion/
  pipeline/                # NDJSON → Parquet (build_dataset.py)
  models/                  # A1Baseline, RamalId, A3ETA
  inference/               # Predictor en tiempo real
  api/                     # FastAPI server
  data/
    line_shapes.json       # Shapes de las 7 líneas (578 KB)
  train.py                 # CLI de entrenamiento
  serve.py                 # CLI del servidor
data/                      # Ignorado por git
  ml/
    training/              # Parquet generados por build_dataset
    models/                # Modelos entrenados
```

## Monitoreo del grabador

```bash
ssh laek@192.168.0.18
cd ~/prediccion-colectivos
docker compose logs --tail 20 grabador
python3 stats.py
```
