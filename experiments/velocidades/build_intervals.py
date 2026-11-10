"""
Convierte los tracks crudos en INTERVALOS entre muestras consecutivas del mismo
viaje, con la distancia recorrida medida por tres métodos independientes:

  dist_hav_m    cuerda haversine entre las dos posiciones   (SIN recorrido)
  dist_odo_m    delta del odómetro reportado por la API     (SIN recorrido)
  dist_shape_m  delta de la progresión sobre la polilínea   (CON recorrido)

El objetivo de tener los tres es poder validar los métodos "sin recorrido"
contra el método "con recorrido" en las líneas donde sí tenemos el shape, y
después aplicar el método sin recorrido al resto del país.

Uso:
    python -m experiments.velocidades.build_intervals \
        --tracks experiments/velocidades/out/tracks.parquet \
        --out    experiments/velocidades/out/intervals.parquet
"""

import argparse
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from prediccion.pipeline.projector import ShapeIndex

SHAPES_PATH = Path("prediccion/data/line_shapes.json")

# El grabador cicla cada ~60 s. Aceptamos 45–90 s: fuera de esa ventana el
# intervalo cubre un hueco (vehículo desaparecido y reaparecido) y la
# velocidad media deja de ser interpretable.
DT_MIN_S, DT_MAX_S = 45, 90

# Un colectivo urbano no supera esto; por encima es salto de GPS.
MAX_PLAUSIBLE_MS = 30.0

# Error perpendicular máximo para aceptar la proyección sobre el shape.
MAX_PERP_M = 120.0

# Delta de odómetro implausible (reset del contador, o unidades raras).
MAX_ODO_DELTA_M = 3000.0

# Tramo de autopista Cantilo / Lugones, donde el límite de velocidad no es el
# urbano. bbox grosero, solo para poder reportar la línea 42 con y sin él.
AUTOPISTA_BBOX = (-34.560, -34.535, -58.470, -58.415)  # lat_min, lat_max, lon_min, lon_max


@lru_cache(maxsize=2)
def load_line_shapes(path: Path) -> dict[str, list[tuple[str, ShapeIndex]]]:
    """{line: [(nombre_ramal, ShapeIndex), ...]} para todos los ramales/sentidos."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out: dict[str, list[tuple[str, ShapeIndex]]] = {}
    for line, entry in raw.items():
        idx = []
        for i, ramal in enumerate(entry.get("ramales", [])):
            pts = [tuple(p) for p in ramal["points"]]
            if len(pts) < 2:
                continue
            name = f"{ramal.get('shortName', line)}#{i}"
            idx.append((name, ShapeIndex(pts)))
        if idx:
            out[line] = idx
    return out


def assign_shapes(df: pd.DataFrame, shapes: dict) -> pd.DataFrame:
    """
    Asigna a cada viaje el ramal+sentido que mejor lo explica.

    No usamos route_id: el mapeo route_id→ramal rota cada pocas semanas y acá
    solo necesitamos geometría. El criterio es el error perpendicular medio
    sobre una muestra de puntos del viaje, que separa limpio los ramales porque
    difieren en tramos largos (Córdoba vs Colegiales vs Plaza Serrano).

    Agrega columnas `shape_name`, `dist_along_m`, `perp_m`.
    """
    df = df.copy()
    df["shape_name"] = pd.NA
    df["dist_along_m"] = np.nan
    df["perp_m"] = np.nan

    for (line, trip_key), grp in df.groupby(["line", "trip_key"], sort=False):
        cands = shapes.get(line)
        if not cands:
            continue
        lats = grp.lat.to_numpy()
        lons = grp.lon.to_numpy()

        # Muestra de hasta 25 puntos para elegir el ramal — barato y estable.
        step = max(1, len(lats) // 25)
        s_lat, s_lon = lats[::step], lons[::step]

        best_name, best_idx, best_err = None, None, np.inf
        for name, idx in cands:
            _, perp = idx.project_many(s_lat, s_lon)
            err = float(np.median(perp))
            if err < best_err:
                best_name, best_idx, best_err = name, idx, err

        dist, perp = best_idx.project_many(lats, lons)
        df.loc[grp.index, "shape_name"] = best_name
        df.loc[grp.index, "dist_along_m"] = dist
        df.loc[grp.index, "perp_m"] = perp

    return df


def haversine_np(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def build(tracks: Path, out: Path) -> pd.DataFrame:
    iv = build_from_frame(pd.read_parquet(tracks))
    out.parent.mkdir(parents=True, exist_ok=True)
    iv.to_parquet(out, index=False)
    return iv


def build_from_frame(df: pd.DataFrame, require_trip_id: bool = True) -> pd.DataFrame:
    """
    Núcleo de `build`, sobre un DataFrame ya cargado. Separado para que
    run_month.py pueda encadenar extracción → intervalos día por día sin
    materializar el parquet de posiciones de todo el mes.

    require_trip_id=True descarta las muestras sin `trip_id`: en general son
    movimientos a/desde garage y giradas de cabecera, que inflan las
    velocidades con tramos sin pasajeros. Pero hay operadores que directamente
    no publican viajes — las líneas 4 y 25 reportan 0 % de `trip_id` — y el
    filtro las borra enteras. Con False el intervalo sólo exige continuidad del
    mismo vehículo; las métricas por viaje quedan sin sentido, las de velocidad
    no.
    """
    if require_trip_id:
        df = df[df.trip_id.notna() & (df.trip_id != "")].copy()
    else:
        df = df.copy()

    # Clave de viaje: un trip_id se reutiliza entre días y entre vehículos.
    df["trip_key"] = (
        df.vid + "|" + df.trip_id.fillna("") + "|"
        + df.start_date.fillna("") + "|" + df.start_time.fillna("")
    )

    df = df.sort_values(["trip_key", "ts"]).reset_index(drop=True)
    df = assign_shapes(df, load_line_shapes(SHAPES_PATH))

    g = df.groupby("trip_key", sort=False)
    prev = {c: g[c].shift(1) for c in ("ts", "lat", "lon", "odo", "dist_along_m", "perp_m", "speed_api")}

    iv = pd.DataFrame(
        {
            "line": df.line,
            "date": df.date,
            "vid": df.vid,
            "trip_key": df.trip_key,
            "shape_name": df.shape_name,
            "ts0": prev["ts"],
            "ts1": df.ts,
            "dt_s": df.ts - prev["ts"],
            "lat": df.lat,
            "lon": df.lon,
            # Velocidad puntual reportada por la API en el instante de la muestra.
            # Es una lectura spot, no un promedio del intervalo: la usamos para
            # la exposición (¿cuánto tiempo por encima de X?), no para distancia.
            "speed_api_ms": df.speed_api,
            "speed_api_prev_ms": prev["speed_api"],
            "after_gap": df.after_gap,
            "dist_hav_m": haversine_np(prev["lat"], prev["lon"], df.lat, df.lon),
            "dist_odo_m": df.odo - prev["odo"],
            "dist_shape_m": (df.dist_along_m - prev["dist_along_m"]).abs(),
            "perp_m": np.maximum(df.perp_m, prev["perp_m"]),
        }
    )

    iv = iv[iv.dt_s.between(DT_MIN_S, DT_MAX_S) & ~iv.after_gap].copy()

    # Validez por método. Un intervalo puede ser válido para uno e inválido
    # para otro; cada métrica se calcula sobre su propio subconjunto.
    iv["ok_hav"] = iv.dist_hav_m / iv.dt_s <= MAX_PLAUSIBLE_MS
    iv["ok_odo"] = iv.dist_odo_m.between(0, MAX_ODO_DELTA_M) & (
        iv.dist_odo_m / iv.dt_s <= MAX_PLAUSIBLE_MS
    )
    iv["ok_shape"] = (
        (iv.perp_m <= MAX_PERP_M)
        & iv.dist_shape_m.notna()
        & (iv.dist_shape_m / iv.dt_s <= MAX_PLAUSIBLE_MS)
    )

    la0, la1, lo0, lo1 = AUTOPISTA_BBOX
    iv["autopista"] = iv.lat.between(la0, la1) & iv.lon.between(lo0, lo1)

    hh = pd.to_datetime(iv.ts1, unit="s", utc=True).dt.tz_convert("America/Argentina/Buenos_Aires")
    iv["hour"] = hh.dt.hour
    iv["dow"] = hh.dt.dayofweek
    iv["is_weekday"] = iv.dow < 5
    return iv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    iv = build(args.tracks, args.out)
    print(f"{len(iv)} intervalos -> {args.out}")
    print(iv.groupby("line")[["ok_hav", "ok_odo", "ok_shape"]].mean().round(3).to_string())
    print("\nramales asignados:")
    print(iv.groupby(["line", "shape_name"]).size().to_string())


if __name__ == "__main__":
    main()
