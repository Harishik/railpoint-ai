# RailPoint&#8202;·&#8202;AI

**AI-Based Failure Detection and Prediction for Railway Point Switch Machines**
철도 선로전환기 고장 탐지 및 예측

Detects and classifies faults in railway point machines from motor-current and
indication-line signals, forecasts remaining useful life, explains every
prediction, and serves it through a live operations console.

> **Provenance.** This is the 2026 rebuild of *Failure Prediction of Railway Point
> Machine* — team **Fault Force**, Woosong University (우송대학교), AI & Big Data,
> Endicott College of International Studies, Sept–Dec 2024, an industry-linked
> capstone (기업연계) with **Sehwa** (Daejeon), advised by Prof. 김영일.
> Department write-up:
> [tech.endicott.ac.kr](https://tech.endicott.ac.kr/board/read.jsp?id=249398&code=tech0604).
> Original team: 유태경, 조재윤, Gazikhodjaev Nodirkhuja, Jamwal Harishik Dev Singh,
> Chaulagai Nishant. Full credit and a candid 2024→2026 comparison in
> [`docs/ORIGIN.md`](docs/ORIGIN.md).

---

## The honest version of the data problem

**There is no publicly downloadable Korean point-machine dataset.** AI Hub,
data.go.kr, KRIC Rail Portal, Kaggle, Hugging Face and Zenodo were all searched;
the Cu-3300 dataset cited in the literature as the field's first open dataset has
been deleted from GitHub. The full search record is in [`docs/DATA.md`](docs/DATA.md).

**The real Sehwa extract cannot train a model.** It is 7 switching events from 2
machines, and **every one carries a fault code** — there are no normal events.

So the data is generated, and the generator is *validated against reality rather
than asserted to match it*:

| Channel | Wasserstein (norm.) | Tolerance | | Statistic | Real | Sim | Error |
|---|---|---|---|---|---|---|---|
| `ac_curr` | 0.0055 | 0.08 | | plateau | 3.855 A | 3.892 A | 1.0% |
| `ac_volt` | 0.0268 | 0.12 | | peak | 9.797 A | 9.536 A | 2.7% |
| `as_volt` | 0.0236 | 0.10 | | throw duration | 205.5 | 208.9 | 1.7% |
| `output_n_volt` | 0.0104 | 0.10 | | capture length | 261.8 | 267.5 | 2.2% |

This runs in CI. If the simulator drifts from the real signals, the build fails.

**The 7 real events are never trained on.** They are the acceptance test.

## What the physics turned out to be

Rendering the real traces for the first time — the 2024 dashboard loaded that file
and never displayed a value from it — showed the classic point-machine current
curve, and the signals independently *corroborate* the Korean maintenance codes:

- **`output_n_volt` is a three-state signal**, not a position ramp: **+23 V** locked
  Normal (정위), **~0 V in transit**, **−23 V** locked Reverse (반위). 78.8% of a
  healthy capture sits at 0 V.
- **PMD055 (E01, 기억쇠 locking latch)** reads ~0 V for all 600 samples — permanently
  in transit, never locking, drive never cut. That *is* the latch diagnosis,
  visible directly in the channel.
- **PMD014#2594** holds −23.9 V throughout with no supply sag: the motor never
  started, so the machine never unlocked.

The simulator reproduces all three.

## Results

Trained on the calibrated simulator, evaluated on machine-held-out splits **and**
on the 7 real events. Every number states which.

### The finding that matters

**Synthetic accuracy and real-world transfer are anti-correlated.**

| Model | Synthetic accuracy | Real diagnostic events |
|---|---|---|
| RandomForest | **0.9683** | 1/3 |
| HistGradientBoosting | 0.9623 | 1/3 |
| MLP | 0.9298 | **3/3** |

The MLP has the *lowest* synthetic accuracy and is the only baseline that passes.
Ranking on the synthetic test split alone would have shipped a model that gets
every real fault wrong. Full analysis:
[`experiments/results/baseline-findings.md`](experiments/results/baseline-findings.md).

Deep-model results: [`experiments/results/deep-summary.json`](experiments/results/).

## Architecture

```
capture ─► phase segmentation ─► 113 features ──────────────► baselines
        └► scale-normalised sequence + explicit scale scalar ─► CNN + Transformer
                                                                ├─ fault (15 classes)
                                                                ├─ RUL (cycles)
                                                                └─ embedding ─► Mahalanobis anomaly
                                                                        └─► conformal sets (90% coverage)
```

- **Input representation** carries shape *and* scale separately, because absolute
  amplitude does not transfer between machine classes but does carry signal.
- **Conformal prediction sets you can act on — in distribution.** RAPS,
  calibrated on a dedicated `calib` split that early stopping never sees. On
  held-out *simulated* machines 88.4% of throws get a single label, wrong 0.20% of
  the time; the 11.6% that get a shortlist are wrong 17.5% of the time — 7.9× the
  base rate. The plain threshold this replaced met its coverage target with every
  set exactly the argmax, so it never once flagged its own mistakes (RP-27).
  **It does not hold on shifted real data:** both real PMD055 errors are confident
  one-label sets, and nothing in the system yet flags a confident wrong fault
  type (RP-28). See `experiments/results/conformal-rules.md`.
- **Anomaly detection is post-hoc**, so it cannot trade classification accuracy
  for its own score, and catches faults outside the taxonomy.

## Quick start

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev,ml]"
```

```bash
.venv/bin/railpoint calibrate      # validate the simulator against real traces
```

```bash
.venv/bin/railpoint build-data     # generate 60,800 labelled events
```

```bash
.venv/bin/railpoint train          # train, calibrate, evaluate, export
```

Run the console — API on :8000, UI on :5173:

```bash
.venv/bin/uvicorn backend.app.main:app --port 8000
```

```bash
npm --prefix frontend install && npm --prefix frontend run dev
```

## Layout

| Path | |
|---|---|
| `ml/pmdlib/sim/` | Physics-informed simulator + CI calibration gate |
| `ml/pmdlib/features/` | Phase-aware feature extraction |
| `ml/pmdlib/models/` | CNN + Transformer, input preparation |
| `ml/pmdlib/eval/` | Conformal prediction, anomaly scoring, acceptance test |
| `backend/` | FastAPI, REST + WebSocket, live simulation |
| `frontend/` | React operations console |
| `legacy/dash-2024/` | The 2024 code, preserved and repaired |
| `docs/BUGS.md` | **34 defects** in the 2024 code, with fixes |
| `docs/DATA.md` | What the data is, and why no public dataset exists |
| `docs/ORIGIN.md` | Attribution and the 2024→2026 comparison |
| `design-system/MASTER.md` | Frontend design system |

## Notes

Environment: PyTorch dropped macOS x86_64 wheels after 2.2.x, so on Intel Macs
torch is pinned `<2.3`, which forces `numpy<2` and `scipy<1.14`. All pins are
platform-conditional; other machines get current versions.

Headline metrics are on **simulated data calibrated to 7 real traces**. The
real-trace acceptance test is reported separately and is the number that matters.

## License

MIT for the code. The Sehwa extract is company-provided industrial data — see
[`docs/DATA.md`](docs/DATA.md) and the open item in [`docs/ORIGIN.md`](docs/ORIGIN.md).
