import torch
import torch.nn as nn
from pathlib import Path


class PerVehicleEncoder(nn.Module):
    def __init__(self, input_dim: int = 3, d_model: int = 64, out_dim: int = 128):
        """
        input_dim=3: [dist_norm, speed_mps, dt_s]
        Arquitectura:
        1. Linear(input_dim → d_model)
        2. TransformerEncoder(d_model=64, nhead=4, num_layers=2, dropout=0.1)
           (batch_first=True)
        3. Mean pool sobre seq_len (ignorando padding via src_key_padding_mask)
        4. Linear(d_model → out_dim)
        """
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=4, dropout=0.1, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
        self.output_proj = nn.Linear(d_model, out_dim)
        self.d_model = d_model
        self.out_dim = out_dim

    def forward(
        self,
        x: torch.Tensor,                      # (batch, n_vehicles, seq_len, input_dim)
        src_key_padding_mask: torch.Tensor,    # (batch * n_vehicles, seq_len) — True=padding
    ) -> torch.Tensor:
        """Returns: (batch, n_vehicles, out_dim)"""
        batch, n_v, seq_len, inp_dim = x.shape
        # Reshape a (batch*n_v, seq_len, inp_dim)
        x_flat = x.reshape(batch * n_v, seq_len, inp_dim)
        # Proyectar
        x_proj = self.input_proj(x_flat)  # (batch*n_v, seq_len, d_model)
        # Transformer (sin positional encoding — dt_s captura orden)
        x_enc = self.transformer(x_proj, src_key_padding_mask=src_key_padding_mask)
        # Mean pooling ignorando padding
        # mask: True = padding → poner a 0 antes de mean
        if src_key_padding_mask is not None:
            # src_key_padding_mask: (batch*n_v, seq_len), True=padding
            # Invertir: valid_mask = ~padding, float
            valid_mask = (~src_key_padding_mask).float().unsqueeze(-1)  # (batch*n_v, seq_len, 1)
            x_enc = x_enc * valid_mask
            lengths = valid_mask.sum(dim=1).clamp(min=1)  # (batch*n_v, 1)
            pooled = x_enc.sum(dim=1) / lengths  # (batch*n_v, d_model)
        else:
            pooled = x_enc.mean(dim=1)
        # Output projection
        out = self.output_proj(pooled)  # (batch*n_v, out_dim)
        return out.reshape(batch, n_v, self.out_dim)


class CrossFleetTransformer(nn.Module):
    def __init__(self, d_model: int = 128, nhead: int = 8, num_layers: int = 4):
        """Self-attention entre todos los vehículos de la línea."""
        super().__init__()
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dropout=0.1, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

    def forward(
        self,
        x: torch.Tensor,                   # (batch, n_vehicles, d_model)
        src_key_padding_mask: torch.Tensor, # (batch, n_vehicles) — True=vehículo de padding
    ) -> torch.Tensor:
        """Returns: (batch, n_vehicles, d_model)"""
        return self.transformer(x, src_key_padding_mask=src_key_padding_mask)


class RamalIdModel(nn.Module):
    def __init__(self, n_ramales: int, vehicle_dim: int = 128):
        """
        n_ramales: número de ramales posibles para esta línea.
        """
        super().__init__()
        self.per_vehicle_enc = PerVehicleEncoder(input_dim=3, d_model=64, out_dim=vehicle_dim)
        self.cross_fleet = CrossFleetTransformer(d_model=vehicle_dim, nhead=8, num_layers=4)
        self.classifier = nn.Linear(vehicle_dim, n_ramales)
        self.n_ramales = n_ramales

    def forward(
        self,
        histories: torch.Tensor,        # (batch, n_vehicles, 40, 3)
        history_mask: torch.Tensor,      # (batch, n_vehicles, 40) — True=padding
        vehicle_mask: torch.Tensor,      # (batch, n_vehicles) — True=vehículo de padding
    ) -> torch.Tensor:
        """Returns: (batch, n_vehicles, n_ramales) — logits"""
        batch, n_v, seq_len, _ = histories.shape
        # Aplanar history_mask para PerVehicleEncoder
        hist_mask_flat = history_mask.reshape(batch * n_v, seq_len)
        # Codificar por vehículo
        embeddings = self.per_vehicle_enc(histories, hist_mask_flat)  # (batch, n_v, 128)
        # Cross-fleet attention
        context = self.cross_fleet(embeddings, vehicle_mask)  # (batch, n_v, 128)
        # Clasificar
        logits = self.classifier(context)  # (batch, n_v, n_ramales)
        return logits
