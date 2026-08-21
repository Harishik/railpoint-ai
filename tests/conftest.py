from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = ROOT / "data" / "raw" / "sehwa" / "pmd_events.csv"


@pytest.fixture(scope="session")
def raw_csv() -> Path:
    if not RAW_CSV.exists():
        pytest.skip(f"real extract not present at {RAW_CSV}")
    return RAW_CSV


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(1234)
