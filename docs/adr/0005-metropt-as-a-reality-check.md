# ADR-0005 — Use MetroPT-3 as a reality check, not as training data

**Status:** accepted · **Date:** 2026-08

## Context

Everything else is trained on data we generated (ADR-0001), which leaves one
question open: does the method work on data nobody built for it? The seven real
Sehwa events cannot answer it — too few, no normal class, and the simulator was
partly fitted to them.

MetroPT-3 (UCI 791, CC BY 4.0) is a real operating railway asset: 1.5 M readings
from a Porto Metro Air Production Unit over six months, with four air-leak
failures documented by the authors rather than inferred from the signal.

## Decision

Run the same unsupervised machinery — window, summarise, fit on normal operation
only, score by Mahalanobis distance — against MetroPT-3, split temporally, and
report it as a separate track.

## Consequences

The repository contains at least one number measured on field data that nobody
generated for this project.

It is **not a point machine**. Different asset, different failure physics,
different sampling rate. No model transfers between the two tracks and no
MetroPT-3 metric describes point-machine performance. Presenting it as if it did
would be the same overclaiming this rebuild exists to correct.

The 208 MB archive is not committed; `scripts/metropt_experiment.py` documents
the fetch.

## Rejected

*Train the point-machine model on it* — meaningless, different physics.
*Skip it* — leaves the central weakness of a simulator-trained project untested.
