# ADR-0004 — Measure ripple periodicity outside the encoder

**Status:** accepted · **Date:** 2026-08

## Context

`GEARBOX_WEAR` scored **precision 0.126, F1 0.216** while every class with a
large-amplitude signature scored above 0.95. The cause was architectural, not
statistical: the CNN stem is three stride-2 convolutions — **8× decimation** —
and the gearbox signature is a ripple with a **7–16 sample period**. After 8×
decimation that is 0.9–2 tokens, at or below Nyquist. The encoder could not have
learned the class under any amount of training, because the information was not
in its input.

`E04_MOTOR` (period 3–8) and `PHASE_LOSS` (period 6) alias just as badly and
score 0.98 and 1.00 — both carry amplitude signatures that survive decimation.
Gearbox wear has nothing else.

## Decision

Compute periodicity at full resolution, before the stem, and pass it as scalars:
tonal peak ratio, ripple-band power, dominant period, spectral flatness.

## Consequences

`peak_ratio` separates gearbox wear from normal by 11× where nothing separated
them before, and `dom_period` distinguishes gearbox (~10.8 samples) from motor
(~5) exactly as the simulator generates them.

The model now has a hand-designed input in an otherwise learned pipeline. That is
a real cost in elegance, paid deliberately: the alternative is attention over
undecimated samples, which is quadratic for one class.

If the stem's stride ever changes, these scalars become partly redundant. The
docstring says so.

## Rejected

*Reduce the stride* — quadratic attention cost for one class. *Wider kernels* —
does not help; the information is destroyed by decimation, not by receptive
field. *More training* — cannot recover aliased signal.
