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

from pmdlib.eval import RULES, ConformalClassifier, ConformalInterval, prediction_set
from pmdlib.utils.splits import DEFAULT_FRACS, machine_split

ROOT = Path(__file__).resolve().parents[1]

N_CLASSES = 6


def _probs(rng, n, y, sharpness):
    """Softmax-like scores that put most mass on the true class."""
    z = rng.normal(0.0, 1.0, (n, N_CLASSES))
    z[np.arange(n), y] += sharpness
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


@pytest.mark.parametrize("rule", RULES)
def test_coverage_holds_on_fresh_data(rule):
    """The whole point: at alpha=0.1 the true label lands in the set at least
    90% of the time on data the quantile was not fitted to — for every score."""
    rng = np.random.default_rng(0)
    y_cal = rng.integers(0, N_CLASSES, 4000)
    y_test = rng.integers(0, N_CLASSES, 4000)
    cc = ConformalClassifier(alpha=0.1, rule=rule).fit(_probs(rng, 4000, y_cal, 3.0), y_cal)
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
    cc = ConformalClassifier(alpha=0.1, rule="thr").fit(_probs(rng, 3000, y_cal, 9.0), y_cal)

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
    optimistic = ConformalClassifier(alpha=0.1, rule="thr").fit(_probs(rng, n, y_sel, 5.0), y_sel)
    honest = ConformalClassifier(alpha=0.1, rule="thr").fit(_probs(rng, n, y_fresh, 3.0), y_fresh)

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


# ── RP-27: the set has to mean something ─────────────────────────────────────


def _mixed_confidence(rng, n):
    """A model that is sure of most events and genuinely torn on some — the
    regime where a prediction set either earns its keep or does not."""
    y = rng.integers(0, N_CLASSES, n)
    sharp = np.where(rng.random(n) < 0.85, 9.0, 1.2)
    z = rng.normal(0.0, 1.0, (n, N_CLASSES))
    z[np.arange(n), y] += sharp
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True), y


def test_threshold_sets_never_widen_on_a_confident_model():
    """The defect RP-27 records, as a measurement: on a confident model the
    threshold rule returns exactly the argmax every time, so when the argmax
    is wrong the truth is never in the set."""
    rng = np.random.default_rng(10)
    p_cal, y_cal = _mixed_confidence(rng, 4000)
    p_te, y_te = _mixed_confidence(rng, 4000)
    cc = ConformalClassifier(alpha=0.1, rule="thr").fit(p_cal, y_cal)
    wrong = p_te.argmax(1) != y_te
    covered = cc.predict_set(p_te)[np.arange(len(y_te)), y_te]
    assert cc.set_sizes(p_te).mean() < 1.05
    assert covered[wrong].mean() < 0.1


def test_raps_widens_where_the_model_is_wrong():
    """What replaces it. A widened set must be markedly likelier to be an error
    than a throw picked at random, and a singleton markedly safer — otherwise
    set size is decoration."""
    rng = np.random.default_rng(11)
    p_cal, y_cal = _mixed_confidence(rng, 4000)
    p_te, y_te = _mixed_confidence(rng, 4000)
    cc = ConformalClassifier(alpha=0.1, rule="raps").fit(p_cal, y_cal)
    sizes = cc.set_sizes(p_te)
    wrong = p_te.argmax(1) != y_te
    covered = cc.predict_set(p_te)[np.arange(len(y_te)), y_te]

    assert (sizes > 1).any() and (sizes == 1).any(), "sets never vary - nothing to learn from size"
    assert wrong[sizes > 1].mean() > 2 * wrong.mean(), "a widened set is not a useful warning"
    assert wrong[sizes == 1].mean() < wrong.mean(), "a singleton is not safer than average"
    assert covered[wrong].mean() > 0.5, "the truth is rarely in the set when top-1 is wrong"


def test_regularisation_trades_set_size_monotonically():
    """lambda is the dial between 'shortlist everything' (APS) and 'shortlist
    nothing'. More penalty must never produce bigger sets on average."""
    rng = np.random.default_rng(12)
    p_cal, y_cal = _mixed_confidence(rng, 4000)
    p_te, _ = _mixed_confidence(rng, 4000)
    sizes = [
        ConformalClassifier(alpha=0.1, rule="raps", lam=lam).fit(p_cal, y_cal).set_sizes(p_te).mean()
        for lam in (0.0, 0.001, 0.01, 0.1, 0.5)
    ]
    assert all(a >= b - 1e-9 for a, b in zip(sizes, sizes[1:], strict=False)), sizes


def test_aps_is_raps_without_the_penalty():
    rng = np.random.default_rng(13)
    p, y = _mixed_confidence(rng, 2000)
    aps = ConformalClassifier(alpha=0.1, rule="aps").fit(p, y)
    raps0 = ConformalClassifier(alpha=0.1, rule="raps", lam=0.0).fit(p, y)
    assert aps.qhat == raps0.qhat
    np.testing.assert_array_equal(aps.predict_set(p), raps0.predict_set(p))


@pytest.mark.parametrize("rule", RULES)
def test_no_rule_returns_an_empty_set(rule):
    """Including the degenerate quantiles at both ends."""
    rng = np.random.default_rng(14)
    p, _ = _mixed_confidence(rng, 500)
    for q in (0.0, 1e-9, 0.5, 0.9999, 1.0):
        assert prediction_set(p, q, rule).sum(axis=1).min() >= 1, (rule, q)


def test_single_row_and_batch_agree():
    """Serving scores one throw at a time; the pipeline scores thousands. The
    same row must produce the same set either way."""
    rng = np.random.default_rng(15)
    p, _ = _mixed_confidence(rng, 50)
    batch = prediction_set(p, 0.95, "raps", 0.01, 1)
    for i in range(len(p)):
        np.testing.assert_array_equal(prediction_set(p[i], 0.95, "raps", 0.01, 1), batch[i])


def test_unknown_rule_is_refused():
    with pytest.raises(ValueError):
        prediction_set(np.array([0.5, 0.5]), 0.9, "magic")
    with pytest.raises(ValueError):
        ConformalClassifier(rule="magic").fit(np.array([[0.5, 0.5]]), np.array([0]))



def test_every_entry_point_defaults_to_the_same_rule():
    """The classifier, the pipeline and the CLI each once carried their own copy
    of the default score, and the CLI copy drifted to "aps". A recalibration
    then ran with the score this module had measured and rejected. One constant,
    and this checks every reader of it."""
    import inspect

    from pmdlib.cli import recalibrate_cmd
    from pmdlib.eval import DEFAULT_RULE
    from pmdlib.train.pipeline import run

    assert ConformalClassifier().rule == DEFAULT_RULE
    assert inspect.signature(prediction_set).parameters["rule"].default == DEFAULT_RULE
    assert inspect.signature(run).parameters["rule"].default == DEFAULT_RULE
    assert inspect.signature(recalibrate_cmd).parameters["rule"].default == DEFAULT_RULE
