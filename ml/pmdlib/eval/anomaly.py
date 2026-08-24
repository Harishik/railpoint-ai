"""Anomaly scoring on the shared embedding.

Deliberately post-hoc rather than a trained head: it adds no loss term, so it
cannot quietly trade classification accuracy for its own score, and it can be
refitted on new normal data without retraining the network.

Two complementary scores. **Mahalanobis distance** asks how far the embedding sits
from the normal-event cloud, which catches a fault type the taxonomy does not
contain. **Maximum softmax probability** asks how unsure the classifier is among
the classes it does know. A genuinely novel fault tends to score high on the
first and low on the second, and neither alone would flag it reliably.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MahalanobisScorer:
    mean: np.ndarray | None = None
    precision: np.ndarray | None = None
    shrinkage: float = 0.1

    def fit(self, embeddings: np.ndarray) -> MahalanobisScorer:
        """Fit on **normal training embeddings only**."""
        self.mean = embeddings.mean(axis=0)
        centred = embeddings - self.mean
        cov = np.cov(centred, rowvar=False)
        # Ledoit-Wolf style shrinkage toward a scaled identity. The embedding is
        # 128-dimensional and the normal set is not vastly larger, so the raw
        # covariance is ill-conditioned and its inverse would be noise.
        d = cov.shape[0]
        cov = (1 - self.shrinkage) * cov + self.shrinkage * np.trace(cov) / d * np.eye(d)
        self.precision = np.linalg.pinv(cov)
        return self

    def score(self, embeddings: np.ndarray) -> np.ndarray:
        assert self.mean is not None and self.precision is not None
        centred = embeddings - self.mean
        return np.einsum("ij,jk,ik->i", centred, self.precision, centred)


def max_softmax(logits: np.ndarray) -> np.ndarray:
    """1 - max softmax probability. Higher means less certain."""
    z = logits - logits.max(axis=1, keepdims=True)
    p = np.exp(z)
    p /= p.sum(axis=1, keepdims=True)
    return 1.0 - p.max(axis=1)
