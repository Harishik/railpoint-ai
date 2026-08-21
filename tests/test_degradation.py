"""Health trajectories and remaining-useful-life labels."""

import numpy as np
import pytest

from pmdlib.sim.degradation import (
    FAILURE_THRESHOLD,
    TrajectoryKind,
    severity_from_health,
    simulate_trajectory,
)


@pytest.mark.parametrize("kind", list(TrajectoryKind))
def test_health_stays_in_range(kind, rng):
    t = simulate_trajectory(600, kind=kind, rng=rng)
    assert t.health.min() >= 0.0 and t.health.max() <= 1.0
    assert len(t) == 600


@pytest.mark.parametrize("kind", list(TrajectoryKind))
def test_damage_is_monotonic_between_repairs(kind, rng):
    """Wear does not un-happen. Health may only rise at a maintenance cycle."""
    t = simulate_trajectory(600, kind=kind, rng=rng)
    rises = np.flatnonzero(np.diff(t.health) > 1e-6)
    repairs = set(t.maintenance_cycles)
    for i in rises:
        assert (i + 1) in repairs, f"health rose at cycle {i + 1} without a repair"


@pytest.mark.parametrize("kind", list(TrajectoryKind))
def test_rul_counts_down_to_failure(kind, rng):
    t = simulate_trajectory(800, kind=kind, rng=rng)
    for i in np.flatnonzero(t.rul >= 0):
        target = i + t.rul[i]
        assert t.failed[target], "RUL must point at a cycle that is actually failed"
        if t.rul[i] > 0:
            assert not t.failed[i]


def test_rul_is_censored_when_no_failure_follows(rng):
    t = simulate_trajectory(400, kind=TrajectoryKind.STABLE, rng=rng)
    assert (t.rul == -1).all(), "a machine that never fails has censored RUL, not 0"


def test_failed_flag_matches_threshold(rng):
    t = simulate_trajectory(500, kind=TrajectoryKind.GRADUAL, rng=rng)
    np.testing.assert_array_equal(t.failed, t.health < FAILURE_THRESHOLD)


def test_infant_mortality_fails_sooner_than_stable(rng):
    early = simulate_trajectory(600, kind=TrajectoryKind.INFANT_MORTALITY, rng=rng)
    stable = simulate_trajectory(600, kind=TrajectoryKind.STABLE, rng=rng)
    assert early.health.min() < stable.health.min()


def test_severity_ramp_is_monotonic_and_bounded():
    healths = np.linspace(0.0, 1.0, 50)
    sev = np.array([severity_from_health(h) for h in healths])
    assert sev.min() == 0.0 and sev.max() == 1.0
    assert (np.diff(sev) <= 1e-9).all(), "severity must not fall as health falls"
    assert severity_from_health(0.9) == 0.0, "a healthy machine shows no fault"
