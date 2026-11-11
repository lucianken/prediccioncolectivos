import math

import torch
import torch.nn as nn

# Bounding box AMBA (el mismo que usa inference/fleet_cache.py)
GRID_LAT_MIN, GRID_LAT_MAX = -35.1, -34.3
GRID_LON_MIN, GRID_LON_MAX = -59.1, -57.9
_M_PER_DEG_LAT = 111_320.0


class TrajectoryEncoder(nn.Module):
    def __init__(self, input_dim: int = 3, d_model: int = 64, nhead: int = 4, num_layers: int = 2):
        """Codifica la historia GPS del viaje actual. Longitud variable."""
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dropout=0.1, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.d_model = d_model

    def forward(
        self,
        x: torch.Tensor,                      # (batch, seq_len, 3)
        src_key_padding_mask: torch.Tensor,   # (batch, seq_len) — True=padding
    ) -> torch.Tensor:
        """Returns: (batch, 64) via mean pooling."""
        x_proj = self.input_proj(x)  # (batch, seq, d_model)
        x_enc = self.transformer(x_proj, src_key_padding_mask=src_key_padding_mask)
        # Mean pooling
        valid_mask = (~src_key_padding_mask).float().unsqueeze(-1)  # (batch, seq, 1)
        x_enc = x_enc * valid_mask
        lengths = valid_mask.sum(dim=1).clamp(min=1)  # (batch, 1)
        return x_enc.sum(dim=1) / lengths  # (batch, d_model)


class FleetEncoder(nn.Module):
    def __init__(self, input_dim: int = 5, d_model: int = 64, nhead: int = 4, num_layers: int = 2):
        """
        Codifica el estado de todos los vehículos de la agencia.
        Usa un CLS token prepended.
        Si n_fleet=0: retorna embedding de ceros.
        """
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, d_model))
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dropout=0.1, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.d_model = d_model

    def forward(
        self,
        fleet: torch.Tensor,               # (batch, n_fleet, 5)
        src_key_padding_mask: torch.Tensor, # (batch, n_fleet) — True=padding
    ) -> torch.Tensor:
        """Returns: (batch, 64) via CLS token."""
        batch, n_fleet, _ = fleet.shape

        if n_fleet == 0:
            return torch.zeros(batch, self.d_model, device=fleet.device)

        x_proj = self.input_proj(fleet)  # (batch, n_fleet, d_model)

        # Prepend CLS token
        cls = self.cls_token.expand(batch, -1, -1)  # (batch, 1, d_model)
        x_with_cls = torch.cat([cls, x_proj], dim=1)  # (batch, n_fleet+1, d_model)

        # Extender padding mask para el CLS token (nunca es padding)
        cls_mask = torch.zeros(batch, 1, dtype=torch.bool, device=fleet.device)
        full_mask = torch.cat([cls_mask, src_key_padding_mask], dim=1)  # (batch, n_fleet+1)

        x_enc = self.transformer(x_with_cls, src_key_padding_mask=full_mask)
        # Extraer CLS token output
        return x_enc[:, 0, :]  # (batch, d_model)


class TimeEncoder(nn.Module):
    def __init__(self, dow_embed_dim: int = 4, out_dim: int = 12):
        """
        hour_sin + hour_cos → 2 features continuas
        dow → Embedding(7, dow_embed_dim)
        → Linear(2 + dow_embed_dim → out_dim)
        """
        super().__init__()
        self.dow_embed = nn.Embedding(7, dow_embed_dim)
        self.out_proj = nn.Linear(2 + dow_embed_dim, out_dim)

    def forward(
        self,
        hour_sin: torch.Tensor,  # (batch, 1)
        hour_cos: torch.Tensor,  # (batch, 1)
        dow: torch.Tensor,       # (batch,) int64
    ) -> torch.Tensor:
        """Returns: (batch, out_dim)"""
        dow_emb = self.dow_embed(dow.squeeze(-1))  # (batch,) → (batch, dow_embed_dim)
        combined = torch.cat([hour_sin, hour_cos, dow_emb], dim=-1)  # (batch, 2+dow_embed_dim)
        return self.out_proj(combined)  # (batch, out_dim)


class CityGridEncoder(nn.Module):
    """
    Mapa aprendido de la ciudad: grilla de celdas de ~`cell_m` metros sobre el bbox AMBA, un embedding por vértice
    e interpolación bilineal entre los 4 vértices de la celda que contiene al punto (continuo, sin escalones).
    Entrada: (batch, 4) = [lat_P, lon_P, lat_T, lon_T]. Salida: (batch, 2 * dim): P y T codificados con la
    MISMA grilla y concatenados. Los puntos fuera del bbox se saturan al borde.
    """

    def __init__(self, cell_m: float = 500.0, dim: int = 16):
        super().__init__()
        mid_lat = (GRID_LAT_MIN + GRID_LAT_MAX) / 2.0
        self.n_lat = max(1, math.ceil((GRID_LAT_MAX - GRID_LAT_MIN) * _M_PER_DEG_LAT / cell_m))
        self.n_lon = max(1, math.ceil((GRID_LON_MAX - GRID_LON_MIN) * _M_PER_DEG_LAT
                                      * math.cos(math.radians(mid_lat)) / cell_m))
        self.dim = dim
        self.embed = nn.Embedding((self.n_lat + 1) * (self.n_lon + 1), dim)  # vértices = celdas + 1 por eje
        nn.init.normal_(self.embed.weight, std=0.1)

    @property
    def out_dim(self) -> int:
        return 2 * self.dim

    def encode(self, lat: torch.Tensor, lon: torch.Tensor) -> torch.Tensor:
        """lat, lon: (batch,) -> (batch, dim)."""
        lat = lat.float()
        lon = lon.float()
        u = (lat - GRID_LAT_MIN) / (GRID_LAT_MAX - GRID_LAT_MIN) * self.n_lat
        v = (lon - GRID_LON_MIN) / (GRID_LON_MAX - GRID_LON_MIN) * self.n_lon
        u = u.clamp(0.0, self.n_lat - 1e-4)
        v = v.clamp(0.0, self.n_lon - 1e-4)
        i0 = u.floor().long()
        j0 = v.floor().long()
        fu = (u - i0.float()).unsqueeze(-1)
        fv = (v - j0.float()).unsqueeze(-1)
        w = self.n_lon + 1

        def e(i, j):
            return self.embed(i * w + j)

        return ((1 - fu) * (1 - fv) * e(i0, j0) + (1 - fu) * fv * e(i0, j0 + 1)
                + fu * (1 - fv) * e(i0 + 1, j0) + fu * fv * e(i0 + 1, j0 + 1))

    def forward(self, geo: torch.Tensor) -> torch.Tensor:
        p = self.encode(geo[:, 0], geo[:, 1])
        t = self.encode(geo[:, 2], geo[:, 3])
        return torch.cat([p, t], dim=-1)


class A3ETAModel(nn.Module):
    def __init__(self, d_model: int = 128, hidden_dims: tuple = (256, 128, 64),
                 city_grid: bool = False, grid_cell_m: float = 500.0, grid_dim: int = 16):
        """
        Concatena: trajectory(d_model) + fleet(d_model) + time(16) + dist(1) + time_since_start(1) + ts_age_s(1) + has_bus(1) + schedule_dev_norm(1)
        MLP: Linear(concat_dim → 256) → GELU → Dropout(0.1) → Linear(256 → 128) → GELU → Linear(128 → 64) → GELU → Linear(64 → 1) → Softplus
        """
        super().__init__()
        self.trajectory_enc = TrajectoryEncoder(d_model=d_model, nhead=4, num_layers=3)
        self.fleet_enc = FleetEncoder(d_model=d_model, nhead=4, num_layers=3)
        self.time_enc = TimeEncoder(dow_embed_dim=8, out_dim=16)

        concat_dim = d_model + d_model + 16 + 1 + 1 + 1 + 1 + 1 + 1 + 1  # = 2 * d_model + 23

        # E1c: con city_grid=False no se crea ningún módulo ni parámetro nuevo (los checkpoints viejos cargan igual).
        self.city_grid_enabled = bool(city_grid)
        if city_grid:
            self.city_grid = CityGridEncoder(cell_m=grid_cell_m, dim=grid_dim)
            concat_dim += self.city_grid.out_dim

        layers = []
        in_dim = concat_dim
        for h_dim in hidden_dims:
            layers.extend([
                nn.Linear(in_dim, h_dim),
                nn.GELU(),
                nn.Dropout(0.1),
            ])
            in_dim = h_dim
        layers.append(nn.Linear(in_dim, 1))
        layers.append(nn.Softplus())  # garantiza output positivo

        self.mlp = nn.Sequential(*layers)

    def forward(
        self,
        trajectory: torch.Tensor,             # (batch, seq, 3)
        trajectory_mask: torch.Tensor,        # (batch, seq) — True=padding
        fleet: torch.Tensor,                  # (batch, n_fleet, 5)
        fleet_mask: torch.Tensor,             # (batch, n_fleet) — True=padding
        hour_sin: torch.Tensor,               # (batch, 1)
        hour_cos: torch.Tensor,               # (batch, 1)
        dow: torch.Tensor,                    # (batch,) int64
        dist_remaining_norm: torch.Tensor,    # (batch, 1)
        time_since_start: torch.Tensor,       # (batch, 1)
        ts_age_s: torch.Tensor,               # (batch, 1)
        has_active_bus: torch.Tensor,         # (batch, 1)
        schedule_dev_norm: torch.Tensor,      # (batch, 1)
        time_since_last_bus_s: torch.Tensor,  # (batch, 1) log1p-normalizado
        last_bus_found: torch.Tensor,         # (batch, 1) 0/1
        geo: torch.Tensor | None = None,      # (batch, 4) lat_P, lon_P, lat_T, lon_T — solo con city_grid
    ) -> torch.Tensor:
        """Returns: (batch, 1) — ETA en segundos, siempre positivo (Softplus)."""
        traj_emb = self.trajectory_enc(trajectory, trajectory_mask)  # (batch, d_model)
        fleet_emb = self.fleet_enc(fleet, fleet_mask)                # (batch, d_model)
        time_emb = self.time_enc(hour_sin, hour_cos, dow)            # (batch, 16)

        extra = []
        if self.city_grid_enabled:
            if geo is None:
                raise ValueError("el modelo tiene city_grid activo: falta el tensor `geo` (batch, 4)")
            extra.append(self.city_grid(geo))                         # (batch, 2 * grid_dim)

        combined = torch.cat([
            traj_emb,
            fleet_emb,
            time_emb,
            dist_remaining_norm,
            time_since_start,
            ts_age_s,
            has_active_bus,
            schedule_dev_norm,
            time_since_last_bus_s,
            last_bus_found,
            *extra,
        ], dim=-1)

        return self.mlp(combined)  # (batch, 1)
