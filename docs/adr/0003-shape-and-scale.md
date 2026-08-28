# ADR-0003 — Feed the encoder shape and scale separately

**Status:** accepted · **Date:** 2026-08

## Context

The first baselines scored **0.968** on held-out synthetic machines and got
**1 of 7** real events right. The gap was absolute amplitude: a PMD-A holds a
3.83 A plateau where a PMD-B holds 5.0 A, so models leaning on raw current were
learning the synthetic fleet's composition rather than the fault. Real PMD014
sits at the low end of a distribution the synthetic fleet centred higher.

Deleting amplitude is not the answer either — plateau height genuinely carries
fault information, and a friction fault *is* an amplitude change.

## Decision

Divide the current channel by the event's own plateau so the sequence carries
pure shape, then hand the divisor back to the network as an explicit scalar.
Both reach the model; neither can be mistaken for the other. The feature models
get the same treatment through scale-free ratios (`curr_active_cv`,
`throw_slope_norm`, `sag_frac`, `inrush_mean_over_plateau`).

## Consequences

Real acceptance went from 1/7 to 6/7 with no architecture change. The model
generalises across machine sizes it has never seen, which matters more than the
synthetic score it costs.

A machine whose plateau is itself the anomaly is now harder to detect from shape
alone — the scalar carries that, and it is one input among several rather than
the dominant signal it used to be.

## Rejected

*Global normalisation* — pins the model to the training fleet's amplitude
distribution, the original bug. *Per-machine baselines* — correct in deployment
where a baseline exists, unusable on a machine's first throw.
