"""Grouping a drive into evaluation segments."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from certain_road.artifacts.io import read_artifact, write_artifact
from certain_road.artifacts.schema import Detection, DetectionRow, DriveLogRow, SegmentRow
from certain_road.canbus.transport import NullTransport
from certain_road.core.paths import repo_root
from certain_road.driving.corridor import load_corridor
from certain_road.driving.decision import load_policy
from certain_road.perception.source import Frame, FrameSource
from certain_road.runtime.pipeline import run
from certain_road.runtime.recorder import record
from certain_road.survey.segment import segment_drive

CORRIDOR = load_corridor(repo_root() / "configs" / "driving" / "corridor.yaml")
POLICY = load_policy(repo_root() / "configs" / "driving" / "decision.yaml")
W = H = 640


class FakeSource(FrameSource):
    def __init__(self, n):
        self.n = n

    def frames(self):
        for i in range(self.n):
            yield Frame(f"f{i:04d}", np.zeros((H, W, 3), dtype=np.uint8), i * 0.1)


def pothole(score=0.9):
    return Detection("pothole", score, 290.0, 560.0, 350.0, 620.0, W, H)


def crack(score=0.8):
    return Detection("linear_crack", score, 280.0, 570.0, 360.0, 610.0, W, H)


def drive_artifacts(tmp_path, detector, frames=30):
    steps = run(FakeSource(frames), detector, CORRIDOR, POLICY, NullTransport(), escape_lanes=5.0)
    record(steps, tmp_path, survey_date=date(2026, 9, 6))
    return (
        read_artifact(tmp_path / "detections.parquet", DetectionRow),
        read_artifact(tmp_path / "drive_log.parquet", DriveLogRow),
    )


def test_frames_are_grouped_into_fixed_blocks(tmp_path):
    dets, log = drive_artifacts(tmp_path, lambda f: [], frames=30)
    segs = segment_drive(dets, log, frames_per_segment=10)
    assert len(segs) == 3
    assert list(segs["n_frames"]) == [10, 10, 10]


def test_trailing_partial_segment_is_kept_and_reports_its_real_size(tmp_path):
    """Dropping it would discard the end of every drive."""
    dets, log = drive_artifacts(tmp_path, lambda f: [], frames=25)
    segs = segment_drive(dets, log, frames_per_segment=10)
    assert list(segs["n_frames"]) == [10, 10, 5]


def test_clean_road_still_produces_segments(tmp_path):
    """A missing segment and a segment with no damage mean very different things."""
    dets, log = drive_artifacts(tmp_path, lambda f: [], frames=20)
    segs = segment_drive(dets, log, frames_per_segment=10)
    assert len(segs) == 2
    assert (segs["n_detections"] == 0).all()


def test_detections_are_counted_per_class(tmp_path):
    dets, log = drive_artifacts(tmp_path, lambda f: [pothole(), crack()], frames=10)
    segs = segment_drive(dets, log, frames_per_segment=10)
    assert segs.loc[0, "n_pothole"] == 10
    assert segs.loc[0, "n_linear_crack"] == 10
    assert segs.loc[0, "n_alligator_crack"] == 0
    assert segs.loc[0, "n_detections"] == 20


def test_segments_carry_frame_and_time_bounds(tmp_path):
    dets, log = drive_artifacts(tmp_path, lambda f: [], frames=20)
    segs = segment_drive(dets, log, frames_per_segment=10)
    assert segs.loc[0, "first_frame_id"] == "f0000"
    assert segs.loc[0, "last_frame_id"] == "f0009"
    assert segs.loc[1, "first_timestamp_s"] > segs.loc[0, "last_timestamp_s"]


def test_mean_score_is_zero_not_nan_on_a_clean_segment(tmp_path):
    """NaN would poison every downstream calculation."""
    dets, log = drive_artifacts(tmp_path, lambda f: [], frames=10)
    segs = segment_drive(dets, log, frames_per_segment=10)
    assert segs.loc[0, "mean_score"] == 0.0


def test_survey_date_survives_into_the_segment(tmp_path):
    dets, log = drive_artifacts(tmp_path, lambda f: [], frames=10)
    segs = segment_drive(dets, log, frames_per_segment=10)
    assert segs.loc[0, "survey_date"] == date(2026, 9, 6)


def test_segments_validate_as_an_artifact(tmp_path):
    dets, log = drive_artifacts(tmp_path, lambda f: [pothole()], frames=20)
    segs = segment_drive(dets, log, frames_per_segment=10)
    out = tmp_path / "segments.parquet"
    write_artifact(segs, out, SegmentRow)
    assert len(read_artifact(out, SegmentRow, validate_rows=True)) == 2


def test_empty_drive_produces_no_segments(tmp_path):
    empty_log = pd.DataFrame(columns=DriveLogRow.columns())
    empty_dets = pd.DataFrame(columns=DetectionRow.columns())
    assert segment_drive(empty_dets, empty_log, frames_per_segment=10).empty


def test_zero_block_size_is_rejected(tmp_path):
    dets, log = drive_artifacts(tmp_path, lambda f: [], frames=5)
    with pytest.raises(ValueError, match="frames_per_segment"):
        segment_drive(dets, log, frames_per_segment=0)
