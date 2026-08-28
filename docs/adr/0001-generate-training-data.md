# ADR-0001 — Generate the training data rather than source it

**Status:** accepted · **Date:** 2026-08

## Context

The project needs labelled point-machine waveforms. It has seven, from two
machines, and every one of them is a fault — there is no normal class at all. A
supervised classifier needs both; an autoencoder needs healthy data to learn from.

No public alternative exists. AI Hub's railway set is track and catenary imagery
behind a Korean account and an application. data.go.kr, the KRIC Rail Portal,
Kaggle, Hugging Face and Zenodo return nothing for point-machine current curves.
**Cu-3300**, cited in the literature as the field's first open point-machine
dataset, has been deleted from GitHub. The ZDJ9 and Network Rail datasets are
described in papers and never released.

## Decision

Build a physics-informed simulator whose healthy current *shape* is a template
fitted directly from the four completed real throws, with amplitude, timing,
supply behaviour, indication sequencing and every fault deformation layered on as
physics. Gate it in CI against the real traces with per-channel Wasserstein and
KS tests plus per-event structural statistics. Hold the seven real events out
entirely as an acceptance test.

## Consequences

**Good.** Labels are exact, including remaining-useful-life, which is otherwise
unobtainable without run-to-failure field data. Rare faults can be sampled to
balance. Data-quality defects can be injected deliberately so the model learns to
survive them.

**Bad, and unavoidable.** Every metric inherits the simulator's assumptions. The
generator was written by the same person who wrote the model, so a fault the
simulator cannot express is a fault the model has never seen. The calibration
gate bounds this; it does not eliminate it.

**Mitigations.** Every reported number states which of the three data sources
produced it. The MetroPT-3 track (ADR-0005) tests the same method on field data
nobody generated for us.

## Rejected

*Wait for more Sehwa data* — the correct answer if it were available; it is an
open request, not a plan. *Train on the seven events* — impossible, no normal
class. *Transfer from a bearing/motor dataset* — different failure physics,
different instrumentation, and it would still need calibrating against the same
seven traces.
