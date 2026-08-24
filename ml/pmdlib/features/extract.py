"""Interpretable features for one throw.

These carry the baseline models and, later, the explanations. Several are
directly diagnostic of a specific fault mechanism rather than generic
statistics - ``in_transit_frac``, ``drive_cut`` and ``lock_achieved`` between
them separate the two real fault exemplars from a healthy throw on their own.
"""

from __future__ import annotations

import numpy as np
import pywt
from scipy import signal as sps

from ..sim.spec import CHANNELS
from .segment import ON_THRESHOLD_A, Phases, segment

#: Indication within this of 0 V means "in transit, no position detected".
IN_TRANSIT_V = 2.0
#: Wavelet used for the packet energy entropy, standard in this literature.
WAVELET = "db4"
WAVELET_LEVEL = 3


def _stats(x: np.ndarray, prefix: str) -> dict[str, float]:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return dict.fromkeys(
            (f"{prefix}_{s}" for s in ("mean", "std", "min", "max", "p2p", "skew", "kurt")),
            np.nan,
        )
    mean = float(np.mean(x))
    sd = float(np.std(x))
    # Shape statistics are undefined on a constant signal - idle segments are
    # near-constant by construction, so guard rather than emit a warning.
    #
    # Computed inline rather than via scipy.stats: those go through
    # axis_nan_policy_wrapper, which re-inspects the function signature on every
    # call. That overhead was 87% of total feature-extraction time.
    if sd < 1e-9 or x.size <= 3:
        skew = kurt = 0.0
    else:
        d = x - mean
        m2 = float(np.mean(d * d))
        skew = float(np.mean(d**3) / m2**1.5)
        kurt = float(np.mean(d**4) / (m2 * m2) - 3.0)  # Fisher, as scipy default
    return {
        f"{prefix}_mean": mean,
        f"{prefix}_std": sd,
        f"{prefix}_min": float(np.min(x)),
        f"{prefix}_max": float(np.max(x)),
        f"{prefix}_p2p": float(np.ptp(x)),
        f"{prefix}_skew": skew,
        f"{prefix}_kurt": kurt,
    }


def _wavelet_energy_entropy(x: np.ndarray) -> dict[str, float]:
    """Wavelet packet energy distribution across sub-bands, plus its entropy.

    A concentrated spectrum means a smooth throw; energy spread into higher
    bands means ripple, chatter or single-phasing.
    """
    x = x[np.isfinite(x)]
    out: dict[str, float] = {}
    n_bands = 2**WAVELET_LEVEL
    if x.size < 2**(WAVELET_LEVEL + 1):
        out.update({f"wpe_{i}": np.nan for i in range(n_bands)})
        out["wpe_entropy"] = np.nan
        return out

    wp = pywt.WaveletPacket(x - x.mean(), wavelet=WAVELET, mode="symmetric", maxlevel=WAVELET_LEVEL)
    nodes = [n.path for n in wp.get_level(WAVELET_LEVEL, "natural")]
    energies = np.array([float(np.sum(np.square(wp[p].data))) for p in nodes])
    total = energies.sum()
    if total <= 0:
        out.update({f"wpe_{i}": 0.0 for i in range(n_bands)})
        out["wpe_entropy"] = 0.0
        return out
    p = energies / total
    out.update({f"wpe_{i}": float(v) for i, v in enumerate(p)})
    nz = p[p > 0]
    out["wpe_entropy"] = float(-np.sum(nz * np.log(nz)))
    return out


def _spectral(x: np.ndarray) -> dict[str, float]:
    """Ripple content of the plateau: gearbox mesh and single-phasing live here."""
    x = x[np.isfinite(x)]
    if x.size < 16:
        return {"spec_centroid": np.nan, "spec_peak_ratio": np.nan, "spec_flatness": np.nan}
    detrended = sps.detrend(x)
    freqs, psd = sps.welch(detrended, nperseg=min(64, x.size))
    total = float(psd.sum())
    if total <= 0:
        return {"spec_centroid": 0.0, "spec_peak_ratio": 0.0, "spec_flatness": 0.0}
    centroid = float((freqs * psd).sum() / total)
    peak_ratio = float(psd.max() / total)
    positive = psd[psd > 0]
    flatness = float(np.exp(np.mean(np.log(positive))) / np.mean(positive)) if positive.size else 0.0
    return {"spec_centroid": centroid, "spec_peak_ratio": peak_ratio, "spec_flatness": flatness}


def extract(signals: np.ndarray, length: int | None = None) -> dict[str, float]:
    """Features for one capture, shaped ``(n_samples, 5)`` in ``CHANNELS`` order."""
    n = int(length) if length is not None else int(signals.shape[0])
    sig = signals[:n]
    curr = sig[:, CHANNELS.index("ac_curr")].astype(float)
    volt = sig[:, CHANNELS.index("ac_volt")].astype(float)
    as_v = sig[:, CHANNELS.index("as_volt")].astype(float)
    out_n = sig[:, CHANNELS.index("output_n_volt")].astype(float)

    ph: Phases = segment(curr)
    f: dict[str, float] = {}

    # --- timing -----------------------------------------------------------
    f["n_samples"] = float(n)
    f["motor_started"] = float(ph.motor_started)
    f["idle_pre_len"] = float(ph.idle_pre[1] - ph.idle_pre[0])
    f["inrush_len"] = float(ph.inrush[1] - ph.inrush[0])
    f["throw_len"] = float(ph.throw[1] - ph.throw[0])
    f["lock_len"] = float(ph.lock[1] - ph.lock[0])
    f["idle_post_len"] = float(ph.idle_post[1] - ph.idle_post[0])
    f["active_len"] = f["inrush_len"] + f["throw_len"] + f["lock_len"]
    f["active_frac"] = f["active_len"] / max(n, 1)
    # A capture that ran to the buffer limit is a throw that never ended: this
    # is exactly why both real PMD055 events are 600 samples long.
    f["hit_capture_cap"] = float(f["idle_post_len"] == 0 and ph.motor_started)

    # --- current, per phase ----------------------------------------------
    for name in ("idle_pre", "inrush", "throw", "lock", "idle_post"):
        a, b = ph.span(name)
        f.update(_stats(curr[a:b], f"curr_{name}"))

    on = curr > ON_THRESHOLD_A
    f.update(_stats(curr[on], "curr_active"))
    f["curr_peak"] = float(np.nanmax(curr)) if np.isfinite(curr).any() else np.nan
    plateau = f.get("curr_throw_mean", np.nan)
    idle = f.get("curr_idle_pre_mean", np.nan)
    f["curr_plateau"] = plateau
    f["inrush_ratio"] = f["curr_peak"] / plateau if plateau and plateau > 0 else np.nan
    f["plateau_over_idle"] = plateau / idle if idle and idle > 0 else np.nan
    # Positive slope across the throw is the obstruction signature; a flat
    # elevated plateau is the locking-latch signature.
    a, b = ph.throw
    if b - a > 8:
        seg = curr[a:b]
        f["throw_slope"] = float(np.polyfit(np.arange(seg.size), np.nan_to_num(seg, nan=0.0), 1)[0])
    else:
        f["throw_slope"] = np.nan

    # --- supply -----------------------------------------------------------
    f.update(_stats(volt, "volt"))
    if on.any() and (~on).any():
        idle_v = float(np.nanmean(volt[~on]))
        load_v = float(np.nanmean(volt[on]))
        f["supply_sag"] = idle_v - load_v
        f["supply_idle"] = idle_v
        # Sag per amp separates a weak supply / resistive cable from a machine
        # that is simply drawing more current.
        f["sag_per_amp"] = f["supply_sag"] / plateau if plateau and plateau > 0 else np.nan
    else:
        f["supply_sag"] = f["sag_per_amp"] = np.nan
        f["supply_idle"] = float(np.nanmean(volt))

    # --- indication -------------------------------------------------------
    # Measured on the real trace: ~79% of a healthy capture sits at 0 V, in
    # transit. 0% means the machine never unlocked; ~100% means it never locked.
    finite_n = out_n[np.isfinite(out_n)]
    f["in_transit_frac"] = (
        float(np.mean(np.abs(finite_n) < IN_TRANSIT_V)) if finite_n.size else np.nan
    )
    def _edge_mean(x: np.ndarray) -> float:
        """Mean of an edge window, tolerating a fully-missing channel."""
        finite = x[np.isfinite(x)]
        return float(finite.mean()) if finite.size else np.nan

    f["ind_start"] = _edge_mean(out_n[:5]) if n >= 5 else np.nan
    f["ind_end"] = _edge_mean(out_n[-5:]) if n >= 5 else np.nan
    f["ind_travel"] = f["ind_end"] - f["ind_start"]
    f["lock_achieved"] = float(abs(f["ind_end"]) > 15.0) if np.isfinite(f["ind_end"]) else np.nan
    f["ind_polarity_flipped"] = (
        float(np.sign(f["ind_start"]) != np.sign(f["ind_end"]))
        if np.isfinite(f["ind_start"]) and np.isfinite(f["ind_end"])
        else np.nan
    )
    f.update(_stats(out_n, "ind"))
    # Chatter: how often the indication reverses direction sample to sample.
    d = np.diff(np.nan_to_num(out_n, nan=0.0))
    f["ind_reversals"] = float(np.sum(np.diff(np.sign(d)) != 0)) / max(n, 1)

    # --- drive command ----------------------------------------------------
    # Whether the drive is cut separates E01 (never cut, motor keeps running)
    # from E03 (cut on timeout after the motor failed to start).
    f["drive_end_v"] = _edge_mean(as_v[-5:]) if n >= 5 else np.nan
    f["drive_cut"] = float(abs(f["drive_end_v"]) < 5.0) if np.isfinite(f["drive_end_v"]) else np.nan
    f["drive_on_frac"] = (
        float(np.mean(np.abs(as_v[np.isfinite(as_v)]) > 5.0)) if np.isfinite(as_v).any() else np.nan
    )
    f.update(_stats(as_v, "drive"))

    # --- spectral / wavelet, over the throw plateau -----------------------
    a, b = ph.throw
    plateau_seg = curr[a:b] if b > a else curr[on]
    f.update(_spectral(plateau_seg))
    f.update(_wavelet_energy_entropy(plateau_seg))

    # --- scale-free shape features ----------------------------------------
    # Absolute amplitude does not transfer between machine types: a PMD-A holds
    # a 3.8 A plateau where a PMD-B holds 5.0 A, and a classifier that leans on
    # raw amplitude learns the fleet's composition rather than the fault. These
    # normalise each event by its own plateau, so they describe the *shape* of
    # the throw and carry across machines of different sizes.
    def _over_plateau(value: float) -> float:
        return value / plateau if plateau and plateau > 0 and np.isfinite(value) else np.nan

    f["curr_active_cv"] = _over_plateau(f.get("curr_active_std", np.nan))
    f["throw_slope_norm"] = _over_plateau(f["throw_slope"])
    f["idle_over_plateau"] = _over_plateau(idle) if np.isfinite(idle) else np.nan
    f["inrush_mean_over_plateau"] = _over_plateau(f.get("curr_inrush_mean", np.nan))
    f["lock_over_plateau"] = _over_plateau(f.get("curr_lock_mean", np.nan))
    f["throw_ripple_over_plateau"] = _over_plateau(f.get("curr_throw_std", np.nan))
    # Fractional supply sag is likewise comparable across 219 V and 230 V rails.
    f["sag_frac"] = (
        f["supply_sag"] / f["supply_idle"]
        if np.isfinite(f.get("supply_sag", np.nan)) and f.get("supply_idle", 0)
        else np.nan
    )
    # Timing normalised by the capture, so a longer buffer does not shift it.
    f["throw_over_capture"] = f["throw_len"] / max(n, 1)
    f["inrush_over_active"] = f["inrush_len"] / f["active_len"] if f["active_len"] else np.nan

    # --- data-quality flags (never labels, but the model should see them) --
    f["nan_frac"] = float(np.mean(~np.isfinite(sig[:, :4])))

    return f


FEATURE_NAMES: tuple[str, ...] = tuple(
    extract(np.zeros((300, len(CHANNELS)), dtype=float)).keys()
)


def extract_batch(signals: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """Features for a padded batch, returned as ``(n_events, n_features)``."""
    rows = [extract(signals[i], int(lengths[i])) for i in range(signals.shape[0])]
    return np.array([[r.get(k, np.nan) for k in FEATURE_NAMES] for r in rows], dtype=np.float32)


#: Features whose value depends on the machine's absolute size.
#:
#: A PMD-A holds a 3.8 A plateau on a 219 V rail; a PMD-B holds 5.0 A on 230 V.
#: A model leaning on these learns the *fleet's composition* rather than the
#: fault, and then fails on a machine whose amplitude sits outside the training
#: mix - which is exactly what happened on the real PMD014 captures.
_ABSOLUTE_PREFIXES = ("curr_", "volt_", "ind_", "drive_")
_ABSOLUTE_EXACT = frozenset({
    "curr_peak", "curr_plateau", "supply_sag", "supply_idle", "throw_slope",
})
_SCALE_FREE_SUFFIXES = ("_skew", "_kurt", "_cv", "_norm", "_frac", "_ratio")
_SCALE_FREE_EXACT = frozenset({
    "ind_reversals", "ind_polarity_flipped", "lock_achieved", "drive_cut",
    "drive_on_frac", "in_transit_frac",
})


def _is_scale_free(name: str) -> bool:
    if name in _SCALE_FREE_EXACT or name.endswith(_SCALE_FREE_SUFFIXES):
        return True
    # Everything else - timing, counts, spectral, wavelet, flags - is scale-free.
    return not (name in _ABSOLUTE_EXACT or name.startswith(_ABSOLUTE_PREFIXES))


#: Indices into FEATURE_NAMES for the amplitude-invariant subset.
SCALE_FREE_FEATURES: tuple[str, ...] = tuple(f for f in FEATURE_NAMES if _is_scale_free(f))
SCALE_FREE_INDEX: tuple[int, ...] = tuple(
    i for i, f in enumerate(FEATURE_NAMES) if _is_scale_free(f)
)
