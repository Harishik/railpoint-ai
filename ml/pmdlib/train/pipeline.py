"""End-to-end: train, calibrate, evaluate, acceptance-test, export.

One entry point so that every artefact in `experiments/results/` comes from a
single reproducible command rather than a notebook someone ran once.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from ..data import CLASS_ORDER, load, load_real
from ..eval import (
    ConformalClassifier,
    ConformalInterval,
    MahalanobisScorer,
    acceptance_test,
    evaluate_classifier,
)
from ..models.prep import prepare
from .deep import CENSORED, TrainConfig, rul_invert, train

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "experiments" / "results"
ARTIFACTS = ROOT / "experiments" / "artifacts"


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


@torch.no_grad()
def infer(model, signals: np.ndarray, lengths: np.ndarray, batch: int = 256) -> dict[str, np.ndarray]:
    model.eval()
    seq, scalars, mask = prepare(signals, lengths)
    logits, ruls, embeddings = [], [], []
    for i in range(0, len(seq), batch):
        out = model(
            torch.from_numpy(seq[i : i + batch]),
            torch.from_numpy(scalars[i : i + batch]),
            torch.from_numpy(mask[i : i + batch]),
        )
        logits.append(out["fault"].numpy())
        ruls.append(rul_invert(out["rul"]).numpy())
        embeddings.append(out["embedding"].numpy())
    logits = np.concatenate(logits)
    return {
        "logits": logits,
        "probs": _softmax(logits),
        "pred": logits.argmax(1),
        "rul": np.concatenate(ruls),
        "embedding": np.concatenate(embeddings),
    }


def run(cfg: TrainConfig | None = None, threads: int | None = None) -> dict:
    cfg = cfg or TrainConfig()
    torch.set_num_threads(threads or max(1, (os.cpu_count() or 4) - 1))
    RESULTS.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print(f"[1/6] training  (threads={torch.get_num_threads()})")
    model, info = train(cfg)

    print("[2/6] inference on val / test / real")
    strat, fleet = load("stratified", with_features=False), load("fleet", with_features=False)
    parts = {}
    for split in ("val", "test"):
        s, f = strat.split(split), fleet.split(split)
        signals = np.concatenate([s.signals, f.signals])
        lengths = np.concatenate([s.lengths, f.lengths])
        meta = pd.concat([s.meta, f.meta], ignore_index=True)
        parts[split] = (infer(model, signals, lengths), meta)
    real = load_real()
    real_out = infer(model, real.signals, real.lengths)

    print("[3/6] conformal calibration on val")
    val_out, val_meta = parts["val"]
    y_val = val_meta.fault.map({c: i for i, c in enumerate(CLASS_ORDER)}).to_numpy()
    cc = ConformalClassifier(alpha=0.1).fit(val_out["probs"], y_val)

    has_rul = val_meta.rul.fillna(CENSORED).to_numpy() > CENSORED if "rul" in val_meta else np.zeros(len(val_meta), bool)
    ci = None
    if has_rul.any():
        ci = ConformalInterval(alpha=0.1).fit(
            val_out["rul"][has_rul], val_meta.rul.to_numpy()[has_rul].astype(float)
        )

    print("[4/6] anomaly scorer on normal training embeddings")
    tr_s, tr_f = strat.split("train"), fleet.split("train")
    tr_signals = np.concatenate([tr_s.signals, tr_f.signals])
    tr_lengths = np.concatenate([tr_s.lengths, tr_f.lengths])
    tr_meta = pd.concat([tr_s.meta, tr_f.meta], ignore_index=True)
    tr_out = infer(model, tr_signals, tr_lengths)
    normal_mask = (tr_meta.fault == "NORMAL").to_numpy()
    scorer = MahalanobisScorer().fit(tr_out["embedding"][normal_mask])

    print("[5/6] evaluation")
    test_out, test_meta = parts["test"]
    y_test = test_meta.fault.map({c: i for i, c in enumerate(CLASS_ORDER)}).to_numpy()
    result = evaluate_classifier("PointMachineNet", y_test, test_out["pred"])

    summary: dict = {
        "params": model.n_parameters(),
        "best_epoch": info["best_epoch"],
        "test": result.row(),
        "conformal": {
            "alpha": cc.alpha,
            "qhat": round(cc.qhat, 4),
            "coverage": round(cc.coverage(test_out["probs"], y_test), 4),
            "mean_set_size": round(float(cc.set_sizes(test_out["probs"]).mean()), 3),
        },
    }

    test_rul_mask = test_meta.rul.fillna(CENSORED).to_numpy() > CENSORED if "rul" in test_meta else np.zeros(len(test_meta), bool)
    if ci is not None and test_rul_mask.any():
        true_rul = test_meta.rul.to_numpy()[test_rul_mask].astype(float)
        pred_rul = test_out["rul"][test_rul_mask]
        summary["rul"] = {
            "n": int(test_rul_mask.sum()),
            "rmse": round(float(np.sqrt(np.mean((pred_rul - true_rul) ** 2))), 2),
            "mae": round(float(np.mean(np.abs(pred_rul - true_rul))), 2),
            "interval_halfwidth": round(ci.qhat, 1),
            "coverage": round(ci.coverage(pred_rul, true_rul), 4),
        }

    anomaly_test = scorer.score(test_out["embedding"])
    is_anom = test_meta.is_anomaly.to_numpy(bool)
    from sklearn.metrics import roc_auc_score

    summary["anomaly"] = {
        "roc_auc": round(float(roc_auc_score(is_anom, anomaly_test)), 4),
        "positive_rate": round(float(is_anom.mean()), 4),
    }

    accept, passed = acceptance_test(real.meta.key.tolist(), real_out["pred"])
    sets = cc.predict_set(real_out["probs"])
    accept["set_size"] = sets.sum(axis=1)
    accept["in_set"] = [
        bool(sets[i, CLASS_ORDER.index(accept.expected.iloc[i])]) for i in range(len(accept))
    ]
    accept["anomaly_score"] = np.round(scorer.score(real_out["embedding"]), 1)
    summary["acceptance"] = {
        "diagnostic_correct": int(accept[accept.diagnostic].correct.sum()),
        "diagnostic_total": int(accept.diagnostic.sum()),
        "all_correct": int(accept.correct.sum()),
        "passed": bool(passed),
        "expected_in_conformal_set": int(accept.in_set.sum()),
    }

    print("[6/6] saving artefacts")
    torch.save({"state_dict": model.state_dict(), "config": asdict(cfg.net)}, ARTIFACTS / "net.pt")
    np.savez(
        ARTIFACTS / "calibration.npz",
        conformal_qhat=cc.qhat,
        rul_qhat=(ci.qhat if ci else np.nan),
        maha_mean=scorer.mean,
        maha_precision=scorer.precision,
    )
    (RESULTS / "deep-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    result.per_class.to_csv(RESULTS / "deep-per-class.csv", index=False)
    accept.to_csv(RESULTS / "deep-acceptance.csv", index=False)
    pd.DataFrame(info["history"]).to_csv(RESULTS / "deep-history.csv", index=False)

    print("\n=== summary ===")
    print(json.dumps(summary, indent=2))
    print("\n=== real acceptance test ===")
    print(accept[["event", "expected", "predicted", "correct", "diagnostic", "set_size", "in_set"]].to_string(index=False))
    return summary
