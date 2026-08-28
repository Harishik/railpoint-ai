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

import gc
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
#: Effective-number reweighting strength; 0.999 keeps the rare/common weight
#: ratio near 8x instead of inverse frequency's 69x.
CLASS_WEIGHT_BETA = 0.999


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


def build_datasets(*splits: str) -> tuple[TensorDataset, ...]:
    """Build several splits from a single pass over the data.

    Loading per split re-read and re-decompressed the full npz each time, which
    materialised well over a gigabyte of raw signals per call and was enough to
    get the training process killed. Loaded once, sliced per split, and the raw
    arrays are dropped as soon as they are tensors.
    """
    out: list[TensorDataset] = []
    for split in splits:
        parts = [
            _to_tensors(load(name, with_features=False).split(split))
            for name in ("stratified", "fleet")
        ]
        out.append(_concat(parts))
        del parts
        gc.collect()
    return tuple(out)


def rul_target(rul: Tensor) -> Tensor:
    return torch.log1p(rul.clamp(min=0)) if RUL_LOG_SCALE else rul.clamp(min=0)


def rul_invert(pred: Tensor) -> Tensor:
    return torch.expm1(pred).clamp(min=0) if RUL_LOG_SCALE else pred.clamp(min=0)


def train(cfg: TrainConfig | None = None, verbose: bool = True) -> tuple[PointMachineNet, dict]:
    cfg = cfg or TrainConfig()
    torch.manual_seed(cfg.seed)
    # torch owns all sampling in this loop (shuffling, dropout, init); numpy is
    # only used for metrics here, so its global seed is deliberately not set.

    train_ds, val_ds = build_datasets("train", "val")

    y_train = train_ds.tensors[3].numpy()
    counts = np.bincount(y_train, minlength=cfg.net.n_classes).astype(np.float64)
    # The fleet's class distribution is deliberately realistic, so the combined
    # set is imbalanced even though the sweep is balanced. Inverse-frequency
    # weighting keeps the rare shock faults from being ignored.
    # Full inverse-frequency weighting overcorrects badly here: NORMAL has ~8.7k
    # samples against GEARBOX_WEAR's ~127, so inverse frequency hands the rare
    # class ~69x the weight and the model starts guessing rare classes whenever
    # it is unsure. Measured cost of that: GEARBOX_WEAR precision 0.126 (87% of
    # its predictions wrong) and NORMAL recall down at 0.879 despite 0.992
    # precision. Effective-number reweighting (Cui et al., CVPR 2019) accounts
    # for the fact that additional samples of a class overlap and so add less
    # than one sample of information each, which compresses that ratio to ~8x.
    beta = CLASS_WEIGHT_BETA
    effective = (1.0 - np.power(beta, counts)) / (1.0 - beta)
    weights = np.where(counts > 0, 1.0 / np.maximum(effective, 1e-8), 0.0)
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
    # A typed record rather than a heterogeneous dict: the previous
    # dict[str, float | None] mixed a float, an int and a state_dict, so every
    # comparison and the final load_state_dict were type errors that CI could
    # not see because the mypy step was suffixed with `|| true`.
    best_f1 = -1.0
    best_epoch = -1
    best_state: dict[str, Tensor] | None = None

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

        if macro_f1 > best_f1:
            best_f1 = macro_f1
            best_epoch = epoch
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        elif epoch - best_epoch >= cfg.patience:
            if verbose:
                print(f"  early stop at epoch {epoch} (best {best_epoch})")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, {"history": history, "best_epoch": best_epoch, "best_macro_f1": best_f1}
