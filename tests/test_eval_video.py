"""D075 — per-track 3-of-5 confirmation behind a horizon gate.

The confirmed-track count is the headline number of a video run, and nothing in
the annotated MP4 would look wrong if the window slid by one, the gate compared
the wrong edge, or hits from different tracks pooled into one confirmation. These
pin the rule, including the bias D075 declares: a pothole re-acquired under a new
ID is confirmed twice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_video import confirm_step  # noqa: E402

HORIZON = 100.0
BELOW = 300.0  # a box bottom edge under the horizon line (image y grows downward)
ABOVE = 50.0


def run(frames, required=3, window=5):
    """Feed per-frame [(track_id, y2)] lists; return the confirmed set per frame."""
    confirmers = {}
    return [confirm_step(confirmers, tracks, HORIZON, required, window) for tracks in frames]


def test_three_hits_spread_over_five_frames_confirm_on_the_third_hit():
    out = run([[(1, BELOW)], [], [(1, BELOW)], [], [(1, BELOW)]])
    assert out == [set(), set(), set(), set(), {1}]


def test_a_one_frame_flash_never_confirms():
    out = run([[(1, BELOW)]] + [[]] * 6)
    assert all(not s for s in out)


def test_two_of_five_never_confirms():
    out = run([[(1, BELOW)], [(1, BELOW)], [], [], [], []])
    assert all(not s for s in out)


def test_a_box_above_the_horizon_never_confirms_even_at_five_of_five():
    out = run([[(1, ABOVE)]] * 5)
    assert all(not s for s in out)


def test_hits_on_different_tracks_do_not_pool():
    # D051's condition confirmer would fire here: something was present 3 frames running.
    out = run([[(1, BELOW)], [(2, BELOW)], [(3, BELOW)], [], []])
    assert all(not s for s in out)


def test_one_pothole_reacquired_under_a_new_id_confirms_twice():
    # The D075 upward bias: an ID switch turns one physical pothole into two tracks.
    frames = [[(1, BELOW)]] * 3 + [[(2, BELOW)]] * 3
    confirmed = set().union(*run(frames))
    assert confirmed == {1, 2}
