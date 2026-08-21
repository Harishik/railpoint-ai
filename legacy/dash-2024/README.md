# FaultForce 2024 — preserved and repaired

The code delivered by the original 2024 capstone, with its **34 defects** fixed.
Originals are kept verbatim as `*.orig` beside each repaired file, so every claim
in [`docs/BUGS.md`](../../docs/BUGS.md) can be checked against the source.

> **This directory is a historical artefact, superseded by the RailPoint-AI
> system at the repository root.** It contains **no machine-learning model** —
> the 2024 code never did, despite the final report describing one. Its
> "Prediction" is a fixed current threshold, and it is labelled as such in the UI.

## Running it

```bash
uv venv --python 3.12 .venv-legacy
uv pip install --python .venv-legacy/bin/python -r legacy/dash-2024/requirements.txt
```

Three independent pieces:

```bash
# 1. The main dashboard  ->  http://127.0.0.1:8051
.venv-legacy/bin/python legacy/dash-2024/app/app.py --port 8051
```

```bash
# 2. The simulation server  ->  http://127.0.0.1:5001/health
.venv-legacy/bin/python legacy/dash-2024/simulation/server.py --port 5001
```

```bash
# 3. The simulation dashboard (needs 2 running)  ->  http://127.0.0.1:8050
.venv-legacy/bin/python legacy/dash-2024/simulation/simulation_code/dashboard.py --port 8050
```

The offline CSV simulator is standalone:

```bash
.venv-legacy/bin/python legacy/dash-2024/simulation/simulation_code/simulation.py --duration 30
```

## What changed that you can see

- **Failure Analysis** page — plots the real Sehwa traces. The 2024 app loaded
  that file and never displayed a single value from it (APP-04).
- **Reports** page — previously a dead `href="#"` link (APP-12).
- Normal / Abnormal charts now actually separate the two classes (APP-06), and
  the third chart shows the decision rather than duplicating the first (APP-07).
- A banner states plainly that the prediction is a threshold, not a model.
