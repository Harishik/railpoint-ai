"""Machine specifications, fault taxonomy and scenario axes.

Every constant in ``CALIBRATED`` is measured from the four completed throws in
the real Sehwa extract (PMD014 #2593/#2595/#2596/#2597), not invented. The
derivation is in ``docs/DATA.md``; ``pmdlib.sim.calibrate`` re-checks generated
signals against the real ones and fails CI if they drift.

Note on which real events count as a healthy *current* reference: all seven real
events carry a fault code, but PMD014's code is E03 (무극선조계전기, a control
relay). A relay fault lives in the control circuit, not the motor, and those four
throws do complete with a textbook current profile. Their current channel is
therefore usable as a healthy reference. PMD014#2594 (motor never started) and
both PMD055 events (stalled throw) are used as fault exemplars instead.

Signal conventions, all verified against the real extract:

* ``ac_curr``       - motor current. Idle ~0.07 A, inrush ~9.1 A, plateau ~3.8 A.
* ``ac_volt``       - single-phase supply. Sags ~5.6 V under motor load.
* ``as_volt``       - drive command. 0 V idle; +V while driving to Normal,
                      -V while driving to Reverse. Returns to 0 when the drive
                      is cut. Staying at +-V means the drive was never cut.
* ``output_n_volt`` - position indication. +V at Normal, -V at Reverse, passing
                      through 0 in transit.
* ``output_r_volt`` - complementary indication; absent on some machines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FaultClass(StrEnum):
    """Fault taxonomy, anchored on Sehwa's own E01-E07 maintenance codes.

    The E-codes name *components*, not failure modes, so each E-class below is
    the characteristic signal signature of that component failing. The remaining
    classes cover mechanical and supply conditions that the code table does not
    enumerate but that dominate real point-machine failure statistics.
    """

    NORMAL = "NORMAL"

    # --- Mechanical -------------------------------------------------------
    E01_LOCK_LATCH = "E01_LOCK_LATCH"        # 기억쇠 - latch never engages
    OBSTRUCTION = "OBSTRUCTION"              # 전환 장애물 - foreign object
    FRICTION_HIGH = "FRICTION_HIGH"          # 마찰 증가 - lubrication loss
    MISALIGNMENT = "MISALIGNMENT"            # 밀착 불량 - poor closure
    GEARBOX_WEAR = "GEARBOX_WEAR"            # 감속기 마모 - tooth-mesh ripple

    # --- Detection and indication ----------------------------------------
    E02_DETECTOR = "E02_DETECTOR"            # 디텍터 - late/chattering detection
    E07_CIRCUIT_CONTROLLER = "E07_CIRCUIT_CONTROLLER"  # 회로제어기 - contact bounce
    INDICATION_LEAKAGE = "INDICATION_LEAKAGE"  # 표시회로 절연저하 - insulation loss

    # --- Control ----------------------------------------------------------
    E03_LINE_RELAY = "E03_LINE_RELAY"        # 무극선조계전기
    E05_CONTROL_RELAY = "E05_CONTROL_RELAY"  # 제어계전기

    # --- Electrical / supply ---------------------------------------------
    E04_MOTOR = "E04_MOTOR"                  # 전동기 - brush/bearing wear
    E06_CABLE = "E06_CABLE"                  # 케이블 - resistive/intermittent
    SUPPLY_UNDERVOLTAGE = "SUPPLY_UNDERVOLTAGE"  # 전원 전압 저하
    PHASE_LOSS = "PHASE_LOSS"                # 결상 - single-phasing


#: (Korean, English, subsystem, severity 1-3). Severity 3 blocks the throw.
FAULT_META: dict[FaultClass, tuple[str, str, str, int]] = {
    FaultClass.NORMAL: ("정상", "Normal", "-", 0),
    FaultClass.E01_LOCK_LATCH: ("기억쇠", "Locking latch never engages", "lock", 3),
    FaultClass.OBSTRUCTION: ("전환 장애물", "Obstruction in the throw path", "mechanical", 3),
    FaultClass.FRICTION_HIGH: ("마찰 증가", "Excessive friction / lubrication loss", "mechanical", 2),
    FaultClass.MISALIGNMENT: ("밀착 불량", "Switch-rail closure out of tolerance", "mechanical", 2),
    FaultClass.GEARBOX_WEAR: ("감속기 마모", "Gearbox wear", "mechanical", 2),
    FaultClass.E02_DETECTOR: ("디텍터", "Detector rod fault", "detection", 2),
    FaultClass.E07_CIRCUIT_CONTROLLER: ("회로제어기", "Circuit controller contact bounce", "indication", 2),
    FaultClass.INDICATION_LEAKAGE: ("표시회로 절연저하", "Indication circuit insulation loss", "indication", 1),
    FaultClass.E03_LINE_RELAY: ("무극선조계전기", "Non-polarised line relay fault", "control", 3),
    FaultClass.E05_CONTROL_RELAY: ("제어계전기", "Control relay fault", "control", 2),
    FaultClass.E04_MOTOR: ("전동기", "Motor brush / bearing wear", "motor", 2),
    FaultClass.E06_CABLE: ("케이블", "Resistive or intermittent cable", "power", 2),
    FaultClass.SUPPLY_UNDERVOLTAGE: ("전원 전압 저하", "Supply undervoltage", "power", 2),
    FaultClass.PHASE_LOSS: ("결상", "Supply phase loss / single-phasing", "power", 3),
}

#: Maps a fault class back to the Sehwa maintenance code, where one exists.
FAULT_TO_ERR_CODE: dict[FaultClass, str | None] = {
    FaultClass.NORMAL: None,
    FaultClass.E01_LOCK_LATCH: "E01",
    FaultClass.E02_DETECTOR: "E02",
    FaultClass.E03_LINE_RELAY: "E03",
    FaultClass.E04_MOTOR: "E04",
    FaultClass.E05_CONTROL_RELAY: "E05",
    FaultClass.E06_CABLE: "E06",
    FaultClass.E07_CIRCUIT_CONTROLLER: "E07",
    FaultClass.OBSTRUCTION: None,
    FaultClass.FRICTION_HIGH: None,
    FaultClass.MISALIGNMENT: None,
    FaultClass.GEARBOX_WEAR: None,
    FaultClass.INDICATION_LEAKAGE: None,
    FaultClass.SUPPLY_UNDERVOLTAGE: None,
    FaultClass.PHASE_LOSS: None,
}

#: Faults *capable* of preventing the throw from completing, i.e. severity 3.
#:
#: Whether one actually blocks depends on how far it has progressed: mild
#: single-phasing or light relay chatter still lets the machine throw, and only
#: becomes blocking past roughly half severity. Treat this as "can block", not
#: "always blocks" - see ``blocks_at`` for the severity-aware question.
CRITICAL_FAULTS: frozenset[FaultClass] = frozenset(
    f for f, meta in FAULT_META.items() if meta[3] == 3
)

#: Severity above which a critical fault reliably prevents the throw.
BLOCKING_SEVERITY = 0.6


def blocks_at(fault: FaultClass, severity: float) -> bool:
    """Whether this fault, at this severity, should prevent the throw."""
    return fault in CRITICAL_FAULTS and severity >= BLOCKING_SEVERITY

#: Faults that develop gradually and therefore drive remaining-useful-life.
#: The rest are modelled as shock (sudden-onset) events.
DEGRADING_FAULTS: tuple[FaultClass, ...] = (
    FaultClass.FRICTION_HIGH,
    FaultClass.E04_MOTOR,
    FaultClass.GEARBOX_WEAR,
    FaultClass.MISALIGNMENT,
    FaultClass.E02_DETECTOR,
    FaultClass.INDICATION_LEAKAGE,
)

#: The five channels, in canonical order. Matches the real extract's columns.
CHANNELS: tuple[str, ...] = ("ac_curr", "ac_volt", "as_volt", "output_n_volt", "output_r_volt")


@dataclass(frozen=True)
class MachineSpec:
    """Physical parameters of one point machine.

    Defaults are the values measured from the real PMD014 throws.
    """

    name: str = "PMD-A"

    # Current channel (A) - measured.
    idle_a: float = 0.0747        # measured mean between throws
    #: Measured spread of the idle current (0.050-0.090 A typical). Modelling
    #: this as a one-sided floor made the synthetic minimum a constant, which is
    #: not what a real quiescent current looks like.
    idle_noise_a: float = 0.0095
    inrush_a: float = 9.14
    plateau_a: float = 3.83
    plateau_ripple_a: float = 0.10
    stall_a: float = 15.5           # current when the motor is fully loaded

    # Timing, in samples.
    throw_samples: int = 205        # measured 205-206 across all four healthy throws
    #: Idle captured before the drive command. Real drive-on lands at sample
    #: 9-10 in every healthy trace, so the pre-roll is short and consistent.
    pre_samples: tuple[int, int] = (6, 14)
    #: Idle captured after the drive is cut. Real captures end ~11 samples later;
    #: the long tail is the drive *hold*, accounted for separately.
    post_samples: tuple[int, int] = (5, 20)
    capture_cap: int = 600          # hardware buffer; PMD055 hits exactly this

    # Supply (V) - measured.
    supply_v: float = 219.0
    supply_noise_v: float = 0.9
    sag_v: float = 5.64             # measured 5.64 +- 0.36
    #: Sag grows sub-linearly with load. Exponent 0.9 reproduces the real
    #: 13.6 V drop at the 2.66x inrush peak from a 5.64 V drop at plateau.
    sag_exponent: float = 0.9

    # Indication lines (V) - measured; the real lines swing about +-23.5 V.
    #: Mean rail magnitude, measured at 23.43 V.
    indication_v: float = 23.43
    #: The real rails are not balanced: +22.95 V against -23.91 V, so the
    #: negative rail sits ~0.96 V further from zero. Small, but it shifts every
    #: indication min/max feature if ignored.
    rail_asymmetry_v: float = 0.96
    #: Measured from the real rails and the in-transit segment: values sit at
    #: 0.05 / 0.02 / -0.02 and 22.90 / 22.93 / 22.96, so the noise floor is
    #: ~0.03 V, not the 0.15 V first assumed.
    indication_noise_v: float = 0.035
    #: Samples the indication takes to traverse from one polarity to the other.
    indication_transition_samples: int = 12

    # --- drive-contactor timing, all measured from the real traces ----------
    #: The drive energises before the motor draws current (measured 14.5 +- 7.8).
    contactor_lead_samples: tuple[int, int] = (6, 24)
    #: The drive is held after current stops, until indication confirms
    #: (measured 22.8 +- 1.1 - notably consistent).
    drive_hold_samples: tuple[int, int] = (21, 25)
    #: Brief opposite-polarity switching transient as the contactor changes over
    #: (measured ~11 samples peaking ~14.5 V).
    drive_transient_samples: tuple[int, int] = (1, 20)
    drive_transient_v: float = 14.5

    #: Plateau ripple is mechanically band-limited, not white. Measured lag-1
    #: autocorrelation across the real throws is 0.90-0.97; modelling it as
    #: white noise made the synthetic spectrum far too flat.
    ripple_ar1: float = 0.93

    #: PMD014 has no output_r_volt instrumentation at all (1224/1224 null).
    has_output_r: bool = False

    # Degradation coupling: parameter shift at zero health.
    friction_gain: float = 0.55
    duration_gain: float = 0.30
    motor_wear_gain: float = 0.40


#: Calibrated reference spec - the one directly fitted to real data.
CALIBRATED = MachineSpec()

#: A second supply class, matching PMD055's 230 V rail. Its healthy plateau is
#: NOT calibrated: both real PMD055 events are faulty (stalled throws), so no
#: healthy PMD055 waveform exists. A documented extrapolation, flagged as such
#: in the dataset card.
SUPPLY_CLASS_B = MachineSpec(
    name="PMD-B",
    idle_a=0.01,
    inrush_a=12.0,
    plateau_a=5.0,
    stall_a=18.0,
    supply_v=230.4,
    sag_v=7.0,
    has_output_r=True,
)


@dataclass(frozen=True)
class Environment:
    """Operating conditions that modulate every event.

    Korean point machines see a genuine -15 C to +35 C annual range, and cold
    grease is a well-documented driver of elevated throw current, so temperature
    is a first-class scenario axis rather than noise.
    """

    temperature_c: float = 15.0
    #: 0 = dry, 1 = saturated. Drives indication-circuit leakage.
    humidity: float = 0.4
    #: 0 = clear, 1 = heavy ice/snow packing the slide chairs.
    ice_severity: float = 0.0
    #: Grid quality; scales supply noise and sag.
    supply_quality: float = 1.0

    @property
    def cold_friction_factor(self) -> float:
        """Grease stiffens as it cools: ~+18% plateau current at -15 C."""
        return 1.0 + max(0.0, (15.0 - self.temperature_c)) * 0.006

    @property
    def ice_friction_factor(self) -> float:
        return 1.0 + self.ice_severity * 0.45


@dataclass(frozen=True)
class DataQuality:
    """Recording-chain defects, injected so the model learns to survive them.

    Real telemetry is not clean, and a model that has only seen clean data will
    flag a stuck sensor as a machine fault. Each of these is applied *after* the
    physics, and never changes the event's label.
    """

    dropout_prob: float = 0.0       # probability of a gap in the capture
    dropout_max_frac: float = 0.05  # longest gap, as a fraction of the capture
    stuck_prob: float = 0.0         # sensor freezes at its last value
    clip_prob: float = 0.0          # ADC saturation
    clip_level_a: float = 12.0
    emi_burst_prob: float = 0.0     # electromagnetic interference burst
    emi_amplitude_a: float = 0.8
    quantisation_a: float = 0.01    # the real extract is quantised to 0.01 A
    missing_channel_prob: float = 0.0


CLEAN = DataQuality()
FIELD_REALISTIC = DataQuality(
    dropout_prob=0.03,
    stuck_prob=0.02,
    clip_prob=0.015,
    emi_burst_prob=0.04,
    missing_channel_prob=0.01,
)


@dataclass
class FleetConfig:
    """How to build a fleet of machines with realistic per-unit variation."""

    n_machines: int = 40
    class_b_frac: float = 0.30
    unit_spread: float = 0.06
    machine_prefix: str = "PMD"
    real_ids: tuple[int, ...] = field(default_factory=lambda: (14, 55))
