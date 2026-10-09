"""End-to-end: train, calibrate, evaluate, acceptance-test, export.

One entry point so that every artefact in `experiments/results/` comes from a
single reproducible command rather than a notebook someone ran once.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from ..data import CLASS_ORDER, load, load_real, real_extract_available
from ..eval import (
    DEFAULT_RULE,
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
    logit_parts: list[np.ndarray] = []
    ruls: list[np.ndarray] = []
    embeddings: list[np.ndarray] = []
    for i in range(0, len(seq), batch):
        out = model(
            torch.from_numpy(seq[i : i + batch]),
            torch.from_numpy(scalars[i : i + batch]),
            torch.from_numpy(mask[i : i + batch]),
        )
        logit_parts.append(out["fault"].numpy())
        ruls.append(rul_invert(out["rul"]).numpy())
        embeddings.append(out["embedding"].numpy())
    logits = np.concatenate(logit_parts)
    return {
        "logits": logits,
        "probs": _softmax(logits),
        "pred": logits.argmax(1),
        "rul": np.concatenate(ruls),
        "embedding": np.concatenate(embeddings),
    }


# Typed `Any` rather than `np.ndarray` because it is spread into np.savez, and
# numpy's stubs give savez a typed `allow_pickle: bool` keyword: a
# dict[str, ndarray] spread cannot be proven not to set it to an array.
def _normal_reference() -> dict[str, Any]:
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


def _set_informativeness(cc: ConformalClassifier, probs: np.ndarray, y: np.ndarray) -> dict:
    """Whether set size carries information an operator can act on.

    A set is only worth showing if its size tracks the model's reliability:
    singletons should almost always be right, and a widened set should be
    markedly more likely to be wrong than a throw picked at random.
    """
    sizes = cc.set_sizes(probs)
    chosen = cc.predict_set(probs)
    wrong = probs.argmax(axis=1) != y
    covered = chosen[np.arange(len(y)), y]
    single, wide = sizes == 1, sizes > 1

    def rate(mask: np.ndarray) -> float | None:
        return round(float(wrong[mask].mean()), 4) if mask.any() else None

    out: dict = {
        "singleton_rate": round(float(single.mean()), 4),
        "max_set_size": int(sizes.max()),
        # When top-1 is wrong, how often the set still contains the truth.
        # Under the old threshold rule this was 0: every set was the argmax.
        "coverage_when_wrong": round(float(covered[wrong].mean()), 4) if wrong.any() else None,
        "error_rate": round(float(wrong.mean()), 4),
        "error_rate_singleton": rate(single),
        "error_rate_widened": rate(wide),
    }
    if out["error_rate_widened"] is not None and out["error_rate"]:
        out["widened_lift"] = round(out["error_rate_widened"] / out["error_rate"], 2)
    return out


def run(
    cfg: TrainConfig | None = None,
    threads: int | None = None,
    *,
    reuse_net: bool = False,
    rule: str = DEFAULT_RULE,
) -> dict:
    """Train, calibrate, evaluate, acceptance-test, export.

    ``reuse_net`` loads the existing ``net.pt`` instead of training. Everything
    downstream of the weights — calibration, evaluation, the acceptance test,
    the exported artefacts — is recomputed exactly as a full run would. That
    matters because changing the conformal score function does not touch a
    single weight, and a three-hour retrain to re-derive a quantile is three
    hours spent proving nothing. The weights and the training history are left
    untouched on disk: both belong to the run that produced them.
    """
    cfg = cfg or TrainConfig()
    torch.set_num_threads(threads or max(1, (os.cpu_count() or 4) - 1))
    RESULTS.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    if reuse_net:
        from ..models.net import NetConfig, PointMachineNet

        net_path = ARTIFACTS / "net.pt"
        if not net_path.exists():
            raise FileNotFoundError(
                f"{net_path} does not exist, so there is nothing to reuse. Run a "
                "full training pass first."
            )
        print(f"[1/6] reusing trained weights from {net_path.name} (no training)")
        blob = torch.load(net_path, map_location="cpu", weights_only=False)
        model = PointMachineNet(NetConfig(**blob["config"]))
        model.load_state_dict(blob["state_dict"])
        model.eval()
        prev = RESULTS / "deep-summary.json"
        best_epoch = -1
        if prev.exists():
            with contextlib.suppress(OSError, ValueError, KeyError):
                best_epoch = int(json.loads(prev.read_text())["best_epoch"])
        # No epochs of its own: the training run's history file is left as is.
        info = {"best_epoch": best_epoch, "history": []}
    else:
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
    # The real-data acceptance test needs the private Sehwa extract. A public
    # clone does not have it, and must still be able to train end to end.
    have_real = real_extract_available()
    if have_real:
        real = load_real()
        real_out = infer(model, real.signals, real.lengths)
    else:
        print("      private Sehwa extract not present: the real-data acceptance test is skipped")

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
    cc = ConformalClassifier(alpha=0.1, rule=rule).fit(cal_out["probs"], y_cal)
    print(f"      {len(cal_meta):,} events from "
          f"{cal_meta.machine_id.nunique()} machines, rule={cc.rule}, "
          f"lambda={cc.lam}, k_reg={cc.k_reg}, qhat={cc.qhat:.5f}")

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
            # The quantile is meaningless without the score it quantifies: 0.0085
            # is a near-certain threshold under `thr` and a near-empty set under
            # `aps`. They travel together, in the summary and in the artefact.
            "rule": cc.rule,
            "qhat": round(cc.qhat, 4),
            # Fitted on `calib`, measured on `test`. Reporting coverage on the
            # split the quantile was fitted to would be circular by construction.
            "coverage": round(cc.coverage(test_out["probs"], y_test), 4),
            "mean_set_size": round(float(cc.set_sizes(test_out["probs"]).mean()), 3),
            "lam": cc.lam,
            "k_reg": cc.k_reg,
            # Marginal coverage alone cannot tell a useful set from a useless
            # one: the plain threshold rule hit 0.978 with every set exactly the
            # argmax, so it covered nothing the argmax did not. These say whether
            # the set *size* means anything.
            **_set_informativeness(cc, test_out["probs"], y_test),
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

    # Where healthy throws sit on the anomaly scale, read off `calib` — the
    # held-out split shipped artefacts are fitted to, never `test` — so the
    # console can say where a real capture falls relative to healthy operation.
    #
    # What this scale can and cannot tell you was learned the hard way. The
    # scorer is fit on NORMAL embeddings, so it measures distance from healthy:
    # every genuine fault scores high, which is what makes it a detector. On the
    # real captures it separates the faulty ones from the healthy ones cleanly.
    # It does NOT separate a wrong diagnosis from a right one — a correct live
    # E01 scored 8,607, above both confidently-wrong PMD055 events. A caveat
    # keyed to it was built and removed for exactly that reason: it fired on
    # every confident, correct fault. Flagging a confident wrong *fault type*
    # needs a class-conditional score; see docs/BUGS.md RP-28.
    healthy_cal = scorer.score(cal_out["embedding"][(cal_meta.fault == "NORMAL").to_numpy()])
    summary["anomaly"] = {
        "roc_auc": round(float(roc_auc_score(is_anom, anomaly_test)), 4),
        "positive_rate": round(float(is_anom.mean()), 4),
        "healthy_calib_n": int(healthy_cal.size),
        "healthy_calib_p99": round(float(np.percentile(healthy_cal, 99)), 1),
        "healthy_calib_p999": round(float(np.percentile(healthy_cal, 99.9)), 1),
        "healthy_calib_max": round(float(healthy_cal.max()), 1),
    }

    if have_real:
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
    else:
        # Written empty rather than left alone: an acceptance file from some
        # earlier model, beside this model's summary, would describe a network
        # that no longer exists.
        accept = pd.DataFrame(columns=[
            "event", "expected", "predicted", "correct", "diagnostic", "why",
            "set_size", "in_set", "anomaly_score",
        ])
        summary["acceptance"] = None

    print("[6/6] saving artefacts")
    # A reused run leaves the weights alone. Re-saving them would write
    # `cfg.net` — the *default* config, not the one loaded from disk — beside
    # weights that may have been trained with another, silently producing a
    # net.pt that no longer loads as the network it contains.
    if not reuse_net:
        torch.save({"state_dict": model.state_dict(), "config": asdict(cfg.net)}, ARTIFACTS / "net.pt")
    np.savez(
        ARTIFACTS / "calibration.npz",
        conformal_qhat=cc.qhat,
        # Without this, APS code loading a pre-APS artefact would read a `thr`
        # quantile as a cumulative-mass threshold and silently serve top-1 for
        # every event. The reader defaults to `thr` when the key is absent.
        conformal_rule=cc.rule,
        # RAPS cannot be reproduced from the quantile alone; serving needs the
        # penalty and the rank it starts at, or it builds a different set.
        conformal_lam=cc.lam,
        conformal_kreg=cc.k_reg,
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
    # Training history belongs to the run that produced the weights. A reused
    # run has no epochs of its own, and round-tripping the old file through
    # pandas rewrites float formatting without changing a value — noise in
    # every diff that suggests the history moved when it did not.
    if not reuse_net:
        pd.DataFrame(info["history"]).to_csv(RESULTS / "deep-history.csv", index=False)

    print("\n=== summary ===")
    print(json.dumps(summary, indent=2))
    if have_real:
        print("\n=== real acceptance test ===")
        cols = ["event", "expected", "predicted", "correct", "diagnostic", "set_size", "in_set"]
        print(accept[cols].to_string(index=False))
    return summary
