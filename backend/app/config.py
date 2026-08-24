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

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    #: Seconds between simulated throws on the live feed.
    stream_interval_s: float = 3.0
    #: Machines on the live schematic.
    fleet_size: int = 12
    stream_seed: int = 7

    #: Risk thresholds driving alert severity.
    risk_warning: float = 0.35
    risk_critical: float = 0.65


settings = Settings()
