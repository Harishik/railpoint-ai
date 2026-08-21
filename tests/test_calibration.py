"""The credibility gate.

Everything downstream trains on generated data, so the generator must be shown to
match the real Sehwa traces. If this fails, the simulator has drifted and the
fix is the simulator - not the tolerance.
"""

from pmdlib.sim.calibrate import calibrate


def test_simulator_matches_real_traces(raw_csv):
    report = calibrate(raw_csv, n_synthetic=200, seed=0)
    assert report.passed, "\n" + report.summary()


def test_every_comparable_channel_is_checked(raw_csv):
    report = calibrate(raw_csv, n_synthetic=50, seed=1)
    assert set(report.distribution.channel) == {
        "ac_curr", "ac_volt", "as_volt", "output_n_volt",
    }
    assert len(report.structure) == 6


def test_calibration_is_deterministic(raw_csv):
    a = calibrate(raw_csv, n_synthetic=40, seed=5).distribution
    b = calibrate(raw_csv, n_synthetic=40, seed=5).distribution
    assert a.equals(b)
