"""How each fault class deforms a throw.

Each entry answers one question: *if this component fails, what changes in the
five recorded channels?* The answers are grounded in the real extract wherever it
provides an exemplar, and in the point-machine condition-monitoring literature
otherwise. Where the real data settles a question, the docstring says so.

``severity`` in [0, 1] scales every effect, so the same class spans "just
detectable" to "hard failure". That continuity is what makes the dataset useful
for remaining-useful-life work rather than only for classification.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .spec import FaultClass


@dataclass
class FaultEffect:
    """Parameter deltas applied to an otherwise-healthy throw."""

    # Current channel
    plateau_scale: float = 1.0
    inrush_scale: float = 1.0
    duration_scale: float = 1.0
    plateau_slope_a: float = 0.0      # linear ramp added across the throw
    ripple_scale: float = 1.0
    harmonic_a: float = 0.0           # periodic torque ripple amplitude
    harmonic_period: int = 0          # in samples
    interruptions: int = 0            # brief current dropouts
    start_delay_samples: int = 0
    stall_a: float | None = None      # current the motor settles to when stalled

    # Supply channel
    sag_scale: float = 1.0
    supply_offset_v: float = 0.0
    supply_instability_v: float = 0.0

    # Sequencing
    motor_starts: bool = True
    completes: bool = True
    drive_cut: bool = True            # as_volt returns to 0 when the drive stops

    # Indication channels
    indication_progress: float = 1.0  # fraction of the N->R traverse achieved
    indication_delay: int = 0
    indication_bounce: float = 0.0
    #: Fraction by which the indication rails are pulled toward 0 V. Leakage
    #: degrades the rail; it cannot drive it past its own supply.
    indication_leak: float = 0.0
    indication_noise_scale: float = 1.0


def _lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * t


def fault_effect(fault: FaultClass, severity: float, rng: np.random.Generator) -> FaultEffect:
    """Build the effect for one fault at one severity."""
    s = float(np.clip(severity, 0.0, 1.0))
    e = FaultEffect()

    if fault is FaultClass.NORMAL:
        return e

    # --- Mechanical -------------------------------------------------------
    if fault is FaultClass.E01_LOCK_LATCH:
        # Grounded in PMD055#5416/#5417: the throw runs to the 600-sample capture
        # cap at an elevated plateau, indication never arrives, and as_volt stays
        # at +-23 V because the drive is never cut.
        e.completes = False
        e.drive_cut = False
        e.duration_scale = _lerp(1.6, 4.0, s)
        e.plateau_scale = _lerp(1.10, 1.75, s)
        e.indication_progress = _lerp(0.75, 0.05, s)
        e.ripple_scale = _lerp(1.1, 1.6, s)

    elif fault is FaultClass.OBSTRUCTION:
        # Distinguished from E01 by the *shape*: the motor works against a rising
        # resistance, so current ramps upward toward stall rather than holding a
        # flat elevated plateau.
        e.completes = False
        e.drive_cut = True
        e.duration_scale = _lerp(1.3, 2.6, s)
        e.plateau_slope_a = _lerp(1.5, 7.0, s)
        e.stall_a = _lerp(11.0, 15.5, s)
        e.indication_progress = _lerp(0.6, 0.1, s)
        e.ripple_scale = _lerp(1.2, 2.0, s)

    elif fault is FaultClass.FRICTION_HIGH:
        # The classic degradation driver: more torque for longer, same shape.
        e.plateau_scale = _lerp(1.05, 1.55, s)
        e.duration_scale = _lerp(1.03, 1.35, s)
        e.inrush_scale = _lerp(1.02, 1.20, s)
        e.ripple_scale = _lerp(1.0, 1.3, s)

    elif fault is FaultClass.MISALIGNMENT:
        # Throw completes, but closure is marginal: the final locking segment is
        # abnormal and the indication only just reaches its endpoint.
        e.plateau_scale = _lerp(1.02, 1.18, s)
        e.plateau_slope_a = _lerp(0.2, 1.2, s)
        e.indication_progress = _lerp(0.98, 0.80, s)
        e.indication_bounce = _lerp(0.05, 0.35, s)
        e.duration_scale = _lerp(1.02, 1.15, s)

    elif fault is FaultClass.GEARBOX_WEAR:
        # Worn teeth impose a periodic torque ripple at the mesh frequency,
        # which is what separates this from plain friction.
        e.harmonic_a = _lerp(0.12, 0.85, s)
        e.harmonic_period = int(rng.integers(7, 16))
        e.plateau_scale = _lerp(1.02, 1.22, s)
        e.ripple_scale = _lerp(1.1, 1.8, s)

    # --- Detection and indication ----------------------------------------
    elif fault is FaultClass.E02_DETECTOR:
        # Mechanically fine; detection arrives late and chatters.
        e.indication_delay = int(_lerp(8, 55, s))
        e.indication_bounce = _lerp(0.15, 0.75, s)
        e.plateau_scale = _lerp(1.0, 1.06, s)

    elif fault is FaultClass.E07_CIRCUIT_CONTROLLER:
        # Contact bank bounce: heavy chatter on the indication lines with the
        # current channel essentially untouched. The pair (E02, E07) is the
        # hardest discrimination in the taxonomy, deliberately.
        e.indication_bounce = _lerp(0.3, 1.0, s)
        e.indication_noise_scale = _lerp(2.0, 9.0, s)
        e.indication_delay = int(_lerp(0, 12, s))

    elif fault is FaultClass.INDICATION_LEAKAGE:
        # Damp insulation pulls the indication rails toward zero. Subtle, and the
        # only severity-1 class - it is the early warning, not the failure.
        e.indication_leak = _lerp(0.02, 0.28, s)
        e.indication_noise_scale = _lerp(1.2, 3.0, s)

    # --- Control ----------------------------------------------------------
    elif fault is FaultClass.E03_LINE_RELAY:
        # Grounded in PMD014#2594: as_volt pulses (the command *was* issued) but
        # output_n_volt never moves and the supply shows no sag, because the
        # motor drew no load. The drive is then cut on timeout, so as_volt
        # returns to 0 - which is exactly what separates it from E01.
        if s > 0.55:
            e.motor_starts = False
            e.completes = False
            e.drive_cut = True
            e.indication_progress = 0.0
            e.duration_scale = _lerp(0.9, 0.6, s)
        else:
            e.indication_bounce = _lerp(0.1, 0.5, s / 0.55)
            e.indication_delay = int(_lerp(4, 25, s / 0.55))

    elif fault is FaultClass.E05_CONTROL_RELAY:
        # Sticking contacts: the drive engages late and drops out briefly.
        e.start_delay_samples = int(_lerp(5, 60, s))
        e.interruptions = int(_lerp(0, 4, s))
        e.indication_delay = int(_lerp(0, 15, s))

    # --- Electrical / supply ---------------------------------------------
    elif fault is FaultClass.E04_MOTOR:
        # Brush and bearing wear: a harder start and a noisier run.
        e.inrush_scale = _lerp(1.15, 2.10, s)
        e.plateau_scale = _lerp(1.03, 1.30, s)
        e.ripple_scale = _lerp(1.3, 3.2, s)
        e.harmonic_a = _lerp(0.05, 0.40, s)
        e.harmonic_period = int(rng.integers(3, 8))
        e.duration_scale = _lerp(1.0, 1.15, s)

    elif fault is FaultClass.E06_CABLE:
        # Added series resistance: deeper sag, unstable rail, brief dropouts.
        e.sag_scale = _lerp(1.2, 2.6, s)
        e.supply_instability_v = _lerp(0.5, 5.0, s)
        e.interruptions = int(_lerp(0, 3, s))
        e.plateau_scale = _lerp(0.99, 0.88, s)

    elif fault is FaultClass.SUPPLY_UNDERVOLTAGE:
        # Low rail: the motor pulls more current for longer at less torque.
        e.supply_offset_v = -_lerp(8.0, 35.0, s)
        e.plateau_scale = _lerp(1.05, 1.35, s)
        e.duration_scale = _lerp(1.05, 1.45, s)
        e.inrush_scale = _lerp(0.95, 0.75, s)

    elif fault is FaultClass.PHASE_LOSS:
        # Single-phasing: severe ripple at twice line frequency, high current,
        # and the throw usually does not complete.
        e.plateau_scale = _lerp(1.3, 1.9, s)
        e.ripple_scale = _lerp(2.5, 6.0, s)
        e.harmonic_a = _lerp(0.6, 2.2, s)
        e.harmonic_period = 6
        e.duration_scale = _lerp(1.3, 2.2, s)
        e.sag_scale = _lerp(1.4, 2.4, s)
        e.completes = s < 0.5
        e.indication_progress = _lerp(0.9, 0.15, s)

    else:  # pragma: no cover - exhaustive above
        raise ValueError(f"no effect defined for {fault}")

    return e
