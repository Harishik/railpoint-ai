"""Physical invariants the simulator must never violate."""

import numpy as np
import pytest

from pmdlib.sim.spec import (
    CALIBRATED,
    CHANNELS,
    CRITICAL_FAULTS,
    SUPPLY_CLASS_B,
    DataQuality,
    Environment,
    FaultClass,
)
from pmdlib.sim.waveform import RAIL_OVERSHOOT, generate_event

ALL_FAULTS = list(FaultClass)


@pytest.mark.parametrize("fault", ALL_FAULTS)
@pytest.mark.parametrize("severity", [0.15, 0.55, 0.95])
def test_signals_are_physically_bounded(fault, severity, rng):
    for _ in range(6):
        ev = generate_event(
            CALIBRATED, fault=fault, severity=severity,
            direction=str(rng.choice(["N", "R"])), rng=rng,
        )
        curr = ev.channel("ac_curr")
        assert np.nanmin(curr) >= 0.0, "current cannot be negative"
        assert np.nanmax(curr) <= 40.0, "current far beyond any plausible stall"
        assert np.nanmin(ev.channel("ac_volt")) > 100.0, "supply collapsed below plausibility"

        rail = CALIBRATED.indication_v * RAIL_OVERSHOOT
        for ch in ("as_volt", "output_n_volt"):
            assert np.nanmax(np.abs(ev.channel(ch))) <= rail + 1e-6, (
                f"{ch} exceeded its supply rail"
            )


@pytest.mark.parametrize("fault", ALL_FAULTS)
def test_shape_and_channel_order(fault, rng):
    ev = generate_event(CALIBRATED, fault=fault, severity=0.5, rng=rng)
    assert ev.signals.ndim == 2
    assert ev.signals.shape[1] == len(CHANNELS)
    assert 0 < len(ev) <= CALIBRATED.capture_cap


@pytest.mark.parametrize("fault", sorted(CRITICAL_FAULTS, key=str))
def test_critical_faults_block_at_high_severity(fault, rng):
    completions = [
        generate_event(CALIBRATED, fault=fault, severity=0.95, rng=rng).completed
        for _ in range(12)
    ]
    assert not any(completions), f"{fault} at full severity must not complete"


@pytest.mark.parametrize("fault", sorted(CRITICAL_FAULTS, key=str))
def test_blocks_at_predicts_completion(fault, rng):
    """The severity-aware contract must match what the generator actually does."""
    from pmdlib.sim.spec import blocks_at

    for severity in (0.1, 0.3, 0.5, 0.7, 0.9):
        if not blocks_at(fault, severity):
            continue
        for _ in range(8):
            ev = generate_event(CALIBRATED, fault=fault, severity=severity, rng=rng)
            assert not ev.completed, f"{fault} at severity {severity} should block"


def test_healthy_event_matches_measured_reference(rng):
    """The measured PMD014 reference: plateau 3.83 A, peak ~9.8 A, throw ~205."""
    stats = []
    for _ in range(40):
        ev = generate_event(CALIBRATED, fault=FaultClass.NORMAL, health=1.0,
                            env=Environment(), dq=DataQuality(), rng=rng)
        c = ev.channel("ac_curr")
        on = c > 0.5
        body = c[on]
        stats.append((np.median(body[int(.3 * body.size):int(.9 * body.size)]),
                      c.max(), ev.throw_samples))
    plateau, peak, throw = (float(np.mean(x)) for x in zip(*stats, strict=True))
    assert 3.5 < plateau < 4.2, plateau
    assert 8.8 < peak < 10.8, peak
    assert 190 < throw < 225, throw


def test_e03_no_start_reproduces_pmd014_2594(rng):
    """The real event: motor never started, no supply sag, indication frozen,
    drive command pulsed and returned to 0."""
    ev = generate_event(CALIBRATED, fault=FaultClass.E03_LINE_RELAY, severity=0.95,
                        direction="R", env=Environment(), dq=DataQuality(), rng=rng)
    assert ev.channel("ac_curr").max() < 0.5, "motor must not draw load"
    assert abs(ev.channel("ac_volt").mean() - CALIBRATED.supply_v) < 2.0, "no load means no sag"
    out_n = ev.channel("output_n_volt")
    assert np.mean(np.abs(out_n) < 2.0) == 0.0, "never unlocked, so never in transit"
    assert abs(ev.channel("as_volt")[-5:].mean()) < 3.0, "drive is cut on timeout"


def test_e01_reproduces_pmd055_stall(rng):
    """The real events: exactly 600 samples, permanently in transit, drive never cut."""
    ev = generate_event(SUPPLY_CLASS_B, fault=FaultClass.E01_LOCK_LATCH, severity=0.9,
                        direction="R", env=Environment(), dq=DataQuality(), rng=rng)
    assert ev.truncated and len(ev) == SUPPLY_CLASS_B.capture_cap
    assert np.mean(np.abs(ev.channel("output_n_volt")) < 2.0) > 0.85, "should never lock"
    assert abs(ev.channel("as_volt")[-5:].mean()) > 15.0, "drive must never be cut"


def test_healthy_indication_is_three_state(rng):
    """Measured on the real trace: ~79% of samples sit at 0 V, in transit."""
    fracs = []
    for _ in range(20):
        ev = generate_event(CALIBRATED, fault=FaultClass.NORMAL, env=Environment(),
                            dq=DataQuality(), rng=rng)
        fracs.append(np.mean(np.abs(ev.channel("output_n_volt")) < 2.0))
    assert 0.6 < float(np.mean(fracs)) < 0.9


def test_degradation_raises_current_and_duration(rng):
    def measure(health):
        out = []
        for _ in range(25):
            ev = generate_event(CALIBRATED, health=health, env=Environment(),
                                dq=DataQuality(), rng=rng)
            c = ev.channel("ac_curr")
            out.append((np.median(c[c > 0.5]), ev.throw_samples))
        return np.mean([o[0] for o in out]), np.mean([o[1] for o in out])

    healthy_a, healthy_t = measure(1.0)
    worn_a, worn_t = measure(0.3)
    assert worn_a > healthy_a * 1.1, "wear must raise plateau current"
    assert worn_t > healthy_t * 1.05, "wear must lengthen the throw"


def test_cold_weather_raises_current(rng):
    def plateau(env):
        vals = []
        for _ in range(25):
            ev = generate_event(CALIBRATED, env=env, dq=DataQuality(), rng=rng)
            c = ev.channel("ac_curr")
            vals.append(np.median(c[c > 0.5]))
        return float(np.mean(vals))

    assert plateau(Environment(temperature_c=-15.0, ice_severity=0.6)) > plateau(
        Environment(temperature_c=25.0)
    ) * 1.1


def test_generation_is_reproducible():
    import numpy as np_

    a = generate_event(CALIBRATED, fault=FaultClass.E04_MOTOR, severity=0.6,
                       rng=np_.random.default_rng(99)).signals
    b = generate_event(CALIBRATED, fault=FaultClass.E04_MOTOR, severity=0.6,
                       rng=np_.random.default_rng(99)).signals
    np_.testing.assert_array_equal(a, b)


def test_data_quality_never_changes_the_label(rng):
    from pmdlib.sim.spec import FIELD_REALISTIC

    ev = generate_event(CALIBRATED, fault=FaultClass.E04_MOTOR, severity=0.7,
                        dq=FIELD_REALISTIC, rng=rng)
    assert ev.fault is FaultClass.E04_MOTOR
