# Origin and attribution

This is the **2026 rebuild of a 2024 university capstone**, not original work.
What follows is the full record of what came before, who did it, and what changed.

## The original project

**Failure Prediction of Railway Point Machine** — team **Fault Force**

| | |
|---|---|
| Institution | Woosong University (우송대학교), **AI & Big Data**, Endicott College of International Studies |
| Period | September – December 2024 |
| Type | Industry-linked capstone (기업연계 기반) |
| Industry partner | **Sehwa** (세화), Daejeon — provided the project, requirements and data |
| Advisor | Prof. 김영일 (Kim Young-il) |
| Department page | <https://tech.endicott.ac.kr/board/read.jsp?id=249398&code=tech0604> |

### Team

The original was a **five-person effort** and is credited as such:

- **유태경** (Yu Tae-kyung)
- **조재윤** (Jo Jae-yoon)
- **Gazikhodjaev Nodirkhuja**
- **Jamwal Harishik Dev Singh** — team lead (대표학생)
- **Chaulagai Nishant**

The 2026 rebuild is by Harishik Dev Singh Jamwal. It reuses the original's
problem framing, the Sehwa data extract and the domain research the team did
together. Nothing here supersedes their contribution to the original.

## What changed, and why

The 2024 deliverables did not agree with each other. The final report and both
competition decks describe an LSTM-Autoencoder + Random Forest + DNN ensemble
with a Gradient Boosting meta-classifier, served by FastAPI over PostgreSQL with
a React dashboard. The code that was actually delivered contains **no machine
learning of any kind**.

| | 2024 | 2026 |
|---|---|---|
| Model | None in the delivered code. `app.py:40` thresholds `ac_curr <= 260` against `np.random.uniform(0.1, 300)` — a constant applied to noise | 1D-CNN + Transformer, 15 fault classes, RUL, conformal prediction sets, post-hoc anomaly detection |
| Real data | Loaded on line 13, **never referenced again**. Every chart plotted random numbers | Characterised in full (`docs/DATA.md`); held out entirely as an acceptance test |
| Training data | 7 events, 2 machines, all faulty — no normal events, so supervised learning was impossible | Physics-informed simulator calibrated against those 7 traces and gated in CI; 60,800 events across 15 classes |
| Backend | Flask returning random numbers, with a SocketIO channel no client subscribed to | FastAPI, REST + WebSocket, model-serving layer that reports which model it is running |
| Frontend | Dash, three pages of which two were dead `href="#"` links | React + TypeScript operations console, design system anchored on the machine's own indication semantics |
| Honesty | ">90% accuracy" obtained by filling empty cells with zeros, as the report itself records | Every metric states which data it was measured on; a real-data acceptance test is run on every model |
| Defects | — | **34 found and fixed**, logged in `docs/BUGS.md` with original line references |

## Why this is presented rather than hidden

Auditing your own past work, finding 34 defects in it, and rebuilding it properly
is a stronger signal than pretending the original was fine. Two of the findings
only surfaced *because* the rebuild insisted on testing against real data:

- The simulator's first indication model scored a normalised Wasserstein distance
  of 0.194 against a 0.10 tolerance. Investigating showed `output_n_volt` is a
  three-state signal, not a ramp. The corrected model scores 0.013.
- Every feature baseline reached 93–97% on synthetic data while getting the real
  faults wrong. The acceptance test caught it; synthetic metrics alone would have
  shipped the worst-transferring model.

Both are recorded in `docs/DATA.md` and
`experiments/results/baseline-findings.md`.

## Data and intellectual property

The Sehwa extract (`data/raw/sehwa/`) is **company-provided industrial data** from
an industry-linked capstone. It comprises 7 switching events from 2 machines.

> **Open item before any public push:** confirm with Sehwa that this extract and
> the decoded Korean maintenance-code table may be published. If not, the loader
> and a SHA-256 checksum ship without the raw file — `data/raw/sehwa/SHA256SUMS`
> already records it, and nothing else in the repository depends on the data being
> present.

Sehwa is credited as data provider. Woosong University and Prof. 김영일 are
credited as the academic context in which the original was produced.
