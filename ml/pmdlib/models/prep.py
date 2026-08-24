"""Turn padded captures into model tensors.

The representation is the important design decision here, not the architecture.
The baseline experiments showed that models leaning on absolute current amplitude
fail to transfer to a real machine whose amplitude sits outside the training
fleet's mix (`experiments/results/baseline-findings.md`). But deleting amplitude
outright hurt too - it carries real signal.

So the network gets **both, separately**: channels normalised to shape, plus the
scale it was divided by as an explicit scalar input. It can then use amplitude
where amplitude matters and ignore it where it does not, instead of having the
choice made for it.
"""

from __future__ import annotations

import numpy as np

from ..sim.spec import CHANNELS

#: Fixed sequence length. Captures are padded or resampled onto this grid.
SEQ_LEN = 512
#: Nominal indication rail, used to bring the 24 V channels into unit range.
RAIL_V = 23.43
ON_THRESHOLD_A = 0.5


def _event_scale(curr: np.ndarray) -> float:
    """Robust per-event current scale: the plateau if the motor ran, else idle."""
    active = curr[curr > ON_THRESHOLD_A]
    if active.size > 8:
        return float(np.median(active))
    finite = curr[np.isfinite(curr)]
    return float(np.median(finite)) if finite.size else 1.0


def prepare(signals: np.ndarray, lengths: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(sequence, scalars, mask)``.

    ``sequence`` is ``(n, SEQ_LEN, 5)`` float32, ``scalars`` is ``(n, 4)`` and
    ``mask`` is ``(n, SEQ_LEN)`` bool marking real samples.
    """
    n = signals.shape[0]
    seq = np.zeros((n, SEQ_LEN, len(CHANNELS)), np.float32)
    mask = np.zeros((n, SEQ_LEN), bool)
    scalars = np.zeros((n, 4), np.float32)

    i_curr, i_volt = CHANNELS.index("ac_curr"), CHANNELS.index("ac_volt")

    for k in range(n):
        length = int(lengths[k])
        raw = signals[k, :length].astype(np.float32)
        # A missing channel (PMD014 has no output_r wiring at all) is zeroed
        # rather than imputed: zero is "no indication", which is the truth.
        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)

        curr = raw[:, i_curr]
        volt = raw[:, i_volt]
        scale = max(_event_scale(curr), 1e-3)
        volt_ref = float(np.median(volt[volt > 50])) if (volt > 50).any() else 1.0

        out = np.empty_like(raw)
        # Current as pure shape: 1.0 == this event's own plateau.
        out[:, i_curr] = curr / scale
        # Supply as fractional deviation from its own idle level, so a 219 V and
        # a 230 V rail produce the same numbers for the same sag.
        out[:, i_volt] = (volt - volt_ref) / max(volt_ref, 1.0) * 10.0
        # The 24 V lines are already on a fixed physical scale - normalise by the
        # rail so they land in [-1, 1] and keep their sign, which is the state.
        for name in ("as_volt", "output_n_volt", "output_r_volt"):
            j = CHANNELS.index(name)
            out[:, j] = raw[:, j] / RAIL_V

        # Pad short captures, resample long ones onto the grid.
        if length <= SEQ_LEN:
            seq[k, :length] = out
            mask[k, :length] = True
        else:
            grid = np.linspace(0, length - 1, SEQ_LEN)
            src = np.arange(length)
            for j in range(out.shape[1]):
                seq[k, :, j] = np.interp(grid, src, out[:, j])
            mask[k, :] = True

        scalars[k] = (
            np.log1p(scale),          # how big this machine's throw actually is
            np.log1p(length),         # capture length, in samples
            volt_ref / 100.0,         # which supply rail (219 V vs 230 V class)
            float(length >= 600),     # hit the hardware capture cap
        )

    return seq, scalars, mask
