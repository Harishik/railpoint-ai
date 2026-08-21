"""FaultForce 2024 offline CSV simulator - repaired.

Original defects fixed here: SIM-01 .. SIM-05 (see docs/BUGS.md).
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

# SIM-01: DATA_DIR was the relative string "../data", so the script only worked
# when run from inside simulation_code/, and os.makedirs was never called, so
# open() raised outright when the directory did not exist.
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path(os.environ.get("FAULTFORCE_SIM_DIR", BASE_DIR.parent / "data"))

# SIM-05: these columns now match server.py's schema. The two "simulators"
# previously emitted mutually incompatible records.
FIELDNAMES = ["timestamp", "pmd_type", "ac_volt", "ac_curr", "value", "status"]

PMD_TYPES = [f"PMD{str(i).zfill(3)}" for i in range(1, 57)]
AC_CURR_IDLE = 0.07
AC_CURR_THROW = 9.0
AC_CURR_MAX = 15.74
AC_VOLT_RANGE = (205.25, 230.49)
ABNORMAL_THRESHOLD_A = 12.0


def make_row(rng: random.Random) -> dict:
    ac_volt = round(rng.uniform(*AC_VOLT_RANGE), 2)
    roll = rng.random()
    if roll < 0.25:
        ac_curr = round(rng.gauss(AC_CURR_IDLE, 0.02), 3)
    elif roll < 0.93:
        ac_curr = round(rng.gauss(AC_CURR_THROW, 1.2), 2)
    else:
        ac_curr = round(rng.uniform(AC_CURR_THROW, AC_CURR_MAX), 2)
    ac_curr = max(0.01, min(ac_curr, AC_CURR_MAX))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pmd_type": rng.choice(PMD_TYPES),
        "ac_volt": ac_volt,
        "ac_curr": ac_curr,
        "value": round(ac_volt * ac_curr, 2),
        # SIM-04: the original drew `status` from an independent coin flip, so
        # the label had no relationship at all to the signal and nothing could
        # ever be learned from the file. It is now derived from the current.
        "status": "error" if ac_curr > ABNORMAL_THRESHOLD_A else "normal",
    }


def rotate_if_needed(path: Path, max_rows: int) -> None:
    """SIM-03: the original grew without bound at 1200 rows / 10 s forever."""
    if not path.exists():
        return
    with path.open(newline="") as fh:
        rows = sum(1 for _ in fh)
    if rows > max_rows:
        backup = path.with_suffix(f".{int(time.time())}.csv")
        path.rename(backup)
        print(f"rotated {path.name} ({rows} rows) -> {backup.name}")


def generate(data_dir: Path, duration_s: float, batch_size: int, interval_s: float, max_rows: int, seed: int) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    data_file = data_dir / "simulated_data.csv"
    rng = random.Random(seed)

    # SIM-02: the header was only written when the file was absent. The shipped
    # simulated_data.csv had no header row at all across 45,000 lines, proving
    # it had been generated in a broken state and appended to ever since.
    # Validate the header on every run instead of assuming it.
    needs_header = True
    if data_file.exists() and data_file.stat().st_size > 0:
        with data_file.open(newline="") as fh:
            first = fh.readline().strip()
        needs_header = first != ",".join(FIELDNAMES)
        if needs_header:
            broken = data_file.with_suffix(".headerless.csv")
            data_file.rename(broken)
            print(f"existing file had no valid header; moved to {broken.name}")

    if needs_header:
        with data_file.open("w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=FIELDNAMES).writeheader()

    start = time.time()
    while time.time() - start < duration_s:
        rotate_if_needed(data_file, max_rows)
        with data_file.open("a", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            for _ in range(batch_size):
                writer.writerow(make_row(rng))
        print(f"wrote {batch_size} rows to {data_file}")
        time.sleep(interval_s)
    return data_file


def main() -> None:
    parser = argparse.ArgumentParser(description="FaultForce CSV simulator (repaired)")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--duration", type=float, default=70.0)
    parser.add_argument("--batch-size", type=int, default=1200)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--max-rows", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    out = generate(args.data_dir, args.duration, args.batch_size, args.interval, args.max_rows, args.seed)
    print(f"done -> {out}")


if __name__ == "__main__":
    main()
