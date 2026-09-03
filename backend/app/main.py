"""RailPoint-AI API."""

from __future__ import annotations

import asyncio
import contextlib
import csv
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .schemas.models import CopilotRequest
from .services import copilot as copilot_service
from .services.inference import EXPLAIN_LABELS, InferenceService
from .services.stream import FleetStream

ML_ROOT = Path(__file__).resolve().parents[2] / "ml"
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from pmdlib.sim.spec import CHANNELS  # noqa: E402

CHANNEL_UNITS = {
    "ac_curr": "A", "ac_volt": "V", "as_volt": "V",
    "output_n_volt": "V", "output_r_volt": "V",
}

inference = InferenceService()
stream = FleetStream(inference)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await stream.start()
    # Seed some history so the dashboard is not empty on first load.
    for _ in range(24):
        stream.step()
    yield
    await stream.stop()


app = FastAPI(title="RailPoint-AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health(response: Response) -> dict:
    # A console that reports "ok" while nothing is scoring is worse than one
    # with no health check at all, so this is a 503 the moment no model loads.
    degraded = inference.degraded
    if degraded:
        response.status_code = 503
    return {
        "status": "degraded" if degraded else "ok",
        "model_source": inference.source,
        "model_version": inference.version,
        "scoring": not degraded,
    }


@app.get("/api/stats")
async def stats() -> dict:
    sev = [m.severity for m in stream.machines.values()]
    # The buckets must be exhaustive. "info" - a Normal prediction the model is
    # not confident about - is its own state, and omitting it made the status bar
    # silently under-report the fleet.
    return {
        "machines": len(stream.machines),
        "normal": sum(s == "normal" for s in sev),
        "info": sum(s == "info" for s in sev),
        "warning": sum(s == "warning" for s in sev),
        "critical": sum(s == "critical" for s in sev),
        "events_streamed": stream.streamed,
        "open_alerts": sum(a["state"] == "open" for a in stream.alerts),
        "model_version": inference.version,
        "model_source": inference.source,
        "stream_interval_s": settings.stream_interval_s,
    }


@app.get("/api/machines")
async def machines() -> list[dict]:
    return [stream.machine_view(m) for m in stream.machines.values()]


@app.get("/api/machines/{machine_id}")
async def machine(machine_id: str) -> dict:
    st = stream.machines.get(machine_id)
    if st is None:
        raise HTTPException(404, f"unknown machine {machine_id}")
    view = stream.machine_view(st)
    view["events"] = [stream.summary(e) for e in stream.events if e["machine_id"] == machine_id][:50]
    return view


@app.get("/api/events")
async def events(machine_id: str | None = None, limit: int = 60) -> list[dict]:
    items = [e for e in stream.events if machine_id is None or e["machine_id"] == machine_id]
    return [stream.summary(e) for e in items[: max(1, min(limit, 200))]]


@app.get("/api/events/{event_id}")
async def event_detail(event_id: str) -> dict:
    rec = stream.find_event(event_id)
    if rec is None:
        raise HTTPException(404, f"unknown event {event_id}")
    sig: np.ndarray = rec["signals"]
    n = rec["n_samples"]
    channels = [
        {
            "name": name,
            "unit": CHANNEL_UNITS[name],
            # NaN is not valid JSON; null preserves "this channel is not wired"
            # rather than pretending a missing reading was zero.
            "values": [None if not np.isfinite(v) else round(float(v), 4) for v in sig[:n, i]],
        }
        for i, name in enumerate(CHANNELS)
    ]
    out = stream.summary(rec)
    out["channels"] = channels
    out["phases"] = rec["phases"]
    out["attributions"] = [
        {**a, "label": EXPLAIN_LABELS.get(a["feature"], a["feature"])}
        for a in rec["attributions"]
    ]
    out["truth"] = rec["truth"]
    return out


@app.get("/api/alerts")
async def alerts(state: str | None = None) -> list[dict]:
    return [a for a in stream.alerts if state is None or a["state"] == state]


@app.post("/api/alerts/{alert_id}/{action}")
async def alert_action(alert_id: str, action: str, assignee: str | None = None) -> dict:
    if action not in {"acknowledge", "resolve", "reopen"}:
        raise HTTPException(400, f"unknown action {action}")
    for a in stream.alerts:
        if a["id"] == alert_id:
            a["state"] = {
                "acknowledge": "acknowledged", "resolve": "resolved", "reopen": "open",
            }[action]
            if assignee:
                a["assignee"] = assignee
            return a
    raise HTTPException(404, f"unknown alert {alert_id}")


@app.get("/api/model")
async def model_card() -> dict:
    """The measured results behind whatever is currently serving.

    Read from the experiment artefacts rather than restated in code, so the
    console cannot drift from what the training run actually produced — a
    dashboard quoting stale metrics is worse than one quoting none.
    """
    results = settings.artifacts_dir.parent / "results"

    def read_json(name: str) -> dict | None:
        path = results / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    acceptance: list[dict] = []
    acc_path = results / "deep-acceptance.csv"
    if acc_path.exists():
        with acc_path.open(newline="") as fh:
            acceptance = list(csv.DictReader(fh))

    per_class: list[dict] = []
    pc_path = results / "deep-per-class.csv"
    if pc_path.exists():
        with pc_path.open(newline="") as fh:
            per_class = list(csv.DictReader(fh))

    return {
        "serving": {"source": inference.source, "version": inference.version,
                    "degraded": inference.degraded},
        "summary": read_json("deep-summary.json"),
        "metropt": read_json("metropt-summary.json"),
        "acceptance": acceptance,
        "per_class": per_class,
    }


@app.post("/api/copilot")
async def copilot(body: CopilotRequest) -> dict:
    """Draft a work order for an event, or answer a question about it.

    Grounded strictly in the event's measured values, the model's own
    attribution, and the decoded Sehwa maintenance-code table. Decision support
    only - it never authorises a movement or declares a machine fit for service.
    """
    record = stream.find_event(body.event_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown event {body.event_id}")
    machine = stream.machines.get(record["machine_id"])
    reply = copilot_service.answer(
        event=record,
        machine=stream.machine_view(machine) if machine else None,
        question=body.question,
    )
    return {
        "answer": reply.answer,
        "source": reply.source,
        "model": reply.model,
        "citations": reply.citations,
        "disclaimer": reply.disclaimer,
    }


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket) -> None:
    await ws.accept()
    q = stream.subscribe()
    try:
        await ws.send_json({"type": "hello", "stats": await stats()})
        while True:
            payload = await q.get()
            await ws.send_json(payload)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:  # pragma: no cover
        raise
    finally:
        stream.unsubscribe(q)
        with contextlib.suppress(Exception):
            await ws.close()
