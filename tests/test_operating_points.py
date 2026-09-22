"""The B-vs-P comparison turns on numbers no eyeball can check.

AP50 comes from pycocotools, which is already trusted. The operating-point
numbers - recall and false alarms per image at a fixed confidence, and at a
matched recall - are computed here, and a quiet error in the greedy matching
would move the selection decision without moving anything visible. These fix the
behaviour that matters: one detection per ground-truth box, IoU 0.5 or it is a
false alarm, and false alarms divided by images rather than by detections.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from t9_b_vs_p import at_conf, at_recall, label_detections, sweep  # noqa: E402


def box(x, y, w, h, score):
    return (float(x), float(y), float(w), float(h), float(score))


def gt(*xyxy):
    return np.array(xyxy, dtype=float) if xyxy else np.zeros((0, 4))


def test_a_perfect_detector_scores_full_recall_and_no_false_alarms():
    boxes = {"a": gt([0, 0, 10, 10]), "b": gt([5, 5, 15, 15])}
    dets = {"a": [box(0, 0, 10, 10, 0.9)], "b": [box(5, 5, 10, 10, 0.8)]}
    rows = sweep(label_detections(dets, boxes), n_gt=2, n_images=2)
    assert at_conf(rows, 0.25) == {"conf": 0.25, "recall": 1.0,
                                   "false_alarms_per_image": 0.0, "detections": 2}


def test_a_second_box_on_the_same_pothole_is_a_false_alarm():
    """Two detections, one pothole: recall is 1 of 1, not 2 of 1."""
    boxes = {"a": gt([0, 0, 10, 10])}
    dets = {"a": [box(0, 0, 10, 10, 0.9), box(0, 0, 10, 10, 0.8)]}
    rows = sweep(label_detections(dets, boxes), n_gt=1, n_images=1)
    point = at_conf(rows, 0.25)
    assert point["recall"] == 1.0
    assert point["false_alarms_per_image"] == 1.0


def test_a_loose_box_below_iou_half_is_a_false_alarm_not_a_hit():
    boxes = {"a": gt([0, 0, 10, 10])}
    dets = {"a": [box(6, 6, 10, 10, 0.9)]}  # IoU 16/184, well under 0.5
    rows = sweep(label_detections(dets, boxes), n_gt=1, n_images=1)
    point = at_conf(rows, 0.25)
    assert point["recall"] == 0.0
    assert point["false_alarms_per_image"] == 1.0


def test_detections_on_an_image_with_no_potholes_count_as_false_alarms():
    boxes = {"a": gt([0, 0, 10, 10]), "empty": gt()}
    dets = {"a": [box(0, 0, 10, 10, 0.9)], "empty": [box(1, 1, 5, 5, 0.7)]}
    rows = sweep(label_detections(dets, boxes), n_gt=1, n_images=2)
    point = at_conf(rows, 0.25)
    assert point["recall"] == 1.0
    assert point["false_alarms_per_image"] == 0.5  # one FP over two images


def test_confidence_threshold_excludes_lower_scoring_detections():
    boxes = {"a": gt([0, 0, 10, 10]), "b": gt([0, 0, 10, 10])}
    dets = {"a": [box(0, 0, 10, 10, 0.9)], "b": [box(0, 0, 10, 10, 0.1)]}
    rows = sweep(label_detections(dets, boxes), n_gt=2, n_images=2)
    assert at_conf(rows, 0.25)["recall"] == 0.5
    assert at_conf(rows, 0.05)["recall"] == 1.0


def test_no_detection_above_the_threshold_is_zero_recall_not_a_crash():
    boxes = {"a": gt([0, 0, 10, 10])}
    dets = {"a": [box(0, 0, 10, 10, 0.01)]}
    rows = sweep(label_detections(dets, boxes), n_gt=1, n_images=1)
    assert at_conf(rows, 0.25) == {"conf": 0.25, "recall": 0.0,
                                   "false_alarms_per_image": 0.0, "detections": 0}


def test_matched_recall_reports_the_threshold_where_recall_first_crosses():
    boxes = {s: gt([0, 0, 10, 10]) for s in "abcde"}
    dets = {s: [box(0, 0, 10, 10, c)]
            for s, c in zip("abcde", [0.9, 0.8, 0.7, 0.6, 0.5], strict=True)}
    rows = sweep(label_detections(dets, boxes), n_gt=5, n_images=5)
    point = at_recall(rows, 0.8)
    assert point["reachable"] is True
    assert point["recall"] == 0.8
    assert point["conf"] == 0.6  # the 4th of 5, in descending order


def test_unreachable_recall_says_so_and_reports_the_ceiling():
    """Recall 0.8 is a target, not a guarantee; a model that cannot reach it
    must say the ceiling rather than silently report its last row."""
    boxes = {s: gt([0, 0, 10, 10]) for s in "abcde"}
    dets = {"a": [box(0, 0, 10, 10, 0.9)], "b": [box(0, 0, 10, 10, 0.8)]}
    rows = sweep(label_detections(dets, boxes), n_gt=5, n_images=5)
    point = at_recall(rows, 0.8)
    assert point["reachable"] is False
    assert point["max_recall"] == 0.4
    assert point["false_alarms_per_image_at_max_recall"] == 0.0


def test_recall_never_decreases_as_the_threshold_drops():
    rng = np.random.default_rng(0)
    boxes, dets = {}, {}
    for i in range(40):
        s = f"i{i}"
        boxes[s] = gt([0, 0, 10, 10])
        dets[s] = [box(0, 0, 10, 10, float(rng.random())),
                   box(50, 50, 10, 10, float(rng.random()))]
    rows = sweep(label_detections(dets, boxes), n_gt=40, n_images=40)
    assert np.all(np.diff(rows[:, 1]) >= 0)
    assert np.all(np.diff(rows[:, 2]) >= 0)
    assert rows[-1, 1] == 1.0
