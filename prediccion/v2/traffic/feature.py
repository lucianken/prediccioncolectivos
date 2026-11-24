"""
Feature de tránsito actual por tramo (ARQUITECTURA.md §11, ítem 1) y tabla densa que la sirve.

CONTRATO PIPELINE / APP (la app todavía NO lo porta; esto es la definición única)
--------------------------------------------------------------------------------
Entrada del modelo por tramo de 250 m del camino que le queda al coche (P -> T), 4 columnas (`TRAFFIC_DIM`), calculadas
sobre la celda de la grilla de ciudad (`CityGridEncoder`, 500 m, id de celda de `grid.cell_index`) que contiene el punto
medio del tramo (el mismo punto medio que usa el embedding de lugar), a partir de la tabla de tránsito.

Tabla de tránsito (cómo se agrega la flota; sin cambios respecto de `data/ml/v2/traffic`, `day.aggregate`):
  - TODA la flota del snapshot (todas las líneas y agencias; protobuf CABA), sin los coches de depósito.
  - Cada par de pings consecutivos del mismo coche con 10 s <= dt <= 150 s da una velocidad por desplazamiento, que se
    asigna a la celda y a la ventana del SEGUNDO ping. Ventana = minuto del día en hora de Buenos Aires (UTC-3) // 2.
    En producción cada snapshot nuevo agrega sus pares contra el snapshot anterior (basta un caché de ~6 min).
  - Por (ventana, celda): n = coches distintos, n_stopped = coches sin ningún intervalo en movimiento (< 1 m/s),
    speed = media de los intervalos en movimiento (NaN si no hay).
  - El tiempo es el `ts` del pipeline (estampado por lote de CABA, ~1/min; NO la hora GPS): el mismo `ts` del ping que
    dispara la consulta (`ts_p` en el parquet, `ts_ping` en la app) y el mismo `ts` de cada ping de la flota.

Causalidad (obligatoria): para una consulta con tiempo t0 = ts del ping de P, w0 = ventana que contiene t0 (floor((t0 - 10800) / 120)).
Solo se usan las ventanas COMPLETAS anteriores: w0 - 1 y w0 - 2 (terminan en o antes de t0). Nunca w0 ni posteriores.

Por tramo, con (s, n, ns) = (velocidad media, coches, coches quietos) de cada una de las dos ventanas en esa celda:
  nm   = n - ns                                   (coches con algún intervalo en movimiento; speed es NaN si nm = 0)
  N    = n(w0-1) + n(w0-2)                        (coches-ventana; un coche puede contar en las dos)
  NS   = ns(w0-1) + ns(w0-2)
  NM   = N - NS
  v    = sum(s * nm) / NM   si NM > 0, si no 0   (media ponderada por coches en movimiento)
Las 4 entradas:
  [0] hay_dato = 1 si N > 0 (algún coche en la celda en esas 4 min), si no 0       <- máscara "sin dato"
  [1] v / 15 m/s, topeado a [0, 2]; 0 si NM = 0 (nadie en movimiento o sin dato)
  [2] log1p(N) / log1p(16), topeado a 1,5; 0 sin dato
  [3] NS / N (fracción de coches quietos); 0 sin dato
Sin dato NO se inventa velocidad: las 4 columnas valen 0 y [0] avisa. Celda fuera de la tabla (no pasa ningún recorrido
de las líneas del modelo) o ventana fuera del rango cargado = sin dato.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

TZ_OFFSET_S = -3 * 3600
WINDOW_S = 120
WINDOWS_PER_DAY = 86400 // WINDOW_S
N_POOLED = 2                      # ventanas completas usadas: w0 - 1 y w0 - 2
TRAFFIC_DIM = 4
SPEED_NORM_MPS = 15.0
N_NORM = math.log1p(16.0)
N_CAP = 255                       # n y n_stopped se guardan en uint8
_DAY0 = 719163                    # date(1970,1,1).toordinal()


def abs_window(ts) -> np.ndarray:
    """Ventana absoluta (int64) que contiene `ts`: día_local * 720 + ventana del día. ts en segundos unix (int/float)."""
    return np.floor_divide(np.asarray(ts, dtype=np.int64) + TZ_OFFSET_S, WINDOW_S)


def last_complete_window(ts) -> np.ndarray:
    """Última ventana absoluta que termina en o antes de `ts` (w0 - 1). Es el ancla causal de la feature."""
    return abs_window(ts) - 1


class TrafficTable:
    """
    Tabla densa (ventanas x celdas) de la zona de interés. `speed` float16 (NaN = nadie en movimiento), `n` y `n_stopped`
    uint8 (0 = sin dato). Fila i = ventana absoluta `w_base + i`; columna j = celda de grilla `cells[j]`.
    """

    def __init__(self, cells, w_base: int, speed, n, n_stopped):
        self.cells = np.asarray(cells, dtype=np.int32)
        self.w_base = int(w_base)
        self.speed = np.asarray(speed, dtype=np.float16)
        self.n = np.asarray(n, dtype=np.uint8)
        self.n_stopped = np.asarray(n_stopped, dtype=np.uint8)
        assert self.speed.shape == self.n.shape == self.n_stopped.shape == (self.speed.shape[0], len(self.cells))

    @property
    def n_windows(self) -> int:
        return self.speed.shape[0]

    def column_of(self, cell_ids) -> np.ndarray:
        """Columna de cada id de celda de grilla (-1 si la celda no está en la tabla)."""
        cell_ids = np.asarray(cell_ids)
        order = np.argsort(self.cells)
        pos = np.searchsorted(self.cells[order], cell_ids)
        pos = np.clip(pos, 0, len(self.cells) - 1)
        hit = self.cells[order][pos] == cell_ids
        return np.where(hit, order[pos], -1).astype(np.int64)

    def sha1(self) -> str:
        h = hashlib.sha1()
        h.update(self.cells.tobytes())
        h.update(str(self.w_base).encode())
        h.update(str(self.speed.shape).encode())
        h.update(np.ascontiguousarray(self.n[:: max(1, self.n_windows // 997)]).tobytes())
        return h.hexdigest()

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as f:
            np.savez_compressed(f, cells=self.cells, w_base=np.int64(self.w_base), speed=self.speed, n=self.n,
                                n_stopped=self.n_stopped)
        tmp.replace(path)

    @classmethod
    def load(cls, path) -> "TrafficTable":
        z = np.load(path)
        return cls(z["cells"], int(z["w_base"]), z["speed"], z["n"], z["n_stopped"])


def pooled_features(speed, n, n_stopped):
    """
    Combina las dos ventanas (último eje = 2) -> (..., TRAFFIC_DIM) float32, según el contrato del módulo.
    speed float (NaN = sin movimiento), n / n_stopped enteros o float, ya con 0 donde no hay dato.
    """
    speed = np.asarray(speed, dtype=np.float32)
    n = np.asarray(n, dtype=np.float32)
    ns = np.asarray(n_stopped, dtype=np.float32)
    nm = np.maximum(n - ns, 0.0)
    s0 = np.where(nm > 0, np.nan_to_num(speed), 0.0)
    N, NS, NM = n.sum(-1), ns.sum(-1), nm.sum(-1)
    v = np.where(NM > 0, (s0 * nm).sum(-1) / np.maximum(NM, 1.0), 0.0)
    has = N > 0
    out = np.stack([has.astype(np.float32),
                    np.where(has, np.clip(v / SPEED_NORM_MPS, 0.0, 2.0), 0.0),
                    np.where(has, np.clip(np.log1p(N) / N_NORM, 0.0, 1.5), 0.0),
                    np.where(has, NS / np.maximum(N, 1.0), 0.0)], axis=-1)
    return out.astype(np.float32)


def traffic_features_np(table: TrafficTable, cell_ids, ts) -> np.ndarray:
    """
    Referencia en numpy del contrato (la que debe replicar la app): (cell_ids, ts) de igual forma -> (..., TRAFFIC_DIM).
    `ts` = ts del ping de P de la consulta; una consulta puede repetirse sobre varios tramos (cell_ids de cada tramo).
    """
    cell_ids = np.asarray(cell_ids)
    ts = np.broadcast_to(np.asarray(ts), cell_ids.shape)
    col = table.column_of(cell_ids)
    w_last = last_complete_window(ts) - table.w_base
    sp = np.zeros(cell_ids.shape + (N_POOLED,), np.float32)
    n = np.zeros_like(sp)
    ns = np.zeros_like(sp)
    for k in range(N_POOLED):
        w = w_last - k
        ok = (col >= 0) & (w >= 0) & (w < table.n_windows)
        wc, cc = np.clip(w, 0, table.n_windows - 1), np.clip(col, 0, len(table.cells) - 1)
        sp[..., k] = np.where(ok, table.speed[wc, cc].astype(np.float32), np.nan)
        n[..., k] = np.where(ok, table.n[wc, cc], 0)
        ns[..., k] = np.where(ok, table.n_stopped[wc, cc], 0)
    return pooled_features(sp, n, ns)


# ── construcción de la tabla densa desde los daily (sparse) de data/ml/v2/traffic ──

def build_dense(daily_dir: Path, first_day: str, last_day: str, cells, grid_n_ids: int) -> tuple[TrafficTable, dict]:
    """Lee `daily/YYYY-MM-DD.parquet` de [first_day, last_day] y arma la tabla densa para las celdas dadas."""
    import datetime as dt
    import pyarrow.parquet as pq
    a, b = dt.date.fromisoformat(first_day), dt.date.fromisoformat(last_day)
    d0 = a.toordinal() - _DAY0
    n_days = (b - a).days + 1
    cells = np.unique(np.asarray(cells, dtype=np.int32))
    col_of = np.full(grid_n_ids, -1, dtype=np.int32)
    col_of[cells] = np.arange(len(cells), dtype=np.int32)
    W = n_days * WINDOWS_PER_DAY
    speed = np.full((W, len(cells)), np.nan, dtype=np.float16)
    n = np.zeros((W, len(cells)), dtype=np.uint8)
    ns = np.zeros((W, len(cells)), dtype=np.uint8)
    present, missing = [], []
    for i in range(n_days):
        day = (a + dt.timedelta(days=i)).isoformat()
        p = Path(daily_dir) / f"{day}.parquet"
        if not p.exists():
            missing.append(day)
            continue
        t = pq.read_table(p).to_pandas()
        c = col_of[t["cell"].to_numpy()]
        sel = c >= 0
        w = i * WINDOWS_PER_DAY + t["window"].to_numpy()[sel].astype(np.int64)
        c = c[sel]
        speed[w, c] = t["speed_mps"].to_numpy()[sel].astype(np.float16)
        n[w, c] = np.minimum(t["n"].to_numpy()[sel], N_CAP).astype(np.uint8)
        ns[w, c] = np.minimum(t["n_stopped"].to_numpy()[sel], N_CAP).astype(np.uint8)
        present.append(day)
    tab = TrafficTable(cells, d0 * WINDOWS_PER_DAY, speed, n, ns)
    return tab, {"days_present": len(present), "days_missing": missing, "n_windows": W, "n_cells": int(len(cells))}


def shape_cells(lines, shapes_dir=None, cell_m: float = 500.0) -> np.ndarray:
    """Ids de celda de grilla que contienen el punto medio de algún tramo de 250 m de los shapes de las líneas."""
    from prediccion.models.path_eta import build_shape_table, load_shape_points
    from prediccion.v2.traffic.grid import cell_index, grid_from_encoder
    ids, lat, lon, _ = build_shape_table(load_shape_points(lines, shapes_dir))
    return np.unique(cell_index(grid_from_encoder(cell_m), lat, lon))


def main(argv=None) -> int:
    from prediccion.v2.traffic.grid import grid_from_encoder
    ap = argparse.ArgumentParser(description="Arma la tabla de tránsito densa (ventanas x celdas) para el modelo por tramos.")
    ap.add_argument("--lines-file", type=Path, default=Path("data/ml/v2c/lines.json"))
    ap.add_argument("--daily-dir", type=Path, default=Path("data/ml/v2/traffic/daily"))
    ap.add_argument("--days", default="2026-07-19:2026-10-14", help="primer:último día (un día antes del primer día de train)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    lf = json.loads(a.lines_file.read_text(encoding="utf-8"))
    lines = sorted({*map(str, lf["train"]), *map(str, lf.get("heldout", []))}, key=int)
    cells = shape_cells(lines)
    d1, d2 = a.days.split(":")
    tab, info = build_dense(a.daily_dir, d1, d2, cells, grid_from_encoder(500.0).n_ids)
    tab.save(a.out)
    print(json.dumps({**info, "sha1": tab.sha1(), "out": str(a.out), "bytes": a.out.stat().st_size}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
