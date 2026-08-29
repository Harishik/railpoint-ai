# Defect log — 2024 FaultForce codebase

Every defect found in the code delivered by the 2024 capstone, with the original
line reference and what was done about it. The original files are preserved
verbatim as `*.orig` beside their repaired counterparts in `legacy/dash-2024/`,
so every claim here is checkable.

**34 defects across 4 files.** Three are severe enough that the delivered system
could not have done what the final report says it did:

- **APP-03** — there is no machine-learning model anywhere in the delivered code.
- **APP-04** — the only real dataset is loaded and then never referenced.
- **SIM-04** — the simulator's label is drawn independently of its signal.

---

## `app.py` — Dash dashboard (15)

| ID | Line | Defect | Fix |
|---|---|---|---|
| APP-01 | 9–10 | Dataset paths hardcoded to `C:\Users\singh\Downloads\...`. Crashes anywhere but that one Windows machine. | Resolve relative to `__file__`, with a `FAULTFORCE_DATA_DIR` override. |
| APP-02 | 311 | `app.run_server()` was removed in Dash 3.x. On Dash 3.4 it raises `ObsoleteAttributeException` — the app is dead on arrival. | `app.run()`. |
| APP-03 | 40 | **The "Prediction" is a hardcoded threshold, `ac_curr <= 260`, not a model.** It is applied to `np.random.uniform(0.1, 300)`, so it labels pure noise. Real machine current never exceeds 15.74 A, so on real data the rule can never fire at all. | Kept as an explicitly-named `HEURISTIC_THRESHOLD_A`, recalibrated to 12 A, with a banner in the UI stating it is not a model. Trained models live in the new system. |
| APP-04 | 13 | **`processed_dataset.csv` — the only real data in the project — is read into `dataset` and never referenced again.** Every chart on screen plots freshly generated random numbers. | Real data now drives the machine list and a new Failure Analysis page that plots the actual traces. |
| APP-05 | 52–58, 88–100 | `create_graph()` assigns ids (`station-1-normal-data`, …) and takes a `title` argument; the callback then replaces the container's children wholesale with different graphs. Both the ids and the title are dead code. | Removed; figures are built in one place. |
| APP-06 | 221 | The chart captioned "Normal Data" plots *every* row regardless of label. | Filters to `Prediction == "Normal"` and reports the count. |
| APP-07 | 246 | The "Predicted Data" chart is a byte-for-byte copy of the Normal chart, recoloured by row 0's label. It shows no prediction. | Replaced with a decision plot: signal, threshold line, and the points that crossed it. |
| APP-08 | 29–31 | `np.random.choice([...,"E04", None])` produces an object-dtype column; merging on it is fragile. | Sentinel string converted to `pd.NA` after the draw. |
| APP-09 | 202 | A 200-row Bootstrap HTML table is re-rendered every 4 s with no pagination. | Paginated, sortable, filterable `DataTable`. |
| APP-10 | 22 | `np.random.seed()` with no argument reseeds from OS entropy on *every* callback, making the app non-reproducible by construction. | Explicit `default_rng(seed)`, seeded per tick. |
| APP-11 | 14 | The EUC-KR Korean maintenance table renders as mojibake in the UI. | Decoded once into a KO/EN table (`data/raw/sehwa/error_codes.csv`). |
| APP-12 | 119–121 | Every `NavLink` is `href="#"`. "Failure Analysis" and "Reports" do nothing. | `dcc.Location` routing; all three pages implemented. |
| APP-13 | 311 | `debug=True` hardcoded in the entrypoint. | CLI flag / `DASH_DEBUG` env, default off. |
| APP-14 | — | No `requirements.txt`, `pyproject.toml` or environment file anywhere in either zip. | Pinned `requirements.txt`. |
| APP-15 | 79–81 | Dropdowns offer PMD001 / PMD014 / PMD020, but the dataset only ever contained PMD014 and PMD055. Two of three options select nothing. | Options derived from the data. |

## `server.py` — Flask simulation server (8)

| ID | Line | Defect | Fix |
|---|---|---|---|
| SRV-01 | 65–66 | `start_background_task` plus `debug=True` makes the Werkzeug reloader fork the process, starting the generator thread **twice** at double the intended rate. | `use_reloader=False`; debug off by default. |
| SRV-02 | 14, 25 | The simulation hard-stops after 90 s. The server keeps serving the same frozen buffer forever with no indication it has stopped. | Runs until stopped; `/health` reports `last_batch_age_s` and a `stale` flag. |
| SRV-03 | 42–45 | `real_time_data` is `extend`ed *and rebound* from a background thread with no lock, racing every `/data` reader. | `collections.deque(maxlen=…)` under a lock; bounded by construction. |
| SRV-04 | 10 | `SECRET_KEY` is literally the string `'your_secret_key'`. | From env, random default. |
| SRV-05 | 57–61 | The `/data` docstring promises 100 records; the code returns 1000. | Validated `limit` query parameter; 400 on bad input. |
| SRV-06 | 11, 48 | `flask_socketio` emits `update_data` on every batch, but **no client ever subscribes** — `dashboard.py` polls `/data` over HTTP instead. The entire SocketIO dependency is dead weight. | Removed. The new backend uses WebSockets with a client that actually listens. |
| SRV-07 | 3–4 | `os` and `csv` imported, never used. | Removed. |
| SRV-08 | — | No CORS configuration, so a browser client served from :8050 can never call :5000. | `flask-cors`, origin configurable. |

## `simulation.py` — offline CSV simulator (5)

| ID | Line | Defect | Fix |
|---|---|---|---|
| SIM-01 | 13–14, 18 | `DATA_DIR = "../data"` is relative, so the script only works when run from inside `simulation_code/`; and `os.makedirs` is never called, so `open()` raises outright if the directory is absent. | Path resolved from `__file__`; `mkdir(parents=True, exist_ok=True)`. |
| SIM-02 | 17–20 | The header is written only when the file does not exist. **The shipped `simulated_data.csv` has no header row at all across 45,000 lines** — proof it was generated in a broken state and appended to ever since. | Header validated on every run; a headerless file is moved aside, not appended to. |
| SIM-03 | 26–35 | Unbounded growth: 1,200 rows every 10 s, forever, with no rotation. | `--max-rows` with rotation. |
| SIM-04 | 31–32 | **`value` and `status` are drawn from two independent random calls.** The label has no relationship whatsoever to the signal, so no model could ever learn anything from this file. | `status` derived from `ac_curr`. |
| SIM-05 | 20 | Columns (`timestamp,pmd_type,value,status`) do not match `server.py`'s schema (which adds `ac_volt`, `ac_curr`). The two "simulators" emit mutually incompatible records. | Unified schema. |

## `dashboard.py` — simulation dashboard (6)

| ID | Line | Defect | Fix |
|---|---|---|---|
| DBD-01 | 112 | `app.run_server()` — removed in Dash 3.x. | `app.run()`. |
| DBD-02 | 65 | `requests.get` with **no timeout**. A hung server blocks the Dash worker thread indefinitely. | 4 s timeout. |
| DBD-03 | 106–109 | A single bare `except Exception` collapses timeout, connection refused, HTTP error and bad JSON into one red dot, with no logging. | Each failure mode caught, logged and reported distinctly. |
| DBD-04 | 69, 109 | Returns `{}` as a Plotly figure, which renders broken rather than empty. | Proper empty figure carrying the reason. |
| DBD-05 | 75–93 | Three 56-category bar charts rebuilt every 5 s, averaging over a rolling window that mixes machines, so the bars jitter meaninglessly. | Time series for the busiest machines plus a ranked peak-current snapshot. |
| DBD-06 | 41, 96 | `page_size=10` on a table only ever handed `df.tail(10)` — the pagination is decorative. | Real window passed; sorting and filtering enabled. |

---

# Part 2 — defects found in the 2026 rebuild

The 2024 code got a 34-defect audit; it would be dishonest not to audit the
replacement to the same standard. These were found by an adversarial multi-agent
review of the rebuilt codebase, then verified individually against the source.

Twenty confirmed. Three of them meant a published claim was false, and one
had been silently corrupting this session's own results.

| ID | Severity | File | Defect | Fix |
|---|---|---|---|---|
| RP-01 | **critical** | `pyproject.toml` | `fastapi`, `uvicorn`, `starlette` and `websockets` were **never declared as dependencies**, yet `backend/app/main.py` imports fastapi and the Dockerfile and Makefile invoke uvicorn. A fresh clone following the README could not start the backend at all. | Added an `api` extra and to `dev`. |
| RP-02 | high | `tests/test_api.py` | Because of RP-01, `pytest.importorskip("fastapi")` skipped the **entire backend contract suite** in CI while the step still reported success. | Fixed by RP-01; the suite now runs — 125 tests pass. |
| RP-03 | high | `.github/workflows/ci.yml:22` | `mypy ml/pmdlib \|\| true` discarded the exit code, so type checking could never fail the build. It was hiding **6 genuine type errors**. | Removed `\|\| true`; fixed all 6. |
| RP-04 | high | `ml/pmdlib/sim/waveform.py` | `MachineSpec.stall_a` was declared but **never read**. Current was clipped only from below, so the multiplicative chain (fault × wear × cold × ice) reached **49.7 A** on a machine whose highest real recorded current is 15.74 A. The model was training on physically impossible waveforms. | Clip to `spec.stall_a`; peaks now bounded at 15.5 A. |
| RP-05 | high | `ml/pmdlib/sim/spec.py` | **Weather and fault were the same signal.** A healthy machine in the icy regime produced a 6.10 A plateau; `FRICTION_HIGH` at mid severity produced 6.14 A — a 0.04 A difference under two different labels. Direct label contamination, and the reason `FRICTION_HIGH` recall sat at 0.471. | Cold and ice friction bounded well below fault magnitude. Separation is now 1.34 A. |
| RP-06 | high | `ml/pmdlib/sim/degradation.py` | The `ACCELERATING` wear ramp was `linspace(0.3, 2.4, n_cycles)` — indexed on the **simulation horizon**, so the same machine with the same seed aged differently depending only on how many cycles you chose to simulate (health at cycle 200 ranged 0.936–0.980). | Ramp indexed on absolute cycle count via `ACCELERATION_SCALE_CYCLES`. |
| RP-07 | high | `ml/pmdlib/sim/calibrate.py` | The two-sample KS test was computed, reported as a column, and **never consulted** — `"pass"` used Wasserstein distance alone. `docs/DATA.md` claimed the KS test gated CI. It did not. | `KS_TOLERANCE` per channel; `pass` now requires both. |
| RP-08 | high | `ml/pmdlib/data/loader.py` | The on-disk feature cache was keyed **only on dataset name**, with a shape check that is invariant under regeneration. Regenerating the simulator silently paired stale features with fresh labels. Hit during this session. | Cache key is now a SHA-256 fingerprint of the signals file plus the feature-name list, so regenerating the data or changing the extractor invalidates it. |
| RP-10 | high | `ml/pmdlib/cli.py:73` | `if __name__ == "__main__": app()` sat **above** the `@app.command("train")` decorator, so `python -m pmdlib.cli` invoked `app()` before `train` was registered. The command silently did not exist via that entrypoint while working fine via the `railpoint` console script. **Two training runs completed with exit status 0 having trained nothing**, and their stale results were nearly reported as new. | Guard moved to the bottom of the file; both entrypoints now expose all three commands. |
| RP-11 | high | `frontend/src/components/Waveform.tsx` | `cursor` is an index into the current event's samples but was never reset when the `event` prop changed, and `App.tsx` mounts `<Waveform>` without a `key`. Hovering sample 520 of a 600-sample capture and then selecting a 259-sample one left the readout describing a sample that does not exist. | Reset `cursor` on `event.id`. Channel visibility deliberately still persists — that is an operator preference, not a property of the event. |
| RP-12 | high | `frontend/src/App.tsx` | Every non-normal push refetched the alert list and replaced state wholesale, rolling back an operator's optimistic acknowledge if the refetch landed before the POST response. | `pendingAlerts` ref plus a `mergeAlerts` reconciliation that preserves local state for in-flight ids. |
| RP-13 | medium | `frontend/src/App.tsx` | A window-level keydown handler called `preventDefault()` on arrow keys **anywhere in the document**, swallowing horizontal scrolling and any other widget's arrow handling, and changed selection without moving focus — leaving a screen-reader user's cursor on a node the app no longer considered selected. | Scoped to the schematic or document body; moves DOM focus to the newly selected node. |
| RP-14 | medium | `frontend/src/components/Waveform.tsx` | Every null sample rendered as "not wired", but the backend emits null for any non-finite value and the simulator injects mid-capture dropouts. A transient gap was reported to the operator as a missing sensor. | Distinguishes a channel with no readings anywhere ("not wired") from a gap in an instrumented channel ("no data"). |
| RP-15 | **critical** | `backend/app/main.py` | `/api/health` returned `{"status": "ok"}` unconditionally. With neither the encoder nor the probe loaded, every event fell through to a uniform distribution while the console reported healthy — the one failure mode a safety system must not have. (The severity rule does downgrade it to "info" on low confidence, so it was not a confident all-clear.) | `InferenceService.degraded`; the endpoint now returns **503** with `status: "degraded"` and `scoring: false`. Regression-tested. |
| RP-16 | high | `backend/app/services/inference.py` | `calibration.npz` was loaded unconditionally *before* the fallback check, so the conformal qhat and Mahalanobis statistics calibrated on the encoder were applied to the linear probe. The probe scores on a different scale and produces no embedding at all, so this voided the coverage guarantee rather than transferring it. | Calibration is loaded only when the encoder is actually serving. Regression-tested. |
| RP-17 | high | `backend/app/services/inference.py` | `rul_invert` is `expm1(...).clamp(min=0)` — bounded below only. `expm1` overflows to `+inf` for any float32 logit above ~88, and `inf`/`NaN` is not valid JSON, so it would 500 `/api/machines` and corrupt the WebSocket frame. | Non-finite RUL is returned as `None`. |
| RP-18 | high | `backend/app/services/stream.py` | Every warning/critical throw appended a new alert with no dedup. A machine past the symptom threshold raises the same condition on *every* subsequent throw, so one degrading machine floods the 200-entry deque and evicts alerts an operator has already acknowledged — losing their triage work. | Alerts collapse per (machine, fault) while unresolved, carrying a `count` and `last_ts`; a warning that escalates to critical reopens. Regression-tested against eviction. |
| RP-19 | high | `frontend/src/App.tsx` | The base data (`machines`, `events`, `alerts`) was fetched exactly once at mount with no retry. The API loads torch and the model weights and takes ~25 s to start, so opening the dashboard first left the schematic and fleet table **permanently empty** — while the WebSocket connected, the counters updated from `/api/stats`, and the header claimed **"Live"** over a blank schematic. Only a manual reload fixed it. | Retry with backoff until it succeeds; the header shows "Waiting for the API…" until the base data lands, so it cannot claim Live over nothing. Verified by stopping the API, loading the page, and restarting it — recovery is automatic with no reload. |
| RP-20 | medium | `.claude/launch.json` | Every path was relative. The preview launcher runs with a working directory it cannot resolve (`getcwd: cannot access parent directories`) because the project folder contains spaces and ends in a period, so both servers failed with `Operation not permitted`. | Absolute paths; the API runs as `python -m uvicorn` with an explicit `--app-dir` instead of depending on the working directory. |
| RP-09 | medium | `ml/pmdlib/train/pipeline.py` | Conformal calibration is fitted on the same `val` split used for early stopping and checkpoint selection, breaking the exchangeability the coverage guarantee rests on. | Needs a dedicated calibration split. *(pending)* |

## Findings recorded but not yet resolved

- **Acceptance-test circularity (important).** `E01_LOCK_LATCH` parameters were
  tuned to match PMD055#5416/#5417, and `calibrate.HEALTHY_REFERENCE` is exactly
  the four PMD014 events the acceptance test expects to read NORMAL. The
  acceptance test is therefore **no longer fully held out**, and its result should
  be read as "the simulator reproduces these traces well enough for the model to
  recognise them", not as independent field validation. This is the single most
  important caveat on the headline number and is repeated in the model card.
- ~~Frontend: cursor state survives an event change; a stream-triggered alert
  refetch can clobber an in-flight acknowledge.~~ **Fixed (RP-11..RP-14).**
- ~~Backend: probe-fit failure while `/api/health` still reads healthy;
  non-finite RUL can reach the JSON encoder.~~ **Fixed (RP-15..RP-17).**
- ~~Backend: alerts are appended per-throw with no dedup.~~ **Fixed (RP-18).**

Nine further findings were raised by the review agents but their adversarial
verification pass was cut off by a usage limit, so they are **unverified** and
deliberately not listed as defects.
