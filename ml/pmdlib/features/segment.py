"""Split a throw into its physical phases.

Every downstream feature is phase-aware, because "mean current" over a whole
capture mixes idle, inrush and plateau and destroys the information. A
maintenance engineer reasons in phases - "the inrush is fine but the plateau is
high" - so the features should too, and that is also what makes the
explanations legible later.

Phases, from the real PMD014 traces:

    IDLE_PRE   command not yet issued; current at ~0.07 A
    INRUSH     motor start; peaks at ~2.4x plateau within a few samples
    THROW      the switch rail moves; current holds the plateau
    LOCK       final segment where the locking latch engages
    IDLE_POST  drive cut; current back to idle
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Current above this counts as "the motor is running".
ON_THRESHOLD_A = 0.5
#: The inrush is over once current falls to this fraction of the way from peak
#: down to plateau.
INRUSH_SETTLE = 0.15
#: Final fraction of the throw treated as the locking segment.
LOCK_FRACTION = 0.12
#: The inrush peak is searched for only in this leading fraction of the active
#: window. Searching the whole window breaks on obstruction faults, where
#: current ramps upward to a stall and the global maximum sits at the *end* -
#: which collapsed the throw segment to nothing.
INRUSH_SEARCH_FRACTION = 0.30


@dataclass(frozen=True)
class Phases:
    """Sample indices delimiting each phase. Half-open [start, end)."""

    idle_pre: tuple[int, int]
    inrush: tuple[int, int]
    throw: tuple[int, int]
    lock: tuple[int, int]
    idle_post: tuple[int, int]
    motor_started: bool

    def span(self, name: str) -> tuple[int, int]:
        return getattr(self, name)


def segment(current: np.ndarray) -> Phases:
    """Locate the phases in one capture's current channel."""
    n = int(current.size)
    finite = np.nan_to_num(current, nan=0.0)
    on = finite > ON_THRESHOLD_A

    if not on.any():
        # The motor never started - a real and diagnostic condition, seen in
        # PMD014#2594. Everything is idle.
        return Phases((0, n), (0, 0), (0, 0), (0, 0), (0, 0), motor_started=False)

    idx = np.flatnonzero(on)
    t0, t1 = int(idx[0]), int(idx[-1]) + 1
    body = finite[t0:t1]

    # The inrush ends when current has decayed most of the way to the plateau.
    head = max(2, int(body.size * INRUSH_SEARCH_FRACTION))
    peak_at = int(np.argmax(body[:head]))
    tail = body[peak_at:] if peak_at + 1 < body.size else body
    plateau = float(np.median(tail[max(1, tail.size // 4) :])) if tail.size > 3 else float(body.min())
    peak = float(body[peak_at])
    settle = plateau + (peak - plateau) * INRUSH_SETTLE

    below = np.flatnonzero(body[peak_at:] <= settle)
    inrush_end = t0 + peak_at + int(below[0]) if below.size else t0 + max(1, body.size // 8)
    inrush_end = min(inrush_end, t1)

    lock_start = max(inrush_end, t1 - max(1, int((t1 - inrush_end) * LOCK_FRACTION)))

    return Phases(
        idle_pre=(0, t0),
        inrush=(t0, inrush_end),
        throw=(inrush_end, lock_start),
        lock=(lock_start, t1),
        idle_post=(t1, n),
        motor_started=True,
    )
