# Data: what exists, what does not, and what we do about it

## 1. The real data — Sehwa PMD extract

`data/raw/sehwa/pmd_events.csv` — 2,424 rows, which is **7 switching events from
2 machines**, not 2,424 samples of anything.

### Channels

| Column | Meaning | Observed range |
|---|---|---|
| `ac_curr` | Motor current (A) | 0.01 – 15.74 |
| `ac_volt` | Single-phase supply (V) | 205.2 – 230.5 |
| `as_volt` | Indication / 표시 line (V) | −24.2 – +24.3 |
| `output_n_volt` | Normal (정위) output (V) | −24.5 – +23.5 |
| `output_r_volt` | Reverse (반위) output (V) | 0.0, or absent |
| `direction` | N (정위) / R (반위) | — |
| `err_code` | Maintenance code — see §2 | E01, E03 |
| `event_seq` | Sample index within the event | 1 – 600 |

### Per-event characterisation

_Table withheld: it reproduced the private Sehwa extract, which is not published._

### What the waveforms actually show

The extract renders as the textbook point-machine current curve — idle, motor
inrush, throw plateau, cutoff — and, importantly, **the physics independently
corroborates the maintenance codes**:

- **PMD014** is a healthy-shaped machine: ~10 A inrush, ~3.8 A plateau, throw
  complete in ~205 samples, `output_n_volt` swinging the full ±24 V as the
  indication switches. `output_r_volt` is **entirely absent** (1224/1224 null) —
  that channel is simply not instrumented on this machine.
- **PMD014#2594 is a failed throw.** Peak 0.09 A, throw length **zero** — the
  motor never started. 177 samples of pure idle current with `output_n_volt`
  pinned at −24 V, never switching. The command was issued; nothing moved.
- **PMD055 (E01, 기억쇠 / locking latch) matches its code exactly.** The throw
  runs 590 samples against PMD014's 205, at a higher plateau (6.6 A vs 3.8 A) and
  higher peak (15.5 A vs 9.8 A), and **hits the 600-sample capture cap** while
  indication never arrives (`output_n_volt` flat at 0.35 V, `output_r_volt` flat
  at 0). That is precisely a latch that never engages: the motor keeps driving
  because the throw never completes.

### The indication lines are a three-state signal

Worth stating separately, because getting it wrong cost a first attempt at the
simulator. `output_n_volt` is **not** a continuous position ramp. The indication
circuit is energised only while the switch is *locked and detected* in a
position:

| Value | Meaning |
|---|---|
| **+23 V** | locked at Normal (정위) |
| **~0 V** | **in transit** — neither position detected |
| **−23 V** | locked at Reverse (반위) |

In PMD014#2593, **78.8% of samples sit in [−2, +2] V** — the line is at 0 for the
whole throw, with fast edges at each end. Two of the fault exemplars fall
straight out of this reading:

- **PMD055 reads ~0 V for all 600 samples** — permanently in transit, never
  locking. That *is* the E01 locking-latch diagnosis, visible directly in the
  channel.
- **PMD014#2594 holds −23.9 V throughout** — never unlocked at all, because the
  motor never started.

`as_volt` is the complementary signal: the **drive command**, 0 V at idle and
±23 V while driving. Whether it returns to 0 is diagnostic on its own — PMD014#2594's
returns (drive cut on timeout) while PMD055's does not (drive never cut).

The first simulator modelled this as a linear ramp and the calibration gate
rejected it at a normalised Wasserstein distance of 0.194 against a 0.10
tolerance. The three-state model scores **0.013**, a 15× improvement. That is the
gate earning its place.

### Why this cannot train a model

**All 7 events carry a fault code. There are zero normal events.** A supervised
classifier needs both classes; an autoencoder needs healthy data to learn from.
Seven events across two machines is also far below what any of the cited
literature uses (Cu-3300 uses 3,300 signals). This extract is therefore used
**only as a held-out real-world acceptance test**, never for training.

### Open question on sampling rate

`duration` is 0.01 for every PMD014 event and 0.007 for every PMD055 event, and
does not scale with sample count (PMD014 varies 177–270 samples at a constant
0.01). So **the sampling rate cannot be derived from `duration`** and is not
stated anywhere in the source material. Indirect estimate: a PMD014 throw of
~205 samples against a typical 3–6 s point-machine throw implies roughly
40–70 Hz; PMD055's 590-sample stalled throw at that rate is ~10 s, consistent
with a drive timeout. **We therefore index on `event_seq` and treat any absolute
timing as an explicitly documented assumption**, rather than asserting a rate we
cannot verify. Worth confirming with Sehwa.

---

## 2. Maintenance codes — `data/raw/sehwa/error_codes.csv`

The shipped `maintenance_code.csv` is EUC-KR encoded and rendered as mojibake in
the 2024 app (APP-11). Decoded, it turns out the codes name **components, not
failure modes** — Sehwa's own maintenance vocabulary:

_Table withheld: it reproduced the private Sehwa extract, which is not published._

This matters for design: the model's output classes are aligned to these seven
real codes rather than to a taxonomy we invent, so a prediction lands directly in
the vocabulary Sehwa's maintenance staff already use.

---

## 3. Why there is no public Korean point-machine dataset

Searched, not assumed. As of August 2026:

| Source | Result |
|---|---|
| **AI Hub** (aihub.or.kr) | Railway set is track / catenary **imagery**, not current signals. Gated behind a Korean account and an application that can be refused. |
| **data.go.kr**, **KRIC Rail Portal** (data.kric.go.kr) | No point-machine condition data. |
| **Kaggle**, **Hugging Face**, **Zenodo**, **Mendeley** | Nothing for point-machine current curves. |
| **Cu-3300** | Cited in the literature as "the first open-source dataset in the area of railway point machines", hosted at `github.com/MichaelYin1994/SignalRepresentationAnalysis`. **That URL now returns 404** and the repo is absent from that account's remaining ~40 repos. It is gone. |
| **ZDJ9** (Shanghai Metro Line 13) | Used in several papers; never released. |
| **Network Rail** | Several thousand daily actuation CSVs used in *Sensors* 2020; unlabelled and not published. |
| *Applied Sciences* 14(1):267, 2024 | Nearest published current-signal work. Data availability is "contained within the article", and it is Indonesian (PT KAI), not Korean. |

**Conclusion: the data has to be manufactured, and manufactured honestly.**

## 4. What we do instead

1. **Physics-informed simulator**, calibrated against the 7 real traces above and
   gated in CI by a two-sample KS + Wasserstein test per channel. Fault classes
   aligned to the E01–E07 component codes. A hidden per-machine degradation state
   makes RUL ground truth exact by construction.
2. **The 7 real events as acceptance test** — never trained on.
3. **MetroPT-3** (UCI 791, CC BY 4.0) as a genuine-field-data track: 1,516,948
   readings at ~0.1 Hz, Feb–Aug 2020, Porto Metro air production unit, with four
   air-leak failures documented by the authors. A different asset, but real, and
   it tests the method on data nobody generated for us. Implemented in
   `ml/pmdlib/data/metropt.py` and `scripts/metropt_experiment.py`; the 208 MB
   archive is not committed.

   **What it found is worth more than the headline.** The same unsupervised
   Mahalanobis pipeline reaches **ROC-AUC 0.956** — failure windows score a
   median 90 against a normal median of 10. But **precision@100 is 0.00**: 337
   normal windows outscore the *highest* failure window, and 431 of the top 1000
   fall on a single undocumented day. MetroPT-3 labels air-leak failures only,
   and the asset plainly has other real anomalies.

   A maintenance team told to investigate the top 100 alarms would find none of
   the four documented failures. **AUC flatters an anomaly detector that could
   not be used as an alarm list**, which is exactly the kind of result a project
   trained mostly on its own simulator needs to publish rather than bury.

Every headline metric in this repository states which of these three it was
measured on.
