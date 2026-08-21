"""Fit the healthy throw template from the real Sehwa traces.

Writes ml/pmdlib/sim/templates.json. Re-run whenever the raw extract changes;
the output is committed so the simulator is reproducible without the raw data.

Healthy reference = PMD014's four *completed* throws. See docs/DATA.md for why
those qualify despite carrying an E03 code (the fault is in the control relay,
not the motor, and the current profile is textbook).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "sehwa" / "pmd_events.csv"
OUT = ROOT / "ml" / "pmdlib" / "sim" / "templates.json"

HEALTHY_THROWS = ["PMD014#2593", "PMD014#2595", "PMD014#2596", "PMD014#2597"]
RESOLUTION = 128
ON_THRESHOLD_A = 0.5


def main() -> None:
    df = pd.read_csv(RAW)
    df["key"] = df.pmd_type + "#" + df.event_num.astype(str)

    profiles, throw_lengths, sags = [], [], []
    for key in HEALTHY_THROWS:
        g = df[df.key == key].sort_values("event_seq")
        curr, volt = g.ac_curr.to_numpy(), g.ac_volt.to_numpy()
        on = curr > ON_THRESHOLD_A
        idx = np.flatnonzero(on)
        body = curr[idx[0] : idx[-1] + 1]
        # Normalise shape by the plateau so the template is amplitude-free.
        plateau = float(np.median(body[int(0.3 * len(body)) : int(0.9 * len(body))]))
        profiles.append(
            np.interp(np.linspace(0, 1, RESOLUTION), np.linspace(0, 1, len(body)), body) / plateau
        )
        throw_lengths.append(int(len(body)))
        sags.append(float(volt[~on].mean() - volt[on].mean()))

    profiles = np.asarray(profiles)
    template = profiles.mean(axis=0)
    spread = profiles.std(axis=0)

    payload = {
        "_comment": (
            "Healthy throw template, fitted from the four completed throws in the "
            "real Sehwa extract. 'current' is normalised by the plateau, so it is "
            "a pure shape; amplitude comes from MachineSpec."
        ),
        "source_events": HEALTHY_THROWS,
        "resolution": RESOLUTION,
        "current": [round(float(v), 6) for v in template],
        "current_spread": [round(float(v), 6) for v in spread],
        "throw_samples_mean": float(np.mean(throw_lengths)),
        "throw_samples_std": float(np.std(throw_lengths)),
        "supply_sag_v_mean": float(np.mean(sags)),
        "supply_sag_v_std": float(np.std(sags)),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  template peak      : {template.max():.3f} x plateau at {template.argmax()/RESOLUTION:.1%}")
    print(f"  template plateau   : {template[int(.3*RESOLUTION):int(.9*RESOLUTION)].mean():.3f} x plateau")
    print(f"  throw samples      : {np.mean(throw_lengths):.1f} +- {np.std(throw_lengths):.1f}")
    print(f"  supply sag         : {np.mean(sags):.2f} +- {np.std(sags):.2f} V")


if __name__ == "__main__":
    main()
