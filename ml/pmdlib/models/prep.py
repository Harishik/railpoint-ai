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
#: Scalars handed to the model beside the sequence. See ``_ripple_spectrum``.
N_SCALARS = 8
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


def _ripple_spectrum(curr: np.ndarray, scale: float) -> tuple[float, float, float, float]:
    """Periodicity descriptors, computed at FULL resolution.

    This exists because of a hard architectural limit. The CNN stem strides by 8
    (512 samples -> 64 tokens), and GEARBOX_WEAR's entire signature is a ripple
    with a 7-16 sample period. After 8x decimation that period is 0.9-2 tokens,
    at or below Nyquist, so the encoder cannot recover it at all - which is
    exactly why that class scored 0.13 precision while every class carrying a
    large-amplitude signature scored above 0.95.

    Rather than pay the quadratic cost of attending over undecimated samples,
    the periodicity is measured here, before any downsampling, and handed to the
    model as scalars alongside the sequence.
    """
    on = curr > 0.3 * scale
    idx = np.flatnonzero(on)
    if idx.size < 32:
        return 0.0, 0.0, 0.0, 0.0
    body = curr[idx[0] : idx[-1] + 1] / max(scale, 1e-6)
    if body.size < 32:
        return 0.0, 0.0, 0.0, 0.0

    # Remove the slow envelope (inrush decay, plateau slope) so only ripple is left.
    k = max(5, body.size // 24) | 1
    trend = np.convolve(body, np.ones(k) / k, mode="same")
    resid = body - trend
    resid = resid - resid.mean()
    if not np.isfinite(resid).all():
        return 0.0, 0.0, 0.0, 0.0

    spec = np.abs(np.fft.rfft(resid * np.hanning(resid.size))) ** 2
    freqs = np.fft.rfftfreq(resid.size)
    total = float(spec[1:].sum()) + 1e-12

    # Ripple band: periods of 3 to 24 samples, covering both the gearbox
    # (7-16) and motor (3-8) harmonics.
    band = (freqs >= 1.0 / 24.0) & (freqs <= 1.0 / 3.0)
    if not band.any():
        return 0.0, 0.0, 0.0, 0.0
    bs, bf = spec[band], freqs[band]
    peak = int(bs.argmax())

    peak_ratio = float(bs[peak]) / total          # power concentrated in one tone
    band_ratio = float(bs.sum()) / total          # power anywhere in the band
    dom_period = 1.0 / max(float(bf[peak]), 1e-6)  # samples per cycle
    p = spec[1:] + 1e-12
    flatness = float(np.exp(np.log(p).mean()) / p.mean())  # tonal -> low
    return peak_ratio, band_ratio, dom_period / 24.0, flatness


def prepare(signals: np.ndarray, lengths: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(sequence, scalars, mask)``.

    ``sequence`` is ``(n, SEQ_LEN, 5)`` float32, ``scalars`` is ``(n, 8)`` and
    ``mask`` is ``(n, SEQ_LEN)`` bool marking real samples.
    """
    n = signals.shape[0]
    seq = np.zeros((n, SEQ_LEN, len(CHANNELS)), np.float32)
    mask = np.zeros((n, SEQ_LEN), bool)
    scalars = np.zeros((n, N_SCALARS), np.float32)

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

        peak_ratio, band_ratio, dom_period, flatness = _ripple_spectrum(curr, scale)
        scalars[k] = (
            np.log1p(scale),          # how big this machine's throw actually is
            np.log1p(length),         # capture length, in samples
            volt_ref / 100.0,         # which supply rail (219 V vs 230 V class)
            float(length >= 600),     # hit the hardware capture cap
            peak_ratio,               # ripple power in a single tone
            band_ratio,               # ripple power across the 3-24 sample band
            dom_period,               # dominant ripple period, normalised
            flatness,                 # spectral flatness; tonal ripple lowers it
        )

    return seq, scalars, mask
