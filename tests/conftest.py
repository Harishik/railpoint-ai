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


@pytest.fixture(autouse=True)
def _no_local_llm(monkeypatch):
    """Tests must not depend on whatever happens to be installed on the machine
    running them — on a developer's laptop the copilot would otherwise call a
    real local model, slowly and nondeterministically, and in CI it would call
    nothing. Point it at a closed port; tests that exercise Ollama fake it."""
    from app.config import settings

    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "copilot_provider", "ollama")
