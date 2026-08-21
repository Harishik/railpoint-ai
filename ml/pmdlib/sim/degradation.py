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
    TrajectoryKind.STABLE: 0.30,
    TrajectoryKind.GRADUAL: 0.26,
    TrajectoryKind.ACCELERATING: 0.12,
    TrajectoryKind.SHOCK: 0.10,
    TrajectoryKind.INTERMITTENT: 0.12,
    TrajectoryKind.SEASONAL: 0.06,
    TrajectoryKind.INFANT_MORTALITY: 0.04,
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

    # Base wear rate, tuned so a GRADUAL machine typically reaches the failure
    # threshold somewhere inside its simulated life rather than at cycle 3.
    base_rate = 0.75 / max(n_cycles, 1)
    shape = 2.0

    if kind is TrajectoryKind.STABLE:
        damage = _gamma_wear(n_cycles, base_rate * 0.18, shape, rng)
    elif kind is TrajectoryKind.GRADUAL:
        damage = _gamma_wear(n_cycles, base_rate * rng.uniform(0.9, 1.6), shape, rng)
    elif kind is TrajectoryKind.ACCELERATING:
        ramp = np.linspace(0.35, 2.6, n_cycles)
        damage = np.cumsum(rng.gamma(shape, base_rate / shape, n_cycles) * ramp)
    elif kind is TrajectoryKind.SEASONAL:
        season = _seasonal_multiplier(n_cycles, cycles_per_year, rng)
        damage = np.cumsum(rng.gamma(shape, base_rate / shape, n_cycles) * season)
    elif kind is TrajectoryKind.SHOCK:
        damage = _gamma_wear(n_cycles, base_rate * 0.3, shape, rng)
        for _ in range(int(rng.integers(1, 4))):
            at = int(rng.integers(n_cycles // 10, n_cycles))
            damage[at:] += rng.uniform(0.25, 0.6)
    elif kind is TrajectoryKind.INTERMITTENT:
        damage = _gamma_wear(n_cycles, base_rate * 0.7, shape, rng)
    elif kind is TrajectoryKind.INFANT_MORTALITY:
        damage = _gamma_wear(n_cycles, base_rate * 4.5, shape, rng)
    else:  # pragma: no cover
        raise ValueError(kind)

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
    active = health < 0.85
    if kind is TrajectoryKind.INTERMITTENT:
        flicker = rng.random(n_cycles) < np.clip((0.85 - health) * 1.4, 0.0, 1.0)
        persistent = health < 0.45
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

    Nothing below 0.85 health, ramping to full severity at the failure threshold.
    """
    if health >= 0.85:
        return 0.0
    return float(np.clip((0.85 - health) / (0.85 - FAILURE_THRESHOLD), 0.0, 1.0))
