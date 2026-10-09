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


def test_health_reports_degraded_when_nothing_can_score(client):
    """A console that says "ok" while nothing is being classified is worse than
    one with no health check, so this must be a 503 and must say so."""
    from app.main import inference

    net, probe = inference._net, inference._probe
    try:
        inference._net, inference._probe = None, None
        r = client.get("/api/health")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "degraded"
        assert body["scoring"] is False
    finally:
        inference._net, inference._probe = net, probe

    ok = client.get("/api/health")
    assert ok.status_code == 200
    assert ok.json()["scoring"] is True


def test_net_calibration_is_not_applied_to_the_fallback_probe(tmp_path, monkeypatch):
    """The conformal qhat and Mahalanobis stats index the encoder's output and
    its embedding space. Applying them to the linear probe would void the
    coverage guarantee rather than transfer it, so a run that falls back to the
    probe must keep the default qhat and must not carry Mahalanobis stats."""
    import numpy as np

    from app.services import inference as inf

    # A calibration file exists, but no net.pt: exactly the fallback case.
    np.savez(
        tmp_path / "calibration.npz",
        conformal_qhat=0.9999,
        rul_qhat=123.0,
        maha_mean=np.zeros(4),
        maha_precision=np.eye(4),
    )
    monkeypatch.setattr(inf.settings, "artifacts_dir", tmp_path)
    svc = inf.InferenceService()

    assert svc._net is None, "no net.pt was written, so the encoder must be absent"
    assert svc._conformal_qhat != 0.9999, "net-calibrated qhat leaked onto the probe"
    assert svc._maha_mean is None and svc._maha_prec is None



def test_serving_and_pipeline_share_one_set_implementation():
    """These were two implementations once, and they disagreed: serving forced
    the argmax in and the pipeline did not, so the reported mean set size
    (0.895) described sets the console never served. One function, by identity."""
    from app.services import inference as inf
    from pmdlib.eval.conformal import prediction_set

    assert inf.conformal_set is prediction_set


def _artefacts_with_real_net(tmp_path):
    """Calibration is only read when the encoder loads, so these tests need the
    real weights beside a hand-written calibration file."""
    import shutil

    from app.services import inference as inf

    real = inf.settings.artifacts_dir / "net.pt"
    if not real.exists():
        pytest.skip("no trained net.pt to load")
    shutil.copy(real, tmp_path / "net.pt")


def test_pre_raps_artefact_is_read_as_threshold(tmp_path, monkeypatch):
    """An artefact written before the rule was recorded carries a `thr`
    quantile. Read as a RAPS cumulative-mass threshold it would serve top-1 for
    every event, silently - so absence of the key must mean `thr`."""
    import numpy as np

    from app.services import inference as inf

    _artefacts_with_real_net(tmp_path)
    np.savez(tmp_path / "calibration.npz", conformal_qhat=0.0085, rul_qhat=240.0,
             maha_mean=np.zeros(4), maha_precision=np.eye(4))
    monkeypatch.setattr(inf.settings, "artifacts_dir", tmp_path)
    svc = inf.InferenceService()
    assert svc._conformal_rule == "thr"
    assert svc.calibration_error is None


def test_malformed_raps_artefact_degrades_instead_of_crashing(tmp_path, monkeypatch):
    """RAPS cannot be rebuilt from the quantile alone. A file naming the rule
    without its penalty must not stop the API - that would take the fleet view
    and alert queue down over one file - and must not be served as if valid."""
    import numpy as np

    from app.services import inference as inf

    _artefacts_with_real_net(tmp_path)
    np.savez(tmp_path / "calibration.npz", conformal_qhat=0.9999, conformal_rule="raps",
             rul_qhat=240.0, maha_mean=np.zeros(4), maha_precision=np.eye(4))
    monkeypatch.setattr(inf.settings, "artifacts_dir", tmp_path)
    svc = inf.InferenceService()  # must not raise

    assert svc._net is not None
    assert svc.calibration_error and "raps" in svc.calibration_error
    # Singleton sets: they claim no shortlist the calibration did not certify.
    assert (svc._conformal_rule, svc._conformal_qhat) == ("thr", 0.0)


def test_health_reports_a_calibration_problem(client, monkeypatch):
    """Scoring still works, so `scoring` stays true - but the sets cannot be
    trusted, and a health check that says "ok" over that is the failure RP-15
    exists to prevent."""
    from app.main import inference

    monkeypatch.setattr(inference, "calibration_error", "calibration is malformed")
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["scoring"] is True
    assert body["calibration"] == "calibration is malformed"



def test_live_stream_simulates_the_same_horizon_as_training():
    """The stream simulated 4,000 cycles while training stopped at 800, so the
    console asked the RUL head about lifetimes it had never been trained on.
    Both now read one constant."""
    from app.main import stream
    from pmdlib.sim.degradation import SERVICE_HORIZON_CYCLES

    for st in stream.machines.values():
        assert st.trajectory.health.size == SERVICE_HORIZON_CYCLES


def test_repeated_faults_collapse_into_one_alert(client):
    """A machine past the symptom threshold raises the same condition on every
    throw. Appending one alert per throw floods the bounded deque and evicts
    alerts the operator has already acknowledged, losing their triage work."""
    from app.main import stream

    stream.alerts.clear()
    for _ in range(400):
        stream.step()

    alerts = client.get("/api/alerts").json()
    pairs = [(a["machine_id"], a["fault"]) for a in alerts]
    assert len(pairs) == len(set(pairs)), "the same fault on one machine appeared twice"

    repeated = [a for a in alerts if a["count"] > 1]
    if repeated:
        a = repeated[0]
        assert a["last_ts"] is not None and a["last_ts"] >= a["ts"]


def test_acknowledged_alert_is_not_evicted_by_a_noisy_machine(client):
    """The specific regression: acknowledge an alert, then let the fleet run.
    Before dedup, one persistently degrading machine could push it out of the
    200-entry deque entirely."""
    from app.main import stream

    stream.alerts.clear()
    for _ in range(60):
        stream.step()
    alerts = client.get("/api/alerts").json()
    if not alerts:
        return  # nothing raised in this window; nothing to assert

    target = alerts[0]["id"]
    client.post(f"/api/alerts/{target}/acknowledge")
    for _ in range(400):
        stream.step()

    still_there = [a for a in client.get("/api/alerts").json() if a["id"] == target]
    assert still_there, "an acknowledged alert was evicted by repeat alerts"
    assert still_there[0]["state"] in ("acknowledged", "resolved")


def test_copilot_is_grounded_and_surfaces_uncertainty():
    """The copilot must cite the real Sehwa maintenance code and must not present
    an ambiguous conformal set as a settled diagnosis."""
    from app.services import copilot

    event = {
        "id": "E1", "machine_id": "PMD055", "direction": "R", "n_samples": 600,
        "prediction": {
            "fault": "E01_LOCK_LATCH", "fault_ko": "기억쇠", "err_code": "E01",
            "confidence": 0.62, "severity": "critical",
            "prediction_set": ["E01_LOCK_LATCH", "OBSTRUCTION"], "anomaly_score": 9671.8,
        },
        "phases": [], "attributions": [{"feature": "drive_cut", "value": 0.0, "contribution": -0.41}],
    }
    reply = copilot.answer(event, {"health": 0.31, "rul_cycles": 42.0,
                                   "rul_low": 8.0, "rul_high": 130.0})

    assert "E01" in reply.citations
    assert "기억쇠" in reply.answer, "must name the component in Korean"
    # The load-bearing behaviour: two labels in the set means the answer says so.
    assert "OBSTRUCTION" in reply.answer and "provisional" in reply.answer.lower()
    assert "42" in reply.answer, "remaining useful life should reach the work order"
    assert "does not authorise" in reply.answer, "safety disclaimer is mandatory"


def test_copilot_works_without_api_credentials(monkeypatch):
    """A reviewer cloning the repo has no ANTHROPIC_API_KEY. The feature must
    still produce a real work order rather than an error."""
    from app.services import copilot

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    reply = copilot.answer(
        {"id": "E2", "machine_id": "PMD001", "direction": "N", "n_samples": 260,
         "prediction": {"fault": "NORMAL", "fault_ko": "정상", "err_code": "",
                        "confidence": 0.97, "severity": "normal",
                        "prediction_set": ["NORMAL"], "anomaly_score": 12.0},
         "phases": [], "attributions": []},
        None,
    )
    assert reply.source == "deterministic"
    assert reply.model is None
    assert "Work order" in reply.answer


def test_copilot_404s_on_unknown_event(client):
    r = client.post("/api/copilot", json={"event_id": "does-not-exist"})
    assert r.status_code == 404

