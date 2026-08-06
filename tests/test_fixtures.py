import pandas as pd

from certain_road.artifacts.io import read_artifact, write_artifact
from certain_road.artifacts.schema import DetectionRow, FrameRow
from tests.fixtures.synthetic import synthetic_detections, synthetic_frames

CLASSES = {"D00", "D10", "D20", "D40"}


def test_frames_have_expected_shape():
    frames = synthetic_frames(n_segments=4, frames_per_segment=15, seed=1)
    assert len(frames) == 60
    assert frames["segment_id"].nunique() == 4
    assert list(frames.columns) == FrameRow.columns()


def test_generation_is_deterministic():
    a = synthetic_frames(n_segments=3, frames_per_segment=5, seed=7)
    b = synthetic_frames(n_segments=3, frames_per_segment=5, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_different_seeds_differ():
    a = synthetic_detections(synthetic_frames(3, 5, seed=1), seed=1)
    b = synthetic_detections(synthetic_frames(3, 5, seed=1), seed=2)
    assert not a.equals(b)


def test_detections_reference_real_frames_and_valid_classes():
    frames = synthetic_frames(n_segments=3, frames_per_segment=10, seed=2)
    dets = synthetic_detections(frames, seed=2)
    assert set(dets["frame_id"]) <= set(frames["frame_id"])
    assert set(dets["class_name"]) <= CLASSES
    assert (dets["x2"] > dets["x1"]).all()
    assert (dets["y2"] > dets["y1"]).all()
    assert (dets["score"].between(0, 1)).all()


def test_fixtures_satisfy_the_artifact_contract(tmp_path):
    frames = synthetic_frames(n_segments=2, frames_per_segment=5, seed=3)
    dets = synthetic_detections(frames, seed=3)

    write_artifact(frames, tmp_path / "frames.parquet", FrameRow)
    write_artifact(dets, tmp_path / "detections.parquet", DetectionRow)

    assert len(read_artifact(tmp_path / "frames.parquet", FrameRow, validate_rows=True)) == 10
    assert len(
        read_artifact(tmp_path / "detections.parquet", DetectionRow, validate_rows=True)
    ) == len(dets)
