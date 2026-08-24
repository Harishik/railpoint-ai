"""Feature-based baselines, plus a faithful rebuild of the 2024 ensemble.

The 2024 capstone report describes an LSTM-Autoencoder + Random Forest + DNN
stack combined by a Gradient Boosting meta-classifier. None of that code survives
in the delivered zips, so it is reconstructed here from the report's description
and run on the *same* splits as the new models. Without that, "the new model is
better" would be an assertion rather than a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import (
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler

RANDOM_STATE = 42


def _imputed(estimator, scaler=None) -> Pipeline:
    """Trees tolerate NaN; the neural nets do not, and NaN is meaningful here.

    A NaN inrush ratio means the motor never started - a diagnosis, not missing
    data - so it is imputed with a sentinel rather than a column mean.
    """
    steps = [("impute", SimpleImputer(strategy="constant", fill_value=-999.0))]
    if scaler is not None:
        steps.append(("scale", scaler))
    steps.append(("model", estimator))
    return Pipeline(steps)


def random_forest(n_estimators: int = 400) -> Pipeline:
    return _imputed(
        RandomForestClassifier(
            n_estimators=n_estimators,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        )
    )


def hist_gradient_boosting(max_iter: int = 500) -> HistGradientBoostingClassifier:
    """Histogram-based gradient boosting, sklearn's own implementation.

    Preferred over XGBoost here because it needs no OpenMP runtime (XGBoost's
    macOS wheel requires a separate `brew install libomp`), and because it
    handles NaN natively - which matters, since a NaN inrush ratio *is* the
    diagnosis when the motor never started.
    """
    return HistGradientBoostingClassifier(
        max_iter=max_iter,
        max_depth=6,
        learning_rate=0.08,
        l2_regularization=1.5,
        early_stopping=True,
        n_iter_no_change=25,
        random_state=RANDOM_STATE,
    )


def xgboost(n_estimators: int = 500):
    """Optional XGBoost baseline. Requires libomp on macOS; see above."""
    from xgboost import XGBClassifier

    return XGBClassifier(
        n_estimators=n_estimators,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.5,
        tree_method="hist",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )


def mlp(hidden: tuple[int, ...] = (256, 128)) -> Pipeline:
    return _imputed(
        MLPClassifier(
            hidden_layer_sizes=hidden,
            max_iter=400,
            early_stopping=True,
            n_iter_no_change=15,
            random_state=RANDOM_STATE,
        ),
        scaler=StandardScaler(),
    )


@dataclass
class Ensemble2024:
    """The 2024 stack, rebuilt from the report.

    Report, verbatim in substance: an LSTM-Autoencoder supplies a reconstruction
    error, a Random Forest and a DNN each supply class probabilities, and a
    Gradient Boosting Classifier combines the three into a final decision.
    MinMaxScaler and SMOTETomek are named for preprocessing.

    Two deviations, both documented rather than hidden:

    * The autoencoder is a dense one over the feature vector, not an LSTM over
      raw sequences. The 2024 code that would say which is gone, and this keeps
      the baseline on identical inputs to the other feature models, so the
      comparison isolates the *model* rather than the representation.
    * SMOTETomek is skipped: the stratified sweep is already exactly balanced, so
      resampling it would only add noise. The 2024 run applied it to imbalanced
      data, which is the case it is for.
    """

    rf: Pipeline = field(default_factory=lambda: random_forest(200))
    dnn: Pipeline = field(default_factory=lambda: mlp((128, 64)))
    meta: GradientBoostingClassifier = field(
        default_factory=lambda: GradientBoostingClassifier(
            n_estimators=200, max_depth=3, random_state=RANDOM_STATE
        )
    )
    scaler: MinMaxScaler = field(default_factory=MinMaxScaler)
    imputer: SimpleImputer = field(
        default_factory=lambda: SimpleImputer(strategy="constant", fill_value=-999.0)
    )
    _ae_mean: np.ndarray | None = None
    _ae_components: np.ndarray | None = None

    def _reconstruction_error(self, Xs: np.ndarray) -> np.ndarray:
        """Autoencoder stand-in: PCA reconstruction error fitted on normal data.

        A linear bottleneck trained only on healthy events, scored by how badly
        it reconstructs an input - the same quantity the 2024 LSTM-AE supplied to
        the meta-classifier.
        """
        assert self._ae_mean is not None and self._ae_components is not None
        centred = Xs - self._ae_mean
        recon = centred @ self._ae_components.T @ self._ae_components
        return np.linalg.norm(centred - recon, axis=1, keepdims=True)

    def fit(self, X: np.ndarray, y: np.ndarray, normal_class: int = 0) -> Ensemble2024:
        Xi = self.imputer.fit_transform(X)
        Xs = self.scaler.fit_transform(Xi)

        # Autoencoder trained on normal data only, exactly as the report states.
        normal = Xs[y == normal_class]
        self._ae_mean = normal.mean(axis=0)
        u, s, vt = np.linalg.svd(normal - self._ae_mean, full_matrices=False)
        self._ae_components = vt[:16]

        self.rf.fit(Xi, y)
        self.dnn.fit(Xi, y)
        meta_features = np.hstack(
            [self._reconstruction_error(Xs), self.rf.predict_proba(Xi), self.dnn.predict_proba(Xi)]
        )
        self.meta.fit(meta_features, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.meta.predict(self._meta_features(X))

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.meta.predict_proba(self._meta_features(X))

    def _meta_features(self, X: np.ndarray) -> np.ndarray:
        Xi = self.imputer.transform(X)
        Xs = self.scaler.transform(Xi)
        return np.hstack(
            [self._reconstruction_error(Xs), self.rf.predict_proba(Xi), self.dnn.predict_proba(Xi)]
        )


BASELINES = {
    "RandomForest": random_forest,
    "HistGradientBoosting": hist_gradient_boosting,
    "MLP": mlp,
}
