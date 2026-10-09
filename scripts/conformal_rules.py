"""Choose the conformal score function on evidence, and leave the evidence.

Runs the trained net over `calib` and `test`, then compares the plain threshold
(THR), Adaptive Prediction Sets (APS) and Regularized APS (RAPS) at several
penalties.

The choice is made on **calib alone**, by leave-one-machine-out: for each calib
machine, fit the quantile on the other machines and measure on that one. Test
is then read exactly once, to report every candidate side by side — never to
choose. Choosing on test would turn the one independent check into a fitted
number.

    .venv/bin/python scripts/conformal_rules.py

Writes experiments/results/conformal-rules.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from pmdlib.data import CLASS_ORDER, load  # noqa: E402
from pmdlib.eval import DEFAULT_LAMBDA, ConformalClassifier  # noqa: E402
from pmdlib.models.net import NetConfig, PointMachineNet  # noqa: E402
from pmdlib.train.pipeline import infer  # noqa: E402

ALPHA = 0.1
CANDIDATES: list[tuple[str, str, float]] = [
    ("thr", "thr", 0.0),
    ("aps", "aps", 0.0),
    *[(f"raps λ={lam}", "raps", lam) for lam in (0.001, 0.01, 0.05, 0.1, 0.2)],
]


def _outputs(model, split: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    strat, fleet = load("stratified", with_features=False), load("fleet", with_features=False)
    s, f = strat.split(split), fleet.split(split)
    meta = pd.concat([s.meta, f.meta], ignore_index=True)
    out = infer(model, np.concatenate([s.signals, f.signals]), np.concatenate([s.lengths, f.lengths]))
    y = meta.fault.map({c: i for i, c in enumerate(CLASS_ORDER)}).to_numpy()
    return out["probs"], y, meta.machine_id.to_numpy().astype(str)


def _measure(cc: ConformalClassifier, p: np.ndarray, y: np.ndarray) -> dict:
    chosen = cc.predict_set(p)
    size = chosen.sum(axis=1)
    covered = chosen[np.arange(len(y)), y]
    wrong = p.argmax(axis=1) != y
    wide = size > 1
    return {
        "coverage": covered.mean(),
        "mean_size": size.mean(),
        "singletons": (size == 1).mean(),
        "max_size": int(size.max()),
        "cov_when_wrong": covered[wrong].mean() if wrong.any() else float("nan"),
        "err_widened": wrong[wide].mean() if wide.any() else float("nan"),
        "err_singleton": wrong[size == 1].mean() if (size == 1).any() else float("nan"),
        "base_err": wrong.mean(),
    }


def main() -> None:
    torch.set_num_threads(8)
    blob = torch.load(ROOT / "experiments/artifacts/net.pt", map_location="cpu", weights_only=False)
    model = PointMachineNet(NetConfig(**blob["config"]))
    model.load_state_dict(blob["state_dict"])
    model.eval()

    print("inference on calib and test …")
    pc, yc, mc = _outputs(model, "calib")
    pt, yt, _ = _outputs(model, "test")

    lomo_rows, test_rows = [], []
    for label, rule, lam in CANDIDATES:
        folds = []
        for m in np.unique(mc):
            fit, held = mc != m, mc == m
            cc = ConformalClassifier(alpha=ALPHA, rule=rule, lam=lam).fit(pc[fit], yc[fit])
            folds.append(_measure(cc, pc[held], yc[held]))
        f = pd.DataFrame(folds)
        lomo_rows.append({
            "rule": label, "coverage": f.coverage.mean(), "worst_machine": f.coverage.min(),
            "mean_size": f.mean_size.mean(), "cov_when_wrong": f.cov_when_wrong.mean(),
        })
        cc = ConformalClassifier(alpha=ALPHA, rule=rule, lam=lam).fit(pc, yc)
        test_rows.append({"rule": label, "qhat": cc.qhat, **_measure(cc, pt, yt)})

    lomo, test = pd.DataFrame(lomo_rows), pd.DataFrame(test_rows)

    # The knee: keep regularising while each step sheds more mean set size than
    # it costs in coverage of the model's own errors. Read off calib only.
    raps = lomo[lomo.rule.str.startswith("raps")].reset_index(drop=True)
    chosen = raps.rule.iloc[0]
    for i in range(1, len(raps)):
        shed = raps.mean_size.iloc[i - 1] - raps.mean_size.iloc[i]
        cost = raps.cov_when_wrong.iloc[i - 1] - raps.cov_when_wrong.iloc[i]
        if shed <= cost:
            break
        chosen = raps.rule.iloc[i]
    print(f"\nselected on calib: {chosen}   (shipped default: raps λ={DEFAULT_LAMBDA})")

    fmt = {"coverage": "{:.4f}", "worst_machine": "{:.4f}", "mean_size": "{:.3f}",
           "cov_when_wrong": "{:.4f}", "qhat": "{:.5f}", "singletons": "{:.3f}",
           "err_widened": "{:.4f}", "err_singleton": "{:.4f}", "base_err": "{:.4f}"}

    def table(df: pd.DataFrame) -> str:
        cols = list(df.columns)
        rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for _, r in df.iterrows():
            rows.append("| " + " | ".join(
                fmt[c].format(r[c]) if c in fmt and pd.notna(r[c]) else str(r[c]) for c in cols
            ) + " |")
        return "\n".join(rows)

    base = test.base_err.iloc[0]
    sel = test[test.rule == chosen].iloc[0]
    doc = f"""# Conformal score function — selection evidence

Generated by `scripts/conformal_rules.py` against `experiments/artifacts/net.pt`.
Target coverage {1 - ALPHA:.0%}. `calib`: {len(yc):,} events from {len(np.unique(mc))} machines.
`test`: {len(yt):,} events, base top-1 error rate {base:.2%}.

## Selection — leave-one-machine-out within `calib`

Test is not read here. `worst_machine` is the lowest coverage on any single
held-out calib machine.

{table(lomo)}

**Selected: `{chosen}`.** The rule is the knee of the curve: keep raising the
penalty while each step sheds more mean set size than it costs in coverage of
the model's own errors, and stop at the first step where that inverts.

## Report — fitted on all of `calib`, measured once on `test`

Every candidate is shown so the choice can be checked against the outcome, but
the outcome did not make the choice.

{table(test)}

## Reading it

- **`thr`** reaches the coverage target with every set exactly the argmax.
  `cov_when_wrong` is zero: when the model is wrong, the truth is never in the
  set. Marginal coverage cannot see this — it equals top-1 accuracy.
- **`aps`** fixes that by overcorrecting: {test[test.rule == 'aps'].singletons.iloc[0]:.1%} of
  sets are singletons, so a widened set is barely likelier to be wrong
  ({test[test.rule == 'aps'].err_widened.iloc[0]:.2%}) than any throw ({base:.2%}).
- **`{chosen}`**: {sel.singletons:.1%} of sets are singletons and they are wrong
  {sel.err_singleton:.2%} of the time; a widened set is wrong {sel.err_widened:.2%} of the time —
  **{sel.err_widened / base:.1f}×** the base rate. When top-1 is wrong, the truth is still in
  the set {sel.cov_when_wrong:.1%} of the time.

All candidates over-cover the {1 - ALPHA:.0%} target. That is the safe direction, and
expected: these are non-randomized scores on a model that is right {1 - base:.1%} of the
time. The guarantee is a floor, not a target to hit exactly.

## Caveats

- **λ and the quantile both come from `calib`.** Choosing one of
  {len(CANDIDATES)} discrete candidates on the same data the quantile is then fitted
  to is a mild reuse of it. `test` played no part in either, and is the
  independent check.
- **`calib` is {len(np.unique(mc))} machines**, and splits are by machine, so
  calibration and test points are exchangeable at the machine level rather than
  the event level. `worst_machine` above shows how much single machines vary.
- **Non-randomized scores, deliberately.** Randomized APS/RAPS would hit the
  target more exactly, but the same throw scored twice could then return two
  different sets. A safety console cannot show an operator a shortlist that
  changes on refresh.
"""
    out = ROOT / "experiments/results/conformal-rules.md"
    out.write_text(doc)
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
