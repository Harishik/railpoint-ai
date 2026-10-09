"""Distribution-free confidence, via split conformal prediction.

A softmax score is not a probability of being right - a network can be
confidently wrong, especially on a machine it has never seen. Conformal
prediction converts any score into a **set** of labels with a guaranteed
marginal coverage: at alpha = 0.1, the true class lands in the returned set at
least 90% of the time, with no assumption about the model or the data
distribution beyond exchangeability.

That matters here for two reasons. A set of size one is a confident diagnosis a
maintainer can act on; a set of size four is the model saying "it is one of
these, go look" - which is honest and still useful. And the *size* of the set is
itself the alarm: sets that widen on a machine indicate the model is off its
training distribution, which is exactly the condition the real Sehwa events
exposed in the baselines.

For RUL we use conformalized quantile regression's simpler cousin - absolute
residual calibration - giving an interval rather than a bare number.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Supported score functions. ``raps`` is the default; ``aps`` and ``thr`` are
#: kept so the three can be measured against each other rather than swapped on
#: faith — see scripts/conformal_rules.py and experiments/results/conformal-rules.md.
RULES = ("raps", "aps", "thr")

#: The one place the default score is named. It used to be written out by hand
#: in the classifier, the pipeline and the CLI, and the CLI copy drifted to
#: "aps" — a recalibration ran with the over-padded score this module had just
#: ruled out, and was caught only because the pipeline logs the rule it used.
DEFAULT_RULE = "raps"

#: RAPS regularisation strength. Chosen on the ``calib`` split alone, by
#: leave-one-machine-out, at the knee of the set-size / informativeness curve:
#: the last step where regularising sheds more mean set size than it costs in
#: coverage of the model's own errors (0.001 -> 0.01 sheds 0.285 for 0.120; the
#: next step, 0.01 -> 0.05, sheds 0.063 for 0.113). The test split was never
#: consulted, so it remains an independent check.
DEFAULT_LAMBDA = 0.01


def prediction_set(
    probs: np.ndarray,
    qhat: float,
    rule: str = DEFAULT_RULE,
    lam: float = DEFAULT_LAMBDA,
    k_reg: int = 1,
) -> np.ndarray:
    """Build the prediction set. **One implementation, used everywhere.**

    The pipeline and the serving path previously each built the set themselves,
    and they disagreed: serving forced the argmax in, the pipeline did not, so
    the reported ``mean_set_size`` of 0.895 described something the console
    never actually did. A shared function is the structural fix.

    Accepts ``(n, k)`` or a single ``(k,)`` row; returns a boolean mask of the
    same shape. No rule can return an empty set.

    ``raps`` — Regularized Adaptive Prediction Sets (Angelopoulos et al., ICLR
    2021). Rank classes by probability and keep a class while the mass ranked
    above it, plus ``lam`` for every rank past ``k_reg``, stays below ``qhat``.
    The penalty is what stops the set filling with classes the model gives
    almost no mass to.

    ``aps`` — the same with ``lam = 0`` (Romano et al., NeurIPS 2020). Measured
    on this model it is badly over-conservative: 91% of sets widen, so a
    widened set carries almost no information. Kept for comparison.

    ``thr`` — ``p >= 1 - qhat`` with the argmax forced in. Measured on this
    model every set is exactly one label and coverage equals top-1 accuracy to
    four decimals. Kept so old artefacts still load.
    """
    p = np.atleast_2d(probs)
    if rule in ("raps", "aps"):
        penalty = lam if rule == "raps" else 0.0
        # Stable sort so ties break the same way on every call — a prediction
        # set that changes between identical requests is not reproducible.
        order = np.argsort(-p, axis=1, kind="stable")
        sorted_p = np.take_along_axis(p, order, axis=1)
        mass_before = np.cumsum(sorted_p, axis=1) - sorted_p
        rank = np.arange(1, p.shape[1] + 1)[None, :]
        keep = mass_before + penalty * np.maximum(0, rank - k_reg) < qhat
        keep[:, 0] = True  # the top class has nothing ranked above it
        chosen = np.zeros(p.shape, dtype=bool)
        np.put_along_axis(chosen, order, keep, axis=1)
    elif rule == "thr":
        chosen = p >= (1.0 - qhat)
        chosen[np.arange(len(p)), p.argmax(axis=1)] = True
    else:
        raise ValueError(f"unknown conformal rule {rule!r}; expected one of {RULES}")
    return chosen if np.ndim(probs) == 2 else chosen[0]


@dataclass
class ConformalClassifier:
    """Split-conformal wrapper.

    Fit on the dedicated ``calib`` split — never on train, and never on the
    ``val`` split used for early stopping. Calibrating on the data that chose
    the checkpoint makes the scores optimistic and the quantile too small, which
    is under-coverage dressed up as confidence.

    The default score is **RAPS**. The plain threshold it replaced was sound but
    useless here: every set came out at exactly one label, so when the model was
    wrong the true class was in the set 0% of the time. Under RAPS it is there
    86% of the time, and a widened set carries eight times the base error rate —
    which is what makes set size usable as a "go and look" signal.
    """

    alpha: float = 0.1
    qhat: float = 1.0
    rule: str = DEFAULT_RULE
    lam: float = DEFAULT_LAMBDA
    #: Rank past which RAPS starts penalising. Fitted in ``fit`` as the
    #: (1 - alpha) quantile of the true class's rank on the calibration data.
    k_reg: int = 1

    def _rank_of_truth(self, probs: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        order = np.argsort(-probs, axis=1, kind="stable")
        sorted_p = np.take_along_axis(probs, order, axis=1)
        rank0 = np.argmax(order == y[:, None], axis=1)
        mass_through = np.cumsum(sorted_p, axis=1)[np.arange(len(y)), rank0]
        return rank0 + 1, mass_through

    def fit(self, probs: np.ndarray, y: np.ndarray) -> ConformalClassifier:
        """Calibrate on held-out data.

        For ``raps``/``aps`` the score is the mass ranked down to and including
        the true class, plus the rank penalty: small when the model put the
        truth first with confidence, large when it buried it. For ``thr`` it is
        ``1 - p(true class)``.
        """
        if self.rule not in RULES:
            raise ValueError(f"unknown conformal rule {self.rule!r}; expected one of {RULES}")
        n = len(y)
        if self.rule in ("raps", "aps"):
            rank, mass_through = self._rank_of_truth(probs, y)
            if self.rule == "raps":
                self.k_reg = int(np.quantile(rank, 1 - self.alpha, method="higher"))
            penalty = self.lam if self.rule == "raps" else 0.0
            scores = mass_through + penalty * np.maximum(0, rank - self.k_reg)
        else:
            scores = 1.0 - probs[np.arange(n), y]
        # The finite-sample correction is what makes the guarantee exact rather
        # than asymptotic; dropping it under-covers on small calibration sets.
        level = np.ceil((n + 1) * (1 - self.alpha)) / n
        self.qhat = float(np.quantile(scores, min(level, 1.0), method="higher"))
        return self

    def predict_set(self, probs: np.ndarray) -> np.ndarray:
        """Boolean ``(n, n_classes)`` mask of labels inside the prediction set."""
        return prediction_set(probs, self.qhat, self.rule, self.lam, self.k_reg)

    def set_sizes(self, probs: np.ndarray) -> np.ndarray:
        return self.predict_set(probs).sum(axis=1)

    def coverage(self, probs: np.ndarray, y: np.ndarray) -> float:
        chosen = self.predict_set(probs)
        return float(chosen[np.arange(len(y)), y].mean())


@dataclass
class ConformalInterval:
    """Absolute-residual calibration for a scalar regression (RUL)."""

    alpha: float = 0.1
    qhat: float = 0.0

    def fit(self, pred: np.ndarray, true: np.ndarray) -> ConformalInterval:
        residuals = np.abs(pred - true)
        n = len(residuals)
        level = np.ceil((n + 1) * (1 - self.alpha)) / n
        self.qhat = float(np.quantile(residuals, min(level, 1.0), method="higher"))
        return self

    def interval(self, pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        # RUL cannot be negative: a machine is never fewer than zero cycles from
        # failing, so the lower bound is clipped rather than allowed to go below.
        return np.maximum(pred - self.qhat, 0.0), pred + self.qhat

    def coverage(self, pred: np.ndarray, true: np.ndarray) -> float:
        lo, hi = self.interval(pred)
        return float(((true >= lo) & (true <= hi)).mean())
