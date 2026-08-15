"""Tests for the predict.py schema/remap boundary.

`_raw_predictions` is the only function in this module that touches
ultralytics; it is monkeypatched here so these tests run fast, offline, and
without any trained weights. The real inference path is exercised by a manual
smoke check (see the task report), never by this suite.
"""

from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

from certain_road.artifacts.io import write_artifact
from certain_road.artifacts.schema import DetectionRow
from certain_road.detect.predict import load_class_map, load_thresholds, predict_to_detections

RAW_COLUMNS = ["frame_id", "det_id", "class_id", "score", "x1", "y1", "x2", "y2", "img_w", "img_h"]


def _make_image(path: Path, w: int, h: int) -> None:
    Image.new("RGB", (w, h), color=(120, 120, 120)).save(path)


def test_predict_to_detections_conforms_to_detection_row_and_remaps(tmp_path, monkeypatch):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _make_image(image_dir / "a.jpg", 640, 480)
    _make_image(image_dir / "b.jpg", 320, 240)

    def fake_raw(weights, image_dir, *, conf, device, imgsz):
        return pd.DataFrame(
            [
                # class_id 3 = D40 (pothole) under rdd2022_4class
                {
                    "frame_id": "a",
                    "det_id": "a-0",
                    "class_id": 3,
                    "score": 0.9,
                    "x1": 10.0,
                    "y1": 20.0,
                    "x2": 60.0,
                    "y2": 80.0,
                    "img_w": 640,
                    "img_h": 480,
                },
                # class_id 1 = D10 (transverse) -> must merge into linear_crack
                {
                    "frame_id": "b",
                    "det_id": "b-0",
                    "class_id": 1,
                    "score": 0.5,
                    "x1": 5.0,
                    "y1": 5.0,
                    "x2": 15.0,
                    "y2": 15.0,
                    "img_w": 320,
                    "img_h": 240,
                },
            ],
            columns=RAW_COLUMNS,
        )

    monkeypatch.setattr("certain_road.detect.predict._raw_predictions", fake_raw)

    out = predict_to_detections(
        tmp_path / "weights.pt",
        image_dir,
        class_map=load_class_map("rdd2022_4class"),
        conf=0.1,
        device="cpu",
        imgsz=640,
    )

    assert list(out.columns) == DetectionRow.columns()
    assert (out["x2"] > out["x1"]).all()
    assert (out["y2"] > out["y1"]).all()
    assert out.loc[out["frame_id"] == "a", "img_w"].iloc[0] == 640
    assert out.loc[out["frame_id"] == "a", "img_h"].iloc[0] == 480
    assert out.loc[out["frame_id"] == "b", "img_w"].iloc[0] == 320
    assert out.loc[out["frame_id"] == "b", "img_h"].iloc[0] == 240
    assert out.loc[out["frame_id"] == "a", "class_name"].iloc[0] == "pothole"
    assert out.loc[out["frame_id"] == "b", "class_name"].iloc[0] == "linear_crack"

    write_artifact(out, tmp_path / "det.parquet", DetectionRow)


def test_image_with_zero_detections_produces_no_rows_but_does_not_drop_others(
    tmp_path, monkeypatch
):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _make_image(image_dir / "empty.jpg", 100, 100)
    _make_image(image_dir / "hit.jpg", 100, 100)

    def fake_raw(weights, image_dir, *, conf, device, imgsz):
        # ultralytics never emits a row for a frame with no boxes; only "hit" appears.
        return pd.DataFrame(
            [
                {
                    "frame_id": "hit",
                    "det_id": "hit-0",
                    "class_id": 0,
                    "score": 0.4,
                    "x1": 1.0,
                    "y1": 1.0,
                    "x2": 5.0,
                    "y2": 5.0,
                    "img_w": 100,
                    "img_h": 100,
                }
            ],
            columns=RAW_COLUMNS,
        )

    monkeypatch.setattr("certain_road.detect.predict._raw_predictions", fake_raw)

    out = predict_to_detections(
        tmp_path / "weights.pt",
        image_dir,
        class_map=load_class_map("identity_3class"),
        conf=0.25,
        device="cpu",
        imgsz=640,
    )

    assert list(out.columns) == DetectionRow.columns()
    assert set(out["frame_id"]) == {"hit"}
    assert len(out) == 1
    write_artifact(out, tmp_path / "det.parquet", DetectionRow)


def test_empty_prediction_set_is_a_well_formed_empty_frame(tmp_path, monkeypatch):
    """No detections anywhere must not produce a malformed frame."""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _make_image(image_dir / "empty.jpg", 100, 100)

    def fake_raw(weights, image_dir, *, conf, device, imgsz):
        return pd.DataFrame(columns=RAW_COLUMNS)

    monkeypatch.setattr("certain_road.detect.predict._raw_predictions", fake_raw)

    out = predict_to_detections(
        tmp_path / "weights.pt",
        image_dir,
        class_map=load_class_map("identity_3class"),
        conf=0.25,
        device="cpu",
        imgsz=640,
    )

    assert list(out.columns) == DetectionRow.columns()
    assert len(out) == 0
    # Must still validate — write_artifact must accept a genuinely empty artifact.
    write_artifact(out, tmp_path / "det.parquet", DetectionRow)


def test_predict_to_detections_rejects_unmapped_class_id(tmp_path, monkeypatch):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _make_image(image_dir / "a.jpg", 100, 100)

    def fake_raw(weights, image_dir, *, conf, device, imgsz):
        return pd.DataFrame(
            [
                {
                    "frame_id": "a",
                    "det_id": "a-0",
                    "class_id": 9,
                    "score": 0.9,
                    "x1": 1.0,
                    "y1": 1.0,
                    "x2": 5.0,
                    "y2": 5.0,
                    "img_w": 100,
                    "img_h": 100,
                }
            ],
            columns=RAW_COLUMNS,
        )

    monkeypatch.setattr("certain_road.detect.predict._raw_predictions", fake_raw)

    with pytest.raises(ValueError, match="9"):
        predict_to_detections(
            tmp_path / "weights.pt",
            image_dir,
            class_map=load_class_map("identity_3class"),
            conf=0.25,
            device="cpu",
            imgsz=640,
        )


def test_load_thresholds_has_required_keys():
    thresholds = load_thresholds()
    assert thresholds["map_conf_floor"] == pytest.approx(0.001)
    assert thresholds["imgsz"] == 640
    assert thresholds["operating_thresholds"] == [0.10, 0.15, 0.20, 0.25]
