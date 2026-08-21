"""Validate the simulator against the real Sehwa traces.

This is the credibility gate for the whole project. Everything downstream is
trained on generated data, so the generator has to be shown to match reality
rather than asserted to. ``pytest tests/test_calibration.py`` runs this in CI; if
the simulator drifts away from the real signals, the build fails.

Compared two ways, because each catches what the other misses:

1. **Distributional** - per-channel Wasserstein distance and a two-sample KS test
   over pooled samples. Catches a generator whose *values* are wrong.
2. **Structural** - per-event summary statistics (idle, peak, plateau, sag, throw
   duration). Catches a generator whose values are right but whose *shape* is
   wrong, which the pooled comparison would miss entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .spec import CALIBRATED, DataQuality, Environment, FaultClass
from .waveform import generate_event

#: The four real events whose current channel is usable as a healthy reference.
#: See docs/DATA.md: PMD014's E03 code is a control-relay fault, which does not
#: deform the motor-current profile, and these four throws all complete.
HEALTHY_REFERENCE = ("PMD014#2593", "PMD014#2595", "PMD014#2596", "PMD014#2597")

#: Channels the reference machine actually instruments (PMD014 has no output_r).
COMPARABLE_CHANNELS = ("ac_curr", "ac_volt", "as_volt", "output_n_volt")

#: Max normalised Wasserstein distance (fraction of the real channel's range).
#: Set from observed performance with headroom; tightening these is a real
#: improvement to the simulator, loosening them to make CI pass is not.
WASSERSTEIN_TOLERANCE: dict[str, float] = {
    "ac_curr": 0.08,
    "ac_volt": 0.12,
    "as_volt": 0.10,
    "output_n_volt": 0.10,
}

#: Relative tolerance on each structural statistic.
STAT_TOLERANCE: dict[str, float] = {
    "idle_a": 0.35,
    "peak_a": 0.15,
    "plateau_a": 0.10,
    "sag_v": 0.30,
    "throw_samples": 0.12,
    "n_samples": 0.20,
}

ON_THRESHOLD_A = 0.5


@dataclass
class CalibrationReport:
    distribution: pd.DataFrame
    structure: pd.DataFrame
    passed: bool

    def summary(self) -> str:
        lines = ["Distributional (normalised Wasserstein, KS):", self.distribution.to_string(index=False),
                 "", "Structural (per-event statistics):", self.structure.to_string(index=False),
                 "", f"RESULT: {'PASS' if self.passed else 'FAIL'}"]
        return "\n".join(lines)


def _event_stats(curr: np.ndarray, volt: np.ndarray) -> dict[str, float]:
    on = curr > ON_THRESHOLD_A
    if not on.any():
        return {"idle_a": float(np.median(curr)), "peak_a": float(curr.max()),
                "plateau_a": np.nan, "sag_v": np.nan,
                "throw_samples": 0.0, "n_samples": float(curr.size)}
    idx = np.flatnonzero(on)
    body = curr[idx[0] : idx[-1] + 1]
    lo, hi = int(0.3 * body.size), int(0.9 * body.size)
    return {
        "idle_a": float(np.median(curr[~on])) if (~on).any() else np.nan,
        "peak_a": float(curr.max()),
        "plateau_a": float(np.median(body[lo:hi])),
        "sag_v": float(volt[~on].mean() - volt[on].mean()) if (~on).any() else np.nan,
        "throw_samples": float(idx[-1] - idx[0] + 1),
        "n_samples": float(curr.size),
    }


def load_real_reference(raw_csv: Path) -> tuple[dict[str, np.ndarray], pd.DataFrame]:
    """Pooled per-channel samples and per-event statistics from the real extract."""
    df = pd.read_csv(raw_csv)
    df["key"] = df.pmd_type + "#" + df.event_num.astype(str)

    pooled: dict[str, list[np.ndarray]] = {c: [] for c in COMPARABLE_CHANNELS}
    stats_rows = []
    for key in HEALTHY_REFERENCE:
        g = df[df.key == key].sort_values("event_seq")
        for c in COMPARABLE_CHANNELS:
            pooled[c].append(g[c].to_numpy(dtype=float))
        stats_rows.append(_event_stats(g.ac_curr.to_numpy(float), g.ac_volt.to_numpy(float)))
    return {c: np.concatenate(v) for c, v in pooled.items()}, pd.DataFrame(stats_rows)


def generate_reference(n: int = 200, seed: int = 0) -> tuple[dict[str, np.ndarray], pd.DataFrame]:
    """Healthy synthetic events matched to the reference machine.

    Clean data quality and a neutral environment, because the real reference
    events were themselves recorded on a healthy machine in mild conditions -
    comparing against iced-up winter events would be comparing two different
    things and calling the difference simulator error.
    """
    rng = np.random.default_rng(seed)
    pooled: dict[str, list[np.ndarray]] = {c: [] for c in COMPARABLE_CHANNELS}
    stats_rows = []
    for i in range(n):
        ev = generate_event(
            CALIBRATED,
            fault=FaultClass.NORMAL,
            direction="R" if i % 2 else "N",
            health=float(rng.uniform(0.93, 1.0)),
            env=Environment(),
            dq=DataQuality(),
            rng=rng,
        )
        for c in COMPARABLE_CHANNELS:
            pooled[c].append(ev.channel(c))
        stats_rows.append(_event_stats(ev.channel("ac_curr"), ev.channel("ac_volt")))
    return {c: np.concatenate(v) for c, v in pooled.items()}, pd.DataFrame(stats_rows)


def calibrate(raw_csv: Path, n_synthetic: int = 200, seed: int = 0) -> CalibrationReport:
    real_pooled, real_stats = load_real_reference(raw_csv)
    sim_pooled, sim_stats = generate_reference(n_synthetic, seed)

    dist_rows = []
    for c in COMPARABLE_CHANNELS:
        r, s = real_pooled[c], sim_pooled[c]
        rng_span = float(r.max() - r.min()) or 1.0
        w = float(stats.wasserstein_distance(r, s)) / rng_span
        ks = stats.ks_2samp(r, s)
        tol = WASSERSTEIN_TOLERANCE[c]
        dist_rows.append(
            {"channel": c, "wasserstein_norm": round(w, 4), "tolerance": tol,
             "ks_stat": round(float(ks.statistic), 4), "pass": w <= tol}
        )

    struct_rows = []
    for stat_name, tol in STAT_TOLERANCE.items():
        rv = float(np.nanmean(real_stats[stat_name]))
        sv = float(np.nanmean(sim_stats[stat_name]))
        rel = abs(sv - rv) / (abs(rv) or 1.0)
        struct_rows.append(
            {"statistic": stat_name, "real": round(rv, 3), "sim": round(sv, 3),
             "rel_error": round(rel, 4), "tolerance": tol, "pass": rel <= tol}
        )

    dist = pd.DataFrame(dist_rows)
    struct = pd.DataFrame(struct_rows)
    return CalibrationReport(dist, struct, bool(dist["pass"].all() and struct["pass"].all()))
