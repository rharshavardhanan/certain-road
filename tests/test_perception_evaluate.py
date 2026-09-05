"""Tests for `certain_road.perception.evaluate`.

Every metric-computation function here is exercised with small, fully
hand-computed synthetic frames -- never a trained model -- per the plan's
Task 3 spec (`docs/superpowers/plans/2026-08-15-detector-evaluation-harness.md`).
Task 4 (validating against the known 0.4220 mAP50 on real weights) is a
separate, non-automated check documented in the task report; it is not part
of this suite because it depends on trained weights and real data on disk.
"""

import math

import pandas as pd
import pytest
from PIL import Image

from certain_road.perception.evaluate import (
    compute_map,
    compute_operating_metrics,
    load_ground_truth,
)

PRED_COLUMNS = [
    "frame_id",
    "det_id",
    "class_name",
    "score",
    "x1",
    "y1",
    "x2",
    "y2",
    "img_w",
    "img_h",
]
GT_COLUMNS = ["frame_id", "class_id", "x1", "y1", "x2", "y2", "img_w", "img_h"]


def _preds(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=PRED_COLUMNS)


def _gt(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=GT_COLUMNS)


def test_perfect_predictions_score_map50_of_one():
    """Feeding ground truth back as predictions must score 1.0."""
    gt = _gt(
        [
            {
                "frame_id": "a",
                "class_id": 0,
                "x1": 10.0,
                "y1": 10.0,
                "x2": 50.0,
                "y2": 50.0,
                "img_w": 100,
                "img_h": 100,
            },
            {
                "frame_id": "b",
                "class_id": 2,
                "x1": 5.0,
                "y1": 5.0,
                "x2": 30.0,
                "y2": 30.0,
                "img_w": 100,
                "img_h": 100,
            },
        ]
    )
    preds = _preds(
        [
            {
                "frame_id": "a",
                "det_id": "a-0",
                "class_name": "linear_crack",
                "score": 0.9,
                "x1": 10.0,
                "y1": 10.0,
                "x2": 50.0,
                "y2": 50.0,
                "img_w": 100,
                "img_h": 100,
            },
            {
                "frame_id": "b",
                "det_id": "b-0",
                "class_name": "pothole",
                "score": 0.9,
                "x1": 5.0,
                "y1": 5.0,
                "x2": 30.0,
                "y2": 30.0,
                "img_w": 100,
                "img_h": 100,
            },
        ]
    )

    result = compute_map(preds, gt, num_classes=3)

    # A perfect detector saturates at 0.995, not 1.0, under ultralytics' own
    # 101-point-interpolation `compute_ap` -- confirmed directly:
    # `ultralytics.utils.metrics.compute_ap([1.0], [1.0])` returns 0.995 for
    # *any* number of perfectly-matched instances, because the trailing
    # sentinel point at recall==1.0 always contributes one interpolated
    # precision-0 sample. Reproducing that exact, non-obvious ceiling (not
    # 1.0, not some other rounding) is itself evidence `compute_map` is wired
    # to the real ultralytics AP machinery rather than an independent
    # reimplementation that would not share this quirk.
    assert result["map50"] == pytest.approx(0.995)
    assert result["map50_95"] == pytest.approx(0.995)
    assert result["per_class_ap50"]["linear_crack"] == pytest.approx(0.995)
    assert result["per_class_ap50"]["pothole"] == pytest.approx(0.995)


def test_no_predictions_scores_zero_not_nan():
    """An empty prediction set must not poison the metric."""
    gt = _gt(
        [
            {
                "frame_id": "a",
                "class_id": 0,
                "x1": 10.0,
                "y1": 10.0,
                "x2": 50.0,
                "y2": 50.0,
                "img_w": 100,
                "img_h": 100,
            }
        ]
    )
    preds = _preds([])

    result = compute_map(preds, gt, num_classes=3)

    assert result["map50"] == 0.0
    assert not math.isnan(result["map50"])
    assert result["map50_95"] == 0.0
    assert not math.isnan(result["map50_95"])
    assert all(v == 0.0 for v in result["per_class_ap50"].values())


def test_ground_truth_loader_converts_yolo_to_absolute_xyxy(tmp_path):
    """YOLO is normalised centre-format; boxes must come back in pixels, using real image dims."""
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()

    # Deliberately not 600x600 or 640x640 -- the loader must read real dims.
    Image.new("RGB", (200, 100), color=(0, 0, 0)).save(images_dir / "x.jpg")
    # class 2 (pothole), cx=0.5, cy=0.5, w=0.2, h=0.4 -> x:[80,120] y:[30,70]
    (labels_dir / "x.txt").write_text("2 0.5 0.5 0.2 0.4\n")

    # A genuine negative frame: present on disk, empty label file, zero gt rows.
    Image.new("RGB", (50, 50), color=(0, 0, 0)).save(images_dir / "empty.jpg")
    (labels_dir / "empty.txt").write_text("")

    gt = load_ground_truth(labels_dir, images_dir)

    assert set(gt.columns) == set(GT_COLUMNS)
    assert len(gt) == 1
    row = gt.iloc[0]
    assert row["frame_id"] == "x"
    assert row["class_id"] == 2
    assert row["x1"] == pytest.approx(80.0)
    assert row["y1"] == pytest.approx(30.0)
    assert row["x2"] == pytest.approx(120.0)
    assert row["y2"] == pytest.approx(70.0)
    assert row["img_w"] == 200
    assert row["img_h"] == 100
    assert "empty" not in set(gt["frame_id"])


def test_operating_metrics_recall_falls_as_threshold_rises():
    """Sanity: a stricter threshold cannot increase recall."""
    gt = _gt(
        [
            {
                "frame_id": f"f{i}",
                "class_id": 0,
                "x1": 0.0,
                "y1": 0.0,
                "x2": 20.0,
                "y2": 20.0,
                "img_w": 100,
                "img_h": 100,
            }
            for i in range(4)
        ]
    )
    # Four true positives at descending confidence, each hitting a different frame's gt box exactly.
    preds = _preds(
        [
            {
                "frame_id": f"f{i}",
                "det_id": f"f{i}-0",
                "class_name": "linear_crack",
                "score": score,
                "x1": 0.0,
                "y1": 0.0,
                "x2": 20.0,
                "y2": 20.0,
                "img_w": 100,
                "img_h": 100,
            }
            for i, score in enumerate([0.9, 0.6, 0.3, 0.05])
        ]
    )

    thresholds = [0.10, 0.15, 0.20, 0.25, 0.5, 0.8]
    recalls = [compute_operating_metrics(preds, gt, conf=t)["recall"] for t in thresholds]

    assert all(a >= b for a, b in zip(recalls, recalls[1:], strict=False)), recalls


def test_empty_images_contribute_false_positives_not_missed_detections():
    """58% of our test set has no objects; they can only generate FPs."""
    gt = _gt(
        [
            {
                "frame_id": "positive",
                "class_id": 0,
                "x1": 0.0,
                "y1": 0.0,
                "x2": 20.0,
                "y2": 20.0,
                "img_w": 100,
                "img_h": 100,
            }
            # "empty" frame deliberately has no gt row at all.
        ]
    )
    preds = _preds(
        [
            {
                "frame_id": "positive",
                "det_id": "positive-0",
                "class_name": "linear_crack",
                "score": 0.9,
                "x1": 0.0,
                "y1": 0.0,
                "x2": 20.0,
                "y2": 20.0,
                "img_w": 100,
                "img_h": 100,
            },
            {
                "frame_id": "empty",
                "det_id": "empty-0",
                "class_name": "pothole",
                "score": 0.9,
                "x1": 5.0,
                "y1": 5.0,
                "x2": 15.0,
                "y2": 15.0,
                "img_w": 100,
                "img_h": 100,
            },
        ]
    )

    result = compute_operating_metrics(preds, gt, conf=0.5)

    # The one real gt box was matched: recall is unaffected by the empty-image FP.
    assert result["recall"] == pytest.approx(1.0)
    # Both predictions counted; the "empty" frame's cannot be anything but a FP.
    assert result["false_positive_count"] == 1
    assert result["precision"] == pytest.approx(0.5)
