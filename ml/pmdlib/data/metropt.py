"""MetroPT-3: the real-field-data track.

Everything else in this project is trained on data we generated. That is a
defensible choice — no public Korean point-machine dataset exists, and the real
Sehwa extract is 7 events with no normal class — but it leaves an obvious
question unanswered: *does this pipeline work on data nobody built for it?*

MetroPT-3 answers that. It is a genuinely public, genuinely messy record of an
operating railway asset: the Air Production Unit of a Porto Metro train,
1.5 M readings at ~0.1 Hz (one roughly every 10 s) from February to
August 2020, with four documented air-leak
failures. Different asset, different failure physics, different sampling rate —
which is the point. The windowing, the health-index construction and the
unsupervised anomaly scoring are the same machinery the point-machine track uses.

**It is not a point machine.** Nothing here transfers a model between the two
datasets, and no metric from this file describes point-machine performance. It
exists to show the *method* survives contact with real field data.

Source: UCI Machine Learning Repository, dataset 791 (CC BY 4.0).
Veloso et al., "The MetroPT dataset for predictive maintenance", *Scientific
Data* 9, 764 (2022).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EXTERNAL = ROOT / "data" / "external"
ARCHIVE = EXTERNAL / "metropt3.zip"

URL = "https://archive.ics.uci.edu/static/public/791/metropt+3+dataset.zip"

#: Analogue sensors. The digital channels are valve states rather than
#: measurements, so they are carried but not used for the health index.
ANALOG = [
    "TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature", "Motor_current",
]
DIGITAL = [
    "COMP", "DV_eletric", "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level",
    "Caudal_impulses",
]

#: The four air-leak failures reported with the dataset, as (start, end).
#: These are the paper's own failure report, not labels inferred from the signal —
#: which is what makes them usable as ground truth rather than circular.
FAILURES: tuple[tuple[str, str], ...] = (
    ("2020-04-18 00:00:00", "2020-04-18 23:59:00"),
    ("2020-05-29 23:30:00", "2020-05-30 06:00:00"),
    ("2020-06-05 10:00:00", "2020-06-07 14:30:00"),
    ("2020-07-15 14:30:00", "2020-07-15 19:00:00"),
)

#: Readings arrive roughly every 10 s (~0.1 Hz, measured on the file - the UCI
#: page's "1Hz" does not match the timestamps). A 30-minute window on a 60 s
#: stride keeps the window count manageable without holding 1.5 M rows
#: downstream.
WINDOW_S = 1800
STRIDE_S = 60


@dataclass
class MetroWindows:
    features: np.ndarray      # (n_windows, n_features)
    labels: np.ndarray        # 1 inside a documented failure window
    timestamps: pd.DatetimeIndex
    feature_names: list[str]

    def __len__(self) -> int:
        return int(self.features.shape[0])


def _find_csv(zf: zipfile.ZipFile) -> str:
    names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not names:
        raise FileNotFoundError("no CSV inside the MetroPT-3 archive")
    # The archive holds one large CSV; pick the biggest if that ever changes.
    return max(names, key=lambda n: zf.getinfo(n).file_size)


def load_raw(archive: Path | None = None, nrows: int | None = None) -> pd.DataFrame:
    """Read the raw readings straight from the zip, without extracting 200 MB."""
    archive = archive or ARCHIVE
    if not archive.exists():
        raise FileNotFoundError(
            f"{archive} not found. Fetch it with:\n"
            f"  curl -L -o {archive} '{URL}'\n"
            "It is CC BY 4.0 but 208 MB, so it is not committed to this repository."
        )
    with zipfile.ZipFile(archive) as zf, zf.open(_find_csv(zf)) as fh:
        df = pd.read_csv(io.TextIOWrapper(fh, "utf-8"), nrows=nrows)

    # The export carries an unnamed index column and a mixed-case timestamp.
    df = df.loc[:, ~df.columns.str.match(r"Unnamed")]
    ts_col = next(c for c in df.columns if c.lower() in {"timestamp", "time", "date"})
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col]).rename(columns={ts_col: "timestamp"})
    return df.sort_values("timestamp").reset_index(drop=True)


def label_failures(ts: pd.Series) -> np.ndarray:
    """1 inside any documented failure window, 0 otherwise."""
    out = np.zeros(len(ts), dtype=np.int8)
    for start, end in FAILURES:
        out |= ((ts >= pd.Timestamp(start)) & (ts <= pd.Timestamp(end))).to_numpy(dtype=np.int8)
    return out


def make_windows(
    df: pd.DataFrame, window_s: int = WINDOW_S, stride_s: int = STRIDE_S
) -> MetroWindows:
    """Summarise each window the way the point-machine track summarises a throw.

    A window is labelled anomalous if *any* reading inside it falls in a
    documented failure period. Requiring the whole window would silently discard
    the onset, which is the part worth predicting.
    """
    present = [c for c in ANALOG if c in df.columns]
    if not present:
        raise ValueError(f"none of the expected analogue columns are present: {ANALOG}")

    df = df.set_index("timestamp")
    rule = f"{stride_s}s"
    grouped = df[present].resample(rule)

    stats = pd.concat(
        {"mean": grouped.mean(), "std": grouped.std(), "min": grouped.min(), "max": grouped.max()},
        axis=1,
    )
    stats.columns = [f"{col}_{stat}" for stat, col in stats.columns]
    stats = stats.dropna(how="all")

    # Roll the per-stride statistics up into the window, so each row summarises
    # window_s seconds of operation rather than a single stride.
    span = max(1, window_s // stride_s)
    rolled = stats.rolling(span, min_periods=max(2, span // 4)).mean().dropna()

    labels_per_row = pd.Series(label_failures(df.index.to_series()), index=df.index)
    win_labels = (
        labels_per_row.resample(rule).max().reindex(rolled.index).fillna(0).to_numpy(dtype=np.int8)
    )

    return MetroWindows(
        features=rolled.to_numpy(dtype=np.float32),
        labels=win_labels,
        timestamps=rolled.index,
        feature_names=list(rolled.columns),
    )


def temporal_split(w: MetroWindows, train_frac: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """Split by time, never at random.

    Consecutive windows overlap heavily, so a random split would put a window's
    own neighbours on the other side and report a score that means nothing. The
    training half is additionally restricted to normal windows downstream, since
    the scorer is unsupervised and must not be shown a failure.
    """
    n_train = int(len(w) * train_frac)
    idx = np.arange(len(w))
    return idx[:n_train], idx[n_train:]
