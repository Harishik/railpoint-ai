"""Load the generated datasets, with a cache for the expensive feature pass."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..features import FEATURE_NAMES, extract_batch
from ..sim.spec import FaultClass
from ..utils.splits import machine_split

ROOT = Path(__file__).resolve().parents[3]
SYNTH_DIR = ROOT / "data" / "synthetic"
#: The 7-event Sehwa extract. Company-provided and **not public**: it is
#: gitignored, only its checksums are committed, and every consumer must cope
#: with its absence, because a public clone will not have it.
REAL_EXTRACT = ROOT / "data" / "raw" / "sehwa" / "pmd_events.csv"
CACHE_DIR = ROOT / "data" / "processed"

#: Fixed label order, so a model trained today lines up with one trained later.
CLASS_ORDER: tuple[str, ...] = tuple(f.value for f in FaultClass)
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASS_ORDER)}


@dataclass
class Dataset:
    signals: np.ndarray          # (n, max_samples, 5) NaN-padded
    lengths: np.ndarray          # (n,)
    meta: pd.DataFrame
    features: np.ndarray | None = None

    @property
    def y(self) -> np.ndarray:
        return self.meta.fault.map(CLASS_TO_IDX).to_numpy(np.int64)

    @property
    def y_binary(self) -> np.ndarray:
        return self.meta.is_anomaly.to_numpy(bool).astype(np.int64)

    def split(self, name: str) -> Dataset:
        mask = (self.meta.split == name).to_numpy()
        idx = np.flatnonzero(mask)
        return Dataset(
            signals=self.signals[idx],
            lengths=self.lengths[idx],
            meta=self.meta.iloc[idx].reset_index(drop=True),
            features=None if self.features is None else self.features[idx],
        )

    def __len__(self) -> int:
        return len(self.meta)


_CACHE: dict[tuple[str, bool, str], Dataset] = {}


def _feature_fingerprint(signals_path: Path) -> str:
    """Identify the (signals, feature-set) pair a cache entry was built from.

    Uses the signals file's size and modification time rather than hashing 120 MB
    of float32 on every load, together with the feature names, so that either
    regenerating the data or changing the extractor invalidates the cache.
    """
    st = signals_path.stat()
    payload = f"{st.st_size}:{st.st_mtime_ns}:{'|'.join(FEATURE_NAMES)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def load(
    name: str = "stratified",
    *,
    with_features: bool = True,
    synth_dir: Path | None = None,
    cache: bool = True,
) -> Dataset:
    """Load ``fleet`` or ``stratified``.

    Features are cached to ``data/processed/``, because extracting 113 features
    over 60k events takes long enough to be annoying in a loop. The cache is
    keyed on a fingerprint of the signals file *and* the feature set, not on the
    dataset name: keying on name alone let a regenerated dataset silently reuse
    features computed from the previous simulator, since the only guard was a
    shape check that is invariant under regeneration. That happened during
    development and pairs stale features with fresh labels.
    """
    synth_dir = synth_dir or SYNTH_DIR
    key = (name, with_features, str(synth_dir))
    if cache and key in _CACHE:
        return _CACHE[key]
    payload = np.load(synth_dir / f"{name}_signals.npz")
    meta = pd.read_parquet(synth_dir / f"{name}_meta.parquet")
    # Recomputed rather than trusted, so an older dataset generated before the
    # rule existed still gets consistent splits.
    meta = meta.copy()
    meta["split"] = meta.machine_id.map(machine_split)
    ds = Dataset(payload["signals"], payload["lengths"], meta)

    if with_features:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = CACHE_DIR / f"{name}_features.npz"
        fingerprint = _feature_fingerprint(synth_dir / f"{name}_signals.npz")
        if cache_path.exists():
            try:
                blob = np.load(cache_path, allow_pickle=False)
                if (
                    str(blob["fingerprint"]) == fingerprint
                    and blob["features"].shape == (len(ds), len(FEATURE_NAMES))
                ):
                    ds.features = blob["features"]
            except (OSError, KeyError, ValueError):
                ds.features = None  # unreadable or stale cache: just recompute
        if ds.features is None:
            ds.features = extract_batch(ds.signals, ds.lengths)
            np.savez(cache_path, features=ds.features, fingerprint=fingerprint)
    if cache:
        _CACHE[key] = ds
    return ds


def real_extract_available() -> bool:
    return REAL_EXTRACT.exists()


def load_real(raw_csv: Path | None = None) -> Dataset:
    """The 7 real Sehwa events, shaped like the synthetic data.

    These are the acceptance test and are **never** trained on. Every one of them
    is a genuine fault, which is what makes the test meaningful: a model that
    calls them all normal has learned nothing transferable.
    """
    from ..sim.spec import CHANNELS

    raw_csv = raw_csv or REAL_EXTRACT
    if not raw_csv.exists():
        raise FileNotFoundError(
            f"{raw_csv} not found. The Sehwa extract is private and is not part of the "
            "public repository; the real-data acceptance test needs it."
        )
    df = pd.read_csv(raw_csv)
    df["key"] = df.pmd_type + "#" + df.event_num.astype(str)

    keys = sorted(df.key.unique())
    max_len = int(df.groupby("key").size().max())
    signals = np.full((len(keys), max_len, len(CHANNELS)), np.nan, np.float32)
    lengths = np.zeros(len(keys), np.int32)
    rows = []
    for i, key in enumerate(keys):
        g = df[df.key == key].sort_values("event_seq")
        n = len(g)
        signals[i, :n] = g[list(CHANNELS)].to_numpy(np.float32)
        lengths[i] = n
        rows.append(
            {
                "idx": i, "key": key, "machine_id": g.pmd_type.iloc[0], "split": "real",
                "direction": g.direction.iloc[0], "err_code": g.err_code.iloc[0],
                # Real events carry a component code, not one of our fault-class
                # names. The mapping is deliberately left to the evaluation step
                # so it is explicit and auditable rather than silently assumed.
                "fault": "UNKNOWN", "is_anomaly": True, "n_samples": n,
            }
        )
    ds = Dataset(signals, lengths, pd.DataFrame(rows))
    ds.features = extract_batch(ds.signals, ds.lengths)
    return ds
