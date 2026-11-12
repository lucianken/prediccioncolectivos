"""Velocidad típica en movimiento por (celda, hora, tipo de día) desde la tabla de tránsito, SOLO días de train
(anteriores a la ventana de validación 2026-09-15). Sirve para medir la desviación respecto de lo habitual.
Salida: data/ml/v2/diag/ceiling_typical.npz  (typ [n_ids, 24, 3] float32 con NaN donde no hay dato; tipo de día 0 hábil, 1 sáb, 2 dom)."""
from __future__ import annotations

from datetime import date

import numpy as np
import pyarrow.parquet as pq

from prediccion.v2.diag.ceiling import common as C


def main():
    grid = C.grid_spec()
    num = np.zeros((grid.n_ids, 24, 3)); den = np.zeros((grid.n_ids, 24, 3))
    days = sorted(p.stem for p in (C.TRAFFIC / "daily").glob("*.parquet") if p.stem < "2026-09-15")
    for d in days:
        wd = date.fromisoformat(d).weekday()
        dt = 0 if wd < 5 else (1 if wd == 5 else 2)
        t = pq.read_table(C.TRAFFIC / "daily" / f"{d}.parquet").to_pandas()
        nm = (t.n.to_numpy().astype(np.float64) - t.n_stopped.to_numpy())
        sp = np.nan_to_num(t.speed_mps.to_numpy().astype(np.float64))
        h = (t.window.to_numpy().astype(np.int64) * 2) // 60
        np.add.at(num, (t.cell.to_numpy(), h, dt), sp * nm)
        np.add.at(den, (t.cell.to_numpy(), h, dt), nm)
    typ = np.where(den >= 5, num / np.maximum(den, 1e-9), np.nan).astype(np.float32)
    np.savez_compressed(C.DIAG / "ceiling_typical.npz", typ=typ, den=den.astype(np.float32))
    print(len(days), "días;", float(np.mean(~np.isnan(typ[:, :, 0]))), "fracción (celda,hora) con dato en día hábil")


if __name__ == "__main__":
    main()
