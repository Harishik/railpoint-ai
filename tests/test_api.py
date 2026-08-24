"""Backend API contract tests.

Uses the real inference service and the real simulator rather than mocks: the
thing worth testing is that a generated capture actually flows through scoring
and out of the API in the shape the frontend expects.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, stream  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_reports_which_model_is_serving(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    # A console that cannot tell you whether it is running the trained model or a
    # fallback is worse than one with no model at all.
    assert body["model_source"] in {"trained", "heuristic"}
    assert body["model_version"]


def test_stats_counts_are_self_consistent(client):
    """The severity buckets must be exhaustive.

    They were not: a Normal prediction the model is unsure about lands in
    "info", which no bucket counted, so the status bar under-reported the fleet.
    """
    s = client.get("/api/stats").json()
    assert s["machines"] == s["normal"] + s["info"] + s["warning"] + s["critical"]
    assert s["events_streamed"] > 0


def test_machines_carry_position_and_health(client):
    machines = client.get("/api/machines").json()
    assert machines
    for m in machines:
        assert m["position"] in {"N", "R", "transit", "unknown"}
        assert 0.0 <= m["health"]["health"] <= 1.0
        assert 0 <= m["x"] <= 200 and 0 <= m["y"] <= 100, "must sit inside the schematic viewBox"


def test_event_detail_returns_every_channel(client):
    events = client.get("/api/events?limit=1").json()
    detail = client.get(f"/api/events/{events[0]['id']}").json()
    names = {c["name"] for c in detail["channels"]}
    assert names == {"ac_curr", "ac_volt", "as_volt", "output_n_volt", "output_r_volt"}
    for ch in detail["channels"]:
        assert len(ch["values"]) == detail["n_samples"]
        # NaN is not valid JSON. A missing channel must serialise as null, so the
        # frontend can break the line rather than invent a reading.
        assert all(v is None or math.isfinite(v) for v in ch["values"])


def test_event_detail_has_phases_and_attributions(client):
    events = client.get("/api/events?limit=1").json()
    detail = client.get(f"/api/events/{events[0]['id']}").json()
    for p in detail["phases"]:
        assert p["end"] > p["start"]
    for a in detail["attributions"]:
        assert a["label"], "every attribution needs an operator-readable label"


def test_prediction_set_always_contains_the_prediction(client):
    for ev in client.get("/api/events?limit=25").json():
        p = ev["prediction"]
        assert p["fault"] in p["prediction_set"]
        assert p["set_size"] == len(p["prediction_set"])
        assert 0.0 <= p["confidence"] <= 1.0


def test_unknown_ids_404(client):
    assert client.get("/api/events/nope").status_code == 404
    assert client.get("/api/machines/nope").status_code == 404


def test_alert_lifecycle_is_reversible(client):
    stream.step()
    alerts = client.get("/api/alerts").json()
    if not alerts:
        pytest.skip("no alert generated in this run")
    aid = alerts[0]["id"]
    assert client.post(f"/api/alerts/{aid}/acknowledge").json()["state"] == "acknowledged"
    assert client.post(f"/api/alerts/{aid}/resolve").json()["state"] == "resolved"
    # Undo matters: an operator who resolves the wrong alert must be able to
    # put it back without an admin.
    assert client.post(f"/api/alerts/{aid}/reopen").json()["state"] == "open"
    assert client.post(f"/api/alerts/{aid}/bogus").status_code == 400


def test_websocket_delivers_a_scored_event(client):
    with client.websocket_connect("/ws/stream") as ws:
        assert ws.receive_json()["type"] == "hello"
        stream.step()
        msg = ws.receive_json()
        assert msg["type"] == "event"
        assert msg["event"]["prediction"]["fault"]
        assert msg["machine"]["id"] == msg["event"]["machine_id"]
