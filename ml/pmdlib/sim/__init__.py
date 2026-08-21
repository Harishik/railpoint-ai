"""Physics-informed point-machine simulator, calibrated to real Sehwa traces."""

from .degradation import TrajectoryKind, simulate_trajectory
from .fleet import DatasetConfig, StratifiedConfig, generate_dataset, generate_stratified
from .spec import CALIBRATED, CHANNELS, FaultClass, MachineSpec
from .waveform import Event, generate_event

__all__ = [
    "CALIBRATED", "CHANNELS", "DatasetConfig", "Event", "FaultClass", "MachineSpec",
    "StratifiedConfig", "TrajectoryKind", "generate_dataset", "generate_event",
    "generate_stratified", "simulate_trajectory",
]
