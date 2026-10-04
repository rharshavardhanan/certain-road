"""Per-pothole scoring of confirmed video tracks against hand-counted intervals.

Hits, duplicates and false alarms are easy to conflate, and the one number the
report needs — potholes caught of those present, and false alarms per minute —
moves silently if they are. These pin the rule: first overlapping track is the
hit, later ones on the same interval are duplicates, a track overlapping nothing
is a false alarm, and one track is never more than one hit.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from score_video_gt import score_tracks  # noqa: E402

FPS = 10.0
WINDOW = (0.0, 60.0)


def track(first_s, last_s, frames=5, confirmed_s=None):
    """A summary.json confirmed-track record, built from seconds at FPS."""
    return {
        "first_frame": round(first_s * FPS),
        "last_frame": round(last_s * FPS),
        "frames_detected": frames,
        "confirmed_at": round((first_s if confirmed_s is None else confirmed_s) * FPS),
    }


def test_a_track_overlapping_an_interval_is_a_hit():
    r = score_tracks({"1": track(10, 12)}, [(11.0, 14.0)], FPS, WINDOW)
    assert (r["hit"], r["duplicates"], r["false_alarms"]) == (1, 0, 0)


def test_a_second_track_on_the_same_interval_is_a_duplicate_and_the_earlier_one_hits():
    r = score_tracks({"7": track(12, 13), "3": track(10, 11)}, [(10.0, 14.0)], FPS, WINDOW)
    assert (r["hit"], r["duplicates"]) == (1, 1)
    assert r["intervals"][0]["hit_by"] == "3"


def test_a_track_overlapping_nothing_is_a_false_alarm_counted_per_minute():
    r = score_tracks(
        {"1": track(40, 41), "2": track(50, 51)}, [(10.0, 12.0)], FPS, (0.0, 30.0 + 30.0)
    )
    assert r["false_alarms"] == 2
    assert r["false_alarms_per_min"] == 2.0
    r = score_tracks({"1": track(40, 41)}, [(10.0, 12.0)], FPS, (30.0, 60.0))
    assert r["false_alarms_per_min"] == 2.0  # one false alarm in half a minute


def test_a_track_confirmed_outside_the_window_is_ignored():
    r = score_tracks({"1": track(70, 72)}, [(10.0, 12.0)], FPS, WINDOW)
    assert (r["tracks_in_window"], r["false_alarms"], r["hit"]) == (0, 0, 0)


def test_one_track_over_two_intervals_is_one_hit_and_another_track_can_take_the_second():
    spanning = score_tracks({"1": track(10, 20)}, [(11.0, 12.0), (18.0, 19.0)], FPS, WINDOW)
    assert (spanning["hit"], spanning["duplicates"]) == (1, 0)
    with_second = score_tracks(
        {"1": track(10, 20), "2": track(18, 19)}, [(11.0, 12.0), (18.0, 19.0)], FPS, WINDOW
    )
    assert (with_second["hit"], with_second["duplicates"]) == (2, 0)


def test_median_frames_per_hit_ignores_duplicates_and_false_alarms():
    tracks = {
        "1": track(10, 11, frames=4),
        "2": track(20, 21, frames=10),
        "3": track(20.5, 21, frames=99),  # duplicate on the second interval
        "4": track(40, 41, frames=99),  # false alarm
    }
    r = score_tracks(tracks, [(10.0, 12.0), (19.0, 22.0)], FPS, WINDOW)
    assert r["median_frames_per_hit"] == 7.0


def test_a_track_ending_where_an_interval_starts_does_not_overlap():
    # last_frame 99 at 10 fps covers [.., 10.0); an interval from 10.0 does not overlap it.
    r = score_tracks(
        {"1": {"first_frame": 90, "last_frame": 99, "frames_detected": 5, "confirmed_at": 92}},
        [(10.0, 12.0)],
        FPS,
        WINDOW,
    )
    assert (r["hit"], r["false_alarms"]) == (0, 1)
