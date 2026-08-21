"""Generate one point-machine throw event across all five channels.

The healthy current *shape* is not guessed: it is a template fitted directly from
the four completed throws in the real Sehwa extract (see
``scripts/fit_template.py`` and ``templates.json``). Amplitude, timing, supply
behaviour, indication sequencing and every fault deformation are layered on top
of that template as physics, so the healthy case matches the real data by
construction and the faults are principled departures from it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from .faults import FaultEffect, fault_effect
from .spec import CHANNELS, DataQuality, Environment, FaultClass, MachineSpec

_TEMPLATE_PATH = Path(__file__).with_name("templates.json")

#: Indication lines are clamped to their supply rail, allowing a little
#: inductive overshoot when a contact opens. 24 V DC circuits do not swing
#: to 75 V because a contact chattered.
RAIL_OVERSHOOT = 1.15


@lru_cache(maxsize=1)
def healthy_template() -> np.ndarray:
    """Plateau-normalised healthy throw shape, fitted from the real traces."""
    payload = json.loads(_TEMPLATE_PATH.read_text())
    return np.asarray(payload["current"], dtype=float)


@dataclass
class Event:
    """One recorded switching event."""

    machine_id: str
    event_num: int
    direction: str                # "N" (정위) or "R" (반위)
    fault: FaultClass
    severity: float
    health: float
    signals: np.ndarray           # (n_samples, 5), channel order == CHANNELS
    completed: bool
    throw_samples: int
    truncated: bool               # hit the hardware capture cap
    meta: dict = field(default_factory=dict)

    def channel(self, name: str) -> np.ndarray:
        return self.signals[:, CHANNELS.index(name)]

    def __len__(self) -> int:
        return int(self.signals.shape[0])


def _resample(template: np.ndarray, n: int) -> np.ndarray:
    return np.interp(np.linspace(0.0, 1.0, n), np.linspace(0.0, 1.0, template.size), template)


def _build_current(
    spec: MachineSpec,
    eff: FaultEffect,
    plateau_a: float,
    inrush_scale: float,
    throw_len: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """The motor-current trace across the throw window alone."""
    shape = _resample(healthy_template(), throw_len)

    # shape is normalised so 1.0 == plateau; the excess above 1.0 is the inrush
    # transient. Scaling only the excess lets a fault raise the start-up peak
    # without disturbing the plateau, and vice versa.
    body = plateau_a * shape
    if inrush_scale != 1.0:
        body = body + plateau_a * np.clip(shape - 1.0, 0.0, None) * (inrush_scale - 1.0)

    if eff.plateau_slope_a:
        body = body + eff.plateau_slope_a * np.linspace(0.0, 1.0, throw_len)

    if eff.harmonic_a and eff.harmonic_period:
        phase = 2.0 * np.pi * np.arange(throw_len) / eff.harmonic_period
        body = body + eff.harmonic_a * np.sin(phase + rng.uniform(0, 2 * np.pi))

    body = body + rng.normal(0.0, spec.plateau_ripple_a * eff.ripple_scale, throw_len)

    if eff.stall_a is not None:
        body = np.minimum(body, eff.stall_a)

    # Brief drive dropouts (sticking relay, intermittent cable).
    for _ in range(eff.interruptions):
        if throw_len < 20:
            break
        start = int(rng.integers(throw_len // 8, max(throw_len // 8 + 1, throw_len - 10)))
        width = int(rng.integers(2, 7))
        body[start : start + width] = spec.idle_a

    return np.clip(body, spec.idle_a, None)


def _build_indication(
    spec: MachineSpec,
    eff: FaultEffect,
    direction: str,
    n_total: int,
    t0: int,
    t1: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Position indication (output_n_volt) and its complement (output_r_volt).

    Measured from the real extract, and it is a **three-state** signal, not a
    ramp: the indication circuit is energised only while the switch is *locked
    and detected* in a position.

        +V  locked at Normal (정위)
         0  in transit - neither position detected
        -V  locked at Reverse (반위)

    In PMD014#2593, 78.8% of samples sit in [-2, +2] V: the line is at 0 for the
    entire throw, with fast edges at each end. Two real fault exemplars fall
    straight out of this:

    * PMD055 (E01) reads ~0 V for all 600 samples - permanently in transit,
      never locking. That *is* the locking-latch diagnosis.
    * PMD014#2594 holds -23.9 V throughout - the machine never unlocked, because
      the motor never started.
    """
    v = spec.indication_v
    start_v = v if direction == "R" else -v
    end_v = -v if direction == "R" else v
    edge = max(2, spec.indication_transition_samples)

    out_n = np.full(n_total, start_v, dtype=float)

    if eff.motor_starts:
        delay = eff.indication_delay
        unlock_at = min(t0 + delay, n_total)
        lock_at = min(t1 + delay, n_total)

        # Leaving the locked position: the detection circuit drops out.
        out_n[unlock_at:] = 0.0
        edge_end = min(unlock_at + edge, n_total)
        if edge_end > unlock_at:
            out_n[unlock_at:edge_end] = np.linspace(start_v, 0.0, edge_end - unlock_at)

        # Arriving at the target. indication_progress is how completely the
        # machine locks: 1.0 is a clean lock, ~0 leaves it stuck in transit.
        final = end_v * eff.indication_progress
        if lock_at < n_total:
            out_n[lock_at:] = final
            edge_end = min(lock_at + edge, n_total)
            if edge_end > lock_at:
                out_n[lock_at:edge_end] = np.linspace(0.0, final, edge_end - lock_at)

    # Contact chatter, concentrated where the contacts actually move. A bouncing
    # contact snaps *between* rail states; it cannot drive the line beyond its
    # own supply, so this interpolates toward another point on the rail rather
    # than adding unbounded noise.
    if eff.indication_bounce > 0 and eff.motor_starts and t1 > t0:
        for _ in range(int(rng.integers(2, 9))):
            at = int(rng.integers(min(t0, n_total - 1), min(t1 + edge, n_total)))
            width = int(rng.integers(1, 5))
            target = rng.uniform(-v, v)
            seg = out_n[at : at + width]
            out_n[at : at + width] = seg + (target - seg) * eff.indication_bounce

    # Insulation leakage bleeds the rail toward 0 V; it can never exceed it.
    out_n = out_n * (1.0 - eff.indication_leak)
    out_n = out_n + rng.normal(0.0, spec.indication_noise_v * eff.indication_noise_scale, n_total)
    # Physical rail limit, with a small allowance for inductive overshoot.
    out_n = np.clip(out_n, -v * RAIL_OVERSHOOT, v * RAIL_OVERSHOOT)

    # The complementary circuit: energised at the opposite position, and also 0
    # in transit. Consistent with PMD055, where both lines read ~0 throughout.
    out_r = -out_n + rng.normal(0.0, spec.indication_noise_v, n_total)
    return out_n, out_r


def _apply_data_quality(
    signals: np.ndarray, dq: DataQuality, spec: MachineSpec, rng: np.random.Generator
) -> tuple[np.ndarray, list[str]]:
    """Recording-chain defects. These never change the event's label."""
    n = signals.shape[0]
    applied: list[str] = []

    if rng.random() < dq.dropout_prob:
        width = max(2, int(n * rng.uniform(0.01, dq.dropout_max_frac)))
        at = int(rng.integers(0, max(1, n - width)))
        ch = int(rng.integers(0, signals.shape[1]))
        signals[at : at + width, ch] = np.nan
        applied.append("dropout")

    if rng.random() < dq.stuck_prob:
        width = max(3, int(n * rng.uniform(0.02, 0.15)))
        at = int(rng.integers(0, max(1, n - width)))
        ch = int(rng.integers(0, signals.shape[1]))
        signals[at : at + width, ch] = signals[at, ch]
        applied.append("stuck")

    if rng.random() < dq.clip_prob:
        signals[:, 0] = np.minimum(signals[:, 0], dq.clip_level_a)
        applied.append("clipped")

    if rng.random() < dq.emi_burst_prob:
        width = int(rng.integers(3, 20))
        at = int(rng.integers(0, max(1, n - width)))
        signals[at : at + width, 0] += rng.normal(0.0, dq.emi_amplitude_a, width)
        applied.append("emi")

    if rng.random() < dq.missing_channel_prob or not spec.has_output_r:
        # PMD014 has no output_r instrumentation at all (1224/1224 null).
        signals[:, CHANNELS.index("output_r_volt")] = np.nan
        if not spec.has_output_r:
            applied.append("no_output_r")
        else:
            applied.append("missing_channel")

    if dq.quantisation_a:
        # The real extract is quantised to 0.01 A / 0.01 V.
        signals[:, 0] = np.round(signals[:, 0] / dq.quantisation_a) * dq.quantisation_a
        signals[:, 1] = np.round(signals[:, 1], 2)

    return signals, applied


def generate_event(
    spec: MachineSpec,
    *,
    fault: FaultClass = FaultClass.NORMAL,
    severity: float = 0.0,
    direction: str = "N",
    health: float = 1.0,
    env: Environment | None = None,
    dq: DataQuality | None = None,
    machine_id: str = "PMD001",
    event_num: int = 0,
    rng: np.random.Generator | None = None,
) -> Event:
    """Generate one throw.

    ``health`` in [0, 1] is the machine's hidden condition (1 = as-new) and
    modulates friction, duration and motor wear even when ``fault`` is NORMAL.
    That coupling is what makes remaining-useful-life labels meaningful.
    """
    rng = rng or np.random.default_rng()
    env = env or Environment()
    dq = dq or DataQuality()
    eff = fault_effect(fault, severity, rng)

    # --- effective parameters: health, then environment, then fault --------
    wear = 1.0 - float(np.clip(health, 0.0, 1.0))
    friction = (1.0 + spec.friction_gain * wear) * env.cold_friction_factor * env.ice_friction_factor

    plateau_a = spec.plateau_a * friction * eff.plateau_scale
    inrush_scale = (1.0 + spec.motor_wear_gain * wear) * eff.inrush_scale
    duration = (1.0 + spec.duration_gain * wear) * eff.duration_scale * (0.5 + 0.5 * friction)

    throw_len = max(6, int(round(spec.throw_samples * duration)))

    # --- timeline ---------------------------------------------------------
    n_pre = int(rng.integers(*spec.pre_samples))
    n_post = int(rng.integers(*spec.post_samples))
    delay = eff.start_delay_samples
    t0 = n_pre + delay
    t1 = t0 + throw_len
    n_total = t1 + n_post

    truncated = n_total > spec.capture_cap
    if truncated:
        # The recorder's buffer is finite: a throw that never ends is captured
        # as exactly capture_cap samples. This is precisely why both real PMD055
        # events are 600 samples long.
        n_total = spec.capture_cap
        t1 = min(t1, n_total)

    # --- current ----------------------------------------------------------
    current = np.full(n_total, spec.idle_a, dtype=float)
    if eff.motor_starts and t1 > t0:
        body = _build_current(spec, eff, plateau_a, inrush_scale, t1 - t0, rng)
        current[t0:t1] = body
    current += np.abs(rng.normal(0.0, spec.idle_a * 0.12, n_total))

    # --- supply -----------------------------------------------------------
    supply = np.full(n_total, spec.supply_v + eff.supply_offset_v, dtype=float)
    supply += rng.normal(0.0, spec.supply_noise_v * env.supply_quality, n_total)
    if eff.supply_instability_v:
        supply += rng.normal(0.0, eff.supply_instability_v, n_total)
    # Sag grows sub-linearly with load; exponent measured from the real traces.
    load = np.clip(current / spec.plateau_a, 0.0, None)
    supply -= spec.sag_v * eff.sag_scale * np.power(load, spec.sag_exponent)

    # --- drive command (as_volt) -----------------------------------------
    # 0 V idle, +V driving to Normal, -V driving to Reverse. Verified against
    # all seven real events. A drive that is never cut stays at +-V to the end,
    # which is the signature that separates E01 from E03.
    drive_sign = 1.0 if direction == "N" else -1.0
    as_volt = np.zeros(n_total, dtype=float)
    drive_end = n_total if not eff.drive_cut else min(t1, n_total)
    as_volt[n_pre:drive_end] = drive_sign * spec.indication_v
    as_volt += rng.normal(0.0, spec.indication_noise_v * eff.indication_noise_scale, n_total)
    as_volt = np.clip(as_volt, -spec.indication_v * RAIL_OVERSHOOT, spec.indication_v * RAIL_OVERSHOOT)

    # --- position indication ---------------------------------------------
    out_n, out_r = _build_indication(spec, eff, direction, n_total, t0, t1, rng)

    signals = np.column_stack([current, supply, as_volt, out_n, out_r])
    signals, dq_applied = _apply_data_quality(signals, dq, spec, rng)

    return Event(
        machine_id=machine_id,
        event_num=event_num,
        direction=direction,
        fault=fault,
        severity=float(severity),
        health=float(health),
        signals=signals,
        completed=bool(eff.completes and eff.motor_starts),
        throw_samples=int(t1 - t0) if eff.motor_starts else 0,
        truncated=truncated,
        meta={
            "spec": spec.name,
            "plateau_a": round(plateau_a, 4),
            "friction": round(friction, 4),
            "temperature_c": env.temperature_c,
            "ice_severity": env.ice_severity,
            "data_quality": dq_applied,
            "drive_cut": eff.drive_cut,
            "motor_started": eff.motor_starts,
        },
    )
