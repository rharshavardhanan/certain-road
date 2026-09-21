"""T11 — a drift detector that alarms on stationary data is worse than none.

The false-alarm test is the one that matters: Ville's inequality promises at most
1/threshold, and the randomised-p-value and growing-bag details exist to keep
that promise. Each is pinned by its own test so a regression says which broke.
"""

import numpy as np
import pytest

from certain_road.assess.drift import DriftMartingale, frame_score, run_stream

EPS = 0.5
THRESHOLD = 100.0


def test_frame_score_is_one_without_detections():
    assert frame_score([], topk=3) == 1.0


def test_frame_score_uses_only_the_top_k():
    # The 0.1 must not drag the score down; top-2 of these is (0.9, 0.8).
    assert frame_score([0.9, 0.8, 0.1], topk=2) == pytest.approx(1 - 0.85)


def test_frame_score_averages_what_exists_when_fewer_than_k():
    assert frame_score([0.6], topk=3) == pytest.approx(0.4)


def test_confident_detections_score_low():
    assert frame_score([0.95, 0.93], topk=3) < frame_score([0.2, 0.1], topk=3)


def test_bag_grows_after_scoring_not_before():
    m = DriftMartingale([0.5] * 10, eps=EPS, alarm_threshold=THRESHOLD)
    assert len(m.bag) == 10
    m.update(0.7)
    assert len(m.bag) == 11 and 0.7 in m.bag


def test_p_values_are_uniform_under_the_null():
    """Tied and continuous data alike must give roughly uniform p."""
    rng = np.random.default_rng(0)
    for draw in (lambda n: rng.uniform(0, 1, n), lambda n: rng.integers(0, 3, n) / 2.0):
        m = DriftMartingale(draw(500), eps=EPS, alarm_threshold=THRESHOLD, seed=1)
        ps = [m.update(float(x)) for x in draw(3000)]
        assert 0.45 < float(np.mean(ps)) < 0.55, float(np.mean(ps))


def test_false_alarm_rate_respects_ville_bound():
    """1,000 exchangeable streams; the spec allows at most 2%."""
    rng = np.random.default_rng(7)
    alarms = 0
    for trial in range(1000):
        pool = rng.uniform(0, 1, 700)
        alarm, _ = run_stream(pool[:200], pool[200:], eps=EPS,
                              alarm_threshold=THRESHOLD, seed=trial)
        alarms += alarm is not None
    assert alarms / 1000 <= 0.02, f"false-alarm rate {alarms / 1000:.3f}"


def test_a_real_shift_is_detected():
    rng = np.random.default_rng(3)
    reference = rng.uniform(0.0, 0.5, 300)
    stream = np.concatenate([rng.uniform(0.0, 0.5, 200), rng.uniform(0.5, 1.0, 300)])
    alarm, _ = run_stream(reference, stream, eps=EPS, alarm_threshold=THRESHOLD, seed=0)
    assert alarm is not None and alarm >= 200, alarm


def test_log_martingale_trace_is_finite_and_full_length():
    rng = np.random.default_rng(1)
    _, trace = run_stream(rng.uniform(0, 1, 100), rng.uniform(0, 1, 250),
                          eps=EPS, alarm_threshold=THRESHOLD)
    assert len(trace) == 250 and np.all(np.isfinite(trace))


def test_eps_outside_the_open_unit_interval_is_rejected():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="eps"):
            DriftMartingale([0.5], eps=bad, alarm_threshold=THRESHOLD)


def test_same_seed_reproduces_the_run():
    rng = np.random.default_rng(5)
    ref, stream = rng.uniform(0, 1, 100), rng.uniform(0, 1, 200)
    a = run_stream(ref, stream, eps=EPS, alarm_threshold=THRESHOLD, seed=42)
    b = run_stream(ref, stream, eps=EPS, alarm_threshold=THRESHOLD, seed=42)
    assert a[0] == b[0] and a[1] == b[1]
