import numpy as np
import pytest

from gazefix.smoothing import BlinkGate, OneEuroFilter


def test_filter_passes_the_first_sample_through():
    f = OneEuroFilter()
    assert f(np.array([3.0, -2.0]), 1 / 30) == pytest.approx([3.0, -2.0])


def test_filter_damps_jitter_around_a_steady_value():
    rng = np.random.default_rng(1)
    f = OneEuroFilter(min_cutoff=0.8, beta=0.0)
    outputs = []
    for _ in range(200):
        outputs.append(f(np.array([5.0]) + rng.normal(0, 1.0, 1), 1 / 30)[0])
    tail = np.array(outputs[100:])
    assert tail.std() < 0.4, "jitter should be well below the input's"
    assert tail.mean() == pytest.approx(5.0, abs=0.3)


def test_filter_keeps_up_with_a_real_move():
    """Sustained motion must not be smoothed into a lag."""
    f = OneEuroFilter(min_cutoff=1.6, beta=0.05)
    for step in range(60):
        out = f(np.array([float(step)]), 1 / 30)
    assert out[0] == pytest.approx(59.0, abs=6.0)


def test_filter_resets_and_reshapes():
    f = OneEuroFilter()
    f(np.array([1.0]), 1 / 30)
    f.reset()
    assert f(np.array([9.0]), 1 / 30) == pytest.approx([9.0])
    # A different shape restarts rather than raising.
    assert f(np.array([1.0, 2.0]), 1 / 30) == pytest.approx([1.0, 2.0])


def test_filter_tolerates_a_zero_timestep():
    f = OneEuroFilter()
    f(np.array([0.0]), 1 / 30)
    assert np.isfinite(f(np.array([1.0]), 0.0)).all()


def test_filter_rejects_a_nonsense_cutoff():
    with pytest.raises(ValueError):
        OneEuroFilter(min_cutoff=0.0)


def test_blink_gate_closes_and_reopens_with_hysteresis():
    gate = BlinkGate(close_below=0.14, open_above=0.20, rate=1.0)
    assert gate.update(0.30) == pytest.approx(1.0)
    assert gate.update(0.10) == pytest.approx(0.0)
    # Between the thresholds the gate holds whatever state it was in.
    assert gate.update(0.17) == pytest.approx(0.0)
    assert gate.update(0.25) == pytest.approx(1.0)
    assert gate.update(0.17) == pytest.approx(1.0)


def test_blink_gate_eases_rather_than_snapping():
    gate = BlinkGate(rate=0.35)
    gate.update(0.30)
    first = gate.update(0.05)
    assert 0.0 < first < 1.0
    for _ in range(30):
        gate.update(0.05)
    assert gate.gain == pytest.approx(0.0)


def test_blink_gate_rejects_inverted_thresholds():
    with pytest.raises(ValueError):
        BlinkGate(close_below=0.3, open_above=0.2)
