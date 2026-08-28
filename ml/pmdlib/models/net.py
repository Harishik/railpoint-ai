"""1D-CNN stem + Transformer encoder with three heads.

Replaces the 2024 LSTM-AE / RF / DNN / GBM stack. One shared encoder feeds:

* **fault** - 15-way classification,
* **rul** - remaining useful life in cycles,
* **embedding** - the shared representation. Anomaly detection is done *post-hoc*
  on this, by Mahalanobis distance against the normal-event embedding
  distribution, rather than by a third trained head. That catches a fault the
  taxonomy does not contain, instead of forcing every unfamiliar event into one
  of the fifteen known classes - and it needs no extra loss term, so it cannot
  quietly trade away classification accuracy to improve itself.

Sized to train on CPU in minutes: this machine is Intel x86_64, so there is no
CUDA and no MPS, and a model that needs a GPU is a model nobody will reproduce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import Tensor, nn


@dataclass
class NetConfig:
    n_channels: int = 5
    n_scalars: int = 8
    n_classes: int = 15
    d_model: int = 128
    n_heads: int = 4
    n_layers: int = 3
    ff_mult: int = 2
    dropout: float = 0.1
    stem_stride: int = 8  # 512 samples -> 64 tokens


class ConvStem(nn.Module):
    """Downsample the raw capture into tokens the Transformer can afford.

    Attention over 512 raw samples is quadratic and wasteful; the informative
    structure here is local (inrush edge, plateau ripple, indication step), which
    is what convolution is for.
    """

    def __init__(self, cfg: NetConfig):
        super().__init__()
        c = cfg.d_model
        self.net = nn.Sequential(
            nn.Conv1d(cfg.n_channels, c // 2, kernel_size=7, stride=2, padding=3),
            nn.BatchNorm1d(c // 2),
            nn.GELU(),
            nn.Conv1d(c // 2, c, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm1d(c),
            nn.GELU(),
            nn.Conv1d(c, c, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm1d(c),
            nn.GELU(),
        )

    def forward(self, x: Tensor) -> Tensor:  # (B, L, C) -> (B, L/8, d)
        return self.net(x.transpose(1, 2)).transpose(1, 2)


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x: Tensor) -> Tensor:
        return x + self.pe[:, : x.size(1)]


class AttentionPool(nn.Module):
    """Masked attention pooling.

    Mean-pooling over a padded sequence dilutes a short capture with its own
    padding; attention pooling lets the model weight the samples that matter,
    which for a point machine is the inrush edge and the lock transition.
    """

    def __init__(self, d_model: int):
        super().__init__()
        self.score = nn.Linear(d_model, 1)

    def forward(self, x: Tensor, mask: Tensor | None = None) -> Tensor:
        w = self.score(x).squeeze(-1)
        if mask is not None:
            w = w.masked_fill(~mask, float("-inf"))
        w = torch.softmax(w, dim=1).unsqueeze(-1)
        return (x * w).sum(dim=1)


class PointMachineNet(nn.Module):
    def __init__(self, cfg: NetConfig | None = None):
        super().__init__()
        self.cfg = cfg = cfg or NetConfig()
        self.stem = ConvStem(cfg)
        self.pos = PositionalEncoding(cfg.d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=cfg.d_model,
            nhead=cfg.n_heads,
            dim_feedforward=cfg.d_model * cfg.ff_mult,
            dropout=cfg.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=cfg.n_layers)
        self.pool = AttentionPool(cfg.d_model)

        # Scale enters here as an explicit, separate signal rather than being
        # baked into the channels - see models/prep.py for why.
        self.scalar_mlp = nn.Sequential(
            nn.Linear(cfg.n_scalars, 32), nn.GELU(), nn.Linear(32, 32)
        )
        d_joint = cfg.d_model + 32
        self.trunk = nn.Sequential(
            nn.LayerNorm(d_joint), nn.Linear(d_joint, cfg.d_model), nn.GELU(),
            nn.Dropout(cfg.dropout),
        )
        self.head_fault = nn.Linear(cfg.d_model, cfg.n_classes)
        self.head_rul = nn.Linear(cfg.d_model, 1)

    def encode(self, seq: Tensor, scalars: Tensor, mask: Tensor) -> Tensor:
        tokens = self.stem(seq)
        # The stem strides by 8, so the padding mask must be pooled to match.
        tok_mask = mask[:, :: self.cfg.stem_stride][:, : tokens.size(1)]
        if tok_mask.size(1) < tokens.size(1):
            pad = tokens.size(1) - tok_mask.size(1)
            tok_mask = torch.nn.functional.pad(tok_mask, (0, pad), value=False)
        h = self.encoder(self.pos(tokens), src_key_padding_mask=~tok_mask)
        pooled = self.pool(h, tok_mask)
        joint = torch.cat([pooled, self.scalar_mlp(scalars)], dim=-1)
        return self.trunk(joint)

    def forward(self, seq: Tensor, scalars: Tensor, mask: Tensor) -> dict[str, Tensor]:
        z = self.encode(seq, scalars, mask)
        return {
            "fault": self.head_fault(z),
            "rul": self.head_rul(z).squeeze(-1),
            "embedding": z,
        }

    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
