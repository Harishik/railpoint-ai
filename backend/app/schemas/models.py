"""API response shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["normal", "info", "warning", "critical"]


class ChannelSeries(BaseModel):
    name: str
    unit: str
    values: list[float]


class PhaseSpan(BaseModel):
    name: str
    start: int
    end: int


class Prediction(BaseModel):
    fault: str
    fault_ko: str
    fault_en: str
    err_code: str | None
    confidence: float
    #: Conformal prediction set - the labels that cannot be ruled out at 90%.
    prediction_set: list[str]
    set_size: int
    anomaly_score: float
    severity: Severity


class Attribution(BaseModel):
    feature: str
    label: str
    value: float
    contribution: float


class EventSummary(BaseModel):
    id: str
    machine_id: str
    ts: datetime
    direction: Literal["N", "R"]
    completed: bool
    throw_samples: int
    n_samples: int
    prediction: Prediction


class EventDetail(EventSummary):
    channels: list[ChannelSeries]
    phases: list[PhaseSpan]
    reference: list[float] = Field(default_factory=list, description="Healthy reference current")
    attributions: list[Attribution] = Field(default_factory=list)


class MachineHealth(BaseModel):
    health: float
    rul_cycles: float | None
    rul_low: float | None
    rul_high: float | None
    trend: list[float]


class Machine(BaseModel):
    id: str
    label: str
    spec: str
    position: Literal["N", "R", "transit", "unknown"]
    severity: Severity
    last_event_at: datetime | None
    events_today: int
    health: MachineHealth
    x: float
    y: float


class Alert(BaseModel):
    id: str
    machine_id: str
    event_id: str
    ts: datetime
    severity: Severity
    fault: str
    fault_ko: str
    message: str
    state: Literal["open", "acknowledged", "resolved"]
    assignee: str | None = None
    #: How many throws have raised this same condition. A persistently degrading
    #: machine reports one alert with a rising count, not one alert per throw.
    count: int = 1
    #: When it was last seen, as distinct from when it was first raised.
    last_ts: datetime | None = None


class FleetStats(BaseModel):
    machines: int
    normal: int
    warning: int
    critical: int
    events_streamed: int
    open_alerts: int
    model_version: str
    model_source: Literal["trained", "heuristic"]


class CopilotRequest(BaseModel):
    """Ask the copilot to draft a work order, or answer a question about an event."""

    event_id: str
    question: str | None = None
