"""Score a capture: fault class, conformal set, anomaly, RUL and attribution.

Loads the trained encoder when one exists and falls back to a feature-model probe
otherwise, reporting which is in use through ``/api/stats`` rather than silently
degrading. A dashboard that cannot tell you whether it is running the real model
is worse than one that has no model at all.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import settings

ML_ROOT = Path(__file__).resolve().parents[3] / "ml"
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from pmdlib.data.loader import CLASS_ORDER  # noqa: E402
from pmdlib.features import FEATURE_NAMES, extract  # noqa: E402
from pmdlib.features.segment import segment  # noqa: E402
from pmdlib.sim.spec import FAULT_META, FAULT_TO_ERR_CODE, FaultClass  # noqa: E402

#: Features surfaced in explanations, with operator-readable labels. Chosen
#: because each maps to something a maintainer can physically go and check.
EXPLAIN_LABELS: dict[str, str] = {
    "in_transit_frac": "Time with no position detected",
    "drive_cut": "Drive released after throw",
    "lock_achieved": "Locked into target position",
    "hit_capture_cap": "Throw ran past the capture buffer",
    "motor_started": "Motor drew current",
    "inrush_ratio": "Start-up peak vs running current",
    "curr_plateau": "Running current",
    "throw_slope_norm": "Current rising through the throw",
    "throw_len": "Throw duration",
    "supply_sag": "Supply voltage drop under load",
    "sag_frac": "Supply drop, as a fraction of rail",
    "wpe_entropy": "Spread of ripple energy",
    "spec_flatness": "Ripple smoothness",
    "ind_reversals": "Indication contact chatter",
    "curr_active_cv": "Running-current variability",
}


@dataclass
class Scored:
    fault: str
    confidence: float
    prediction_set: list[str]
    anomaly_score: float
    rul: float | None
    rul_low: float | None
    rul_high: float | None
    attributions: list[tuple[str, float, float]]
    phases: list[tuple[str, int, int]]


class InferenceService:
    def __init__(self) -> None:
        self.source = "heuristic"
        self.version = "fallback-0"
        self._net = None
        self._conformal_qhat = 0.6
        self._rul_qhat = float("nan")
        self._maha_mean = None
        self._maha_prec = None
        self._probe = None
        self._probe_mean = None
        #: Per-feature mean/std over healthy training events, used to express a
        #: measurement as a deviation from normal operation.
        self._normal_mean = None
        self._normal_std = None
        self._load()

    @property
    def degraded(self) -> bool:
        """True when nothing can actually score an event.

        With neither the encoder nor the probe loaded, every event falls through
        to a uniform distribution whose argmax is CLASS_ORDER[0] - NORMAL. The
        severity rule downgrades that to "info" on low confidence, so it does not
        surface as a confident all-clear, but /api/health must still say so
        rather than reporting "ok" while nothing is being classified.
        """
        return self._net is None and self._probe is None

    # -- loading ---------------------------------------------------------
    def _load(self) -> None:
        net_path = settings.artifacts_dir / "net.pt"
        calib_path = settings.artifacts_dir / "calibration.npz"
        if net_path.exists():
            try:
                import torch

                from pmdlib.models.net import NetConfig, PointMachineNet

                blob = torch.load(net_path, map_location="cpu")
                net = PointMachineNet(NetConfig(**blob["config"]))
                net.load_state_dict(blob["state_dict"])
                net.eval()
                self._net = net
                self.source = "trained"
                self.version = f"net-{blob['config']['d_model']}d-{blob['config']['n_layers']}L"
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[inference] trained model present but unusable: {exc}")
        # Only meaningful for the encoder these were calibrated against. The
        # probe produces scores on a completely different scale, so applying the
        # net's conformal qhat to it voids the coverage guarantee rather than
        # transferring it - and the Mahalanobis stats index the net's embedding
        # space, which the probe does not even produce.
        if calib_path.exists() and self._net is not None:
            c = np.load(calib_path)
            self._conformal_qhat = float(c["conformal_qhat"])
            self._rul_qhat = float(c["rul_qhat"])
            self._maha_mean, self._maha_prec = c["maha_mean"], c["maha_precision"]
            if "normal_mean" in c and c["normal_mean"].size:
                self._normal_mean = c["normal_mean"]
                self._normal_std = c["normal_std"]
        if self._net is None:
            self._fit_probe()

    def _fit_probe(self) -> None:
        """Fallback: a linear probe on features, trained on the stratified sweep.

        Deliberately linear. It is weaker than the encoder, but its coefficients
        give an honest local attribution, so explanations stay meaningful while
        the real model is unavailable.
        """
        try:
            from sklearn.impute import SimpleImputer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler

            from pmdlib.data import load

            ds = load("stratified").split("train")
            self._probe = Pipeline(
                [
                    ("impute", SimpleImputer(strategy="constant", fill_value=-999.0)),
                    ("scale", StandardScaler()),
                    ("clf", LogisticRegression(max_iter=1500)),
                ]
            ).fit(ds.features, ds.y)
            self._probe_mean = np.nan_to_num(ds.features, nan=-999.0).mean(axis=0)
            self.version = "linear-probe-1"
        except Exception as exc:  # pragma: no cover
            print(f"[inference] probe unavailable: {exc}")

    # -- scoring ---------------------------------------------------------
    def score(self, signals: np.ndarray, length: int) -> Scored:
        feats = extract(signals, length)
        vec = np.array([feats.get(k, np.nan) for k in FEATURE_NAMES], np.float32)[None, :]
        ph = segment(np.nan_to_num(signals[:length, 0]))
        phases = [
            (name, *ph.span(name))
            for name in ("idle_pre", "inrush", "throw", "lock", "idle_post")
            if ph.span(name)[1] > ph.span(name)[0]
        ]

        if self._net is not None:
            probs, rul, embedding = self._score_net(signals, length)
        else:
            probs, rul, embedding = self._score_probe(vec)

        idx = int(np.argmax(probs))
        pred_set = [CLASS_ORDER[i] for i in np.flatnonzero(probs >= 1.0 - self._conformal_qhat)]
        if not pred_set:
            pred_set = [CLASS_ORDER[idx]]

        anomaly = 0.0
        if embedding is not None and self._maha_mean is not None:
            d = embedding - self._maha_mean
            anomaly = float(d @ self._maha_prec @ d)
        else:
            anomaly = float(1.0 - probs.max()) * 100.0

        lo = hi = None
        if rul is not None and np.isfinite(self._rul_qhat):
            lo, hi = max(0.0, rul - self._rul_qhat), rul + self._rul_qhat

        return Scored(
            fault=CLASS_ORDER[idx],
            confidence=float(probs[idx]),
            prediction_set=pred_set,
            anomaly_score=anomaly,
            rul=rul,
            rul_low=lo,
            rul_high=hi,
            attributions=self._attribute(feats, vec, idx),
            phases=phases,
        )

    def _score_net(self, signals: np.ndarray, length: int):
        import torch

        from pmdlib.models.prep import prepare
        from pmdlib.train.deep import rul_invert

        seq, scalars, mask = prepare(signals[None, :], np.array([length]))
        with torch.no_grad():
            out = self._net(torch.from_numpy(seq), torch.from_numpy(scalars), torch.from_numpy(mask))
        logits = out["fault"].numpy()[0]
        e = np.exp(logits - logits.max())
        # expm1 overflows to +inf for any float32 logit above ~88, and a
        # degenerate capture can produce an all-masked attention row. inf/NaN is
        # not valid JSON, so it would 500 /api/machines and corrupt the socket
        # frame rather than simply being an implausible number.
        rul = float(rul_invert(out["rul"]).numpy()[0])
        return e / e.sum(), (rul if np.isfinite(rul) else None), out["embedding"].numpy()[0]

    def _score_probe(self, vec: np.ndarray):
        if self._probe is None:
            uniform = np.full(len(CLASS_ORDER), 1.0 / len(CLASS_ORDER))
            return uniform, None, None
        return self._probe.predict_proba(vec)[0], None, None

    def _attribute(self, feats: dict, vec: np.ndarray, class_idx: int) -> list[tuple[str, float, float]]:
        """Local attribution over the operator-readable feature subset.

        With the linear probe this is exact: coefficient x standardised
        deviation. With the encoder it is a **deviation proxy** - how many
        standard deviations this measurement sits from healthy operation,
        signed. That is not a true attribution and the model card says so;
        integrated gradients is the honest upgrade.

        What it must never be is the raw measurement. That was the previous
        fallback, and it made the ranking a function of each feature's *units*:
        throw duration, measured in hundreds of samples, outranked every
        binary indicator on every event regardless of relevance.
        """
        rows: list[tuple[str, float, float]] = []
        have_reference = (
            self._normal_mean is not None
            and self._normal_std is not None
            and len(self._normal_mean) == len(FEATURE_NAMES)
        )
        for name in EXPLAIN_LABELS:
            if name not in FEATURE_NAMES:
                continue
            j = FEATURE_NAMES.index(name)
            value = float(vec[0, j]) if np.isfinite(vec[0, j]) else 0.0
            if self._probe is not None and self._probe_mean is not None:
                scale = self._probe.named_steps["scale"].scale_[j]
                coef = self._probe.named_steps["clf"].coef_[class_idx, j]
                contribution = float(coef * (value - self._probe_mean[j]) / (scale or 1.0))
            elif have_reference:
                contribution = float((value - self._normal_mean[j]) / self._normal_std[j])
            else:
                # No reference available: report zero rather than inventing a
                # number. A blank evidence panel is honest; a wrong one is not.
                contribution = 0.0
            rows.append((name, value, contribution))
        rows.sort(key=lambda r: abs(r[2]), reverse=True)
        return rows[:8]


def fault_meta(name: str) -> tuple[str, str, str | None, int]:
    f = FaultClass(name)
    ko, en, _sub, sev = FAULT_META[f]
    return ko, en, FAULT_TO_ERR_CODE[f], sev
