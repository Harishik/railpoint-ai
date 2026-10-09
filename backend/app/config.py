"""Backend settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAILPOINT_", env_file=".env", extra="ignore")

    #: SQLite by default so the stack runs with one command and no external
    #: service. The schema is time-series shaped and goes through SQLAlchemy, so
    #: pointing this at Postgres/TimescaleDB is a connection-string change.
    database_url: str = f"sqlite+aiosqlite:///{ROOT / 'data' / 'railpoint.db'}"

    artifacts_dir: Path = ROOT / "experiments" / "artifacts"
    synthetic_dir: Path = ROOT / "data" / "synthetic"
    raw_dir: Path = ROOT / "data" / "raw" / "sehwa"
    #: The built dashboard. When present the API serves it, so one container on
    #: one port is the whole product.
    frontend_dist: Path = ROOT / "frontend" / "dist"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    #: Seconds between simulated throws on the live feed.
    stream_interval_s: float = 3.0
    #: Machines on the live schematic.
    fleet_size: int = 12
    stream_seed: int = 7

    #: The maintenance copilot drafts work orders with a language model. Any
    #: failure — no model reachable, model missing, timeout — falls back to a
    #: deterministic drafter built from the same grounded context, so a reviewer
    #: who clones this repo sees the real feature rather than an error box.
    copilot_enabled: bool = True
    #: "ollama" runs a local model: no API key and no per-token bill, so anyone
    #: using the console may choose among the models installed on this machine.
    #: "claude" uses the Claude API and the operator's key; its model is fixed
    #: here and never selectable from the dashboard, because it is billed.
    copilot_provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    #: Used when installed; otherwise the first installed model. `ollama pull`
    #: a model to make it available.
    ollama_model: str = "qwen3.5:4b"
    #: Local models on CPU are slow; a bilingual work order can take a minute.
    ollama_timeout_s: float = 240.0
    claude_model: str = "claude-opus-5"

    #: Risk thresholds driving alert severity.
    risk_warning: float = 0.35
    risk_critical: float = 0.65


settings = Settings()
