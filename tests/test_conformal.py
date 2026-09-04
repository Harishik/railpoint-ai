"""Split-conformal prediction: the guarantee, and the two ways it was broken.

RP-09. Calibration used to be fitted on `val` — the split early stopping uses to
choose the checkpoint. That is the one dependency conformal prediction forbids:
the selected epoch is the one that fits `val` best, so the nonconformity scores
measured there are smaller than on fresh data, the quantile comes out too small,
and the console advertises a coverage it does not deliver.
"""

from pathlib import Path

import numpy as np
import pytest

from pmdlib.eval import ConformalClassifier, ConformalInterval
from pmdlib.utils.splits import DEFAULT_FRACS, machine_split

ROOT = Path(__file__).resolve().parents[1]

N_CLASSES = 6


def _probs(rng, n, y, sharpness):
    """Softmax-like scores that put most mass on the true class."""
    z = rng.normal(0.0, 1.0, (n, N_CLASSES))
    z[np.arange(n), y] += sharpness
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def test_coverage_holds_on_fresh_data():
    """The whole point: at alpha=0.1 the true label lands in the set at least
    90% of the time on data the quantile was not fitted to."""
    rng = np.random.default_rng(0)
    y_cal = rng.integers(0, N_CLASSES, 4000)
    y_test = rng.integers(0, N_CLASSES, 4000)
    cc = ConformalClassifier(alpha=0.1).fit(_probs(rng, 4000, y_cal, 3.0), y_cal)
    coverage = cc.coverage(_probs(rng, 4000, y_test, 3.0), y_test)
    assert coverage >= 0.88, coverage


def test_prediction_set_is_never_empty():
    """An accurate model drives almost every calibration score to zero, so the
    quantile lands near zero and the threshold `p >= 1 - qhat` sits just under
    1.0. Every event whose top probability falls below it used to receive an
    empty set — the console rendering "not a fault, and also not normal"."""
    rng = np.random.default_rng(1)
    # Sharp enough that the plain threshold rule would exclude everything on the
    # less-confident events.
    y_cal = rng.integers(0, N_CLASSES, 3000)
    cc = ConformalClassifier(alpha=0.1).fit(_probs(rng, 3000, y_cal, 9.0), y_cal)

    y_test = rng.integers(0, N_CLASSES, 3000)
    probs = _probs(rng, 3000, y_test, 2.0)
    sizes = cc.set_sizes(probs)

    assert cc.qhat < 0.5, "test is vacuous unless the quantile is genuinely tight"
    assert sizes.min() >= 1, f"{int((sizes == 0).sum())} events received an empty set"
    # Forcing the argmax in can only add labels, so coverage cannot drop below
    # what the bare threshold achieved.
    bare = (probs >= 1.0 - cc.qhat)
    assert cc.coverage(probs, y_test) >= bare[np.arange(len(y_test)), y_test].mean()


def test_calibrating_on_the_selection_split_understates_the_quantile():
    """RP-09 itself, as a measurement rather than an assertion about intent.

    Early stopping keeps the epoch that scores best on `val`. Standing in for
    that here: scores on the selection split are optimistic relative to fresh
    data, so a quantile fitted there is too small and under-covers."""
    rng = np.random.default_rng(2)
    n = 4000
    y_sel = rng.integers(0, N_CLASSES, n)
    y_fresh = rng.integers(0, N_CLASSES, n)
    # The selection split is where the model looks best, by construction.
    optimistic = ConformalClassifier(alpha=0.1).fit(_probs(rng, n, y_sel, 5.0), y_sel)
    honest = ConformalClassifier(alpha=0.1).fit(_probs(rng, n, y_fresh, 3.0), y_fresh)

    assert optimistic.qhat < honest.qhat, (optimistic.qhat, honest.qhat)
    fresh_probs = _probs(rng, n, y_fresh, 3.0)
    assert optimistic.coverage(fresh_probs, y_fresh) < honest.coverage(fresh_probs, y_fresh)


def test_rul_interval_covers_and_never_goes_negative():
    rng = np.random.default_rng(3)
    true = rng.uniform(0, 900, 3000)
    pred = true + rng.normal(0, 60, 3000)
    ci = ConformalInterval(alpha=0.1).fit(pred, true)
    lo, hi = ci.interval(pred)
    assert (lo >= 0).all(), "a machine is never fewer than zero cycles from failing"
    assert ci.coverage(pred, true) >= 0.88


# ── The split rule itself ────────────────────────────────────────────────────

MACHINES = [f"PMD{i:03d}" for i in range(1, 401)]


def test_calib_is_disjoint_from_train_and_from_model_selection():
    """The calibration split must be data the model was neither fitted to nor
    selected on. Both, not either."""
    assigned = {m: machine_split(m) for m in MACHINES}
    by_split: dict[str, set[str]] = {}
    for m, s in assigned.items():
        by_split.setdefault(s, set()).add(m)

    assert set(by_split) == {"train", "val", "calib", "test"}
    assert by_split["calib"], "empty calibration split"
    assert not by_split["calib"] & by_split["train"]
    assert not by_split["calib"] & by_split["val"]
    assert not by_split["calib"] & by_split["test"]


def test_adding_calib_did_not_move_train_or_test():
    """`calib` is carved out of the old val band, so any metric measured on
    `test` stays comparable across the change. If someone re-tunes the
    fractions and quietly reshapes the test set, this fails."""
    def old_rule(mid: str) -> str:
        import hashlib
        u = int(hashlib.sha256(f"railpoint-v1:{mid}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        return "train" if u < 0.70 else ("val" if u < 0.85 else "test")

    for m in MACHINES:
        old, new = old_rule(m), machine_split(m)
        if old in ("train", "test"):
            assert new == old, f"{m} moved from {old} to {new}"
        else:
            assert new in ("val", "calib"), f"{m} left the old val band into {new}"


def test_calibration_can_actually_fit_an_rul_interval():
    """A split can hold thousands of events and still be unable to calibrate an
    RUL interval, because intervals need *uncensored* targets and those are rare
    and clustered by machine. The first cut of this fix put zero of them in
    `calib`; the interval silently disappeared and `rul_qhat` was written NaN."""
    import pandas as pd

    meta_path = ROOT / "data" / "synthetic" / "fleet_meta.parquet"
    if not meta_path.exists():
        pytest.skip("fleet dataset not generated")
    m = pd.read_parquet(meta_path, columns=["machine_id", "rul"])
    m["split"] = m.machine_id.map(machine_split)
    uncensored = m[m.rul.fillna(-1.0) > -1.0]
    assert not uncensored.empty, "no uncensored RUL anywhere - dataset problem, not a split problem"
    assert (uncensored.split == "calib").any(), (
        "the calib split contains no uncensored RUL target, so no conformal "
        "interval can be fitted"
    )


@pytest.mark.parametrize("frac", DEFAULT_FRACS)
def test_every_split_gets_a_share(frac):
    assert frac > 0
