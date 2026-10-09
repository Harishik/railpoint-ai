"""Hidden health trajectories over a machine's service life.

No run-to-failure field data exists for these machines, so remaining-useful-life
cannot be learned from the real extract. Here health is *generated*, which makes
the RUL label exact by construction rather than inferred - the one genuine
advantage of a simulator over a small real dataset.

Wear accumulates as a gamma process: increments are independent, non-negative and
gamma-distributed, so damage is monotonic. That is the standard degradation model
in reliability engineering precisely because wear does not un-happen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from .spec import DEGRADING_FAULTS, FaultClass

#: Health below this counts as failed; the machine is withdrawn for maintenance.
FAILURE_THRESHOLD = 0.25
#: How many throws of a machine's service life are simulated — for training data
#: *and* for the live stream. One constant, because the two used to differ: the
#: stream simulated 4,000 cycles while the training fleet stopped at 800, so the
#: RUL head was asked about lifetimes it had never seen, and only 11 of 64
#: training machines ever reached a failure (docs/BUGS.md RP-26).
SERVICE_HORIZON_CYCLES = 4000
#: Cycles over which an ACCELERATING machine's wear rate ramps up. Absolute,
#: so a trajectory does not change shape with the simulation horizon.
ACCELERATION_SCALE_CYCLES = 1200
#: Health below which degradation becomes visible in the signal. Set so that a
#: generated fleet shows anomalies on roughly 10-20% of throws. Real railway
#: fleets fail rarely; a dataset where 50% of throws are abnormal teaches the
#: wrong prior and makes anomaly detection artificially easy.
SYMPTOM_THRESHOLD = 0.62
#: Health restored by a maintenance intervention (never quite as-new).
POST_MAINTENANCE_HEALTH = 0.96


class TrajectoryKind(StrEnum):
    """How a machine ages. Real fleets contain all of these at once."""

    STABLE = "STABLE"                    # healthy, negligible wear
    GRADUAL = "GRADUAL"                  # steady wear - the textbook case
    ACCELERATING = "ACCELERATING"        # damage compounds; wear rate climbs
    SHOCK = "SHOCK"                      # sudden step damage (impact, debris)
    INTERMITTENT = "INTERMITTENT"        # comes and goes before turning persistent
    SEASONAL = "SEASONAL"                # wear rate tracks the weather
    INFANT_MORTALITY = "INFANT_MORTALITY"  # a bad repair fails early


#: Relative prevalence in a generated fleet. Most machines are fine most of the
#: time; a dataset where half the fleet is dying teaches the wrong prior.
TRAJECTORY_WEIGHTS: dict[TrajectoryKind, float] = {
    TrajectoryKind.STABLE: 0.44,
    TrajectoryKind.GRADUAL: 0.20,
    TrajectoryKind.ACCELERATING: 0.09,
    TrajectoryKind.SHOCK: 0.08,
    TrajectoryKind.INTERMITTENT: 0.10,
    TrajectoryKind.SEASONAL: 0.06,
    TrajectoryKind.INFANT_MORTALITY: 0.03,
}


@dataclass
class Trajectory:
    """One machine's health over ``n_cycles`` throws."""

    kind: TrajectoryKind
    mode: FaultClass                 # which fault this machine degrades toward
    health: np.ndarray               # (n_cycles,) in [0, 1]
    rul: np.ndarray                  # (n_cycles,) cycles until failure; -1 if none ahead
    failed: np.ndarray               # (n_cycles,) bool - health below threshold
    active: np.ndarray               # (n_cycles,) bool - fault is expressing itself
    maintenance_cycles: list[int] = field(default_factory=list)
    failure_cycles: list[int] = field(default_factory=list)

    def __len__(self) -> int:
        return int(self.health.size)


#: Median cycles-to-failure for a machine on a normal wear trajectory. Wear is
#: expressed per *cycle*, not per simulation window - an earlier version scaled
#: the rate by n_cycles, which meant a machine's lifetime silently depended on
#: how long you chose to simulate.
MEDIAN_LIFETIME_CYCLES = 900.0
#: Log-normal spread of lifetime across the fleet. Real fleets are wide: some
#: units run for years, others fail early.
LIFETIME_LOG_SIGMA = 0.75

#: Per-trajectory lifetime multipliers.
LIFETIME_SCALE: dict[str, float] = {
    "STABLE": 8.0,
    "GRADUAL": 1.0,
    "ACCELERATING": 1.3,
    "SHOCK": 3.0,
    "INTERMITTENT": 1.6,
    "SEASONAL": 1.2,
    "INFANT_MORTALITY": 0.22,
}


def _wear_rate(kind: TrajectoryKind, rng: np.random.Generator) -> float:
    """Damage accumulated per cycle for one machine.

    Failure is health < FAILURE_THRESHOLD, i.e. cumulative damage of
    ``1 - FAILURE_THRESHOLD``, so the rate is that divided by this unit's
    lifetime.
    """
    lifetime = float(
        rng.lognormal(np.log(MEDIAN_LIFETIME_CYCLES), LIFETIME_LOG_SIGMA)
        * LIFETIME_SCALE[kind.value]
    )
    return (1.0 - FAILURE_THRESHOLD) / max(lifetime, 1.0)


def _gamma_wear(n: int, rate: float, shape: float, rng: np.random.Generator) -> np.ndarray:
    """Cumulative monotonic damage from a gamma process."""
    increments = rng.gamma(shape=shape, scale=rate / shape, size=n)
    return np.cumsum(increments)


def _seasonal_multiplier(n: int, cycles_per_year: int, rng: np.random.Generator) -> np.ndarray:
    """Cold weather stiffens grease and accelerates mechanical wear."""
    phase = rng.uniform(0, 2 * np.pi)
    t = 2.0 * np.pi * np.arange(n) / max(1, cycles_per_year)
    return 1.0 + 0.55 * np.cos(t + phase)  # peak in winter


def simulate_trajectory(
    n_cycles: int,
    *,
    kind: TrajectoryKind | None = None,
    mode: FaultClass | None = None,
    rng: np.random.Generator | None = None,
    cycles_per_year: int = 3000,
    allow_maintenance: bool = True,
) -> Trajectory:
    """Generate one machine's health, RUL and fault-activity over its service life."""
    rng = rng or np.random.default_rng()
    if kind is None:
        kinds = list(TRAJECTORY_WEIGHTS)
        weights = np.array([TRAJECTORY_WEIGHTS[k] for k in kinds])
        kind = kinds[int(rng.choice(len(kinds), p=weights / weights.sum()))]
    if mode is None:
        mode = DEGRADING_FAULTS[int(rng.integers(len(DEGRADING_FAULTS)))]

    rate = _wear_rate(kind, rng)
    shape = 2.0

    if kind is TrajectoryKind.ACCELERATING:
        # Damage compounds: the wear rate itself climbs over the machine's life.
        # Indexed on absolute cycle count, not on i/n_cycles. Using the
        # horizon made the same machine with the same seed age differently
        # depending only on how many cycles we chose to simulate.
        ramp = 0.3 + np.arange(n_cycles) * (2.1 / ACCELERATION_SCALE_CYCLES)
        damage = np.cumsum(rng.gamma(shape, rate / shape, n_cycles) * ramp)
    elif kind is TrajectoryKind.SEASONAL:
        season = _seasonal_multiplier(n_cycles, cycles_per_year, rng)
        damage = np.cumsum(rng.gamma(shape, rate / shape, n_cycles) * season)
    elif kind is TrajectoryKind.SHOCK:
        # Mostly fine, punctuated by discrete damage events.
        damage = _gamma_wear(n_cycles, rate * 0.35, shape, rng)
        for _ in range(int(rng.integers(1, 4))):
            at = int(rng.integers(max(1, n_cycles // 10), n_cycles))
            damage[at:] += rng.uniform(0.20, 0.55)
    else:
        damage = _gamma_wear(n_cycles, rate, shape, rng)

    health = np.clip(1.0 - damage, 0.0, 1.0)

    # --- maintenance: withdraw and repair once health crosses the threshold --
    maintenance: list[int] = []
    failures: list[int] = []
    if allow_maintenance:
        i = 0
        while i < n_cycles:
            below = np.flatnonzero(health[i:] < FAILURE_THRESHOLD)
            if below.size == 0:
                break
            fail_at = i + int(below[0])
            failures.append(fail_at)
            # A crew takes a few cycles to arrive; the machine keeps working.
            repair_at = min(n_cycles, fail_at + int(rng.integers(1, 25)))
            maintenance.append(repair_at)
            if repair_at >= n_cycles:
                break
            recovered = POST_MAINTENANCE_HEALTH - rng.uniform(0.0, 0.06)
            health[repair_at:] = np.clip(
                health[repair_at:] + (recovered - health[repair_at]), 0.0, 1.0
            )
            i = repair_at + 1

    failed = health < FAILURE_THRESHOLD

    # --- RUL: cycles until the next crossing of the failure threshold -------
    rul = np.full(n_cycles, -1, dtype=np.int32)
    next_fail = -1
    for i in range(n_cycles - 1, -1, -1):
        if failed[i]:
            next_fail = i
            rul[i] = 0
        elif next_fail >= 0:
            rul[i] = next_fail - i
    # A machine repaired before ever failing has no failure ahead of it; -1
    # marks "censored", exactly as in real reliability data.

    # --- when does the fault actually show in the signal? -------------------
    # Severity ramps as health falls: nothing visible while healthy, unmistakable
    # near failure. INTERMITTENT machines flicker before settling.
    active = health < SYMPTOM_THRESHOLD
    if kind is TrajectoryKind.INTERMITTENT:
        flicker = rng.random(n_cycles) < np.clip((SYMPTOM_THRESHOLD - health) * 1.8, 0.0, 1.0)
        persistent = health < 0.40
        active = (active & flicker) | persistent

    return Trajectory(
        kind=kind,
        mode=mode,
        health=health.astype(np.float32),
        rul=rul,
        failed=failed,
        active=active,
        maintenance_cycles=maintenance,
        failure_cycles=failures,
    )


def severity_from_health(health: float) -> float:
    """Map health onto fault severity in [0, 1].

    Nothing above SYMPTOM_THRESHOLD, ramping to full severity at failure.
    """
    if health >= SYMPTOM_THRESHOLD:
        return 0.0
    return float(
        np.clip((SYMPTOM_THRESHOLD - health) / (SYMPTOM_THRESHOLD - FAILURE_THRESHOLD), 0.0, 1.0)
    )
