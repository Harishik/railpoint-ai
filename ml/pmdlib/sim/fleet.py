"""Assemble a fleet of machines over their service lives into a dataset.

Splits are **by machine**, never by event. Two throws from the same machine
minutes apart are near-duplicates, so splitting on events would leak the test set
into training and inflate every metric - the same class of mistake that produced
the 2024 report's ">90% accuracy" after filling empty cells with zeros.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from ..utils.splits import DEFAULT_FRACS, machine_split
from .degradation import (
    SERVICE_HORIZON_CYCLES,
    Trajectory,
    severity_from_health,
    simulate_trajectory,
)
from .spec import (
    CALIBRATED,
    CHANNELS,
    DEGRADING_FAULTS,
    FAULT_TO_ERR_CODE,
    FIELD_REALISTIC,
    SUPPLY_CLASS_B,
    DataQuality,
    Environment,
    FaultClass,
    MachineSpec,
)
from .waveform import Event, generate_event

#: Faults that strike without warning rather than developing over time.
SHOCK_FAULTS: tuple[FaultClass, ...] = tuple(
    f for f in FaultClass if f is not FaultClass.NORMAL and f not in DEGRADING_FAULTS
)


@dataclass
class DatasetConfig:
    n_machines: int = 64
    #: Throws *recorded* per machine, spread evenly across ``horizon_cycles``.
    #: Recording a sample of a long life rather than every throw of a short one
    #: is what lets most machines reach a failure without the dataset — and the
    #: training run — growing five-fold. Measured over three seeds: 62% of
    #: machines fail in-horizon and `calib` receives 2-4 failing machines, against
    #: 21% and 0-2 when the first 800 throws were recorded one by one. Fault
    #: prevalence stays realistic (15% of throws, from 10%).
    cycles_per_machine: int = 800
    #: Simulated service life. Defaults to the live stream's horizon so training
    #: covers every RUL the console will ask about.
    horizon_cycles: int = SERVICE_HORIZON_CYCLES
    class_b_frac: float = 0.30
    unit_spread: float = 0.06
    #: Per-event probability of a sudden-onset fault, independent of health.
    shock_fault_prob: float = 0.022
    data_quality: DataQuality = FIELD_REALISTIC
    seasonal: bool = True
    cycles_per_year: int = 3000
    max_samples: int = 600
    seed: int = 42
    #: Fractions of *machines* assigned to each split.
    split_fracs: tuple[float, float, float, float] = DEFAULT_FRACS


def seasonal_environment(cycle: int, cycles_per_year: int, rng: np.random.Generator) -> Environment:
    """Daejeon-like annual weather: about -8 C in January to +30 C in August."""
    phase = 2.0 * np.pi * (cycle % cycles_per_year) / cycles_per_year
    temperature = 11.0 - 19.0 * np.cos(phase) + rng.normal(0.0, 3.0)
    winter = float(np.clip((2.0 - temperature) / 12.0, 0.0, 1.0))
    return Environment(
        temperature_c=float(temperature),
        humidity=float(np.clip(rng.beta(2.0, 3.0) + 0.25 * winter, 0.0, 1.0)),
        ice_severity=float(winter * rng.beta(1.4, 6.0)),
        supply_quality=float(rng.uniform(0.8, 1.35)),
    )


def _make_machine_specs(cfg: DatasetConfig, rng: np.random.Generator) -> list[MachineSpec]:
    """A fleet of individuals, not clones: every unit differs a little."""
    specs: list[MachineSpec] = []
    for i in range(cfg.n_machines):
        base = SUPPLY_CLASS_B if rng.random() < cfg.class_b_frac else CALIBRATED
        j = lambda: float(rng.normal(1.0, cfg.unit_spread))  # noqa: E731
        specs.append(
            replace(
                base,
                name=f"{base.name}-{i:02d}",
                plateau_a=base.plateau_a * j(),
                inrush_a=base.inrush_a * j(),
                throw_samples=max(40, int(base.throw_samples * j())),
                supply_v=base.supply_v + rng.normal(0.0, 1.8),
                sag_v=base.sag_v * j(),
            )
        )
    return specs


def _assign_splits(n: int, fracs: tuple[float, float, float, float], _rng: object = None) -> np.ndarray:
    """Split by machine id, not at random - see pmdlib.utils.splits."""
    return np.array([machine_split(f"PMD{i + 1:03d}", fracs) for i in range(n)])


def generate_dataset(cfg: DatasetConfig | None = None) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Build the full dataset.

    Returns ``(signals, lengths, meta)`` where ``signals`` is
    ``(n_events, max_samples, 5)`` float32 padded with NaN, ``lengths`` gives the
    true capture length of each event, and ``meta`` carries one row per event.
    """
    cfg = cfg or DatasetConfig()
    rng = np.random.default_rng(cfg.seed)

    specs = _make_machine_specs(cfg, rng)
    splits = _assign_splits(cfg.n_machines, cfg.split_fracs, rng)

    signals = np.full((cfg.n_machines * cfg.cycles_per_machine, cfg.max_samples, len(CHANNELS)),
                      np.nan, dtype=np.float32)
    lengths = np.zeros(cfg.n_machines * cfg.cycles_per_machine, dtype=np.int32)
    rows: list[dict] = []
    k = 0

    if cfg.horizon_cycles < cfg.cycles_per_machine:
        raise ValueError(
            f"horizon_cycles ({cfg.horizon_cycles}) must be at least cycles_per_machine "
            f"({cfg.cycles_per_machine}): a machine cannot record more throws than it lives"
        )
    # Evenly spaced through the service life. Every per-cycle quantity below —
    # health, RUL, fault activity, the season — is read at the true cycle number.
    recorded = np.unique(
        np.linspace(0, cfg.horizon_cycles - 1, cfg.cycles_per_machine).round().astype(int)
    )

    for m, spec in enumerate(specs):
        machine_id = f"PMD{m + 1:03d}"
        traj: Trajectory = simulate_trajectory(
            cfg.horizon_cycles, rng=rng, cycles_per_year=cfg.cycles_per_year
        )
        direction = "N"

        for cycle in (int(c) for c in recorded):
            # Points normally alternate, but a route can call the same position
            # twice in a row, so this is not a strict alternation.
            if rng.random() < 0.82:
                direction = "R" if direction == "N" else "N"

            env = (
                seasonal_environment(cycle, cfg.cycles_per_year, rng)
                if cfg.seasonal
                else Environment()
            )

            # Which fault, if any, is expressing itself on this throw?
            if traj.active[cycle]:
                fault = traj.mode
                severity = severity_from_health(float(traj.health[cycle]))
                origin = "degradation"
            elif rng.random() < cfg.shock_fault_prob:
                fault = SHOCK_FAULTS[int(rng.integers(len(SHOCK_FAULTS)))]
                severity = float(rng.beta(2.2, 1.8))
                origin = "shock"
            else:
                fault = FaultClass.NORMAL
                severity = 0.0
                origin = "none"

            ev: Event = generate_event(
                spec,
                fault=fault,
                severity=severity,
                direction=direction,
                health=float(traj.health[cycle]),
                env=env,
                dq=cfg.data_quality,
                machine_id=machine_id,
                event_num=cycle,
                rng=rng,
            )

            n = min(len(ev), cfg.max_samples)
            signals[k, :n] = ev.signals[:n]
            lengths[k] = n
            rows.append(
                {
                    "idx": k,
                    "machine_id": machine_id,
                    "spec": spec.name,
                    "split": splits[m],
                    "cycle": cycle,
                    "direction": direction,
                    "fault": fault.value,
                    "err_code": FAULT_TO_ERR_CODE[fault] or "",
                    "severity": round(severity, 4),
                    "fault_origin": origin,
                    "health": round(float(traj.health[cycle]), 4),
                    "rul": int(traj.rul[cycle]),
                    "failed": bool(traj.failed[cycle]),
                    "trajectory": traj.kind.value,
                    "degradation_mode": traj.mode.value,
                    "completed": ev.completed,
                    "throw_samples": ev.throw_samples,
                    "n_samples": n,
                    "truncated": ev.truncated,
                    "temperature_c": round(env.temperature_c, 2),
                    "ice_severity": round(env.ice_severity, 4),
                    "humidity": round(env.humidity, 4),
                    "dq_flags": "|".join(ev.meta["data_quality"]),
                    "is_anomaly": fault is not FaultClass.NORMAL,
                }
            )
            k += 1

    meta = pd.DataFrame(rows)
    return signals[:k], lengths[:k], meta


# ---------------------------------------------------------------------------
# Stratified scenario sweep
# ---------------------------------------------------------------------------

#: Named operating regimes, spanning the Korean annual range.
ENVIRONMENT_REGIMES: dict[str, Environment] = {
    "summer": Environment(temperature_c=28.0, humidity=0.72, ice_severity=0.0, supply_quality=1.1),
    "mild": Environment(temperature_c=15.0, humidity=0.45, ice_severity=0.0, supply_quality=1.0),
    "winter": Environment(temperature_c=-5.0, humidity=0.50, ice_severity=0.15, supply_quality=1.2),
    "icy": Environment(temperature_c=-12.0, humidity=0.78, ice_severity=0.70, supply_quality=1.35),
}

#: Clean bench capture versus messy field telemetry.
DQ_MODES: dict[str, DataQuality] = {"clean": DataQuality(), "field": FIELD_REALISTIC}


@dataclass
class StratifiedConfig:
    """A balanced sweep over every scenario axis.

    ``generate_dataset`` reproduces *realistic prevalence*, where shock faults are
    genuinely rare and a 15-class classifier would see three examples of some
    classes. This sweep instead covers the grid uniformly, which is what the
    classifier needs to train on. Both are produced; each is used for what it is
    honest for, and the split is by machine in both cases.
    """

    n_machines: int = 64
    severities: tuple[float, ...] = (0.15, 0.35, 0.55, 0.75, 0.95)
    replicates: int = 6
    regimes: tuple[str, ...] = ("summer", "mild", "winter", "icy")
    dq_modes: tuple[str, ...] = ("clean", "field")
    directions: tuple[str, ...] = ("N", "R")
    class_b_frac: float = 0.30
    unit_spread: float = 0.06
    max_samples: int = 600
    seed: int = 7
    split_fracs: tuple[float, float, float, float] = DEFAULT_FRACS


def _health_for(fault: FaultClass, severity: float, rng: np.random.Generator) -> float:
    """Health consistent with the fault being shown.

    A machine expressing an advanced wear fault cannot also be in perfect health;
    a machine struck by a sudden shock fault usually is.
    """
    if fault is FaultClass.NORMAL:
        return float(rng.uniform(0.85, 1.0))
    if fault in DEGRADING_FAULTS:
        return float(np.clip(1.0 - severity * 0.7 + rng.normal(0.0, 0.04), 0.05, 1.0))
    return float(rng.uniform(0.78, 1.0))


def generate_stratified(
    cfg: StratifiedConfig | None = None,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Sweep every (fault x severity x direction x machine class x weather x data
    quality) cell with ``replicates`` events each."""
    cfg = cfg or StratifiedConfig()
    rng = np.random.default_rng(cfg.seed)

    pool = _make_machine_specs(
        DatasetConfig(
            n_machines=cfg.n_machines,
            class_b_frac=cfg.class_b_frac,
            unit_spread=cfg.unit_spread,
        ),
        rng,
    )
    splits = _assign_splits(cfg.n_machines, cfg.split_fracs, rng)
    faults = list(FaultClass)

    rows: list[dict] = []
    buf: list[np.ndarray] = []
    lens: list[int] = []
    k = 0

    for fault in faults:
        # Severity is meaningless for NORMAL, so it gets one slot and
        # proportionally more replicates, keeping the classes balanced.
        sev_grid = (0.0,) if fault is FaultClass.NORMAL else cfg.severities
        reps = cfg.replicates * (len(cfg.severities) if fault is FaultClass.NORMAL else 1)

        for severity in sev_grid:
            for regime in cfg.regimes:
                for dq_name in cfg.dq_modes:
                    for direction in cfg.directions:
                        for _ in range(reps):
                            m = int(rng.integers(cfg.n_machines))
                            spec = pool[m]
                            health = _health_for(fault, severity, rng)
                            ev = generate_event(
                                spec,
                                fault=fault,
                                severity=severity,
                                direction=direction,
                                health=health,
                                env=ENVIRONMENT_REGIMES[regime],
                                dq=DQ_MODES[dq_name],
                                machine_id=f"PMD{m + 1:03d}",
                                event_num=k,
                                rng=rng,
                            )
                            n = min(len(ev), cfg.max_samples)
                            padded = np.full((cfg.max_samples, len(CHANNELS)), np.nan, np.float32)
                            padded[:n] = ev.signals[:n]
                            buf.append(padded)
                            lens.append(n)
                            rows.append(
                                {
                                    "idx": k,
                                    "machine_id": f"PMD{m + 1:03d}",
                                    "spec": spec.name,
                                    "split": splits[m],
                                    "direction": direction,
                                    "fault": fault.value,
                                    "err_code": FAULT_TO_ERR_CODE[fault] or "",
                                    "severity": round(float(severity), 4),
                                    "health": round(health, 4),
                                    "regime": regime,
                                    "dq_mode": dq_name,
                                    "completed": ev.completed,
                                    "throw_samples": ev.throw_samples,
                                    "n_samples": n,
                                    "truncated": ev.truncated,
                                    "temperature_c": ENVIRONMENT_REGIMES[regime].temperature_c,
                                    "ice_severity": ENVIRONMENT_REGIMES[regime].ice_severity,
                                    "dq_flags": "|".join(ev.meta["data_quality"]),
                                    "is_anomaly": fault is not FaultClass.NORMAL,
                                }
                            )
                            k += 1

    return np.stack(buf), np.asarray(lens, dtype=np.int32), pd.DataFrame(rows)
