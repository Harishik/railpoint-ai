# Model card — PointMachineNet

## What it is

A 1D-CNN stem feeding a Transformer encoder over five synchronised channels from
one point-machine throw, with two supervised heads and one post-hoc scorer.

| | |
|---|---|
| Parameters | 515,089 |
| Input | 5 channels × 512 samples + 4 scalars |
| Outputs | 15-class fault, RUL (cycles), embedding |
| Inference | ~1.3 ms/event, CPU, batch 4 |
| Framework | PyTorch (pinned `<2.3` on Intel macOS — no x86_64 wheels after 2.2.x) |

**Intended use.** Decision *support* for point-machine maintenance planning:
triage which machines a crew should inspect first, and give a maintainer the
evidence behind that ranking.

**Not intended for.** Anything on a safety path. This model must never gate a
train movement, release an interlocking, or replace a physical inspection. It has
never been validated on an operational railway.

## Inputs

Channels, in order: `ac_curr` (A), `ac_volt` (V), `as_volt` (V),
`output_n_volt` (V), `output_r_volt` (V).

The representation is the load-bearing design decision. Current is divided by the
event's own plateau so the network sees **shape**; the divisor is then handed back
as an explicit scalar so the network also sees **scale**. Baselines that leaned on
raw amplitude scored 0.968 on synthetic data and got 1 of 3 real faults right —
absolute amplitude does not transfer between machine classes, but it does carry
signal, so neither keeping nor deleting it alone is correct.

## Training data

**Generated, not collected.** See [`DATA.md`](DATA.md) for why: no public Korean
point-machine dataset exists, and the available real extract is 7 events from 2
machines with no normal events at all.

- **stratified** — 9,600 events, exactly balanced across 15 classes, for classification.
- **fleet** — 51,200 events at realistic (~16%) fault prevalence, for RUL and anomaly.

Splits are **by machine**, assigned by hashing the machine id so both datasets
agree. Two throws from one machine minutes apart are near-duplicates; splitting
on events would leak.

The generator is validated against the real traces in CI (per-channel Wasserstein
and per-event structural statistics). If it drifts, the build fails.

## Evaluation

Every metric states which data produced it.

- **Synthetic held-out test** — machines never seen in training.
- **Real acceptance test** — the 7 genuine Sehwa events, never trained on. Scored
  on the 3 whose fault is unambiguously present in the signal; the other 4 are
  reported, not scored, because their maintenance code names a component that
  their capture does not show.

Conformal prediction supplies distribution-free 90% coverage. A prediction set of
size one is an actionable diagnosis; size four is the model saying "one of these",
which is honest and still useful. Widening sets on a machine indicate the model
is off its training distribution.

## Limitations

1. **Trained on simulated data.** Headline numbers describe performance on a
   generator calibrated to 7 real traces — not on an operational fleet.
2. **Two machine types.** `PMD-B`'s healthy baseline is extrapolated: both real
   PMD055 events are faults, so no healthy PMD055 waveform exists to fit.
3. **Sampling rate unverified.** It cannot be derived from the `duration` field
   and is not documented anywhere in the source material; the model indexes on
   sample number and any absolute timing is a stated assumption.
4. **Seven real events** is far too few to estimate real-world accuracy. The
   acceptance test proves transfer is *possible*, not that it is *reliable*.
5. **Attribution is a linear local approximation** when the fallback probe is
   serving, and a deviation-magnitude proxy for the encoder. Integrated gradients
   would be the honest upgrade.
6. **No adversarial or drift testing.** A sensor fault that mimics a machine fault
   has not been studied.

## Ethical and operational considerations

Railway signalling is safety-critical and regulated. A false negative here means
a fault reaches service; a false positive wastes a maintenance visit. The
asymmetry is deliberate in the RUL scoring, which penalises late predictions more
heavily than early ones, but the appropriate operating threshold is an
infrastructure-manager decision and is not baked in.

The model reports which weights are serving (`/api/stats`), because a console
that cannot tell an operator whether it is running the trained model or a
fallback is worse than one with no model at all.

## Reproduce

```bash
make data && make train
```

Writes `experiments/results/deep-summary.json`, per-class metrics, the acceptance
table and the training history.
