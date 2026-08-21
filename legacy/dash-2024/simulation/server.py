"""FaultForce 2024 simulation server - repaired.

Original defects fixed here: SRV-01 .. SRV-08 (see docs/BUGS.md).
"""

from __future__ import annotations

import argparse
import os
import random
import threading
from collections import deque
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
# SRV-04: the secret key was literally the string 'your_secret_key'.
app.config["SECRET_KEY"] = os.environ.get("FAULTFORCE_SECRET_KEY", os.urandom(32).hex())

# SRV-08: no CORS, so a browser client served from :8050 could never call :5000.
CORS(app, resources={r"/*": {"origins": os.environ.get("FAULTFORCE_CORS_ORIGINS", "*")}})

# SRV-06: flask_socketio emitted "update_data" that no client ever subscribed to
# - the dashboard polled /data over HTTP instead. The dependency is removed
# rather than left in place as dead weight. The RailPoint-AI backend uses real
# WebSockets, with a client that actually listens.

BATCH_SIZE = 600
BATCH_INTERVAL_S = 5.0
MAX_RECORDS = 5000
PMD_TYPES = [f"PMD{str(i).zfill(3)}" for i in range(1, 57)]

# Calibrated to the real Sehwa traces (idle ~0.07 A, throw plateau ~9 A,
# peak 15.74 A, supply 205-230 V) instead of the original's invented ranges.
AC_CURR_IDLE = 0.07
AC_CURR_THROW = 9.0
AC_CURR_MAX = 15.74
AC_VOLT_RANGE = (205.25, 230.49)
ABNORMAL_THRESHOLD_A = 12.0

# SRV-03: real_time_data was extended and rebound from a background thread with
# no lock, racing every /data reader. A deque with a maxlen is atomic for append
# and bounded by construction; the lock guards the snapshot read.
_lock = threading.Lock()
_records: deque[dict] = deque(maxlen=MAX_RECORDS)
_stop = threading.Event()
_state = {"last_batch_at": None, "batches": 0}


def _make_record(rng: random.Random) -> dict:
    pmd_type = rng.choice(PMD_TYPES)
    ac_volt = round(rng.uniform(*AC_VOLT_RANGE), 2)
    roll = rng.random()
    if roll < 0.25:
        ac_curr = round(rng.gauss(AC_CURR_IDLE, 0.02), 3)
    elif roll < 0.93:
        ac_curr = round(rng.gauss(AC_CURR_THROW, 1.2), 2)
    else:
        ac_curr = round(rng.uniform(AC_CURR_THROW, AC_CURR_MAX), 2)
    ac_curr = max(0.01, min(ac_curr, AC_CURR_MAX))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pmd_type": pmd_type,
        "ac_volt": ac_volt,
        "ac_curr": ac_curr,
        "value": round(ac_volt * ac_curr, 2),
        # SRV-07 / SIM-04: status is derived from the signal, so the label
        # actually means something. The original drew it independently.
        "status": "error" if ac_curr > ABNORMAL_THRESHOLD_A else "normal",
    }


def generate_simulation_data(seed: int | None = None) -> None:
    """SRV-02: the original stopped after 90 s and then served permanently stale
    data with no indication it had stopped. This runs until told to stop, and
    /health reports staleness either way."""
    rng = random.Random(seed)
    while not _stop.is_set():
        batch = [_make_record(rng) for _ in range(BATCH_SIZE)]
        with _lock:
            _records.extend(batch)
            _state["last_batch_at"] = datetime.now(timezone.utc)
            _state["batches"] += 1
        _stop.wait(BATCH_INTERVAL_S)


@app.route("/")
def index():
    return jsonify({"message": "FaultForce simulation server (repaired)", "endpoints": ["/data", "/health"]})


@app.route("/data")
def get_data():
    """Return the most recent records.

    SRV-05: the original docstring promised 100 records and returned 1000.
    The count is now a documented, validated query parameter.
    """
    try:
        limit = int(request.args.get("limit", 1000))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    limit = max(1, min(limit, MAX_RECORDS))
    with _lock:
        snapshot = list(_records)[-limit:]
    return jsonify(snapshot)


@app.route("/health")
def health():
    with _lock:
        last = _state["last_batch_at"]
        count = len(_records)
        batches = _state["batches"]
    age = (datetime.now(timezone.utc) - last).total_seconds() if last else None
    return jsonify(
        {
            "running": not _stop.is_set(),
            "records": count,
            "batches": batches,
            "last_batch_age_s": age,
            "stale": age is None or age > BATCH_INTERVAL_S * 3,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="FaultForce simulation server (repaired)")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--debug", action="store_true", default=os.environ.get("FLASK_DEBUG") == "1")
    args = parser.parse_args()

    worker = threading.Thread(target=generate_simulation_data, args=(args.seed,), daemon=True)
    worker.start()
    try:
        # SRV-01: debug=True made the Werkzeug reloader fork the process and
        # start the generator thread twice. The reloader is disabled explicitly.
        app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)
    finally:
        _stop.set()


if __name__ == "__main__":
    main()
