"""Live fleet simulation feeding the dashboard.

Runs the same physics-informed generator the models were trained on, so the
dashboard shows real model behaviour on real signal shapes rather than replaying
a fixture. Machines carry persistent health, so watching long enough shows a
machine actually degrade - which is the point of the RUL display.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ..config import settings
from .inference import InferenceService, fault_meta

ML_ROOT = Path(__file__).resolve().parents[3] / "ml"
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from pmdlib.sim.degradation import (  # noqa: E402
    severity_from_health,
    simulate_trajectory,
)
from pmdlib.sim.fleet import seasonal_environment  # noqa: E402
from pmdlib.sim.spec import CALIBRATED, FIELD_REALISTIC, SUPPLY_CLASS_B, FaultClass  # noqa: E402
from pmdlib.sim.waveform import generate_event  # noqa: E402

MAX_EVENTS = 600
MAX_ALERTS = 200
#: Track-schematic coordinates, laid out as two interlocking approaches rather
#: than a grid - the diagram should read like a signalling layout, not a table.
def _layout(n: int) -> list[tuple[float, float]]:
    """Two running lines with points staggered along them, spanning the diagram.

    Coordinates are in the schematic's 200x100 viewBox and are computed from the
    fleet size so the layout fills the width at any scale.
    """
    pts: list[tuple[float, float]] = []
    steps = max(1, (n + 1) // 2)
    margin, span = 14.0, 172.0
    for i in range(n):
        lane, step = i % 2, i // 2
        x = margin + (span * step / max(1, steps - 1)) if steps > 1 else margin + span / 2
        pts.append((x, 30.0 + lane * 40.0))
    return pts


@dataclass
class MachineState:
    id: str
    spec: object
    trajectory: object
    cycle: int = 0
    position: str = "N"
    x: float = 0.0
    y: float = 0.0
    events_today: int = 0
    last_event_at: datetime | None = None
    severity: str = "normal"
    health_trend: deque = field(default_factory=lambda: deque(maxlen=60))
    rul: float | None = None
    rul_low: float | None = None
    rul_high: float | None = None


class FleetStream:
    def __init__(self, inference: InferenceService) -> None:
        self.inference = inference
        self.rng = np.random.default_rng(settings.stream_seed)
        self.events: deque = deque(maxlen=MAX_EVENTS)
        self.alerts: deque = deque(maxlen=MAX_ALERTS)
        self.subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._ids = itertools.count(1)
        self._alert_ids = itertools.count(1)
        self.streamed = 0
        self.machines: dict[str, MachineState] = {}
        self._build_fleet()

    def _build_fleet(self) -> None:
        coords = _layout(settings.fleet_size)
        for i in range(settings.fleet_size):
            spec = SUPPLY_CLASS_B if self.rng.random() < 0.3 else CALIBRATED
            mid = f"PMD{i + 1:03d}"
            traj = simulate_trajectory(4000, rng=self.rng)
            st = MachineState(id=mid, spec=spec, trajectory=traj, x=coords[i][0], y=coords[i][1])
            # Start each machine somewhere different in its life so the fleet is
            # not uniformly brand new.
            st.cycle = int(self.rng.integers(0, 2500))
            st.health_trend.extend(
                float(traj.health[max(0, st.cycle - k)]) for k in range(30, 0, -1)
            )
            self.machines[mid] = st

    # -- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    async def _loop(self) -> None:
        while True:
            try:
                payload = self.step()
                for q in list(self.subscribers):
                    if q.full():
                        # A slow client must not stall the fleet: drop its oldest.
                        with contextlib.suppress(asyncio.QueueEmpty):
                            q.get_nowait()
                    with contextlib.suppress(asyncio.QueueFull):
                        q.put_nowait(payload)
            except Exception as exc:  # pragma: no cover - keep the feed alive
                print(f"[stream] step failed: {exc}")
            await asyncio.sleep(settings.stream_interval_s)

    # -- one throw -------------------------------------------------------
    def step(self) -> dict:
        mid = str(self.rng.choice(list(self.machines)))
        st = self.machines[mid]
        st.cycle = min(st.cycle + 1, len(st.trajectory) - 1)
        health = float(st.trajectory.health[st.cycle])

        direction = "R" if st.position == "N" else "N"
        if st.trajectory.active[st.cycle]:
            fault = st.trajectory.mode
            severity = severity_from_health(health)
        elif self.rng.random() < 0.05:
            fault = FaultClass(
                str(self.rng.choice([f.value for f in FaultClass if f is not FaultClass.NORMAL]))
            )
            severity = float(self.rng.beta(2.2, 1.8))
        else:
            fault, severity = FaultClass.NORMAL, 0.0

        env = seasonal_environment(st.cycle, 3000, self.rng)
        ev = generate_event(
            st.spec, fault=fault, severity=severity, direction=direction, health=health,
            env=env, dq=FIELD_REALISTIC, machine_id=mid, event_num=st.cycle, rng=self.rng,
        )
        scored = self.inference.score(ev.signals, len(ev))
        ko, en, code, sev_rank = fault_meta(scored.fault)

        severity_label = "normal"
        if scored.fault != "NORMAL":
            severity_label = "critical" if sev_rank >= 3 else "warning"
        elif scored.confidence < 0.5:
            severity_label = "info"

        now = datetime.now(UTC)
        st.position = direction if ev.completed else "transit"
        st.last_event_at = now
        st.events_today += 1
        st.severity = severity_label
        st.health_trend.append(health)
        st.rul = scored.rul
        st.rul_low, st.rul_high = scored.rul_low, scored.rul_high

        event_id = f"E{next(self._ids):06d}"
        record = {
            "id": event_id, "machine_id": mid, "ts": now.isoformat(),
            "direction": direction, "completed": ev.completed,
            "throw_samples": ev.throw_samples, "n_samples": len(ev),
            "signals": ev.signals.astype(np.float32),
            "truth": fault.value, "health": health,
            "prediction": {
                "fault": scored.fault, "fault_ko": ko, "fault_en": en, "err_code": code,
                "confidence": scored.confidence, "prediction_set": scored.prediction_set,
                "set_size": len(scored.prediction_set),
                "anomaly_score": scored.anomaly_score, "severity": severity_label,
            },
            "phases": [{"name": n, "start": a, "end": b} for n, a, b in scored.phases],
            "attributions": [
                {"feature": n, "value": v, "contribution": c} for n, v, c in scored.attributions
            ],
        }
        self.events.appendleft(record)
        self.streamed += 1

        if severity_label in ("warning", "critical"):
            # Collapse repeats of the same condition on the same machine. A
            # machine past the symptom threshold raises this on *every* throw
            # for the rest of its life, so appending unconditionally floods the
            # 200-entry deque and evicts alerts an operator has already
            # acknowledged - losing their triage work to a single noisy machine.
            existing = next(
                (
                    a for a in self.alerts
                    if a["machine_id"] == mid
                    and a["fault"] == scored.fault
                    and a["state"] != "resolved"
                ),
                None,
            )
            if existing is not None:
                existing["count"] += 1
                existing["last_ts"] = now.isoformat()
                existing["event_id"] = event_id
                # A condition that worsens is worth surfacing again, so a
                # warning that becomes critical reopens for a second look.
                if severity_label == "critical" and existing["severity"] != "critical":
                    existing["severity"] = "critical"
                    existing["state"] = "open"
            else:
                self.alerts.appendleft(
                    {
                        "id": f"A{next(self._alert_ids):05d}", "machine_id": mid,
                        "event_id": event_id, "ts": now.isoformat(), "severity": severity_label,
                        "fault": scored.fault, "fault_ko": ko,
                        "message": f"{en} detected on {mid}" + (f" ({code})" if code else ""),
                        "state": "open", "assignee": None,
                        "count": 1, "last_ts": now.isoformat(),
                    }
                )
        return {"type": "event", "event": self.summary(record), "machine": self.machine_view(st)}

    # -- views -----------------------------------------------------------
    def summary(self, rec: dict) -> dict:
        return {k: v for k, v in rec.items() if k not in ("signals", "attributions", "phases")}

    def machine_view(self, st: MachineState) -> dict:
        return {
            "id": st.id, "label": st.id, "spec": getattr(st.spec, "name", "PMD-A"),
            "position": st.position, "severity": st.severity,
            "last_event_at": st.last_event_at.isoformat() if st.last_event_at else None,
            "events_today": st.events_today, "x": st.x, "y": st.y,
            "health": {
                "health": float(st.trajectory.health[st.cycle]),
                "rul_cycles": st.rul, "rul_low": st.rul_low, "rul_high": st.rul_high,
                "trend": [round(v, 4) for v in st.health_trend],
            },
        }

    def find_event(self, event_id: str) -> dict | None:
        return next((e for e in self.events if e["id"] == event_id), None)
