# ADR-0002 — Split by machine, never by event

**Status:** accepted · **Date:** 2026-08

## Context

The generated corpus holds many throws per machine. Two throws from one machine
minutes apart are near-duplicates: same unit-specific plateau, same supply rail,
same wear state, same instrumentation quirks.

The 2024 project reported ">90% accuracy" reached partly by filling empty cells
with zeros. Optimistic evaluation is the failure mode this project most needs to
avoid, because it is the one that already happened here.

## Decision

Assign splits by hashing the machine id, so `fleet` and `stratified` cannot
disagree about which machines are held out. A machine appears in exactly one
split. The real Sehwa events are never in any training split.

## Consequences

Reported numbers describe generalisation to *unseen machines*, which is the
deployment question — a new installation, not another throw from a machine
already in training.

Scores are lower than an event-level split would produce. That difference is the
leakage the event-level split would have hidden.

Machine-level splitting makes rare shock faults unevenly distributed across
splits, since a fault striking one machine lands entirely in one split. The
stratified sweep exists partly to counter that.

## Rejected

*Random event split* — leaks. *Temporal split within machine* — still leaks the
machine's identity and its unit-specific amplitude, which is precisely the
shortcut the model must not learn (ADR-0003).
