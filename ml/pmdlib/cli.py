"""Command-line entry points. ``railpoint --help`` after an editable install."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False, help="RailPoint-AI tooling")
console = Console()

ROOT = Path(__file__).resolve().parents[2]
RAW_CSV = ROOT / "data" / "raw" / "sehwa" / "pmd_events.csv"
SYNTH_DIR = ROOT / "data" / "synthetic"


@app.command()
def calibrate(n: int = 200, seed: int = 0) -> None:
    """Check the simulator against the real Sehwa traces."""
    from pmdlib.sim.calibrate import calibrate as run

    report = run(RAW_CSV, n_synthetic=n, seed=seed)
    console.print(report.summary())
    raise typer.Exit(0 if report.passed else 1)


@app.command("build-data")
def build_data(
    machines: int = 64,
    cycles: int = 800,
    replicates: int = 8,
    seed: int = 42,
    out: Path = SYNTH_DIR,
) -> None:
    """Generate both datasets: the realistic fleet and the stratified sweep."""
    from pmdlib.sim.fleet import (
        DatasetConfig,
        StratifiedConfig,
        generate_dataset,
        generate_stratified,
    )

    out.mkdir(parents=True, exist_ok=True)

    console.print("[bold]fleet[/bold] — realistic prevalence, for anomaly detection and RUL")
    Xf, Lf, Mf = generate_dataset(
        DatasetConfig(n_machines=machines, cycles_per_machine=cycles, seed=seed)
    )
    np.savez_compressed(out / "fleet_signals.npz", signals=Xf, lengths=Lf)
    Mf.to_parquet(out / "fleet_meta.parquet", index=False)

    console.print("[bold]stratified[/bold] — balanced scenario sweep, for classification")
    Xs, Ls, Ms = generate_stratified(StratifiedConfig(replicates=replicates, seed=seed))
    np.savez_compressed(out / "stratified_signals.npz", signals=Xs, lengths=Ls)
    Ms.to_parquet(out / "stratified_meta.parquet", index=False)

    table = Table(title="generated datasets")
    for col in ("dataset", "events", "machines", "classes", "anomaly rate", "MB"):
        table.add_column(col, justify="right")
    for name, M in (("fleet", Mf), ("stratified", Ms)):
        size = (out / f"{name}_signals.npz").stat().st_size / 1e6
        table.add_row(
            name, f"{len(M):,}", str(M.machine_id.nunique()),
            str(M.fault.nunique()), f"{M.is_anomaly.mean():.1%}", f"{size:.0f}",
        )
    console.print(table)
    console.print(f"written to [cyan]{out.relative_to(ROOT)}[/cyan]")




@app.command("train")
def train_cmd(
    epochs: int = 30,
    batch_size: int = 128,
    lr: float = 3e-4,
    threads: int = 0,
) -> None:
    """Train the deep model end to end, then calibrate, evaluate and export."""
    from pmdlib.train.deep import TrainConfig
    from pmdlib.train.pipeline import run

    run(TrainConfig(epochs=epochs, batch_size=batch_size, lr=lr), threads=threads or None)


# Must stay at the very bottom. When this sits above a command
# definition, `python -m pmdlib.cli` runs app() before that command is
# registered, so the command silently does not exist - which is exactly how
# two training runs completed "successfully" without training anything.
if __name__ == "__main__":
    app()
