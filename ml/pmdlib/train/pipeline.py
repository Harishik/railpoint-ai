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


def _normal_reference() -> dict[str, np.ndarray]:
    """Mean and standard deviation of each feature over healthy events.

    Computed from the stratified sweep's NORMAL class only, so a deviation
    measured against it answers "how unusual is this reading for a machine that
    is working", which is the question an operator is actually asking.

    Restricted to the **train** split. This reference is persisted into
    `calibration.npz` and ships with the model, so fitting it over every split
    would put held-out machines into a serving artefact. It drives explanation
    rather than prediction, so nothing reported today would move — but "the
    number is only used for display" is exactly the argument that lets test data
    leak into a shipped file.
    """
    from ..data import load
    from ..features import FEATURE_NAMES

    ds = load("stratified").split("train")
    if ds.features is None:
        return {"normal_mean": np.zeros(0), "normal_std": np.zeros(0)}
    healthy = ds.features[(ds.meta.fault == "NORMAL").to_numpy()]
    if healthy.size == 0:
        return {"normal_mean": np.zeros(0), "normal_std": np.zeros(0)}
    mean = np.nanmean(healthy, axis=0)
    std = np.nanstd(healthy, axis=0)
    # A feature that never varies among healthy events cannot produce a
    # meaningful z-score; 1.0 makes its deviation read as raw difference
    # rather than dividing by ~0 and exploding.
    std = np.where(np.isfinite(std) & (std > 1e-9), std, 1.0)
    assert mean.shape[0] == len(FEATURE_NAMES)
    return {"normal_mean": np.nan_to_num(mean), "normal_std": std}


def run(cfg: TrainConfig | None = None, threads: int | None = None) -> dict:
    cfg = cfg or TrainConfig()
    torch.set_num_threads(threads or max(1, (os.cpu_count() or 4) - 1))
    RESULTS.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print(f"[1/6] training  (threads={torch.get_num_threads()})")
    model, info = train(cfg)

    print("[2/6] inference on calib / test / real")
    strat, fleet = load("stratified", with_features=False), load("fleet", with_features=False)
    parts = {}
    for split in ("calib", "test"):
        s, f = strat.split(split), fleet.split(split)
        signals = np.concatenate([s.signals, f.signals])
        lengths = np.concatenate([s.lengths, f.lengths])
        meta = pd.concat([s.meta, f.meta], ignore_index=True)
        parts[split] = (infer(model, signals, lengths), meta)
    real = load_real()
    real_out = infer(model, real.signals, real.lengths)

    # Calibration runs on `calib`, a split the model was neither trained on nor
    # selected on. It used to run on `val` — the split early stopping uses to
    # pick the checkpoint — which is precisely the dependency conformal
    # prediction's exchangeability assumption forbids: the chosen epoch is the
    # one that fits `val` best, so the scores there understate the error the
    # model makes on fresh data and the quantile comes out too small.
    print("[3/6] conformal calibration on the held-out calib split")
    cal_out, cal_meta = parts["calib"]
    if len(cal_meta) == 0:
        raise RuntimeError(
            "the calib split is empty - conformal calibration would silently "
            "fall back to a meaningless quantile. Check pmdlib.utils.splits."
        )
    y_cal = cal_meta.fault.map({c: i for i, c in enumerate(CLASS_ORDER)}).to_numpy()
    cc = ConformalClassifier(alpha=0.1).fit(cal_out["probs"], y_cal)
    print(f"      {len(cal_meta):,} events from "
          f"{cal_meta.machine_id.nunique()} machines, qhat={cc.qhat:.4f}")

    # An RUL interval needs *uncensored* targets — events with a failure ahead of
    # them. Those are rare and clustered by machine: only 11 of the 64 simulated
    # machines ever reach one. A calibration split can therefore contain
    # thousands of events and still be unable to calibrate an interval, which is
    # exactly what happened on the first run of this fix. It failed *silently* —
    # `ci` stayed None, the RUL block vanished from the summary and `rul_qhat`
    # was written as NaN, so the console quietly stopped showing intervals while
    # still describing them. Fail loudly instead.
    ci = None
    rul_machines = 0
    if "rul" in cal_meta:
        has_rul = cal_meta.rul.fillna(CENSORED).to_numpy() > CENSORED
        if not has_rul.any():
            raise RuntimeError(
                f"the calib split has {len(cal_meta):,} events but not one uncensored "
                "RUL target, so no conformal interval can be fitted. Shipping without "
                "one silently is how the console came to claim a 90% interval it did "
                "not have. Rebalance the split in pmdlib.utils.splits so calibration "
                "receives machines that reach a failure."
            )
        rul_machines = int(cal_meta.machine_id[has_rul].nunique())
        ci = ConformalInterval(alpha=0.1).fit(
            cal_out["rul"][has_rul], cal_meta.rul.to_numpy()[has_rul].astype(float)
        )
        print(f"      RUL interval from {int(has_rul.sum()):,} uncensored targets "
              f"across {rul_machines} machine(s)")

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
            # Fitted on `calib`, measured on `test`. Reporting coverage on the
            # split the quantile was fitted to would be circular by construction.
            "coverage": round(cc.coverage(test_out["probs"], y_test), 4),
            "mean_set_size": round(float(cc.set_sizes(test_out["probs"]).mean()), 3),
            # How often the bare threshold `p >= 1 - qhat` names no label at
            # all. Measured against the raw rule on purpose: `set_sizes` forces
            # the argmax in, so counting empties there would be a tautology that
            # always reports zero. This is the diagnostic that made the old
            # mean_set_size come out below 1.
            "threshold_empty_sets": int(
                ((test_out["probs"] >= 1.0 - cc.qhat).sum(axis=1) == 0).sum()
            ),
            "calib_events": int(len(cal_meta)),
            "calib_machines": int(cal_meta.machine_id.nunique()),
            "calib_split": "calib",
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
            # The number that says how much the interval is worth. Conformal
            # coverage is a marginal guarantee over exchangeable draws; with
            # splits by machine, one calibration machine means the quantile is
            # one machine's error profile, not the fleet's.
            "calib_machines": rul_machines,
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
        # The scorer is always fitted before this point, but its fields are
        # Optional on the class, so make the invariant explicit rather than
        # letting np.savez receive a possible None.
        maha_mean=scorer.mean if scorer.mean is not None else np.zeros(0),
        maha_precision=scorer.precision if scorer.precision is not None else np.zeros((0, 0)),
        # Per-feature statistics over NORMAL training events. The console needs
        # these to say how far a measurement sits from healthy; without them its
        # "attribution" degrades to echoing the raw value, which ranks whichever
        # feature happens to be measured in the largest units.
        **_normal_reference(),
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
