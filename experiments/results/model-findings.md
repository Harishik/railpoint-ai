# Model findings — what the failures actually taught us

A record of the diagnoses, not just the scores. Each entry is a case where a
metric looked acceptable and the underlying system was wrong.

---

## 1. The acceptance test earned its place immediately

The first baselines scored **0.968 accuracy** on held-out synthetic machines and
got **1 of 7** real events right. Had the project reported only synthetic
accuracy — as the 2024 version effectively did — it would have claimed success
while the model could not read a real waveform at all.

The gap was **absolute amplitude**. A PMD-A holds a 3.83 A plateau; a PMD-B holds
5.0 A. Models leaning on raw current learned the *fleet's composition*, and the
real PMD014 sits at the low end of a distribution the synthetic fleet centred
higher.

**Fix.** Scale-free shape features (`curr_active_cv`, `throw_slope_norm`,
`sag_frac`, `inrush_mean_over_plateau`, …), and in the network, current divided
by the event's own plateau with the divisor handed back as an explicit scalar.
Shape and scale both reach the model, separately.

**Result.** Real acceptance went **1/7 → 5/7**. All four healthy PMD014 throws
read NORMAL.

---

## 2. A latch failure persists between throws

PMD055's two real events were predicted `OBSTRUCTION`, not `E01_LOCK_LATCH`.

The discriminator was `ind_std`: **0.016 real versus 5.263 synthetic** — a 300×
gap. The real machine reads ~0 V on `output_n_volt` from *sample zero*. It was
already out of position before the capture began.

That is not noise, it is physics the simulator had missed: **a latch that fails
to engage leaves the switch mid-stroke, and it is still there on the next
throw.** The generator was starting every event from a cleanly locked rail.

**Fix.** `starts_unlocked` on E01 above severity 0.5 — no locked rail to leave.
`ind_std` went 5.263 → **0.035** against the real 0.016.

---

## 3. An architectural bug that made one class unlearnable

`GEARBOX_WEAR` scored **precision 0.126, recall 0.748, F1 0.216** while firing
~750 times for 127 true cases. Every class with a large-amplitude signature
scored above 0.95.

The cause was in the encoder, not the data. The CNN stem is three stride-2
convolutions — **8× decimation**, 512 samples to 64 tokens. GEARBOX_WEAR's entire
signature is a ripple with a **7–16 sample period**. After 8× decimation that is
0.9–2 tokens: **at or below Nyquist.** The stem aliased the signature away, so
the Transformer could not have learned the class from the sequence under any
amount of training.

E04_MOTOR (period 3–8) and PHASE_LOSS (period 6) alias just as badly yet score
0.98 and 1.00 — because both *also* carry amplitude signatures that survive
decimation. GEARBOX_WEAR had nothing else.

**Fix.** Measure the periodicity at full resolution, before the stem destroys it,
and pass it as scalars (`_ripple_spectrum` in `models/prep.py`): tonal peak
ratio, ripple-band power, dominant period, spectral flatness. Cheaper than
attending over undecimated samples, and it recovers precisely what was lost.

| class | peak_ratio | band_ratio | dom_period | flatness |
|---|---|---|---|---|
| NORMAL | 0.049 | 0.455 | 0.417 | 0.239 |
| GEARBOX_WEAR | **0.554** | **0.971** | 0.449 | **0.021** |
| E04_MOTOR | 0.471 | 0.847 | **0.207** | 0.084 |
| FRICTION_HIGH | 0.038 | 0.387 | 0.531 | 0.189 |

An 11× separation on `peak_ratio` where none existed, and `dom_period` splits
gearbox (≈10.8 samples) from motor (≈5) exactly as the simulator generates them.

**A note on method.** This was found by asking *why* a class scored badly rather
than by tuning. No amount of hyperparameter search would have fixed it, because
the information was not in the encoder's input.

---

## 4. Two faults the simulator made physically identical

`E06_CABLE` scored **precision 0.313, recall 0.994** — a sink absorbing ~500
healthy events.

Both ambient grid noise (`env.supply_quality`, up to 1.35× on the fleet) and the
cable fault added **load-independent zero-mean Gaussian noise** to the supply.
They were the same signal. No model could separate them, because there was
nothing to separate.

The physics says otherwise: a resistive cable fault drops the rail in proportion
to the current it carries (**V = IR**), always downward and tracking the load.
Grid noise is symmetric and load-independent.

**Fix.** Cable instability is now load-correlated and one-directional.

| case | sag_frac | sag_per_amp | supply_idle |
|---|---|---|---|
| NORMAL, quiet grid | 0.0273 | 1.570 | 218.83 |
| NORMAL, **noisy** grid | 0.0273 | **1.567** | 218.82 |
| E06_CABLE sev 0.9 | 0.0811 | **5.472** | 218.51 |
| SUPPLY_UNDERVOLTAGE sev 0.6 | 0.0367 | 1.526 | **194.64** |

Grid noise no longer moves `sag_per_amp` at all, a cable fault reaches 3.5×
NORMAL, and the two power faults now separate on **different physical axes** —
cable raises series resistance, undervoltage drops the rail.

---

## 5. Real field data: an AUC that a maintenance team could not use

MetroPT-3 (UCI 791, CC BY 4.0) is the only data in this project that nobody
generated for it: 1,516,948 readings from a Porto Metro air production unit over
six months, with four air-leak failures documented by the authors.

Running the same unsupervised pipeline against it produced two numbers that
disagree:

| metric | value |
|---|---|
| ROC-AUC | **0.9564** |
| precision@50 | **0.00** |
| precision@100 | **0.00** |
| precision@1000 | 0.048 |
| failure-window score, median / max | 89.7 / 327.7 |
| normal-window score, median | 10.2 |
| normal windows scoring above the **highest** failure window | **337** |

The AUC is not wrong. Failure windows really do score ~9x a typical normal
window. But the extreme tail is dominated by something else entirely — 431 of
the top 1000 windows fall on 2020-06-23, which is not a documented failure day at
all. MetroPT-3 labels **air-leak failures only**, and a six-month record of an
operating compressor plainly contains other genuine anomalies: maintenance
activity, sensor excursions, unusual duty cycles.

**A team told "investigate the top 100 alarms" would find none of the four
failures.** That is the number that decides whether anyone uses the system, and
ROC-AUC hides it completely.

Two things follow. First, ranking metrics belong next to AUC in any
anomaly-detection report — this project now prints both. Second, an unsupervised
detector on real data is answering "what is unusual", not "what is the failure
you care about", and those diverge more than the literature's AUC tables suggest.

---

## Standing limitations

- **PMD055 is still misclassified** as of the last completed run, and its
  conformal set does not contain the true label. Fixes 3 and 4 are not yet
  reflected in a completed training run.
- **Three scoreable real events** is far too few to estimate real accuracy. The
  acceptance test proves transfer is *possible*, not that it is reliable.
- Every fix above was validated against a generator we also wrote. The generator
  is checked against the real traces in CI, which bounds but does not eliminate
  that circularity.
