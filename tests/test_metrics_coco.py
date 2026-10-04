"""T6 — the class-id offset is the bug that would not announce itself.

Ultralytics writes 1-indexed `category_id`; our ground truth is 0-indexed. Get
that wrong and nothing raises — pothole predictions get scored against
alligator_crack ground truth and a plausible, wrong mAP comes out. These tests
put predictions that are *exactly* the ground truth through the real conversion
and demand AP50 ~= 1.0, then show the same data scores ~0 when the shift is
dropped.
"""

import json

import numpy as np
import pytest
from PIL import Image

from certain_road.perception.metrics_coco import coco_eval, load_predictions, yolo_to_coco_gt

NAMES = {0: "linear_crack", 1: "alligator_crack", 2: "pothole"}


@pytest.fixture
def dataset(tmp_path):
    """Six images, one box each, cycling through all three classes."""
    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()
    paths, boxes = [], []
    for i in range(6):
        stem = f"Dummy__{i:03d}"
        Image.fromarray(np.zeros((200, 200, 3), np.uint8)).save(tmp_path / "images" / f"{stem}.jpg")
        cls = i % 3
        cx, cy, w, h = 0.5, 0.5, 0.2, 0.2
        (tmp_path / "labels" / f"{stem}.txt").write_text(f"{cls} {cx} {cy} {w} {h}\n")
        paths.append(tmp_path / "images" / f"{stem}.jpg")
        boxes.append((stem, cls, (cx - w / 2) * 200, (cy - h / 2) * 200, w * 200, h * 200))
    return tmp_path, paths, boxes


def write_preds(tmp_path, boxes, *, offset: int):
    """Perfect predictions, with `offset` added to the class id as ultralytics does."""
    records = [
        {"image_id": stem, "category_id": cls + offset, "bbox": [x, y, w, h], "score": 0.9}
        for stem, cls, x, y, w, h in boxes
    ]
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps(records))
    return path


def test_gt_conversion_puts_boxes_where_the_label_says(dataset):
    tmp_path, paths, boxes = dataset
    gt, stem_to_id = yolo_to_coco_gt(paths, tmp_path / "labels", NAMES)
    assert len(gt["images"]) == 6
    assert len(gt["annotations"]) == 6
    # normalised centre 0.5,0.5 size 0.2 on a 200px image -> top-left 80,80 size 40
    assert gt["annotations"][0]["bbox"] == pytest.approx([80.0, 80.0, 40.0, 40.0])
    assert set(stem_to_id) == {f"Dummy__{i:03d}" for i in range(6)}


def test_perfect_predictions_score_one_after_the_offset_is_applied(dataset):
    """The real path: ultralytics-style 1-indexed input, shifted down by one."""
    tmp_path, paths, boxes = dataset
    gt, stem_to_id = yolo_to_coco_gt(paths, tmp_path / "labels", NAMES)
    preds = load_predictions(write_preds(tmp_path, boxes, offset=1), stem_to_id, len(NAMES))
    assert {p["category_id"] for p in preds} == {0, 1, 2}
    result = coco_eval(gt, preds, NAMES)
    assert result["map50"] == pytest.approx(1.0, abs=1e-6)
    assert result["map50_95"] == pytest.approx(1.0, abs=1e-6)


def test_forgetting_the_offset_scores_near_zero(dataset):
    """Proof the offset matters: same boxes, wrong class ids, and no error raised.

    This is what a silent failure looks like - a number, not an exception.
    """
    tmp_path, paths, boxes = dataset
    gt, stem_to_id = yolo_to_coco_gt(paths, tmp_path / "labels", NAMES)
    raw = json.loads(write_preds(tmp_path, boxes, offset=1).read_text())
    unshifted = [
        {
            "image_id": stem_to_id[r["image_id"]],
            "category_id": r["category_id"],
            "bbox": r["bbox"],
            "score": r["score"],
        }
        for r in raw
    ]
    assert coco_eval(gt, unshifted, NAMES)["map50"] < 0.4


def test_out_of_range_category_ids_raise_rather_than_shift(dataset):
    """A future ultralytics changing convention must fail loudly."""
    tmp_path, paths, boxes = dataset
    _, stem_to_id = yolo_to_coco_gt(paths, tmp_path / "labels", NAMES)
    with pytest.raises(ValueError, match="outside the expected"):
        load_predictions(write_preds(tmp_path, boxes, offset=50), stem_to_id, len(NAMES))


def test_zero_indexed_input_is_rejected_not_silently_shifted(dataset):
    """0-indexed input would shift to -1; that must raise, not produce a number."""
    tmp_path, paths, boxes = dataset
    _, stem_to_id = yolo_to_coco_gt(paths, tmp_path / "labels", NAMES)
    with pytest.raises(ValueError, match="outside the expected"):
        load_predictions(write_preds(tmp_path, boxes, offset=0), stem_to_id, len(NAMES))


def test_classes_below_the_reliability_floor_are_flagged(dataset):
    tmp_path, paths, boxes = dataset
    gt, stem_to_id = yolo_to_coco_gt(paths, tmp_path / "labels", NAMES)
    result = coco_eval(
        gt, load_predictions(write_preds(tmp_path, boxes, offset=1), stem_to_id, len(NAMES)), NAMES
    )
    # two instances per class, far under 100
    assert all(v["unreliable"] for v in result["per_class"].values())
    assert result["per_class"]["pothole"]["instances"] == 2


def test_no_predictions_gives_zero_not_a_crash(dataset):
    tmp_path, paths, _ = dataset
    gt, _ = yolo_to_coco_gt(paths, tmp_path / "labels", NAMES)
    result = coco_eval(gt, [], NAMES)
    assert result["map50"] == 0.0 and result["note"] == "no predictions"
