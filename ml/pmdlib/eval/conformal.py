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


@dataclass
class ConformalClassifier:
    """Split-conformal wrapper.

    Fit on the dedicated ``calib`` split — never on train, and never on the
    ``val`` split used for early stopping. Calibrating on the data that chose
    the checkpoint makes the scores optimistic and the quantile too small, which
    is under-coverage dressed up as confidence.
    """

    alpha: float = 0.1
    qhat: float = 1.0

    def fit(self, probs: np.ndarray, y: np.ndarray) -> ConformalClassifier:
        """Calibrate on held-out data.

        The nonconformity score is 1 - p(true class): high when the model gave
        the correct label little mass.
        """
        n = len(y)
        scores = 1.0 - probs[np.arange(n), y]
        # The finite-sample correction is what makes the guarantee exact rather
        # than asymptotic; dropping it under-covers on small calibration sets.
        level = np.ceil((n + 1) * (1 - self.alpha)) / n
        self.qhat = float(np.quantile(scores, min(level, 1.0), method="higher"))
        return self

    def predict_set(self, probs: np.ndarray) -> np.ndarray:
        """Boolean ``(n, n_classes)`` mask of labels inside the prediction set.

        The plain threshold rule ``p >= 1 - qhat`` can return **nothing**. On an
        accurate model almost every calibration score is near zero, so the
        quantile lands near zero too and the threshold sits just under 1.0; any
        event whose top probability falls below it gets an empty set. That is
        not a cautious answer, it is a broken one — the console has to render
        "the model believes no fault, and also not normal".

        The argmax is therefore always included. This can only *add* labels, so
        the marginal guarantee is a lower bound that still holds: forcing a
        label in raises empirical coverage, never lowers it.
        """
        chosen = probs >= (1.0 - self.qhat)
        top = probs.argmax(axis=1)
        chosen[np.arange(len(probs)), top] = True
        return chosen

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
