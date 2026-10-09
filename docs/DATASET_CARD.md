# Dataset card — RailPoint synthetic corpus

## Summary

Two generated datasets plus one small real extract held out as an acceptance test.

| Dataset | Events | Machines | Balance | Purpose |
|---|---|---|---|---|
| `stratified` | 9,600 | 64 | exactly balanced, 640/class | classification |
| `fleet` | 51,200 | 64 | 18.2% anomalous | RUL, anomaly detection |
| `sehwa` (real, private) | **7** | 2 | 100% faulty | acceptance test only; not published |

## Why it is generated

There is no publicly downloadable Korean point-machine dataset — AI Hub,
data.go.kr, KRIC Rail Portal, Kaggle, Hugging Face and Zenodo were all searched,
and the Cu-3300 dataset cited in the literature as the field's first open dataset
has been deleted from GitHub. The full search record is in [`DATA.md`](DATA.md).

The real extract has **no normal events**, so it cannot train a supervised model
or an autoencoder. Generating data was the only honest option; validating the
generator against the real traces is what makes it defensible.

## Generation

A physics-informed simulator whose healthy current *shape* is a template fitted
directly from the four completed real throws, with amplitude, timing, supply
behaviour, indication sequencing and every fault deformation layered on as
physics. Scenario axes:

- **15 fault classes**, anchored on Sehwa's own E01–E07 component codes plus
  mechanical and supply conditions the code table does not enumerate
- **Severity** — continuous 0–1, so each class spans just-detectable to hard failure
- **Weather** — four regimes across the Korean annual range; cold grease raises
  plateau current measurably
- **Data quality** — dropouts, stuck sensors, ADC clipping, EMI bursts, missing
  channels. These never change an event's label; a model that has only seen clean
  data will call a stuck sensor a machine fault
- **Degradation** — seven trajectory kinds (stable, gradual, accelerating, shock,
  intermittent, seasonal, infant mortality) with per-machine lifetimes drawn
  log-normally. Health is *generated*, so RUL ground truth is exact by
  construction — the one real advantage a simulator has here
- **Service horizon** — each machine is simulated over 4,000 cycles, the same
  horizon the live console uses, and 800 throws are recorded evenly across it.
  Recording a sample of a whole life, rather than every throw of its first 800
  cycles, is what lets 39 of 64 machines reach a failure — against 11 before —
  so RUL is calibrated on several machines instead of one (RP-26).

## Fields

`signals` is `(n_events, 600, 5)` float32, **NaN-padded** — padding is NaN rather
than zero because zero is a valid reading. `lengths` gives the true capture
length. `meta` carries the label, severity, health, RUL, trajectory kind, weather,
data-quality flags and split.

RUL uses `-1` for **censored** samples — no failure ahead of them. That is not
"fails immediately", and it is excluded from the RUL loss.

## Splits

By **machine**, assigned by hashing the machine id, so `fleet` and `stratified`
cannot disagree about which machines are held out.

Four of them — `train` 70%, `val` 7.5%, `calib` 7.5%, `test` 15%. `val` selects
the checkpoint and `calib` calibrates the conformal quantile; keeping them apart
is what makes the coverage guarantee mean anything, since a quantile fitted on
the split that chose the checkpoint is fitted on the model's best day. See
`ml/pmdlib/utils/splits.py`.

## Known limitations

1. `PMD-B`'s healthy baseline is **extrapolated**, not calibrated — both real
   PMD055 events are faults.
2. `output_r_volt`'s healthy behaviour is **inferred**: it is absent on PMD014 and
   flat zero on PMD055, so no healthy reference exists.
3. Class *co-occurrence* is not modelled — each event carries one fault, whereas
   a real machine can have a worn motor and a damp indication circuit at once.
4. Sampling rate is not established; the corpus indexes on sample number.
5. Being generated, the corpus inherits every assumption in the fault model. It
   should not be used to estimate real-world class priors.

## Provenance and licence

Code MIT. The real extract is **company-provided industrial data** from an
industry-linked capstone with Sehwa (Daejeon) — see the open item in
[`ORIGIN.md`](ORIGIN.md) before publishing it. A SHA-256 record is kept at
`data/raw/sehwa/SHA256SUMS` so the loader can be used without the raw file.

MetroPT-3 (UCI, CC BY 4.0) is referenced as a real-field-data track and is not
redistributed here.

## Regenerate

```bash
.venv/bin/railpoint build-data
```

Deterministic given the seed. `.venv/bin/railpoint calibrate` re-checks the
generator against the real traces.
