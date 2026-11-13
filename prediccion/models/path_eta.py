"""
Modelo de ETA por tramos del camino (ARQUITECTURA.md §6.2, paso 6.2.3; sin tránsito y sin flota).

El camino de P (coche) a T (objetivo) sobre el shape se parte en tramos de 250 m alineados a una grilla fija
desde el inicio del shape (el primero y el último son parciales y llevan su fracción de largo). Cada tramo recibe:
  - embedding de lugar (CityGridEncoder interpolado en el punto medio del tramo),
  - embedding de línea + una interacción línea x lugar (MLP chico sobre la concatenación),
  - hora y día, posición del tramo (m desde el inicio del shape) y largo del tramo,
y un MLP da su tiempo: softplus(salida) * largo (s/m positivo por metro).
Aparte, un ajuste global (signo libre) calculado con el estado del coche (velocidad, antigüedad del GPS, detenido,
tiempo de viaje, metros desde el inicio del shape, hace cuánto pasó el coche anterior) se suma al total:

    ETA = sum(tiempo de cada tramo) + ajuste

Tope de tramos (`max_seg`, 160 = 40 km): si el camino lo excede, los tramos de esa fila pasan a un múltiplo de
250 m (más largos) para seguir cubriendo exactamente P->T con la máscara. Para caminos de hasta ~39,5 km los
tramos son siempre de 250 m.

Eficiencia: los puntos medios (lat/lon) de las celdas de 250 m de cada shape se precomputan una vez y viven como
buffers del modelo; los índices de tramos de cada fila salen de (shape, dist_along_m, dist_remaining_m) de forma
vectorizada y solo se evalúa el MLP sobre tramos válidos (sin trabajo en el relleno).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from prediccion.models.a3_eta import CityGridEncoder, TimeEncoder

SEG_BASE_M = 250.0
MAX_SEG = 160
N_STATE = 9            # estado del coche; con start_unknown (v2b) son 10 (ver PathETAModel.n_state)
_LOG1P_3600 = math.log1p(3600.0)


# ── geometría de tramos (pura, testeable) ────────────────────────────────────

def build_path_segments(d0: torch.Tensor, rem: torch.Tensor, max_seg: int = MAX_SEG, base: float = SEG_BASE_M):
    """
    d0: metros desde el inicio del shape hasta P (B,); rem: distancia restante P->T en metros (B,).
    Devuelve (k, step, length, mask), cada uno (B, N) salvo step (B,):
      k       índice de celda de la grilla (celda k cubre [k*step, (k+1)*step])
      step    largo de la celda de cada fila (250 salvo que el camino supere el tope)
      length  metros del tramo dentro de [d0, d0 + rem] (parcial en el primero y el último), 0 donde mask=False
      mask    True = tramo válido (False = relleno)
    N = máximo de tramos del batch (<= max_seg). sum(length, dim=1) == rem.
    """
    d0 = d0.double()
    rem = rem.double().clamp(min=0.0)
    d1 = d0 + rem
    mult = torch.ceil(rem / (base * (max_seg - 2))).clamp(min=1.0)
    step = base * mult
    k0 = torch.floor(d0 / step)
    k1 = torch.clamp(torch.ceil(d1 / step) - 1.0, min=0.0)
    k1 = torch.maximum(k1, k0)
    n = (k1 - k0 + 1.0).long()
    n_max = int(n.max().item()) if n.numel() else 0
    j = torch.arange(n_max, device=d0.device)[None, :]
    mask = j < n[:, None]
    k = k0[:, None] + j
    lo = torch.maximum(k * step[:, None], d0[:, None])
    hi = torch.minimum((k + 1.0) * step[:, None], d1[:, None])
    length = torch.where(mask, (hi - lo).clamp(min=0.0), torch.zeros_like(lo))
    return k.long(), step, length.float(), mask


def shape_cell_midpoints(points, base: float = SEG_BASE_M):
    """(lat, lon) de los puntos medios de las celdas de `base` metros de un shape (la última puede ser parcial)."""
    from prediccion.models.geo import ShapeGeo
    sg = ShapeGeo(points)
    n = max(1, math.ceil(sg.length_m / base))
    mid = np.minimum((np.arange(n) + 0.5) * base, sg.length_m)
    lat, lon = sg.latlon_at(mid)
    return lat.astype(np.float32), lon.astype(np.float32)


def build_shape_table(shape_points: dict[str, list]) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray]:
    """{shape_id: puntos} -> (shape_ids ordenados, lat, lon concatenados, offsets (n_shapes+1))."""
    ids = sorted(shape_points)
    lats, lons, off = [], [], [0]
    for sid in ids:
        la, lo = shape_cell_midpoints(shape_points[sid])
        lats.append(la)
        lons.append(lo)
        off.append(off[-1] + len(la))
    return ids, np.concatenate(lats), np.concatenate(lons), np.asarray(off, dtype=np.int64)


def load_shape_points(lines, shapes_dir=None) -> dict[str, list]:
    """Puntos de todos los shapes de las líneas dadas (solo geometría; solo lectura de line_shapes/)."""
    import json
    from prediccion.v2.shapes import DEFAULT_LINE_SHAPES_DIR
    d = Path(shapes_dir or DEFAULT_LINE_SHAPES_DIR)
    out: dict[str, list] = {}
    for ln in lines:
        p = d / f"{ln}.json"
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("ramales", []):
            sid, pts = r.get("shapeId"), r.get("points", [])
            if sid is None or len(pts) < 2:
                continue
            sid = str(sid)
            if sid in out and len(out[sid]) != len(pts):
                raise ValueError(f"shape_id repetido con distinta geometría: {sid}")
            out[sid] = pts
    return out


# ── modelo ───────────────────────────────────────────────────────────────────

class IndexMaps:
    """shape_id / línea -> índice. Liviano y picklable (lo usan los workers del DataLoader, sin el modelo)."""

    def __init__(self, shape_ids, line_ids, start_unknown: bool = False):
        self.start_unknown = bool(start_unknown)
        self._s = {s: i for i, s in enumerate(shape_ids)}
        self._l = {s: i + 1 for i, s in enumerate(line_ids)}       # 0 = línea desconocida

    def shape_index(self, shape_ids) -> np.ndarray:
        return np.array([self._s.get(str(s), -1) for s in shape_ids], dtype=np.int64)

    def line_index(self, lines) -> np.ndarray:
        return np.array([self._l.get(str(s), 0) for s in lines], dtype=np.int64)


class PathETAModel(nn.Module):
    def __init__(self, shape_ids: list[str], seg_lat, seg_lon, shape_off, line_ids: list[str],
                 max_seg: int = MAX_SEG, grid_dim: int = 16, line_dim: int = 16, hidden: int = 96,
                 grid_cell_m: float = 500.0, start_unknown: bool = False):
        super().__init__()
        self.start_unknown = bool(start_unknown)      # v2b: una entrada más al ajuste global (inicio desconocido 0/1)
        self.n_state = N_STATE + (1 if start_unknown else 0)
        self.shape_ids = list(shape_ids)
        self.line_ids = list(line_ids)             # índice 0 reservado para "línea desconocida"
        self.max_seg = int(max_seg)
        self.cfg = {"max_seg": self.max_seg, "grid_dim": grid_dim, "line_dim": line_dim, "hidden": hidden,
                    "grid_cell_m": grid_cell_m, "start_unknown": self.start_unknown}
        self.register_buffer("seg_lat", torch.as_tensor(np.asarray(seg_lat), dtype=torch.float32))
        self.register_buffer("seg_lon", torch.as_tensor(np.asarray(seg_lon), dtype=torch.float32))
        self.register_buffer("shape_off", torch.as_tensor(np.asarray(shape_off), dtype=torch.long))
        self.grid = CityGridEncoder(cell_m=grid_cell_m, dim=grid_dim)
        self.line_emb = nn.Embedding(len(self.line_ids) + 1, line_dim)
        nn.init.normal_(self.line_emb.weight, std=0.1)
        self.inter = nn.Sequential(nn.Linear(grid_dim + line_dim, 32), nn.GELU(), nn.Linear(32, 16))
        self.time_enc = TimeEncoder(dow_embed_dim=8, out_dim=16)
        seg_in = grid_dim + line_dim + 16 + 16 + 2
        self.seg_mlp = nn.Sequential(nn.Linear(seg_in, hidden), nn.GELU(), nn.Linear(hidden, 64), nn.GELU(),
                                     nn.Linear(64, 1))
        with torch.no_grad():
            self.seg_mlp[-1].bias.fill_(-1.8)        # softplus(-1,8) ~ 0,15 s/m ~ 6,7 m/s al arrancar
        self.adj = nn.Sequential(nn.Linear(self.n_state + 16, 64), nn.GELU(), nn.Linear(64, 32), nn.GELU(), nn.Linear(32, 1))
        with torch.no_grad():
            self.adj[-1].weight.zero_()              # arranca como suma pura de tramos
            self.adj[-1].bias.zero_()

    # índices ---------------------------------------------------------------
    @property
    def maps(self) -> IndexMaps:
        return IndexMaps(self.shape_ids, self.line_ids, self.start_unknown)

    def shape_index(self, shape_ids) -> np.ndarray:
        return self.maps.shape_index(shape_ids)

    def line_index(self, lines) -> np.ndarray:
        return self.maps.line_index(lines)

    def segment_times(self, shape_idx, line_idx, d0, rem, h_sin, h_cos, dow, time_row=None):
        """Tiempo (s) de cada tramo. Devuelve (times (B, N), length (B, N), mask (B, N))."""
        k, step, length, mask = build_path_segments(d0, rem, self.max_seg)
        B, N = mask.shape
        row, col = mask.nonzero(as_tuple=True)
        kk = k[row, col]
        st = step[row]
        mid_m = (kk.double() + 0.5) * st
        cell = torch.floor(mid_m / SEG_BASE_M).long()
        s_idx = shape_idx[row]
        n_cells = self.shape_off[s_idx + 1] - self.shape_off[s_idx]
        cell = torch.minimum(cell.clamp(min=0), n_cells - 1)
        flat = self.shape_off[s_idx] + cell
        g = self.grid.encode(self.seg_lat[flat], self.seg_lon[flat])
        le = self.line_emb(line_idx[row])
        it = self.inter(torch.cat([g, le], dim=-1))
        if time_row is None:
            time_row = self.time_enc(h_sin, h_cos, dow)
        seg_len = length[row, col]
        feats = torch.cat([g, le, it, time_row[row], (mid_m / 50000.0).float()[:, None],
                           (seg_len / SEG_BASE_M)[:, None]], dim=-1)
        slow = F.softplus(self.seg_mlp(feats).squeeze(-1))        # s/m, positivo
        t_valid = slow * seg_len
        times = torch.zeros(B, N, device=mask.device, dtype=t_valid.dtype)
        times[row, col] = t_valid
        return times, length, mask

    def forward(self, shape_idx, line_idx, d0, rem, h_sin, h_cos, dow, state):
        """
        shape_idx (B,) long, line_idx (B,) long, d0/rem (B,) metros, h_sin/h_cos (B,1), dow (B,1) long,
        state (B, N_STATE) float. Devuelve (eta (B,), suma_tramos (B,), ajuste (B,)).
        """
        time_row = self.time_enc(h_sin, h_cos, dow)
        times, _, _ = self.segment_times(shape_idx, line_idx, d0, rem, h_sin, h_cos, dow, time_row)
        total = times.sum(dim=1)
        a_in = torch.cat([state, time_row], dim=-1)
        # el término de tramos entra al ajuste como escala (log), para que pueda hablar de proporciones
        n = self.n_state
        a_in = torch.cat([a_in[:, :n - 1], (torch.log1p(total.detach()) / 8.0)[:, None], a_in[:, n:]], dim=-1)
        adj = self.adj(a_in).squeeze(-1)
        return total + adj, total, adj

    # checkpoints ---------------------------------------------------------------
    def checkpoint_dict(self) -> dict:
        return {"model_state_dict": self.state_dict(), "shape_ids": self.shape_ids, "line_ids": self.line_ids,
                "cfg": self.cfg, "n_seg_total": int(self.seg_lat.numel())}

    @classmethod
    def from_checkpoint(cls, ckpt: dict) -> "PathETAModel":
        sd = ckpt["model_state_dict"]
        m = cls(ckpt["shape_ids"], sd["seg_lat"], sd["seg_lon"], sd["shape_off"], ckpt["line_ids"], **ckpt["cfg"])
        m.load_state_dict(sd)
        return m


# ── datos ────────────────────────────────────────────────────────────────────

PATH_COLS = ["line", "shape_id", "dist_along_m", "dist_remaining_m", "dist_along_norm", "speed_mps", "hour_sin",
             "hour_cos", "dow", "observed_eta_s", "time_since_start", "ts_age_s", "time_since_last_bus_s",
             "last_bus_found"]
STOPPED_MPS = 0.5
OPTIONAL_COLS = ["start_unknown"]      # v2b; si el parquet no la trae, start_unknown = 0 (o NaN en time_since_start)


def read_cols(parquet_path) -> list[str]:
    import pyarrow.parquet as pq
    names = set(pq.ParquetFile(str(parquet_path)).schema_arrow.names)
    return PATH_COLS + [c for c in OPTIONAL_COLS if c in names]


def state_features(speed, ts_age, tss, d0, tlb, lbf, rem, start_unknown=None) -> np.ndarray:
    """(N, N_STATE): velocidad, detenido, antigüedad GPS, tiempo de viaje, m desde inicio, hace cuánto el anterior
    (+ encontrado), distancia restante; la columna N_STATE-1 la reserva el modelo para la escala de la suma. Con `start_unknown`
    (array 0/1) se agrega esa entrada antes de la reservada: (N, N_STATE + 1). time_since_start NaN cuenta como 0."""
    speed = np.nan_to_num(np.asarray(speed, np.float32))
    cols = [
        np.clip(speed / 30.0, 0.0, 2.0),
        (speed < STOPPED_MPS).astype(np.float32),
        np.clip(np.nan_to_num(np.asarray(ts_age, np.float32)) / 600.0, 0.0, 1.5),
        np.clip(np.nan_to_num(np.asarray(tss, np.float32)) / 3600.0, 0.0, 4.0),
        np.clip(np.asarray(d0, np.float32) / 50000.0, 0.0, 2.0),
        np.log1p(np.clip(np.nan_to_num(np.asarray(tlb, np.float32)), 0.0, 3600.0)) / _LOG1P_3600,
        np.nan_to_num(np.asarray(lbf, np.float32)),
        np.log1p(np.clip(np.asarray(rem, np.float32), 0.0, 80000.0)) / math.log1p(80000.0),
    ]
    if start_unknown is not None:
        cols.append(np.asarray(start_unknown, np.float32))
    cols.append(np.zeros(len(speed), np.float32))
    return np.stack(cols, axis=1).astype(np.float32)


def table_to_batch(df: dict, model: "PathETAModel | IndexMaps", max_eta_s: float = 7200.0, train: bool = False,
                   unk_line_p: float = 0.0) -> tuple[dict, np.ndarray]:
    """
    df: dict de columnas (numpy / listas) de PATH_COLS. Aplica el mismo filtro que ETADataset
    (eta > 0, dist_remaining >= 100 m, dist_along_norm en [0,1]) y además descarta shapes fuera de la tabla.
    Devuelve (tensores en CPU, índices de filas válidas).
    """
    eta = np.asarray(df["observed_eta_s"], np.float32)
    rem = np.asarray(df["dist_remaining_m"], np.float32)
    norm = np.asarray(df["dist_along_norm"], np.float32)
    sidx = model.shape_index(df["shape_id"])
    ok = (eta > 0) & (rem >= 100.0) & (norm >= 0) & (norm <= 1.0) & (sidx >= 0)
    v = np.where(ok)[0]
    d0 = np.asarray(df["dist_along_m"], np.float32)[v]
    lidx = model.line_index(np.asarray(df["line"], dtype=object)[v])
    if train and unk_line_p > 0:
        lidx = np.where(np.random.random(len(lidx)) < unk_line_p, 0, lidx)
    tss = np.asarray(df["time_since_start"], np.float32)[v]
    su = None
    if getattr(model, "start_unknown", False):
        su = np.isnan(tss)
        if "start_unknown" in df:
            su = su | np.asarray(df["start_unknown"]).astype(bool)[v]
    state = state_features(np.asarray(df["speed_mps"])[v], np.asarray(df["ts_age_s"])[v],
                           tss, d0, np.asarray(df["time_since_last_bus_s"])[v],
                           np.asarray(df["last_bus_found"])[v], rem[v], su)
    batch = {
        "shape_idx": torch.from_numpy(sidx[v]), "line_idx": torch.from_numpy(lidx),
        "d0": torch.from_numpy(d0), "rem": torch.from_numpy(rem[v]),
        "h_sin": torch.from_numpy(np.asarray(df["hour_sin"], np.float32)[v, None]),
        "h_cos": torch.from_numpy(np.asarray(df["hour_cos"], np.float32)[v, None]),
        "dow": torch.from_numpy(np.asarray(df["dow"]).astype(np.int64)[v, None]),
        "state": torch.from_numpy(state),
        "eta": torch.from_numpy(np.clip(eta[v], 1.0, max_eta_s)[:, None]),
    }
    return batch, v


def run_model(model: PathETAModel, batch: dict, device) -> torch.Tensor:
    g = lambda k: batch[k].to(device)  # noqa: E731
    return model(g("shape_idx"), g("line_idx"), g("d0"), g("rem"), g("h_sin"), g("h_cos"), g("dow"), g("state"))[0]


class PathETADataset(torch.utils.data.IterableDataset):
    """Lee el parquet de a un row group y emite batches ya armados (como ETADataset); batch_size=1 en el DataLoader."""

    def __init__(self, parquet_path, model: IndexMaps, batch_size: int = 1024, shuffle: bool = True,
                 max_groups: int | None = None, unk_line_p: float = 0.0):
        import pyarrow.parquet as pq
        self.path = str(parquet_path)
        self.model = model
        self.bs = batch_size
        self.shuffle = shuffle
        self.unk_line_p = unk_line_p
        self.cols = read_cols(self.path)
        pf = pq.ParquetFile(self.path)
        total = pf.metadata.num_row_groups
        self.n_groups = min(total, max_groups) if max_groups else total
        self.approx_len = sum(pf.metadata.row_group(i).num_rows for i in range(self.n_groups))
        # cota superior de batches por epoch (cada row group emite ceil(filas / batch))
        self.n_batches = sum(-(-pf.metadata.row_group(i).num_rows // batch_size) for i in range(self.n_groups))

    def __len__(self):
        return self.n_batches

    def __iter__(self):
        import pyarrow.parquet as pq
        wi = torch.utils.data.get_worker_info()
        groups = list(range(self.n_groups))
        if wi is not None:
            groups = groups[wi.id::wi.num_workers]
        if self.shuffle:
            np.random.shuffle(groups)
        pf = pq.ParquetFile(self.path)
        for g in groups:
            tbl = pf.read_row_group(g, columns=self.cols)
            df = {c: (tbl[c].to_pylist() if c in ("line", "shape_id") else np.asarray(tbl[c])) for c in self.cols}
            batch, v = table_to_batch(df, self.model, train=self.shuffle, unk_line_p=self.unk_line_p)
            n = len(v)
            order = np.random.permutation(n) if self.shuffle else np.arange(n)
            for s in range(0, n, self.bs):
                sl = torch.from_numpy(order[s:s + self.bs])
                yield {k: t[sl] for k, t in batch.items()}


BAND_Q = 0.30           # pinball_band: cuantil dentro de la banda (llegar antes de lo anunciado pesa 0,7 / 0,3 = 2,3x)
BAND_RAMP_M = 300.0     # pinball_band: rampa lineal hasta q = 0,5 fuera de cada borde


def band_calibration(dist_m, eta_s, eta_lo_s: float = 180.0, eta_hi_s: float = 600.0) -> tuple[float, float]:
    """(d_lo, d_hi) en metros: percentiles p10 y p90 de la distancia restante de las filas con ETA real en [eta_lo, eta_hi]."""
    dist_m = np.asarray(dist_m, np.float64)
    eta_s = np.asarray(eta_s, np.float64)
    sel = dist_m[(eta_s >= eta_lo_s) & (eta_s <= eta_hi_s)]
    if sel.size == 0:
        raise ValueError("sin filas con ETA real en la franja de calibración")
    lo, hi = np.percentile(sel, [10, 90])
    return float(round(lo)), float(round(hi))


def band_quantile(dist_m: torch.Tensor, d_lo: float, d_hi: float, q: float = BAND_Q, ramp_m: float = BAND_RAMP_M) -> torch.Tensor:
    """q(distancia restante): `q` dentro de [d_lo, d_hi]; rampa lineal a 0,5 en los `ramp_m` metros afuera de cada borde; 0,5 en el resto."""
    out = torch.clamp(torch.minimum(dist_m - (d_lo - ramp_m), (d_hi + ramp_m) - dist_m) / ramp_m, 0.0, 1.0)
    return 0.5 - (0.5 - q) * out


def pinball(pred: torch.Tensor, target: torch.Tensor, dist_m: torch.Tensor, loss: str = "pinball",
            band: tuple[float, float] | None = None) -> torch.Tensor:
    """Misma pérdida que el A3 (trainer.train_phase3): q 0,5 -> 0,8 por debajo de 1 km.
    loss="l1": q = 0,5 a toda distancia (mediana; llegar antes o después de lo anunciado pesa igual).
    loss="pinball_band": q = 0,3 en la banda de distancia `band` = (d_lo, d_hi), rampa a 0,5 (ver band_quantile).
    q depende solo de la distancia restante (entrada del modelo), nunca de la ETA real."""
    if loss == "l1":
        q = torch.full_like(dist_m, 0.5)
    elif loss == "pinball":
        q = 0.5 + 0.3 * torch.clamp(1.0 - dist_m / 1000.0, 0.0, 1.0)
    elif loss == "pinball_inv":
        # q 0,5 -> 0,2 bajo 1 km: con err = real - pred, anunciar tarde (llega antes de lo anunciado) pesa 4x más
        q = 0.5 - 0.3 * torch.clamp(1.0 - dist_m / 1000.0, 0.0, 1.0)
    elif loss == "pinball_band":
        if band is None:
            raise ValueError("pinball_band necesita band=(d_lo, d_hi)")
        q = band_quantile(dist_m, band[0], band[1])
    else:
        raise ValueError(f"loss inválida: {loss!r} (l1 | pinball | pinball_inv | pinball_band)")
    err = target - pred
    return torch.where(err >= 0, q * err, (q - 1.0) * err).mean()


def predict_path(parquet_path, ckpt_path, n_expected: int, batch_size: int = 8192, device: str | None = None) -> np.ndarray:
    """Predice (en segundos, >= 0) sobre un parquet de eval; verifica que no se descarte ninguna fila."""
    import pyarrow.parquet as pq
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    model = PathETAModel.from_checkpoint(ckpt).to(device).eval()
    cols = read_cols(parquet_path)
    tbl = pq.read_table(parquet_path, columns=cols)
    df = {c: (tbl[c].to_pylist() if c in ("line", "shape_id") else np.asarray(tbl[c])) for c in cols}
    batch, v = table_to_batch(df, model)
    if len(v) != n_expected:
        raise RuntimeError(f"path_eta predijo {len(v)} filas pero el eval tiene {n_expected}")
    out = []
    with torch.no_grad():
        for s in range(0, len(v), batch_size):
            b = {k: t[s:s + batch_size] for k, t in batch.items()}
            out.append(run_model(model, b, device).clamp(min=0.0).float().cpu().numpy())
    return np.concatenate(out).astype(np.float64) if out else np.empty(0)
