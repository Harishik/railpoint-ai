# RailPoint-AI

**AI-Based Failure Detection and Prediction for Railway Point Switch Machines**
(철도 선로전환기 고장 탐지 및 예측)

A 2026 rebuild of a 2024 industry-linked university capstone. Detects and
classifies faults in railway point machines from motor-current and indication-line
signals, forecasts remaining useful life, explains every prediction, and serves it
all through a live operations dashboard.

> **Provenance.** This is the successor to *Failure Prediction of Railway Point
> Machine* — team **Fault Force**, Woosong University (우송대학교), AI & Big Data,
> Endicott College of International Studies, Sept–Dec 2024, an industry-linked
> capstone (기업연계) with **Sehwa** (Daejeon). Department write-up:
> [tech.endicott.ac.kr](https://tech.endicott.ac.kr/board/read.jsp?id=249398&code=tech0604).
> See [`docs/ORIGIN.md`](docs/ORIGIN.md) for full credit and what changed.

---

## Status

| Phase | State |
|---|---|
| 0 · Repository scaffold | ✅ |
| 1 · Repair the 2024 codebase (34 defects) | ✅ [`docs/BUGS.md`](docs/BUGS.md) |
| 2 · Data foundation — simulator, calibration, MetroPT-3 | 🚧 |
| 3 · Models — classification, RUL, conformal, XAI | ⬜ |
| 4 · FastAPI backend | ⬜ |
| 5 · React dashboard | ⬜ |
| 6 · Docs & deploy | ⬜ |

## Honest data provenance

There is **no publicly downloadable Korean point-machine dataset** — AI Hub,
data.go.kr, KRIC Rail Portal, Kaggle, Hugging Face and Zenodo were all searched,
and the Cu-3300 dataset cited in the literature as the field's first open dataset
has been deleted from GitHub. Full search record in [`docs/DATA.md`](docs/DATA.md).

The real Sehwa extract is **7 switching events from 2 machines, all of them
faulty** — no normal events, so it cannot train a supervised model. This project
therefore:

1. Builds a **physics-informed simulator**, calibrated against those 7 real traces
   and gated in CI by a per-channel KS + Wasserstein test.
2. Holds the **7 real events out entirely** as a real-world acceptance test.
3. Adds **MetroPT-3** (UCI, CC BY 4.0) as a genuine field-data track.

**Every metric in this repository states which of those three it was measured on.**

## Quick start

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev,ml]"
```

The repaired 2024 code lives separately — see [`legacy/dash-2024/`](legacy/dash-2024/).

## License

MIT for the code. The Sehwa extract is company-provided industrial data; see
[`docs/DATA.md`](docs/DATA.md) for its handling.
