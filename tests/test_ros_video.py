"""The video camera's pure half: ground truth in view, the frame facts and the decisions' score.

`certain_road_ros.video` imports no ROS, so these run everywhere, CI included. The node that
plays the clip (`video_node`) needs ROS and is checked by running it (ros/README.md).
"""

import sys

import pytest

from certain_road.core.paths import repo_root

ROOT = repo_root()
sys.path.insert(0, str(ROOT / "ros" / "certain_road_ros"))
sys.path.insert(0, str(ROOT / "scripts"))

from certain_road_ros.video import (  # noqa: E402
    FrameInfo,
    Interval,
    gt_strip,
    in_view,
    read_intervals,
    score_decisions,
)
from score_video_gt import read_gt  # noqa: E402

GT = ROOT / "configs" / "eval" / "gt" / "2DV-cYmIvT4_claude.csv"


def test_reads_the_ground_truth_as_the_offline_scorer_does():
    ours = read_intervals(GT)
    theirs = read_gt(GT)
    assert len(ours) == len(theirs) == 17
    assert [(i.start_s, i.end_s, i.note) for i in ours] == [
        (r["start_s"], r["end_s"], r["note"]) for r in theirs
    ]


def test_an_interval_that_ends_before_it_starts_is_refused(tmp_path):
    bad = tmp_path / "gt.csv"
    bad.write_text("# a comment\nstart_s,end_s,note\n12.0,11.0,backwards\n")
    with pytest.raises(ValueError, match="ends before it starts"):
        read_intervals(bad)


def test_in_view_is_half_open_and_lists_every_overlapping_pothole():
    ivs = [Interval(1.0, 2.0, "a"), Interval(1.5, 3.0, "b"), Interval(5.0, 6.0, "c")]
    assert in_view(ivs, 0.99) == ()
    assert in_view(ivs, 1.0) == (1,)
    assert in_view(ivs, 1.7) == (1, 2)
    assert in_view(ivs, 2.0) == (2,)
    assert in_view(ivs, 3.0) == ()
    assert in_view(ivs, 5.5) == (3,)


def test_overlapping_potholes_of_the_real_clip_are_all_shown():
    ivs = read_intervals(GT)
    # 159.0-161.8, 158.8-160.8 and 159.4-160.8 overlap: three counted potholes at once
    assert in_view(ivs, 160.0) == (7, 8, 9)
    assert in_view(ivs, 130.0) == ()


def test_strip_text():
    assert gt_strip((), 17) == "ground truth: no counted pothole in view"
    assert gt_strip((4,), 17) == "GROUND TRUTH: pothole #4 of 17 in view"
    assert gt_strip((7, 8), 17) == "GROUND TRUTH: potholes #7, #8 of 17 in view"
    assert gt_strip((), None) == "no ground truth for this clip"


@pytest.mark.parametrize(
    "seen,total,lockstep", [((), 17, True), ((7, 8, 9), 17, True), ((), None, False)]
)
def test_frame_info_round_trips_through_its_string_values(seen, total, lockstep):
    info = FrameInfo("2DV-cYmIvT4", 4801, 160.0333333, seen, total, "PACE", lockstep, "OPEN", "")
    values = info.to_values()
    assert all(isinstance(v, str) for v in values.values())
    assert FrameInfo.from_values(values) == info


def row(frame, t, seen, state):
    return {"frame": frame, "video_time_s": t, "gt_in_view": list(seen), "state": state}


def test_score_counts_potholes_reacted_to_and_onsets_outside_ground_truth():
    rows = [
        row(0, 0.0, (), "normal"),
        row(1, 0.1, (1,), "normal"),
        row(2, 0.2, (1,), "warning"),  # reaction onset inside GT; pothole 1 left NORMAL
        row(3, 0.3, (1,), "avoid_right"),  # manoeuvre onset inside GT
        row(4, 0.4, (), "avoid_right"),
        row(5, 0.5, (), "normal"),
        row(6, 0.6, (), "stop"),  # reaction and manoeuvre onset with nothing in view
        row(7, 0.7, (2,), "normal"),  # pothole 2: never left NORMAL
        row(8, 0.8, (2, 3), "normal"),
        row(9, 0.9, (3,), "warning"),  # pothole 3 left NORMAL, no manoeuvre
    ]
    s = score_decisions(rows, gt_total=4)
    assert s["frames"] == 10
    assert s["gt_potholes"] == 4
    assert s["gt_potholes_in_processed_frames"] == 3  # pothole 4 never in a processed frame
    assert s["gt_potholes_left_normal"] == 2
    assert s["gt_potholes_manoeuvred"] == 1
    assert s["reaction_onsets"] == 3
    assert s["reaction_onsets_outside_gt"] == 1
    assert s["manoeuvre_onsets"] == 2
    assert s["manoeuvre_onsets_outside_gt"] == 1
    by_k = {p["pothole"]: p for p in s["potholes"]}
    assert by_k[1]["in_view_s"] == [0.1, 0.3]
    assert by_k[2]["states"] == ["normal"]
    assert by_k[3]["left_normal"] and not by_k[3]["manoeuvred"]
    assert s["frames_by_state_no_gt_in_view"] == {"avoid_right": 1, "normal": 2, "stop": 1}


def test_a_first_frame_out_of_normal_is_an_onset_and_warning_to_avoid_is_one_manoeuvre():
    rows = [row(0, 0.0, (), "warning"), row(1, 0.1, (), "avoid_left"), row(2, 0.2, (), "stop")]
    s = score_decisions(rows, gt_total=None)
    assert s["reaction_onsets"] == 1  # the planner starts in NORMAL
    assert s["manoeuvre_onsets"] == 1  # avoid_left -> stop stays inside the manoeuvres
    assert s["gt_potholes"] is None


def test_no_decisions_score_empty():
    s = score_decisions([], gt_total=17)
    assert s["frames"] == 0
    assert s["video_time_s"] is None
    assert s["reaction_onsets"] == 0
