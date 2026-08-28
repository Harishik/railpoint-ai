"""Run the anomaly pipeline against real field data.

Applies the same unsupervised machinery the point-machine track uses — window,
summarise, fit on normal operation only, score by Mahalanobis distance in the
feature space — to the MetroPT-3 Air Production Unit recordings, and scores it
against the four air-leak failures documented with the dataset.

The point is not the number. The point is that the number comes from data nobody
generated for this project.

    .venv/bin/python scripts/metropt_experiment.py [--nrows N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from pmdlib.data.metropt import (  # noqa: E402
    FAILURES,
    load_raw,
    make_windows,
    temporal_split,
)

RESULTS = ROOT / "experiments" / "results"


def mahalanobis_scorer(train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit on normal operation only. Shrunk covariance, because the summary
    features are strongly correlated and a raw inverse is ill-conditioned."""
    mean = train.mean(axis=0)
    centred = train - mean
    cov = np.cov(centred, rowvar=False)
    cov += np.eye(cov.shape[0]) * (1e-3 * np.trace(cov) / cov.shape[0])
    return mean, np.linalg.pinv(cov)


def score(x: np.ndarray, mean: np.ndarray, precision: np.ndarray) -> np.ndarray:
    d = x - mean
    return np.einsum("ij,jk,ik->i", d, precision, d)


def roc_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Rank-based AUC, so no sklearn import is needed for one number."""
    pos, neg = scores[labels == 1], scores[labels == 0]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(order.size, dtype=float)
    ranks[order] = np.arange(1, order.size + 1)
    return float((ranks[: pos.size].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))


def precision_at_k(labels: np.ndarray, scores: np.ndarray, k: int) -> float:
    """What a maintenance team actually experiences: of the k windows you chose
    to investigate, how many were real?"""
    k = min(k, scores.size)
    top = np.argsort(scores)[::-1][:k]
    return float(labels[top].mean())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nrows", type=int, default=None, help="limit rows (for a quick check)")
    ap.add_argument("--train-frac", type=float, default=0.5)
    args = ap.parse_args()

    print("[1/4] reading MetroPT-3")
    df = load_raw(nrows=args.nrows)
    print(f"      {len(df):,} readings, {df.timestamp.min()} to {df.timestamp.max()}")

    print("[2/4] windowing")
    w = make_windows(df)
    n_anom = int(w.labels.sum())
    print(f"      {len(w):,} windows, {len(w.feature_names)} features, "
          f"{n_anom:,} inside a documented failure ({n_anom / max(len(w), 1):.2%})")
    if n_anom == 0:
        print("      no failure windows in this slice - rerun without --nrows")
        return

    tr, te = temporal_split(w, args.train_frac)
    # Unsupervised: the scorer never sees a failure.
    tr_normal = tr[w.labels[tr] == 0]
    print(f"[3/4] fitting on {len(tr_normal):,} normal windows from the first "
          f"{args.train_frac:.0%} of the record")

    finite = np.isfinite(w.features).all(axis=1)
    tr_normal = tr_normal[finite[tr_normal]]
    te = te[finite[te]]

    mean, prec = mahalanobis_scorer(w.features[tr_normal])
    s = score(w.features[te], mean, prec)
    y = w.labels[te]

    auc = roc_auc(y, s)
    # AUC alone is misleading here, so report what a maintenance team would
    # actually experience alongside it. See the interpretation printed below.
    fail_med, fail_max = float(np.median(s[y == 1])), float(s[y == 1].max())
    norm_med = float(np.median(s[y == 0]))
    above = int((s[y == 0] > fail_max).sum())
    print("[4/4] evaluation on the held-out second half")
    summary = {
        "dataset": "MetroPT-3 (UCI 791, CC BY 4.0)",
        "asset": "Porto Metro train, Air Production Unit",
        "readings": int(len(df)),
        "windows": int(len(w)),
        "features": len(w.feature_names),
        "documented_failures": len(FAILURES),
        "train_windows_normal_only": int(len(tr_normal)),
        "test_windows": int(len(te)),
        "test_anomaly_rate": round(float(y.mean()), 4),
        "roc_auc": round(auc, 4),
        "precision_at_50": round(precision_at_k(y, s, 50), 4),
        "precision_at_100": round(precision_at_k(y, s, 100), 4),
        "precision_at_1000": round(precision_at_k(y, s, 1000), 4),
        "failure_score_median": round(fail_med, 1),
        "failure_score_max": round(fail_max, 1),
        "normal_score_median": round(norm_med, 1),
        "normal_windows_above_failure_max": above,
    }
    for k, v in summary.items():
        print(f"      {k}: {v}")

    print()
    print("      Interpretation — read the two numbers together:")
    print(f"      AUC {auc:.3f} is real: failure windows score {fail_med:.0f} against a")
    print(f"      normal median of {norm_med:.0f}. But precision@100 is "
          f"{precision_at_k(y, s, 100):.2f}, because")
    print(f"      {above:,} normal windows outscore the *highest* failure window. The extreme")
    print("      tail is dominated by unlabelled abnormal events - MetroPT-3 documents")
    print("      air-leak failures only, and the asset has other genuine anomalies.")
    print("      A team told to investigate the top 100 would find none of the four.")
    print("      AUC flatters an anomaly detector that could not be used as an alarm list.")
    print()

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "metropt-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nwrote {(RESULTS / 'metropt-summary.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
