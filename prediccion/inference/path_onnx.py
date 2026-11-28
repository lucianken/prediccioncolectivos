"""
Exportación del modelo por tramos (models/path_eta.py) a ONNX.

El grafo ONNX recibe los tramos YA ARMADOS (lat/lon del punto medio, metros del punto medio, largo, máscara) y el
estado por fila; no contiene la geometría de tramos (build_path_segments), que es aritmética simple y vive en el
cliente (contrato en INFERENCIA_PATH.md; especificación ejecutable en inference/path_reference.py).

Entradas (todas float32 salvo line_idx / dow, int32); B = filas (candidatos de ramal), N = tramos (relleno con máscara 0):
  seg_lat, seg_lon  (B, N)  punto medio del tramo
  seg_mid_m         (B, N)  metros desde el inicio del shape hasta el punto medio de la celda de la grilla
  seg_len           (B, N)  metros del tramo dentro de [d0, d0 + rem]
  seg_mask          (B, N)  1 = tramo válido, 0 = relleno
  line_idx          (B,)    índice de línea (1..n_líneas; 0 = desconocida)
  dow               (B,)    0 = lunes
  h_sin, h_cos      (B,)    hora local BA del ping
  state             (B, n_state - 1)  vector de estado sin la columna reservada (la agrega el grafo)
  seg_stop_n        (B, N)  [solo con stops_feature] paradas con lo <= parada < hi del tramo (ver models/stops.py)
  seg_stop_next     (B, N)  [solo con stops_feature] metros desde lo hasta la próxima parada, tope 1000 m
Salidas: eta (B,), seg_sum (B,), adj (B,) en segundos.
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from prediccion.models.path_eta import SEG_BASE_M, PathETAModel, build_path_segments, stop_features
from red.stops import STOP_NEXT_CAP_M

INPUT_NAMES = ["seg_lat", "seg_lon", "seg_mid_m", "seg_len", "seg_mask", "line_idx", "dow", "h_sin", "h_cos", "state"]
STOP_INPUT_NAMES = ["seg_stop_n", "seg_stop_next"]    # solo con stops_feature: conteo y metros a la próxima parada (tope 1000)
OUTPUT_NAMES = ["eta", "seg_sum", "adj"]


def input_names(model: PathETAModel) -> list[str]:
    return INPUT_NAMES + (STOP_INPUT_NAMES if model.stops_feature else [])


class PathETAOnnx(nn.Module):
    """Mismo cálculo que PathETAModel.forward, con tramos de entrada en vez de (shape, d0, rem)."""

    def __init__(self, m: PathETAModel):
        super().__init__()
        self.m = m

    def forward(self, seg_lat, seg_lon, seg_mid_m, seg_len, seg_mask, line_idx, dow, h_sin, h_cos, state,
                seg_stop_n=None, seg_stop_next=None):
        m = self.m
        B, N = seg_lat.shape[0], seg_lat.shape[1]
        g = m.grid.encode(seg_lat.reshape(-1), seg_lon.reshape(-1))
        le = m.line_emb(line_idx.long())
        time_row = m.time_enc(h_sin.unsqueeze(-1), h_cos.unsqueeze(-1), dow.long().unsqueeze(-1))
        le_n = le.unsqueeze(1).expand(B, N, le.shape[-1]).reshape(B * N, -1)
        tr_n = time_row.unsqueeze(1).expand(B, N, time_row.shape[-1]).reshape(B * N, -1)
        it = m.inter(torch.cat([g, le_n], dim=-1))
        parts = [g, le_n, it, tr_n, (seg_mid_m / 50000.0).reshape(-1, 1), (seg_len / SEG_BASE_M).reshape(-1, 1)]
        if m.stops_feature:
            parts += [seg_stop_n.reshape(-1, 1), (seg_stop_next / STOP_NEXT_CAP_M).reshape(-1, 1)]
        feats = torch.cat(parts, dim=-1)
        slow = F.softplus(m.seg_mlp(feats).squeeze(-1)).reshape(B, N)
        total = (slow * seg_len * seg_mask).sum(dim=1)
        a_in = torch.cat([state, (torch.log1p(total) / 8.0).unsqueeze(-1), time_row], dim=-1)
        adj = m.adj(a_in).squeeze(-1)
        return total + adj, total, adj


def segment_inputs_from_rows(model: PathETAModel, shape_idx, d0, rem) -> dict[str, np.ndarray]:
    """
    Arma, con el código de entrenamiento, las entradas de tramos (B, N) de filas (shape_idx, d0, rem) en tensores.
    Sirve para el chequeo de exportación y para el test de paridad (no es parte del contrato del cliente).
    """
    k, step, length, mask = build_path_segments(d0, rem, model.max_seg)
    mid_m = (k.double() + 0.5) * step.double()[:, None]
    cell = torch.floor(mid_m / SEG_BASE_M).long().clamp(min=0)
    n_cells = (model.shape_off[shape_idx + 1] - model.shape_off[shape_idx])[:, None]
    cell = torch.minimum(cell, n_cells - 1)
    flat = model.shape_off[shape_idx][:, None] + cell
    flat = torch.where(mask, flat, torch.zeros_like(flat))
    f32 = lambda t: t.float().numpy()  # noqa: E731
    out = {
        "seg_lat": f32(torch.where(mask, model.seg_lat[flat], torch.zeros_like(model.seg_lat[flat]))),
        "seg_lon": f32(torch.where(mask, model.seg_lon[flat], torch.zeros_like(model.seg_lon[flat]))),
        "seg_mid_m": f32(torch.where(mask, mid_m, torch.zeros_like(mid_m))),
        "seg_len": f32(length),
        "seg_mask": f32(mask.float()),
    }
    if model.stops_feature:
        d1 = d0.double() + rem.double().clamp(min=0.0)
        lo = torch.maximum(k.double() * step.double()[:, None], d0.double()[:, None])
        hi = torch.minimum((k.double() + 1.0) * step.double()[:, None], d1[:, None])
        sb = shape_idx[:, None].expand_as(k)
        cnt, nxt = stop_features(model.stop_key, sb.reshape(-1), lo.reshape(-1), hi.reshape(-1))
        out["seg_stop_n"] = f32(torch.where(mask, cnt.reshape(k.shape), torch.zeros_like(lo)))
        out["seg_stop_next"] = f32(torch.where(mask, nxt.reshape(k.shape), torch.zeros_like(lo)))
    return out


def export_onnx(model: PathETAModel, path, opset: int = 17) -> None:
    """Exporta con batch (B) y tramos (N) dinámicos."""
    wrapper = PathETAOnnx(model).eval()
    n_in = model.n_state - 1
    B, N = 2, 5
    dummy = (torch.rand(B, N) * 0.1 - 34.6, torch.rand(B, N) * 0.1 - 58.4, torch.rand(B, N) * 5000.0,
             torch.rand(B, N) * 250.0, torch.ones(B, N), torch.tensor([1, 2], dtype=torch.int32),
             torch.tensor([0, 3], dtype=torch.int32), torch.rand(B), torch.rand(B), torch.rand(B, n_in))
    names = input_names(model)
    if model.stops_feature:
        dummy = dummy + (torch.randint(0, 3, (B, N)).float(), torch.rand(B, N) * 1000.0)
    dyn = {n: {0: "B", 1: "N"} for n in INPUT_NAMES[:5] + (STOP_INPUT_NAMES if model.stops_feature else [])}
    dyn.update({n: {0: "B"} for n in INPUT_NAMES[5:]})
    dyn.update({n: {0: "B"} for n in OUTPUT_NAMES})
    with torch.no_grad():
        torch.onnx.export(wrapper, dummy, str(path), input_names=names, output_names=OUTPUT_NAMES,
                          dynamic_axes=dyn, opset_version=opset, dynamo=False)


def run_onnx(session, inputs: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    feed = {k: (v.astype(np.int32) if k in ("line_idx", "dow") else v.astype(np.float32)) for k, v in inputs.items()}
    eta, seg_sum, adj = session.run(OUTPUT_NAMES, feed)
    return eta, seg_sum, adj
