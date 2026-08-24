"""Train the shared encoder on fault classification and remaining useful life.

Both datasets feed one model. The stratified sweep supplies balanced class labels
but has no service history, so it carries no RUL target; the fleet supplies RUL
but its class distribution reflects real (rare) failure prevalence. Each sample
therefore contributes to whichever heads it actually has labels for, and the RUL
loss is masked everywhere else.

Splits come from ``pmdlib.data.machine_split`` so the two datasets cannot
disagree about which machines are held out.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import Tensor, nn
from torch.utils.data import DataLoader, TensorDataset

from ..data import Dataset, load
from ..models.net import NetConfig, PointMachineNet
from ..models.prep import prepare

#: RUL is regressed in log space: the difference between 5 and 20 cycles matters
#: far more than between 500 and 515, and a linear target says otherwise.
RUL_LOG_SCALE = True
#: Censored samples - no failure ahead of them - carry rul == -1 and are excluded
#: from the RUL loss rather than being treated as "fails immediately".
CENSORED = -1


@dataclass
class TrainConfig:
    epochs: int = 40
    batch_size: int = 128
    lr: float = 3e-4
    weight_decay: float = 0.01
    rul_weight: float = 0.3
    patience: int = 8
    seed: int = 42
    net: NetConfig = field(default_factory=NetConfig)


def _to_tensors(ds: Dataset) -> tuple[Tensor, ...]:
    seq, scalars, mask = prepare(ds.signals, ds.lengths)
    y = ds.y
    rul = (
        ds.meta.rul.to_numpy(np.float32)
        if "rul" in ds.meta.columns
        else np.full(len(ds), CENSORED, np.float32)
    )
    return (
        torch.from_numpy(seq),
        torch.from_numpy(scalars),
        torch.from_numpy(mask),
        torch.from_numpy(y),
        torch.from_numpy(rul.astype(np.float32)),
    )


def _concat(parts: list[tuple[Tensor, ...]]) -> TensorDataset:
    return TensorDataset(*[torch.cat([p[i] for p in parts]) for i in range(5)])


def build_datasets(split: str) -> TensorDataset:
    parts = [_to_tensors(load(name).split(split)) for name in ("stratified", "fleet")]
    return _concat(parts)


def rul_target(rul: Tensor) -> Tensor:
    return torch.log1p(rul.clamp(min=0)) if RUL_LOG_SCALE else rul.clamp(min=0)


def rul_invert(pred: Tensor) -> Tensor:
    return torch.expm1(pred).clamp(min=0) if RUL_LOG_SCALE else pred.clamp(min=0)


def train(cfg: TrainConfig | None = None, verbose: bool = True) -> tuple[PointMachineNet, dict]:
    cfg = cfg or TrainConfig()
    torch.manual_seed(cfg.seed)
    # torch owns all sampling in this loop (shuffling, dropout, init); numpy is
    # only used for metrics here, so its global seed is deliberately not set.

    train_ds = build_datasets("train")
    val_ds = build_datasets("val")

    y_train = train_ds.tensors[3].numpy()
    counts = np.bincount(y_train, minlength=cfg.net.n_classes).astype(np.float64)
    # The fleet's class distribution is deliberately realistic, so the combined
    # set is imbalanced even though the sweep is balanced. Inverse-frequency
    # weighting keeps the rare shock faults from being ignored.
    weights = np.where(counts > 0, counts.sum() / np.maximum(counts, 1), 0.0)
    weights = weights / weights[weights > 0].mean()

    model = PointMachineNet(cfg.net)
    ce = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32))
    huber = nn.HuberLoss(reduction="none")
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=cfg.lr, total_steps=cfg.epochs * max(1, len(train_ds) // cfg.batch_size + 1)
    )

    train_dl = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, drop_last=False)
    val_dl = DataLoader(val_ds, batch_size=256)

    history: list[dict] = []
    best = {"macro_f1": -1.0, "epoch": -1, "state": None}

    for epoch in range(cfg.epochs):
        model.train()
        t0 = time.time()
        totals = {"loss": 0.0, "ce": 0.0, "rul": 0.0, "n": 0}
        for seq, scalars, mask, y, rul in train_dl:
            opt.zero_grad(set_to_none=True)
            out = model(seq, scalars, mask)
            loss_ce = ce(out["fault"], y)

            has_rul = rul > CENSORED
            if has_rul.any():
                per = huber(out["rul"][has_rul], rul_target(rul[has_rul]))
                loss_rul = per.mean()
            else:
                loss_rul = torch.zeros((), dtype=torch.float32)

            loss = loss_ce + cfg.rul_weight * loss_rul
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()

            bs = y.size(0)
            totals["loss"] += float(loss) * bs
            totals["ce"] += float(loss_ce) * bs
            totals["rul"] += float(loss_rul) * bs
            totals["n"] += bs

        model.eval()
        preds, trues, rul_err = [], [], []
        with torch.no_grad():
            for seq, scalars, mask, y, rul in val_dl:
                out = model(seq, scalars, mask)
                preds.append(out["fault"].argmax(1).numpy())
                trues.append(y.numpy())
                has_rul = rul > CENSORED
                if has_rul.any():
                    pred_cycles = rul_invert(out["rul"][has_rul])
                    rul_err.append((pred_cycles - rul[has_rul]).numpy())
        preds, trues = np.concatenate(preds), np.concatenate(trues)
        macro_f1 = float(f1_score(trues, preds, average="macro", zero_division=0))
        acc = float((preds == trues).mean())
        rmse = float(np.sqrt(np.mean(np.concatenate(rul_err) ** 2))) if rul_err else float("nan")

        history.append(
            {
                "epoch": epoch, "loss": totals["loss"] / totals["n"],
                "ce": totals["ce"] / totals["n"], "rul": totals["rul"] / totals["n"],
                "val_acc": acc, "val_macro_f1": macro_f1, "val_rul_rmse": rmse,
                "sec": round(time.time() - t0, 1),
            }
        )
        if verbose:
            h = history[-1]
            print(
                f"  epoch {epoch:3d}  loss {h['loss']:.4f}  ce {h['ce']:.4f}  rul {h['rul']:.4f}"
                f"   val_acc {acc:.4f}  macroF1 {macro_f1:.4f}  rulRMSE {rmse:7.1f}  {h['sec']}s"
            )

        if macro_f1 > best["macro_f1"]:
            best = {
                "macro_f1": macro_f1, "epoch": epoch,
                "state": {k: v.detach().clone() for k, v in model.state_dict().items()},
            }
        elif epoch - best["epoch"] >= cfg.patience:
            if verbose:
                print(f"  early stop at epoch {epoch} (best {best['epoch']})")
            break

    if best["state"] is not None:
        model.load_state_dict(best["state"])
    return model, {"history": history, "best_epoch": best["epoch"], "best_macro_f1": best["macro_f1"]}
